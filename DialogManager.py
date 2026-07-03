from typing import List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class DialogState(TypedDict):
    domanda: str
    cronologia: List[dict]
    sotto_domande: Optional[List[str]]
    artista_corrente: Optional[str]
    opera_corrente: Optional[str]
    museo_corrente: Optional[str]
    risposta: Optional[str]


class DialogManager:
    """Traccia lo stato della conversazione (artista/opera/museo 'a fuoco') tramite un grafo
    LangGraph, così da poter risolvere riferimenti impliciti tra un turno e l'altro
    (es. "chi l'ha dipinta?"). Se manca un'informazione necessaria, il grafo si mette in pausa
    con interrupt() e chi lo chiama (es. il loop vocale) deve chiedere chiarimento all'utente
    e poi riprendere con rispondi_chiarimento()."""

    DB_FILE = "dialog_state.sqlite"

    def __init__(self, chain, llm_riferimenti):
        """
        chain: la GraphCypherQAChain (con .invoke({"query": ...}) -> {"result": ...}) usata per rispondere.
        llm_riferimenti: chat model con .invoke(str) -> oggetto con .content, usato per decidere
                          se la domanda ha bisogno di un chiarimento.
        """
        self._chain = chain
        self._llm_riferimenti = llm_riferimenti
        self._checkpointer_cm = SqliteSaver.from_conn_string(self.DB_FILE)
        self._checkpointer = self._checkpointer_cm.__enter__()
        self._graph = self._costruisci_grafo()

    def _costruisci_grafo(self):
        g = StateGraph(DialogState)
        g.add_node("risolvi_riferimenti", self._risolvi_riferimenti)
        g.add_node("genera_risposta", self._genera_risposta)
        g.add_node("aggiorna_stato", self._aggiorna_stato)

        g.add_edge(START, "risolvi_riferimenti")
        # se risolvi_riferimenti ha già prodotto una risposta diretta (nessuna query necessaria),
        # si salta genera_risposta e si va dritti ad aggiornare la cronologia
        g.add_conditional_edges(
            "risolvi_riferimenti",
            lambda state: "aggiorna_stato" if state.get("risposta") else "genera_risposta",
            {"genera_risposta": "genera_risposta", "aggiorna_stato": "aggiorna_stato"},
        )
        g.add_edge("genera_risposta", "aggiorna_stato")
        g.add_edge("aggiorna_stato", END)

        return g.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _cronologia_recente(stato: DialogState, n: int = 3) -> str:
        """Formatta gli ultimi n scambi domanda/risposta, per dare al modello il contesto
        necessario a risolvere riferimenti impliciti (es. "questi quadri", "quell'opera")."""
        cronologia = stato.get("cronologia", [])[-n:]
        if not cronologia:
            return "nessuno"
        return "\n".join(
            f"- Domanda: {turno['domanda']}\n  Risposta: {turno['risposta']}"
            for turno in cronologia
        )

    def _analizza_domanda(self, domanda: str, stato: DialogState) -> dict:
        """In UNA sola chiamata LLM classifica la domanda e, se è una QUERY, la scompone già nelle
        sotto-domande atomiche. Ritorna uno di:
        - {"tipo": "query", "sotto_domande": [...]}
        - {"tipo": "chiarimento", "testo": ...}
        - {"tipo": "diretta", "testo": ...}"""
        prompt = f"""Sei l'instradatore di un chatbot su Caravaggio, Caracciolo, le loro opere e i musei di
Napoli che le ospitano. Analizza la richiesta dell'utente e classificala in una di queste tre categorie,
usando anche gli scambi precedenti come contesto:

1. QUERY — la richiesta contiene ANCHE UNA SOLA domanda di informazioni su opere, artisti o musei
   (conteggi, nomi, descrizioni, luoghi, date, ecc.), comprensibile anche grazie a un riferimento
   implicito risolvibile dagli scambi precedenti (es. "questi quadri" dopo aver appena parlato di 2 quadri).
   Vale anche se la richiesta è COMPOSTA e una parte è fuori tema o fuori ambito (es. un altro artista non
   trattato): basta che una parte richieda dati su opere/artisti/musei. In caso di dubbio, scegli QUERY.
   Se è QUERY, SCOMPONI la richiesta nelle singole domande atomiche che la compongono: ognuna autonoma,
   su UN solo argomento, riscritta in forma completa risolvendo i riferimenti impliciti dagli scambi
   precedenti (es. "queste opere" -> le opere di cui si è parlato).
2. CHIARIMENTO — la richiesta richiederebbe una query, ma usa un riferimento implicito (es. "lui",
   "quell'opera") che né la richiesta né gli scambi precedenti chiariscono.
3. DIRETTA — SOLO messaggi puramente sociali (saluti, ringraziamenti, commiati, small talk) che NON
   contengono NESSUNA richiesta di informazioni. Se il messaggio contiene una qualsiasi domanda su
   opere/artisti/musei, NON è mai DIRETTA: è QUERY.

Scambi precedenti (dal più vecchio al più recente):
{self._cronologia_recente(stato)}

Richiesta dell'utente: {domanda}

Rispondi SOLO in uno di questi formati esatti, senza altro testo:
- se QUERY: la PRIMA riga è esattamente "QUERY", poi UNA domanda atomica per riga (senza numeri né trattini);
  se la richiesta è già una singola domanda, metti quell'unica domanda sulla riga dopo "QUERY".
- se CHIARIMENTO: "CHIARIMENTO: <unica domanda di chiarimento, breve e diretta>"
- se DIRETTA: "DIRETTA: <risposta breve e cordiale in italiano>"

Esempi:
Richiesta: "Quanti quadri di Caravaggio sono a Napoli?"
QUERY
Quanti quadri di Caravaggio sono a Napoli?

Richiesta: "Come si chiamano queste opere e quante ne ha fatte Botticelli?"
QUERY
Come si chiamano queste opere?
Quante opere ha fatto Botticelli?

Richiesta: "Chi l'ha dipinta?" (nessuna opera nominata prima)
CHIARIMENTO: Di quale opera stai parlando?

Richiesta: "Grazie mille!"
DIRETTA: Prego, è stato un piacere!"""

        risposta = self._llm_riferimenti.invoke(prompt).content.strip()
        righe = [r.strip() for r in risposta.splitlines() if r.strip()]
        prima = righe[0] if righe else ""
        maiuscolo = prima.upper()

        if maiuscolo.startswith("CHIARIMENTO"):
            testo = prima.split(":", 1)[1].strip() if ":" in prima else prima[len("CHIARIMENTO"):].strip()
            return {"tipo": "chiarimento", "testo": testo}
        if maiuscolo.startswith("DIRETTA"):
            testo = prima.split(":", 1)[1].strip() if ":" in prima else prima[len("DIRETTA"):].strip()
            return {"tipo": "diretta", "testo": testo}

        # QUERY: le sotto-domande sono le righe successive (ignorando l'eventuale riga "QUERY")
        sotto_domande = [r.strip(" -*\t") for r in righe if r.strip().upper() != "QUERY"]
        return {"tipo": "query", "sotto_domande": sotto_domande or [domanda]}

    def _risolvi_riferimenti(self, state: DialogState) -> dict:
        domanda = state["domanda"]
        analisi = self._analizza_domanda(domanda, state)

        if analisi["tipo"] == "chiarimento":
            # mette in pausa il grafo: chi chiama deve chiedere il chiarimento all'utente
            # (via gTTS) e poi far ripartire il grafo con rispondi_chiarimento()
            risposta_utente = interrupt(analisi["testo"])
            # dopo il chiarimento trattiamo la domanda chiarita come un'unica sotto-domanda
            domanda_chiarita = f"{domanda} (chiarimento: {risposta_utente})"
            return {"domanda": domanda_chiarita, "sotto_domande": [domanda_chiarita]}

        if analisi["tipo"] == "diretta":
            # nessuna query necessaria: la risposta è già pronta, si salta genera_risposta
            return {"domanda": domanda, "risposta": analisi["testo"]}

        return {"domanda": domanda, "sotto_domande": analisi["sotto_domande"]}

    def _genera_risposta(self, state: DialogState) -> dict:
        cronologia = self._cronologia_recente(state)
        sotto_domande = state.get("sotto_domande") or [state["domanda"]]

        risposte = []
        for sotto_domanda in sotto_domande:
            # includo gli scambi precedenti così la generazione della query Cypher può risolvere
            # eventuali riferimenti impliciti ancora presenti nella singola sotto-domanda
            domanda_con_contesto = f"""Scambi precedenti della conversazione (dal più vecchio al più recente):
{cronologia}

Nuova domanda dell'utente, da usare per generare la query: {sotto_domanda}"""
            risposte.append(self._invoca_chain_con_retry(sotto_domanda, domanda_con_contesto))

        risposta_finale = " ".join(r for r in risposte if r) or "Si è verificato un errore."
        return {"risposta": risposta_finale}

    def _invoca_chain_con_retry(self, sotto_domanda: str, domanda_con_contesto: str, max_retry: int = 3) -> str:
        """Interroga la chain riprovando se la generazione della query Cypher fallisce (i modelli
        piccoli producono a volte Cypher sintatticamente errato; essendo la generazione stocastica,
        un nuovo tentativo spesso produce una query valida). Se tutti i tentativi falliscono, ritorna
        un messaggio di fallback per quella sotto-domanda invece di scartarla in silenzio."""
        for tentativo in range(max_retry):
            try:
                risultato = self._chain.invoke({"query": domanda_con_contesto})
                return risultato["result"].strip()
            except Exception as e:
                print(f"[DialogManager] tentativo {tentativo + 1}/{max_retry} fallito "
                      f"su sotto-domanda {sotto_domanda!r}: {e}")
        return f"Non sono riuscito a recuperare le informazioni per: «{sotto_domanda}»."

    @staticmethod
    def _aggiorna_stato(state: DialogState) -> dict:
        cronologia = state.get("cronologia", []) + [
            {"domanda": state["domanda"], "risposta": state["risposta"]}
        ]
        return {"cronologia": cronologia}

    def invoke(self, domanda: str, thread_id: str = "default") -> dict:
        """Avvia un nuovo turno di conversazione.
        Ritorna {"tipo": "risposta", "testo": ...} se il turno è completo,
        oppure {"tipo": "chiarimento", "testo": ...} se serve chiedere qualcosa all'utente."""
        config = {"configurable": {"thread_id": thread_id}}
        risultato = self._graph.invoke({"domanda": domanda}, config=config)
        return self._interpreta_risultato(risultato)

    def rispondi_chiarimento(self, risposta_utente: str, thread_id: str = "default") -> dict:
        """Riprende un turno rimasto in pausa in attesa di un chiarimento dall'utente."""
        config = {"configurable": {"thread_id": thread_id}}
        risultato = self._graph.invoke(Command(resume=risposta_utente), config=config)
        return self._interpreta_risultato(risultato)

    @staticmethod
    def _interpreta_risultato(risultato: dict) -> dict:
        if "__interrupt__" in risultato:
            testo_chiarimento = risultato["__interrupt__"][0].value
            return {"tipo": "chiarimento", "testo": testo_chiarimento}
        return {"tipo": "risposta", "testo": risultato["risposta"]}

    def close(self):
        self._checkpointer_cm.__exit__(None, None, None)
