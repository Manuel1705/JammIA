"""Dialogue state management via a LangGraph graph.

The DialogManager orchestrates between the user and the RAG chain. For each turn:
1. `_analyze_question` — ONE LLM call that classifies the request (QUERY / CLARIFICATION / DIRECT)
   and, if it is a QUERY, already splits it into atomic, self-contained sub-questions.
2. if a CLARIFICATION is needed, the graph pauses with `interrupt()` and the caller must collect the
   user's answer and resume with `answer_clarification()`.
3. `_generate_answer` — queries the RAG chain for each sub-question and joins the answers.

State is persisted on SQLite (checkpointer), so it survives restarts; each conversation is identified
by a `thread_id`.

Note: the LLM prompt and the user-facing messages are intentionally kept in Italian; the parser also
matches the Italian tags (QUERY / CHIARIMENTO / DIRETTA / IN: / FUORI:) produced by that prompt.
"""
from typing import List, Optional, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from chatbot import config

# standard answer for out-of-scope sub-questions (other artists or unrelated topics)
OUT_OF_SCOPE_MESSAGE = (
    "Questo esula dal mio ambito: rispondo solo a domande su Caravaggio, Caracciolo, "
    "le loro opere e i musei di Napoli che le espongono."
)


class DialogState(TypedDict):
    question: str
    history: List[dict]
    # each sub-question is {"text": str, "in_scope": bool}: out-of-scope ones get a fixed
    # answer without querying the graph
    sub_questions: Optional[List[dict]]
    current_artist: Optional[str]
    current_work: Optional[str]
    current_museum: Optional[str]
    answer: Optional[str]


