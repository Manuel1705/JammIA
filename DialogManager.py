from typing import List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class DialogState(TypedDict):
    domanda: str
    cronologia: List[dict]
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

    def _classifica_domanda(self, domanda: str, stato: DialogState) -> dict:
        """Decide come gestire la domanda: se serve interrogare il database (QUERY), se manca
        un'informazione necessaria per farlo (CHIARIMENTO), oppure se si può rispondere subito
        senza alcuna query, come per saluti, ringraziamenti o commiati (DIRETTA)."""
        prompt = f"""Sei l'instradatore di un chatbot su Caravaggio, Caracciolo, le loro opere e i musei di
Napoli che le ospitano. Classifica la domanda dell'utente in una di queste tre categorie, usando anche
gli scambi precedenti come contesto:

1. QUERY — la domanda richiede di consultare informazioni su opere, artisti o musei (conteggi, nomi,
   descrizioni, luoghi, date, ecc.) ed è comprensibile, anche grazie a un riferimento implicito
   risolvibile dagli scambi precedenti (es. "questi quadri" dopo aver appena parlato di 2 quadri).
   USA QUERY OGNI VOLTA CHE LA DOMANDA MENZIONA (anche implicitamente) opere, artisti, musei, conteggi,
   nomi, luoghi o date: in caso di dubbio, scegli sempre QUERY.
2. CHIARIMENTO — la domanda richiederebbe una query, ma usa un riferimento implicito (es. "lui",
   "quell'opera") che né la domanda né gli scambi precedenti chiariscono.
3. DIRETTA — la domanda NON richiede alcuna consultazione del database: SOLO saluti, ringraziamenti,
   commiati o small talk puro, senza alcun riferimento a opere/artisti/musei.

Esempi:
- "Quanti quadri di Caravaggio sono a Napoli?" -> QUERY (chiede un conteggio su opere)
- "Come si chiamano queste opere?" (dopo aver parlato di alcune opere) -> QUERY (riferimento risolvibile)
- "Chi l'ha dipinta?" (senza aver mai nominato un'opera prima) -> CHIARIMENTO
- "Grazie mille, è stato utile!" -> DIRETTA
- "Ciao, come funzioni?" -> DIRETTA

Scambi precedenti (dal più vecchio al più recente):
{self._cronologia_recente(stato)}

Domanda dell'utente: {domanda}

Rispondi SOLO in uno di questi tre formati esatti, senza altro testo:
QUERY
CHIARIMENTO: <unica domanda di chiarimento da fare all'utente, breve e diretta>
DIRETTA: <risposta breve e cordiale in italiano da dare direttamente all'utente>"""

        risposta = self._llm_riferimenti.invoke(prompt).content.strip()
        maiuscolo = risposta.upper()

        if maiuscolo.startswith("CHIARIMENTO"):
            testo = risposta.split(":", 1)[1].strip() if ":" in risposta else risposta[len("CHIARIMENTO"):].strip()
            return {"tipo": "chiarimento", "testo": testo}
        if maiuscolo.startswith("DIRETTA"):
            testo = risposta.split(":", 1)[1].strip() if ":" in risposta else risposta[len("DIRETTA"):].strip()
            return {"tipo": "diretta", "testo": testo}
        return {"tipo": "query"}

    def _risolvi_riferimenti(self, state: DialogState) -> dict:
        domanda = state["domanda"]
        classificazione = self._classifica_domanda(domanda, state)

        if classificazione["tipo"] == "chiarimento":
            # mette in pausa il grafo: chi chiama deve chiedere il chiarimento all'utente
            # (via gTTS) e poi far ripartire il grafo con rispondi_chiarimento()
            risposta_utente = interrupt(classificazione["testo"])
            return {"domanda": f"{domanda} (chiarimento: {risposta_utente})"}

        if classificazione["tipo"] == "diretta":
            # nessuna query necessaria: la risposta è già pronta, si salta genera_risposta
            return {"domanda": domanda, "risposta": classificazione["testo"]}

        return {"domanda": domanda}

    def _genera_risposta(self, state: DialogState) -> dict:
        # includo gli scambi precedenti nella domanda inviata alla chain, così anche la
        # generazione della query Cypher può risolvere riferimenti impliciti come "questi quadri"
        domanda_con_contesto = f"""Scambi precedenti della conversazione (dal più vecchio al più recente):
{self._cronologia_recente(state)}

Nuova domanda dell'utente, da usare per generare la query: {state["domanda"]}"""

        risultato = self._chain.invoke({"query": domanda_con_contesto})
        return {"risposta": risultato["result"]}

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
