from typing import Literal, Optional
from pydantic import BaseModel

from chatbot.dialog.dialog_state import SubQuestion


class ModelResponse(BaseModel):
    type: Literal["query", "clarification", "chitchat"]
    sub_questions: Optional[list[SubQuestion]] = None  # if type query
    clarification_question: Optional[str] = None  # if type clarification
    response: Optional[str] = None  # if type chitchat

    def __str__(self):
        return f"""
            ModelResponse:
            type: {self.type}
            sub_questions: {self.sub_questions}
            clarification_question: {self.clarification_question}
            response: {self.response}
        """
