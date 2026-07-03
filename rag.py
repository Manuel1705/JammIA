from langchain_neo4j import Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

URI = "neo4j://127.0.0.1:7687"
USER = "neo4j"
PASSWORD = "password"

graph = Neo4jGraph(URI, USER, PASSWORD)

# Ollama integrato con langchain
llm_cypher = ChatOllama(model="gemma4:latest", temperature=0.1)

# 1. Definiamo il comportamento generale nel System Prompt
QA_PROMPT_TEMPLATE = """Sei una guida esperta di opere artistiche, in particolare di Caravaggio e Caracciolo.
L'utente ti chiederà domande sulle opere, sui musei o sugli artisti presenti nel database.

REGOLE DI STILE (obbligatorie):
- Rispondi in italiano in modo diretto e conciso: massimo 2-3 frasi in totale.
- Vai subito al dato richiesto: niente introduzioni, premesse poetiche o inviti finali ad approfondire.
- Attieniti esclusivamente alle informazioni fornite dal database, ma non nominarlo mai: non dire mai
  "secondo il database", "le informazioni disponibili indicano", "il dato riportato è" o simili. Rispondi
  come se conoscessi già il fatto, in modo naturale e diretto (es. "A Napoli si trovano 14 opere di
  Caracciolo." invece di "Secondo le informazioni del database, il numero di opere è 14.").

IMPORTANTE: le "Informazioni dal database" sono il risultato già calcolato della query, quindi contengono
già la risposta esatta (anche se è un solo numero o valore con un nome di campo tecnico tipo
"count(DISTINCT o)"). Riportalo esplicitamente nella risposta, senza dire che mancano dettagli se il
valore è presente.

Se invece le "Informazioni dal database" sono vuote E la domanda riguarda un argomento chiaramente al
di fuori del tuo ambito (non su Caravaggio, Caracciolo, le loro opere, o i musei di Napoli che le
ospitano), NON dire semplicemente che i dati non sono disponibili: dichiara esplicitamente che la
domanda esce dal tuo ambito, es. "Questo esula dal mio ambito: rispondo solo a domande su Caravaggio,
Caracciolo, le loro opere e i musei di Napoli che le espongono."

Informazioni dal database:
{context}

Domanda dell'utente: {question}

Risposta concisa (2-3 frasi):"""

QA_PROMPT = PromptTemplate(
    input_variables=["context", "question"], template=QA_PROMPT_TEMPLATE
)

CYPHER_GENERATION_TEMPLATE = """Task: Genera una query Cypher da utilizzare sul database.
Istruzioni:
Usa solo le relazioni e proprietà presenti nello schema.
Non inventare etichette e relazioni che non esistono.
NOTA BENE sui nomi degli artisti: nel database il nome esatto del nodo Artista è quello indicato tra
virgolette. Usa SEMPRE e SOLO l'artista effettivamente nominato nella domanda dell'utente:
- se la domanda nomina "Caravaggio" (o "Merisi"), il nodo da cercare è {{name: "Caravaggio"}} — MAI Caracciolo.
- se la domanda nomina "Caracciolo" (o "Battistello"), il nodo da cercare è {{name: "Battistello Caracciolo"}} — MAI Caravaggio.
Non sostituire mai un artista con l'altro: sono due persone diverse.

REGOLE TASSATIVE DI SINTASSI:
1. NON inserire MAI le punte delle frecce (< o >) nelle relazioni. Genera query sempre BIDIREZIONALI.
2. Usa sempre la sintassi piatta: -[:NOME_RELAZIONE]-
   - Per collegare Opera e Artista usa: (o:Opera)-[:DIPINTA_DA]-(a:Artista) o (a:Artista)-[:DIPINTA_DA]-(o:Opera)
   - Per collegare Opera e Museo usa: (o:Opera)-[:ESPOSTA_IN]-(m:Museo)  o (m:Museo)-[:ESPOSTA_IN]-(o:Opera)
   - Per collegare Museo e Città usa: (m:Museo)-[:SITUATO_IN]-(c:Città) o  (c:Città)-[:SITUATO_IN]-(m:Museo)
3. Non inventare etichette o proprietà non presenti nello schema fornito e attieniti alle relazioni presenti nel database.
4. Ogni valore aggregato (count, sum, avg, collect, ecc.) DEVE avere un alias leggibile con AS,
   es. "RETURN count(DISTINCT o) AS numero_opere" invece di "RETURN count(DISTINCT o)".

Esempio errato: (a:Artista)-[:ESPOSTA_IN]-(m:Museo) o (m:Museo)-[:ESPOSTA_IN]-(o:Città)

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
        # "Chi ha dipinto il 'Ritratto di papa Paolo V'?",
        # "Dove posso trovare il 'Ritratto di papa Paolo V'?",
        # "Quale opera di Caravaggio contiene papa Paolo V?",
        # "Quali opere di Caravaggio posso vedere nella Galleria Borghese?",
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
