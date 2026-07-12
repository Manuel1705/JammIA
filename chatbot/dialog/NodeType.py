from enum import StrEnum


class NodeType(StrEnum):
    USER_PROMPT_CLASSIFICATION = "user_prompt_classification"
    USER_INTENT_CLARIFICATION = "user_intent_clarification"
    HISTORY_UPDATE = "history_update"
    RESPONSE_GENERATION = "response_generation"
