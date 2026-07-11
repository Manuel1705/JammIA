from typing import TypedDict, List, Optional


class DialogState(TypedDict):
    question: str
    history: List[dict]  # [{"question", "answer"}]
    sub_questions: Optional[List[dict]]  # {"text": str, "in_scope": bool}
    clarification_text: Optional[str]  # question to ask the user when a clarification is needed
    answer: Optional[str]
    greeted: Optional[bool] #True dopo che il chatbot ha salutato all'inizio
    intent: Optional[str] # quale delle 4 azioni è intrapresa dall'utente (opera, museo, artista o cerca)
    slots: Optional[dict] # info raccolte per l'intent attuale


def get_recent_history(state: DialogState, n: int = 3) -> str:
    """Format the last n question/answer exchanges, to give the model the context needed to
    resolve implicit references (e.g. "these paintings", "that work"). The labels stay Italian
    because this text is fed into the Italian LLM prompt."""
    history = state.get("history", [])[-n:]
    if not history: return "nessuno"
    return "\n".join(
        f"- Domanda: {turn['question']}\n  Risposta: {turn['answer']}"
        for turn in history
    )
