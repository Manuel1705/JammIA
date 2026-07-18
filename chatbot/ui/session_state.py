import uuid
from typing import TypedDict


class SessionState(TypedDict):
    """Per-session state carried in gr.State: which conversation and whether the last turn asked
    the user for a clarification (so the next message is routed as the clarification answer)."""
    thread_id: str
    awaiting_clarification: bool


def new_session_state() -> SessionState:
    """Fresh session state with a new conversation id."""
    return SessionState(thread_id=str(uuid.uuid4()), awaiting_clarification=False)
