from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_ollama import ChatOllama

from chatbot import config
from chatbot.rag.prompts import CYPHER_PROMPT, QA_PROMPT


class RagChain:
    """RAG (Retrieval-Augmented Generation) chain over the Neo4j graph.

    Wraps the Neo4j connection, the LLM (Ollama) and LangChain's GraphCypherQAChain, which:
    (1) generates a Cypher query from the question, (2) runs it on the graph, (3) turns the result
    into a natural-language answer.

    Exposes two attributes used by the DialogManager:
    - `chain`: the GraphCypherQAChain (`.invoke({"query": ...}) -> {"result": ...}`)
    - `llm`:   the LLM, reused also for classifying the questions
    """

    def __init__(self):
        self.graph = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
        self.llm = ChatOllama(model=config.LLM_MODEL, temperature=config.LLM_TEMPERATURE)
        self.chain = GraphCypherQAChain.from_llm(
            llm=self.llm,
            graph=self.graph,
            verbose=True,
            allow_dangerous_requests=True,
            qa_prompt=QA_PROMPT,
            cypher_prompt=CYPHER_PROMPT,
        )