class DialogManager:
    def __init__(self, chain, llm, db_file=None):
        """
        chain: the GraphCypherQAChain (`.invoke({"query": ...}) -> {"result": ...}`) used to answer.
        llm: chat model (`.invoke(str) -> object with .content`) used to classify and split the question.
        db_file: path of the SQLite checkpoint (default: config.DIALOG_DB).
        """
        self._chain = chain
        self._llm = llm
        self._checkpointer_cm = SqliteSaver.from_conn_string(str(db_file or config.DIALOG_DB))
        self._checkpointer = self._checkpointer_cm.__enter__()
        self._graph = self._build_graph()

    def _build_graph(self):
        g = StateGraph(DialogState)
        g.add_node("resolve_references", self._resolve_references)
        g.add_node("generate_answer", self._generate_answer)
        g.add_node("update_state", self._update_state)

        g.add_edge(START, "resolve_references")
        # if resolve_references already produced a direct answer (no query needed),
        # skip generate_answer and go straight to updating the history
        g.add_conditional_edges(
            "resolve_references",
            lambda state: "update_state" if state.get("answer") else "generate_answer",
            {"generate_answer": "generate_answer", "update_state": "update_state"},
        )
        g.add_edge("generate_answer", "update_state")
        g.add_edge("update_state", END)

        return g.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _recent_history(state: DialogState, n: int = 3) -> str:
        """Format the last n question/answer exchanges, to give the model the context needed to
        resolve implicit references (e.g. "these paintings", "that work"). The labels stay Italian
        because this text is fed into the Italian LLM prompt."""
        history = state.get("history", [])[-n:]
        if not history:
            return "nessuno"
        return "\n".join(
            f"- Domanda: {turn['question']}\n  Risposta: {turn['answer']}"
            for turn in history
        )

    def _analyze_question(self, question: str, state: DialogState) -> dict:
        """In a SINGLE LLM call, classify the question and, if it is a QUERY, already split it into
        atomic sub-questions. Returns one of:
        - {"type": "query", "sub_questions": [...]}
        - {"type": "clarification", "text": ...}
        - {"type": "direct", "text": ...}"""
        prompt = f"""Sei l'instradatore di un chatbot su Caravaggio, Caracciolo, le loro opere e i musei di
Napoli che le ospitano. Analizza la richiesta dell'utente e classificala in una di queste tre categorie,
usando anche gli scambi precedenti come contesto:

1. QUERY — la richiesta contiene ANCHE UNA SOLA domanda di informazioni su opere, artisti o musei
   (conteggi, nomi, descrizioni, luoghi, date, ecc.), comprensibile anche grazie a un riferimento
   implicito risolvibile dagli scambi precedenti (es. "questi quadri" dopo aver appena parlato di 2 quadri).
   Vale anche se la richiesta è COMPOSTA e una parte è fuori tema o fuori ambito (es. un altro artista non
   trattato): basta che una parte richieda dati su opere/artisti/musei. In caso di dubbio, scegli QUERY.
   Se è QUERY, SCOMPONI la richiesta nelle singole domande atomiche che la compongono: ognuna autonoma,
   su UN solo argomento, e COMPLETAMENTE AUTO-CONTENUTA. Sostituisci OGNI riferimento implicito
   (dimostrativi come "questi/queste/quei", pronomi come "lui/lei/le", avverbi come "lì") con il nome
   esplicito dell'entità preso dagli scambi precedenti (il titolo dell'opera, il nome dell'artista o del
   museo). Nella sotto-domanda riscritta NON devono più comparire dimostrativi o pronomi: chi la legge non
   deve aver bisogno della conversazione precedente per capirla.
   Etichetta OGNI sotto-domanda con l'ambito: "IN:" se riguarda Caravaggio, Caracciolo (anche "Merisi" o
   "Battistello"), le loro opere o i musei/luoghi di Napoli; "FUORI:" se riguarda un ALTRO artista (es.
   Botticelli, Michelangelo, Raffaello) o un tema non pertinente.
2. CHIARIMENTO — la richiesta richiederebbe una query, ma usa un riferimento implicito (es. "lui",
   "quell'opera") che né la richiesta né gli scambi precedenti chiariscono.
3. DIRETTA — SOLO messaggi puramente sociali (saluti, ringraziamenti, commiati, small talk) che NON
   contengono NESSUNA richiesta di informazioni. Se il messaggio contiene una qualsiasi domanda su
   opere/artisti/musei, NON è mai DIRETTA: è QUERY.

Scambi precedenti (dal più vecchio al più recente):
{self._recent_history(state)}

Richiesta dell'utente: {question}

Rispondi SOLO in uno di questi formati esatti, senza altro testo:
- se QUERY: la PRIMA riga è esattamente "QUERY", poi UNA domanda atomica per riga, ciascuna preceduta
  dall'etichetta di ambito "IN:" o "FUORI:" (senza numeri né trattini).
- se CHIARIMENTO: "CHIARIMENTO: <unica domanda di chiarimento, breve e diretta>"
- se DIRETTA: "DIRETTA: <risposta breve e cordiale in italiano>"

Esempi:
Richiesta: "Quanti quadri di Caravaggio sono a Napoli?"
QUERY
IN: Quanti quadri di Caravaggio sono a Napoli?

Richiesta: "Elencami questi quadri." (dopo aver parlato dei quadri di Caravaggio a Napoli)
QUERY
IN: Quali sono i titoli dei quadri di Caravaggio esposti a Napoli?

Richiesta: "Come si chiamano queste opere e quante ne ha fatte Botticelli?" (dopo aver parlato delle opere di Caravaggio a Napoli)
QUERY
IN: Come si chiamano le opere di Caravaggio esposte a Napoli?
FUORI: Quante opere ha fatto Botticelli?

Richiesta: "Chi l'ha dipinta?" (nessuna opera nominata prima)
CHIARIMENTO: Di quale opera stai parlando?

Richiesta: "Grazie mille!"
DIRETTA: Prego, è stato un piacere!"""

        response = self._llm.invoke(prompt).content.strip()
        lines = [r.strip() for r in response.splitlines() if r.strip()]
        first = lines[0] if lines else ""
        upper = first.upper()

        if upper.startswith("CHIARIMENTO"):
            text = first.split(":", 1)[1].strip() if ":" in first else first[len("CHIARIMENTO"):].strip()
            return {"type": "clarification", "text": text}
        if upper.startswith("DIRETTA"):
            text = first.split(":", 1)[1].strip() if ":" in first else first[len("DIRETTA"):].strip()
            return {"type": "direct", "text": text}

        # QUERY: every line (except "QUERY") is a sub-question with an IN:/FUORI: scope tag.
        # If the tag is missing (the model omitted it), it is treated as in-scope for safety.
        sub_questions = []
        for r in lines:
            text = r.strip(" -*\t")
            if text.upper() == "QUERY":
                continue
            if text.upper().startswith("FUORI"):
                sub_questions.append({"text": text.split(":", 1)[-1].strip(), "in_scope": False})
            elif text.upper().startswith("IN:"):
                sub_questions.append({"text": text.split(":", 1)[1].strip(), "in_scope": True})
            else:
                sub_questions.append({"text": text, "in_scope": True})

        return {"type": "query", "sub_questions": sub_questions or [{"text": question, "in_scope": True}]}

    def _resolve_references(self, state: DialogState) -> dict:
        question = state["question"]
        analysis = self._analyze_question(question, state)

        # NB: ALWAYS reset the previous turn's answer. Since it stays persisted in the SQLite
        # checkpoint, if not cleared the conditional edge would mistake it for a direct answer of
        # THIS turn, skipping generate_answer and repeating the old answer (echo across turns).
        if analysis["type"] == "clarification":
            # pause the graph: the caller must ask the user for the clarification
            # and then resume the graph with answer_clarification()
            user_answer = interrupt(analysis["text"])
            # after the clarification, treat the clarified question as a single in-scope sub-question
            clarified_question = f"{question} (chiarimento: {user_answer})"
            subs = [{"text": clarified_question, "in_scope": True}]
            return {"question": clarified_question, "sub_questions": subs, "answer": None}

        if analysis["type"] == "direct":
            # no query needed: the answer is already ready, generate_answer is skipped
            return {"question": question, "answer": analysis["text"]}

        return {"question": question, "sub_questions": analysis["sub_questions"], "answer": None}

    def _generate_answer(self, state: DialogState) -> dict:
        # sub-questions are already self-contained (references were resolved in _analyze_question),
        # so the history is NOT passed to the chain: feeding it here would make the model copy the
        # previous turns' answers instead of using the new result
        sub_questions = state.get("sub_questions") or [{"text": state["question"], "in_scope": True}]

        answers = []
        for sq in sub_questions:
            if sq.get("in_scope", True):
                answers.append(self._invoke_chain_with_retry(sq["text"], sq["text"]))
            else:
                # out-of-scope sub-question (other artist/topic): fixed answer, no graph query
                answers.append(OUT_OF_SCOPE_MESSAGE)

        final_answer = " ".join(a for a in answers if a) or "Si è verificato un errore."
        return {"answer": final_answer}

    def _invoke_chain_with_retry(self, sub_question: str, question_with_context: str, max_retry: int = 3) -> str:
        """Query the chain, retrying if the Cypher generation fails (small models sometimes produce
        syntactically invalid Cypher; since generation is stochastic, a new attempt often produces a
        valid query). If all attempts fail, return a fallback message for that sub-question instead of
        dropping it silently."""
        for attempt in range(max_retry):
            try:
                result = self._chain.invoke({"query": question_with_context})
                return result["result"].strip()
            except Exception as e:
                print(f"[DialogManager] attempt {attempt + 1}/{max_retry} failed "
                      f"on sub-question {sub_question!r}: {e}")
        return f"Non sono riuscito a recuperare le informazioni per: «{sub_question}»."

    @staticmethod
    def _update_state(state: DialogState) -> dict:
        history = state.get("history", []) + [
            {"question": state["question"], "answer": state["answer"]}
        ]
        return {"history": history}

    def invoke(self, question: str, thread_id: str = "default") -> dict:
        """Start a new conversation turn.
        Returns {"type": "answer", "text": ...} if the turn is complete,
        or {"type": "clarification", "text": ...} if something must be asked to the user."""
        graph_config = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke({"question": question}, config=graph_config)
        return self._interpret_result(result)

    def answer_clarification(self, user_answer: str, thread_id: str = "default") -> dict:
        """Resume a turn that was paused waiting for a clarification from the user."""
        graph_config = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke(Command(resume=user_answer), config=graph_config)
        return self._interpret_result(result)

    @staticmethod
    def _interpret_result(result: dict) -> dict:
        if "__interrupt__" in result:
            clarification_text = result["__interrupt__"][0].value
            return {"type": "clarification", "text": clarification_text}
        return {"type": "answer", "text": result["answer"]}

    def close(self):
        self._checkpointer_cm.__exit__(None, None, None)
