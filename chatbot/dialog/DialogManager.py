import json
from concurrent.futures import ThreadPoolExecutor

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from chatbot import config
from chatbot.dialog.DialogState import DialogState, get_recent_history
from chatbot.rag.RagChain import RagChain
from chatbot.rag.prompts import SYNTHESIS_PROMPT_TEMPLATE

_MAX_RETRIEVAL_WORKERS = 4  # upper bound on concurrent Cypher retrievals

# Etichette di intent riconosciute al primo turno -> nome del nodo di slot-filling dedicato.
_MENU_INTENTS = {"OPERA": "opera", "MUSEO": "museo", "ARTISTA": "artista", "CERCA": "cerca_opera"}
#messaggio inixiale che viene mostrato
_MENU_TEXT = (
    "Ciao! Come posso aiutarti? Posso darti informazioni su:\n"
    "1) un'opera\n2) un museo\n3) un artista\n4) aiutarti a cercare un'opera specifica\n"
    "Dimmi pure cosa ti interessa."
)


def _out_of_scope_note(texts: list) -> str:
    refs = "; ".join(f"«{t}»" for t in texts)
    return f"Riguardo a {refs}, questo esula dal mio ambito: rispondo solo a domande su Caravaggio, Caracciolo, le loro opere e i musei di Napoli che le espongono."


class DialogManager:
    def __init__(self):
        rag = RagChain()
        self._chain = rag.chain
        self._llm = rag.llm
        self._router_llm = ChatOllama(model=config.LLM_MODEL, temperature=0)
        self._checkpointer = MemorySaver()
        self._graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(DialogState)
        g.add_node("saluta_e_menu", self._saluta_e_menu)
        g.add_node("classifica_intent", self._classifica_intent)
        g.add_node("slot_opera", self._slot_opera)
        g.add_node("slot_museo", self._slot_museo)
        g.add_node("slot_artista", self._slot_artista)
        g.add_node("cerca_opera_flow", self._cerca_opera_flow)
        g.add_node("slot_to_sub_question", self._slot_to_sub_question)

        g.add_node("resolve_references", self._update_state)
        g.add_node("clarify", self._clarify)
        g.add_node("generate_answer", self._generate_answer)
        g.add_node("update_history", self._update_history)

        # --- primo turno: saluto + menu a 4 intent ---
        g.add_edge(START, "saluta_e_menu")
        g.add_edge("saluta_e_menu", "classifica_intent")
        g.add_conditional_edges(
            "classifica_intent",
            self._route_after_intent,
            {
                "opera": "slot_opera", "museo": "slot_museo",
                "artista": "slot_artista", "cerca_opera": "cerca_opera_flow",
                "resolve_references": "resolve_references",
            },
        )
        for n in ("slot_opera", "slot_museo", "slot_artista", "cerca_opera_flow"):
            g.add_edge(n, "slot_to_sub_question")
        g.add_edge("slot_to_sub_question", "generate_answer")

        # --- turni successivi (e primo turno se il testo non è riconducibile a nessun intent) ---
        # route by what resolve_references produced: a ready direct answer skips retrieval; a pending
        # clarification goes to the clarify node (which owns the interrupt); otherwise it is a query.
        g.add_conditional_edges(
            "resolve_references",
            self._route_after_resolve,
            {"clarify": "clarify", "generate_answer": "generate_answer", "update_history": "update_history"},
        )
        g.add_edge("clarify", "generate_answer")
        g.add_edge("generate_answer", "update_history")
        g.add_edge("update_history", END)

        return g.compile(checkpointer=self._checkpointer)

    # ------------------------------------------------------------------
    # Nodi del primo turno: saluto, classificazione intent, slot-filling
    # ------------------------------------------------------------------

    @staticmethod
    def _saluta_e_menu(state: DialogState) -> dict:
        """Primo nodo del grafo. Se ha già salutato, dopo non fa nulla."""
        if state.get("greeted"):
            return {}
        scelta = interrupt(_MENU_TEXT)
        return {"greeted": True, "question": scelta}

    def _classifica_intent(self, state: DialogState) -> dict:
        """
        Al primo turno, classifica l'intent dell'utente su una delle 4 opzioni (Strada A),
        se nessuna viene scelta passa al flusso libero (Strada B) con la classificazione di clarify ecc."""
        if state.get("history"):
            return {"intent": None, "slots": None}

        prompt = f"""Classifica la richiesta dell'utente in una di queste 4 categorie, oppure ALTRO
        se non è chiaramente riconducibile a nessuna:
        OPERA — chiede informazioni su un'opera specifica di cui si sa già il nome
        MUSEO — chiede informazioni su un museo
        ARTISTA — chiede informazioni su un artista (Caravaggio o Battistello/Caracciolo)
        CERCA — vuole cercare/identificare un'opera che non sa nominare con certezza 
        ALTRO — nessuna delle precedenti, incluso small talk o domande generiche

        Richiesta: {state['question']}

        Rispondi con una sola parola: OPERA, MUSEO, ARTISTA, CERCA o ALTRO."""
        raw = self._router_llm.invoke(prompt).content.strip().upper()
        # prende la prima etichetta riconosciuta contenuta nella risposta, per tollerare testo extra
        label = next((k for k in _MENU_INTENTS if k in raw), None)
        intent = _MENU_INTENTS.get(label)
        return {"intent": intent, "slots": {}}

    @staticmethod
    def _route_after_intent(state: DialogState) -> str:
        """capisce quale delle due strade intraprendere"""
        return state.get("intent") or "resolve_references"

    def _slot_semplice(self, state: DialogState, campo: str, domanda: str) -> dict:
        """Se gli slot sono vuoti interrompe il flusso e passa al fare le domande"""
        slots = dict(state.get("slots") or {})
        if not slots.get(campo):
            slots[campo] = interrupt(domanda)
        return {"slots": slots}

