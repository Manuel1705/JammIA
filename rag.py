from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_ollama import ChatOllama
from langchain_core.prompts import  PromptTemplate

URI = "neo4j://127.0.0.1:7687"
USER = "neo4j"
PASSWORD = "CambioManuAle417"

graph = Neo4jGraph(URI, USER, PASSWORD)

# Ollama integrato con langchain
llm_cypher = ChatOllama(model="gemma2", temperature=0)

# 1. Definiamo il comportamento generale nel System Prompt
QA_PROMPT_TEMPLATE = """Sei una guida esperta opere artistiche, in particolare di Caravaggio e Caracciolo. 
L'utente ti chiederà domande sulle opere, sui musei o sugli artisti presenti nel database.  
Rispondi in italiano, in modo chiaro, approfondito e creando un'esperienza coinvolgente per l'utente. Non ti dilungare troppo e 
attieniti alle informazioni fornite dal database. 

Informazioni dal database:
{context}

Domanda dell'utente: {question}

Risposta dettagliata:"""

QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"], template=QA_PROMPT_TEMPLATE
)

CYPHER_GENERATION_TEMPLATE = """Task: Genera una query Cypher da utilizzare sul database.
Istruzioni:
Usa solo le relazioni e proprietà presenti nello schema.
Non inventare etichette e relazioni che non esistono.

REGOLE TASSATIVE DI SINTASSI:
1. NON inserire MAI le punte delle frecce (< o >) nelle relazioni. Genera query sempre BIDIREZIONALI.
2. Usa sempre la sintassi piatta: -[:NOME_RELAZIONE]-
   - Per collegare Opera e Artista usa: (o:Opera)-[:DIPINTA_DA]-(a:Artista) o (a:Artista)-[:DIPINTA_DA]-(o:Opera)
   - Per collegare Opera e Museo usa: (o:Opera)-[:ESPOSTA_IN]-(m:Museo)  o (m:Museo)-[:ESPOSTA_IN]-(o:Opera)
   - Per collegare Museo e Città usa: (m:Museo)-[:SITUATO_IN]-(c:Città) o  (c:Città)-[:SITUATO_IN]-(m:Museo)
3. Non inventare etichette o proprietà non presenti nello schema fornito e .

Schema:
{schema}

Question: {question}
Cypher Query:"""

CYPHER_PROMPT = PromptTemplate(
    input_variables=["schema", "question"],
    template=CYPHER_GENERATION_TEMPLATE
)

chain = GraphCypherQAChain.from_llm(
    llm=llm_cypher,
    graph=graph,
    verbose=True,
    allow_dangerous_requests=True,
    qa_prompt=QA_PROMPT,
    cypher_prompt=CYPHER_PROMPT,
)

def genera_risposta(domanda):
    try:
        risultato = chain.invoke({"query": domanda})
        return risultato["result"]
    except Exception as e:
        print(f"Errore: {e}")
        return "Si è verificato un errore."

if __name__ == "__main__":
    domande_test = [
        #"Chi ha dipinto il 'Ritratto di papa Paolo V'?",
        #"Dove posso trovare il 'Ritratto di papa Paolo V'?",
        #"Quale opera di Caravaggio contiene papa Paolo V?",
        #"Quali opere di Caravaggio posso vedere nella Galleria Borghese?",
        "Quali opere di Caravaggio contengono della frutta?",
        "Ci sono opere di Caravaggio e Caracciolo che rappresentano gli stessi soggetti?",
        "Quali musei di Napoli contengono le opere di Caracciolo?",
        "Quali sono le opere di Caravaggio presenti a Napoli?"
    ]

    for domanda in domande_test:
        print(f"\n {domanda}")
        risposta = genera_risposta(domanda)
        print(f" {risposta}")
        print("─" * 60)