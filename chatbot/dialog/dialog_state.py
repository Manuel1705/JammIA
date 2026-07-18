from typing import List, Optional, TypedDict

from pydantic import BaseModel, Field


class Turn(BaseModel):
    question: str
    answer: Optional[str] = None

    def __str__(self) -> str:
        return f"Question: {self.question}\n Response: {self.answer}"


class SubQuestion(BaseModel):
    question: str
    in_scope: bool = True

    def __str__(self) -> str:
        return f"Question: {self.question}\n In scope: {self.in_scope}"


class DialogState(BaseModel):
    question: str = ""
    sub_questions: Optional[List[SubQuestion]] = None
    clarification_question: Optional[str] = None
    clarification_attempts: int = 0
    history: List[Turn] = Field(default_factory=list)
    response: Optional[str] = None

    def get_recent_history(self, n: int = 3) -> str:
        return "\n".join(str(turn) for turn in self.history[-n:]) or "nessuno"

    def current_turn(self) -> Turn:
        return Turn(question=self.question, answer=self.response)

    def append_current_turn_to_history(self, n: int = 10) -> List[Turn]:
        new_history = self.history.copy()
        new_history.append(self.current_turn())
        return new_history[-n:]


class DialogStateUpdate(TypedDict, total=False):
    question: str
    sub_questions: Optional[List[SubQuestion]]
    clarification_question: Optional[str]
    clarification_attempts: int
    history: List[Turn]
    response: Optional[str]
