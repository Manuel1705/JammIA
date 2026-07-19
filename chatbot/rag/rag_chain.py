from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain

from chatbot import config
from chatbot.rag.prompts import CYPHER_PROMPT


class RagChain:
    """RAG (Retrieval-Augmented Generation) chain over the Neo4j graph.

    Wraps the Neo4j connection, the LLM (Ollama) and LangChain's GraphCypherQAChain. With
    `return_direct=True` the chain is used only for RETRIEVAL: it generates a Cypher query from the
    question, runs it on the graph, and returns the RAW result (no natural-language step). Turning the
    result into a coherent Italian answer is done separately by the DialogManager in a single synthesis
    call for the whole turn (so a compound question costs 1 synthesis call instead of one per part).

    Exposes two attributes used by the DialogManager:
    - `chain`: retrieval chain (`.invoke({"query": ...}) -> {"result": <raw query rows>}`)
    - `llm`:   the LLM, reused for classifying the question and for the final synthesis
    """

    def __init__(self):
        self.llm = config.make_llm(config.LLM_TEMPERATURE)
        self.chain = GraphCypherQAChain.from_llm(
            llm=self.llm,
            graph=Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD),
            verbose=True,
            allow_dangerous_requests=True,
            cypher_prompt=CYPHER_PROMPT,
            return_direct=True,   # return raw rows, skip the built-in QA step (saves 1 LLM call each)
            validate_cypher=True,  # auto-correct wrong relationship directions to match the schema, so a
                                   # backwards arrow from the LLM doesn't silently return an empty result
        )