# togliamo opera? credo sia una ripetizione di quello di sotto
    def _slot_opera(self, state: DialogState) -> dict:
        return self._slot_semplice(state, "opera", "Di quale opera vuoi sapere qualcosa? Dimmi il titolo.")

    def _slot_museo(self, state: DialogState) -> dict:
        return self._slot_semplice(state, "museo", "Di quale museo vuoi sapere qualcosa?")

    def _slot_artista(self, state: DialogState) -> dict:
        return self._slot_semplice(
            state, "artista", "Di quale artista vuoi sapere qualcosa: Caravaggio o Battistello Caracciolo?"
        )

    def _cerca_opera_flow(self, state: DialogState) -> dict:
        """Chiede inizialmente se si qualcosa sull'opera, altrimenti si passa a chiedere le singole cose"""
        slots = dict(state.get("slots") or {})

        if not any(slots.get(k) for k in ("artista", "titolo", "soggetto")):
            risposta = interrupt(
                "Per aiutarti a trovarla: conosci l'artista, il titolo (anche parziale) o il soggetto raffigurato?"
            )
            slots.update(self._estrai_criteri(risposta))

        if not any(slots.get(k) for k in ("artista", "titolo", "soggetto")):
            artista = interrupt("Proviamo diversamente: conosci almeno l'artista?")
            if artista.strip().lower() not in ("no", "non lo so"):
                slots["artista"] = artista
            else:
                titolo = interrupt("Ricordi anche solo una parola del titolo?")
                if titolo.strip().lower() not in ("no", "non lo so"):
                    slots["titolo"] = titolo
                else:
                    slots["soggetto"] = interrupt("Ricordi cosa raffigura (persone, scena, oggetti)?")

        return {"slots": slots}

    def _estrai_criteri(self, testo: str) -> dict:
        """Chiede al modello di estrarre gli slot dal messaggio dell'utente, quindi artista, titolo e soggetti"""
        prompt = f"""Estrai da questo testo, se presenti, il nome dell'artista, il titolo (anche parziale)
        e il soggetto raffigurato. Rispondi SOLO con un oggetto JSON valido, senza altro testo, tipo:
        {{"artista": null, "titolo": null, "soggetto": null}}

        Testo: {testo}"""
        raw = self._router_llm.invoke(prompt).content.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            return {}
        try:
            data = json.loads(raw[start:end + 1])
        except (ValueError, TypeError):
            return {}
        return {k: v for k, v in data.items() if k in ("artista", "titolo", "soggetto") and v}

    @staticmethod
    def _slot_to_sub_question(state: DialogState) -> dict:
        """Gli slot riempiti vengono utilizzati per creare le subquestion da passare al modello"""
        intent = state.get("intent")
        slots = state.get("slots") or {}
        if intent == "opera":
            testo = f"Dimmi tutto su {slots.get('opera', '')}."
        elif intent == "museo":
            testo = f"Dimmi tutto sul museo {slots.get('museo', '')}."
        elif intent == "artista":
            testo = f"Dimmi tutto su {slots.get('artista', '')}."
        else:  # cerca_opera
            parti = [f"{k}: {v}" for k, v in slots.items() if v]
            testo = "Trova l'opera con queste caratteristiche: " + ", ".join(parti)
        return {"sub_questions": [{"text": testo, "in_scope": True}]}

    # ------------------------------------------------------------------
    # Parte precedente
    # ------------------------------------------------------------------

    @staticmethod
    def _route_after_resolve(state: DialogState) -> str:
        if state.get("answer"):
            return "update_history"
        if state.get("clarification_text"):
            return "clarify"
        return "generate_answer"

    def _classify_question(self, question: str, state: DialogState) -> dict:
        """Classify a question in a single LLM call, returning one of:
        - {"type": "query", "sub_questions": [{"text", "in_scope"}, ...]}
        - {"type": "clarification", "text": ...}
        - {"type": "direct", "text": ...}
        The model is asked for JSON; parsing tolerates surrounding text/reasoning and falls back to a
        single in-scope query if the output can't be parsed (a turn never crashes on a bad output)."""
        prompt = _build_prompt(question, state)
        response = self._router_llm.invoke(prompt).content.strip()
        print("\n" + "─" * 70)
        print(f"🧠 [CLASSIFY] question: {question!r}")
        print(f"🧠 [CLASSIFY] raw model output:\n{response}")
        print("─" * 70)
        return _parse_analysis(response, question)

    def _update_state(self, state: DialogState) -> dict:
        question = state["question"]
        res = self._classify_question(question, state)
        new_partial_state = {
            "question": question,
            "answer": None,
            "sub_questions": None,
            "clarification_text": None
        }
        if res["type"] == "direct":
            new_partial_state["answer"] = res["text"]
        elif res["type"] == "clarification":
            new_partial_state["clarification_text"] = res["text"]
        else:
            new_partial_state["sub_questions"] = res["sub_questions"]
        return new_partial_state

    def _clarify(self, state: DialogState) -> dict:
        """Own the clarification pause. Kept as a SEPARATE node so that on resume only this node
        re-executes: the initial analysis in resolve_references already ran and was checkpointed, so
        it is not repeated (one fewer LLM call per clarification)."""
        user_answer = interrupt(state["clarification_text"])
        question = f"{state['question']} (chiarimento: {user_answer})"
        # re-analyze WITH history so implicit references get rewritten. No second interrupt: if it is
        # still not a clean query, force a single in-scope query to avoid a clarification loop.
        analysis = self._classify_question(question, state)
        if analysis["type"] != "query":
            analysis = {"type": "query", "sub_questions": [{"text": question, "in_scope": True}]}
        return {"question": question, "sub_questions": analysis["sub_questions"],
                "answer": None, "clarification_text": None}

    def _generate_answer(self, state: DialogState) -> dict:
        sub_questions = state.get("sub_questions") or [{"text": state["question"], "in_scope": True}]

        in_scope: list[str] = [sq["text"] for sq in sub_questions if sq.get("in_scope", True)]
        out_of_scope: list[str] = [sq["text"] for sq in sub_questions if not sq.get("in_scope", True)]

        answer_parts = []
        if in_scope:  # not empty
            # dedupe identical sub-questions (same text -> same rows) and retrieve them in parallel:
            # dict.fromkeys keeps the first occurrence and preserves order.
            unique = list(dict.fromkeys(in_scope))
            with ThreadPoolExecutor(max_workers=min(_MAX_RETRIEVAL_WORKERS, len(unique))) as pool:
                rows_by_query = dict(zip(unique, pool.map(self._query_graph_with_retries, unique)))
            retrieved = [(q, rows_by_query[q]) for q in unique]
            answer_parts.append(self._synthesize(retrieved))
        if out_of_scope:
            answer_parts.append(_out_of_scope_note(out_of_scope))

        return {"answer": " ".join(answer_parts).strip()}

    def _query_graph_with_retries(self, query: str, max_retry: int = 3) -> list:
        for attempt in range(max_retry):
            try:
                result_rows = self._chain.invoke({"query": query})["result"]
                print(f"📊 [RESULT] {query!r} -> {result_rows}")
                if result_rows:
                    return result_rows
                print(f"[DialogManager] empty result, retrying {attempt + 1}/{max_retry} "
                      f"on query {query!r}")
            except Exception as e:
                print(f"[DialogManager] attempt {attempt + 1}/{max_retry} failed "
                      f"on query {query!r}: {e}")
        return []

    def _synthesize(self, retrieved: list) -> str:
        """Combine the raw rows retrieved for the in-scope sub-questions into a single coherent Italian
        answer (one LLM call). `retrieved` is a list of (sub_question_text, raw_rows). The original user
        question is intentionally NOT passed: the model must answer only these blocks, so it cannot
        comment on out-of-scope parts (handled separately by the out-of-scope note)."""
        blocks = "\n".join(
            f"- Sotto-domanda: {sub_q}\n  Dati: {rows}"
            for sub_q, rows in retrieved
        )
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(results=blocks)
        answer = self._llm.invoke(prompt).content.strip()
        print(f"🧠 [SYNTHESIS] {answer}")
        return answer or "Si è verificato un errore."

    @staticmethod
    def _update_history(state: DialogState) -> dict:
        history = list(state.get("history", []))
        history.append({"question": state["question"], "answer": state["answer"]})
        return {"history": history[-10:]}

    def invoke(self, question: str, thread_id: str = "default") -> dict:
        """Start a new conversation turn.
        Returns {"type": "answer", "text": ...} if the turn is complete,
        or {"type": "clarification", "text": ...} if something must be asked to the user."""
        graph_config = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke({"question": question}, config=graph_config)
        return self._interpret_result(result)

    def answer_clarification(self, user_answer: str, thread_id: str = "default") -> dict:
        """Resume a turn that was paused waiting for a clarification from the user (this covers
        BOTH the classic clarification node AND any interrupt() raised by the menu/slot nodes:
        the graph pauses/resumes the same way regardless of which node owns the interrupt)."""
        graph_config = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke(Command(resume=user_answer), config=graph_config)
        return self._interpret_result(result)

    @staticmethod
    def _interpret_result(result: dict) -> dict:
        if "__interrupt__" in result:
            clarification_text = result["__interrupt__"][0].value
            return {"type": "clarification", "text": clarification_text}
        return {"type": "answer", "text": result["answer"]}


