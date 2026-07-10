from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_ollama import ChatOllama

from chatbot import config
from chatbot.rag.prompts import CYPHER_PROMPT, QA_PROMPT


class RagChain:
    """
    Catena RAG (Retrieval-Augmented Generation) su grafo Neo4j.
    Incapsula il collegamento a Neo4j, il modello LLM (Ollama) e la GraphCypherQAChain di LangChain,che: (1) genera una query Cypher dalla domanda, (2) la esegue sul grafo, (3) trasforma il risultato in una risposta in linguaggio naturale.
    Costruisce ed espone la GraphCypherQAChain e il modello LLM sottostante.

    Espone due attributi usati dal DialogManager:
    - `chain`: la GraphCypherQAChain (`.invoke({"query": ...}) -> {"result": ...}`)
    - `llm`:   il modello LLM, riutilizzato anche per la classificazione delle domande
    """

    def __init__(self):
        self.graph = Neo4jGraph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
        self.llm = ChatOllama(model=config.MODELLO_LLM, temperature=config.LLM_TEMPERATURE)
        self.chain = GraphCypherQAChain.from_llm(
            llm=self.llm,
            graph=self.graph,
            verbose=True,
            allow_dangerous_requests=True,
            qa_prompt=QA_PROMPT,
            cypher_prompt=CYPHER_PROMPT,
        )
