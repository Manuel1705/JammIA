from concurrent.futures import ThreadPoolExecutor
from typing import Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from chatbot import config
from chatbot.dialog.ModelResponse import ModelResponse
from chatbot.dialog.NodeType import NodeType
from chatbot.dialog.DialogState import DialogState, SubQuestion, Turn, DialogStateUpdate
from chatbot.dialog.prompts import build_prompt_classifier_prompt
from chatbot.rag.RagChain import RagChain
from chatbot.rag.prompts import COMBINE_PROMPTS_TEMPLATE


class TurnResult(TypedDict):
    """Esito di un turno restituito alla UI."""
    type: Literal["answer", "clarification_question"]
    text: str


class DialogManager:
    def __init__(self):
        self._rag = RagChain()
        self._chat_model = ChatOllama(model=config.LLM_MODEL, temperature=0)
        self._structured_chat_model = self._chat_model.with_structured_output(ModelResponse)
        self._checkpointer = MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=[Turn, SubQuestion]))
        self._graph = self._build_state_graph()

    def _build_state_graph(self) -> CompiledStateGraph[DialogState]:
        g = StateGraph(DialogState)

        # Nodes
        g.add_node(NodeType.USER_PROMPT_CLASSIFICATION, self._classify_user_prompt)
        g.add_node(NodeType.USER_INTENT_CLARIFICATION, self._clarify_user_intent)
        g.add_node(NodeType.RESPONSE_GENERATION, self._generate_response)
        g.add_node(NodeType.HISTORY_UPDATE, self._update_history)

        # Edges
        g.add_edge(START, NodeType.USER_PROMPT_CLASSIFICATION)
        g.add_conditional_edges(
            NodeType.USER_PROMPT_CLASSIFICATION,
            self._route_after_resolve,
            {
                NodeType.USER_INTENT_CLARIFICATION: NodeType.USER_INTENT_CLARIFICATION,
                NodeType.RESPONSE_GENERATION: NodeType.RESPONSE_GENERATION,
                NodeType.HISTORY_UPDATE: NodeType.HISTORY_UPDATE,
            },
        )
        g.add_conditional_edges(
            NodeType.USER_INTENT_CLARIFICATION,
            self._route_after_clarification,
            {
                NodeType.USER_INTENT_CLARIFICATION: NodeType.USER_INTENT_CLARIFICATION,
                NodeType.RESPONSE_GENERATION: NodeType.RESPONSE_GENERATION,
            },
        )
        g.add_edge(NodeType.RESPONSE_GENERATION, NodeType.HISTORY_UPDATE)
        g.add_edge(NodeType.HISTORY_UPDATE, END)

        return g.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _out_of_scope_note(questions: list) -> str:
        refs = "; ".join(f"«{t}»" for t in questions)
        return (f"Riguardo a {refs}, questo esula dal mio ambito: rispondo solo a domande su "
                f"Caravaggio, Caracciolo, le loro opere e i musei di Napoli che le espongono.")

    @staticmethod
    def _route_after_resolve(state: DialogState) -> NodeType:
        if state.response:
            return NodeType.HISTORY_UPDATE
        if state.clarification_question:
            return NodeType.USER_INTENT_CLARIFICATION
        if state.sub_questions:
            return NodeType.RESPONSE_GENERATION

        return NodeType.USER_INTENT_CLARIFICATION

    @staticmethod
    def _route_after_clarification(state: DialogState) -> NodeType:
        if state.clarification_question:
            return NodeType.USER_INTENT_CLARIFICATION
        return NodeType.RESPONSE_GENERATION

    def _classify_question(self, question: str, state: DialogState) -> ModelResponse:
        prompt = build_prompt_classifier_prompt(question, state)
        response = cast(ModelResponse, self._structured_chat_model.invoke(prompt))
        print(response)
        return response

    def _classify_user_prompt(self, state: DialogState) -> DialogStateUpdate:
        response = self._classify_question(state.question, state)
        return DialogStateUpdate(
            response=response.response if response.type == "chitchat" else None,
            clarification_question=response.clarification_question if response.type == "clarification" else None,
            sub_questions=response.sub_questions if response.type == "query" else None,
            clarification_attempts=0)

    def _clarify_user_intent(self, state: DialogState) -> DialogStateUpdate:
        user_reply = interrupt(state.clarification_question)
        question = f"{state.question} (chiarimento: {user_reply})"
        attempts = state.clarification_attempts + 1
        response: ModelResponse = self._classify_question(question, state)
        if response.type == "clarification" and attempts < 3:
            return DialogStateUpdate(
                question=question,
                clarification_attempts=attempts,
                clarification_question=response.clarification_question,
                sub_questions=None,
                response=None)
        return DialogStateUpdate(
            question=question,
            clarification_attempts=0,
            sub_questions=response.sub_questions,
            clarification_question=None,
            response=None)

    def _generate_response(self, state: DialogState) -> dict:
        sub_questions = state.sub_questions or [SubQuestion(question=state.question)]

        in_scope = [sq.question for sq in sub_questions if sq.in_scope]
        out_of_scope = [sq.question for sq in sub_questions if not sq.in_scope]

        answer_parts = []
        if len(in_scope) > 0:
            unique = list(dict.fromkeys(in_scope))  # remove duplicate and preserve order
            with ThreadPoolExecutor(max_workers=min(5, len(unique))) as pool:
                rows_by_query = dict(zip(unique, pool.map(self._query_graph_with_retries, unique)))
            retrieved = [(q, rows_by_query[q]) for q in unique]
            answer_parts.append(self._combine_sub_responses(retrieved))
        if len(out_of_scope) > 0:
            answer_parts.append(self._out_of_scope_note(out_of_scope))

        return {"response": " ".join(answer_parts).strip()}

    def _query_graph_with_retries(self, query: str, max_retry: int = 3) -> list:
        for attempt in range(max_retry):
            try:
                result_rows = self._rag.chain.invoke({"query": query})["result"]
                print(f"📊 [RESULT] {query!r} -> {result_rows}")
                if result_rows:
                    return result_rows
                print(f"[DialogManager] empty result, retrying {attempt + 1}/{max_retry} "
                      f"on query {query!r}")
            except Exception as e:
                print(f"[DialogManager] attempt {attempt + 1}/{max_retry} failed "
                      f"on query {query!r}: {e}")
        return []

    def _combine_sub_responses(self, retrieved: list) -> str:
        blocks = "\n".join(
            f"- Subquestion: {sub_q}\n  Data: {rows}"
            for sub_q, rows in retrieved
        )
        prompt = COMBINE_PROMPTS_TEMPLATE.format(results=blocks)
        answer = self._rag.llm.invoke(prompt).content.strip()
        print(f"🧠 [RESPONSE] {answer}")
        return answer or "An Error occurred during sub answers combination"

    @staticmethod
    def _update_history(state: DialogState) -> DialogStateUpdate:
        return DialogStateUpdate(history=state.append_current_turn_to_history())

    def invoke(self, question: str, thread_id: str = "default") -> TurnResult:
        graph_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke({"question": question}, config=graph_config)
        return self._interpret_result(result)

    def answer_clarification(self, user_clarification: str, thread_id: str = "default") -> TurnResult:
        graph_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        result = self._graph.invoke(Command(resume=user_clarification), config=graph_config)
        return self._interpret_result(result)

    @staticmethod
    def _interpret_result(result: dict) -> TurnResult:
        """Takes the graph response and maps it to a TurnResult to be displayed in the UI"""
        if "__interrupt__" in result:
            return TurnResult(type="clarification_question", text=result["__interrupt__"][0].value)
        return TurnResult(type="answer", text=result["response"])