def _parse_analysis(raw: str, question: str) -> dict:
    """Parse the router's JSON output. Extracts the first {...} block (the model may wrap it in
    markdown fences or emit reasoning around it) and validates its shape. On any failure it falls back
    to treating the whole request as a single in-scope query, so a turn never crashes on bad output."""
    fallback = {"type": "query", "sub_questions": [{"text": question, "in_scope": True}]}
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return fallback
    try:
        data = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return fallback

    kind = str(data.get("type", "")).lower()
    if kind == "clarification":
        text = str(data.get("text", "")).strip()
        return {"type": "clarification", "text": text} if text else fallback
    if kind == "direct":
        text = str(data.get("text", "")).strip()
        return {"type": "direct", "text": text} if text else fallback
    if kind == "query":
        sub_questions = []
        for sq in data.get("sub_questions", []) or []:
            if isinstance(sq, dict):
                text = str(sq.get("text", "")).strip()
                if text:
                    sub_questions.append({"text": text, "in_scope": bool(sq.get("in_scope", True))})
        return {"type": "query", "sub_questions": sub_questions or fallback["sub_questions"]}
    return fallback


def _build_prompt(question: str, state: DialogState) -> str:
    return f"""
    Sei l'instradatore di un chatbot su Caravaggio, Caracciolo, le loro opere e i musei di
    Napoli che le ospitano. Analizza la richiesta dell'utente e classificala in una di queste tre categorie,
    usando anche gli scambi precedenti come contesto:

    1. QUERY — la richiesta contiene anche una sola domanda di informazioni su opere, artisti o musei
    (conteggi, nomi, descrizioni, luoghi, date, ecc.), comprensibile anche grazie a un riferimento
    implicito risolvibile dagli scambi precedenti (es. "questi quadri" dopo aver appena parlato di 2 quadri).
    Vale anche se la richiesta è composta e una parte è fuori tema o fuori ambito (es. un altro artista non
    trattato): basta che una parte richieda dati su opere/artisti/musei. In caso di dubbio, scegli QUERY.
    Se è QUERY, SCOMPONI la richiesta nelle singole domande atomiche che la compongono: ognuna autonoma,
    su UN solo argomento, e COMPLETAMENTE AUTO-CONTENUTA. Sostituisci OGNI riferimento implicito
    (dimostrativi come "questi/queste/quei", pronomi come "lui/lei/le", avverbi come "lì") con il nome
    esplicito dell'entità preso dagli scambi precedenti (il titolo dell'opera, il nome dell'artista o del
    museo). Nella sotto-domanda riscritta NON devono più comparire dimostrativi o pronomi: chi la legge non
    deve aver bisogno della conversazione precedente per capirla.
    Per OGNI sotto-domanda indica "in_scope": true se riguarda Caravaggio, Caracciolo (anche "Merisi" o
    "Battistello"), le loro opere o i musei/luoghi di Napoli; false se riguarda un ALTRO (es.
    Botticelli, Michelangelo, Raffaello) o un tema non pertinente. Se ti chiedo rigurdo a un opera o un museo che non sai se rigurda Caravaggio o Caracciolo imposta in_scope: true.
    2. CHIARIMENTO — la richiesta richiederebbe una query, ma usa un riferimento implicito
    (es. "lui", "quell'opera") che né la richiesta né gli scambi precedenti chiariscono.
    3. DIRETTA — SOLO messaggi puramente sociali (saluti, ringraziamenti, commiati, small talk) che NON
    contengono NESSUNA richiesta di informazioni. Se il messaggio contiene una qualsiasi domanda su
    opere/artisti/musei, NON è mai DIRETTA: è QUERY.

    Scambi precedenti (dal più vecchio al più recente):
    {get_recent_history(state)}

    Richiesta dell'utente: {question}

    Rispondi SOLO con un oggetto JSON valido (nessun altro testo, nessun markdown, nessun commento),
    in UNO di questi formati:
    - QUERY:       {{"type": "query", "sub_questions": [{{"text": "<domanda atomica auto-contenuta>", "in_scope": true}}]}}
    - CHIARIMENTO: {{"type": "clarification", "text": "<unica domanda di chiarimento, breve e diretta>"}}
    - DIRETTA:     {{"type": "direct", "text": "<risposta breve e cordiale in italiano>"}}

    Esempi (richiesta -> output JSON):
    "Quanti quadri di Caravaggio sono a Napoli?"
    {{"type": "query", "sub_questions": [{{"text": "Quanti quadri di Caravaggio sono a Napoli?", "in_scope": true}}]}}

    "Elencami questi quadri." (dopo aver parlato dei quadri di Caravaggio a Napoli)
    {{"type": "query", "sub_questions": [{{"text": "Quali sono i titoli dei quadri di Caravaggio esposti a Napoli?", "in_scope": true}}]}}

    "Come si chiamano queste opere e quante ne ha fatte Botticelli?" (dopo aver parlato delle opere di Caravaggio a Napoli)
    {{"type": "query", "sub_questions": [{{"text": "Come si chiamano le opere di Caravaggio esposte a Napoli?", "in_scope": true}}, {{"text": "Quante opere ha fatto Botticelli?", "in_scope": false}}]}}

    "Chi l'ha dipinta?" (nessuna opera nominata prima)
    {{"type": "clarification", "text": "Di quale opera stai parlando?"}}

    "Grazie mille!"
    {{"type": "direct", "text": "Prego, è stato un piacere!"}}"""