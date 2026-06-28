## Implementazione della Rag, collegando il db al LLM
from neo4j import GraphDatabase
from langchain_groq import ChatGroq
from langchain.prompts import ChatPromptTemplate
from mlx_lm import load, generate


# ── Configurazione ────────────────────────────────────────────
URI      = "neo4j://127.0.0.1:7687"
USER     = "neo4j"
PASSWORD = "CambioManuAle417"

MODEL_NAME = "mlx-community/Meta-Llama-3.1-8B-Instruct-8bit"

# ── Carica modello una volta sola ─────────────────────────────
MODEL, TOKENIZER = load(MODEL_NAME)
print("✅ Modello caricato!")

# ── Connessione Neo4j ─────────────────────────────────────────
driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# ── Retriever ─────────────────────────────────────────────────
def recupera_contesto(domanda):
    """
    Cerca in Neo4j le informazioni rilevanti per la domanda.
    Prova più strategie in cascata.
    """
    contesto = []

    with driver.session() as session:

        # Strategia 1 — cerca per titolo opera
        result = session.run("""
            MATCH (o:Opera)-[:DIPINTA_DA]->(a:Artista)
            OPTIONAL MATCH (o)-[:ESPOSTA_IN]->(m:Museo)
            OPTIONAL MATCH (m)-[:SITUATO_IN]->(c:Città)
            WHERE toLower(o.titolo) CONTAINS toLower($domanda)
            RETURN o.titolo      AS titolo,
                   o.anno        AS anno,
                   o.tecnica     AS tecnica,
                   o.soggetti    AS soggetti,
                   o.descrizione AS descrizione,
                   o.tipo        AS tipo,
                   a.nome        AS artista,
                   m.nome        AS museo,
                   m.indirizzo   AS indirizzo,
                   c.nome        AS citta
            LIMIT 3
        """, domanda=domanda)

        for r in result:
            citta   = r["citta"]   or "N/D"
            a_napoli = "A NAPOLI" if citta.lower() == "napoli" else "NON a Napoli"
            contesto.append(
                f"Opera: {r['titolo']} [{a_napoli}]\n"
                f"Artista: {r['artista']}\n"
                f"Anno: {r['anno']}\n"
                f"Tipo: {r['tipo']}\n"
                f"Tecnica: {r['tecnica']}\n"
                f"Soggetti: {r['soggetti']}\n"
                f"Museo: {r['museo']}, {r['indirizzo']}, {citta}\n"
                f"Descrizione: {r['descrizione']}"
            )

        # Strategia 2 — cerca per artista
        if not contesto:
            result = session.run("""
                MATCH (o:Opera)-[:DIPINTA_DA]->(a:Artista)
                OPTIONAL MATCH (o)-[:ESPOSTA_IN]->(m:Museo)
                OPTIONAL MATCH (m)-[:SITUATO_IN]->(c:Città)
                WHERE toLower(a.nome) CONTAINS toLower($domanda)
                RETURN a.nome          AS artista,
                       a.data_nascita  AS nascita,
                       a.luogo_nascita AS luogo,
                       a.movimenti     AS movimenti,
                       a.opere_notevoli AS notevoli,
                       collect(DISTINCT o.titolo) AS opere,
                       collect(DISTINCT m.nome)   AS musei
                LIMIT 1
            """, domanda=domanda)

            for r in result:
                contesto.append(
                    f"Artista: {r['artista']}\n"
                    f"Nato il: {r['nascita']} a {r['luogo']}\n"
                    f"Movimenti: {r['movimenti']}\n"
                    f"Opere notevoli: {r['notevoli']}\n"
                    f"Opere nel db: {', '.join(r['opere'][:10])}\n"
                    f"Musei: {', '.join([m for m in r['musei'] if m])[:5]}"
                )

        # Strategia 3 — cerca per soggetti/depicts
        if not contesto:
            result = session.run("""
                MATCH (o:Opera)-[:DIPINTA_DA]->(a:Artista)
                OPTIONAL MATCH (o)-[:ESPOSTA_IN]->(m:Museo)
                OPTIONAL MATCH (m)-[:SITUATO_IN]->(c:Città)
                WHERE toLower(o.soggetti) CONTAINS toLower($domanda)
                RETURN o.titolo    AS titolo,
                       o.soggetti  AS soggetti,
                       a.nome      AS artista,
                       m.nome      AS museo,
                       c.nome      AS citta
                LIMIT 3
            """, domanda=domanda)

            for r in result:
                citta    = r["citta"] or "N/D"
                a_napoli = "A NAPOLI" if citta.lower() == "napoli" else "NON a Napoli"
                contesto.append(
                    f"Opera: {r['titolo']} [{a_napoli}]\n"
                    f"Artista: {r['artista']}\n"
                    f"Soggetti: {r['soggetti']}\n"
                    f"Museo: {r['museo']}, {citta}"
                )

        # Strategia 4 — cerca per museo
        if not contesto:
            result = session.run("""
                MATCH (m:Museo)
                OPTIONAL MATCH (m)-[:SITUATO_IN]->(c:Città)
                OPTIONAL MATCH (o:Opera)-[:ESPOSTA_IN]->(m)
                OPTIONAL MATCH (o)-[:DIPINTA_DA]->(a:Artista)
                WHERE toLower(m.nome) CONTAINS toLower($domanda)
                RETURN m.nome        AS museo,
                       m.indirizzo   AS indirizzo,
                       m.sito        AS sito,
                       m.telefono    AS telefono,
                       m.fondazione  AS fondazione,
                       m.biglietto   AS biglietto,
                       c.nome        AS citta,
                       collect(DISTINCT o.titolo) AS opere
                LIMIT 1
            """, domanda=domanda)

            for r in result:
                contesto.append(
                    f"Museo: {r['museo']}\n"
                    f"Città: {r['citta']}\n"
                    f"Indirizzo: {r['indirizzo']}\n"
                    f"Sito: {r['sito']}\n"
                    f"Telefono: {r['telefono']}\n"
                    f"Anno fondazione: {r['fondazione']}\n"
                    f"Biglietto: {r['biglietto']}\n"
                    f"Opere presenti: {', '.join([o for o in r['opere'] if o][:10])}"
                )

    return "\n\n".join(contesto) if contesto else ""


# ── Generatore ────────────────────────────────────────────────
SYSTEM_PROMPT = """
Sei una guida esperta di Caravaggio e Caracciolo, principalmente sulle opere 
presenti a Napoli. Ti verranno poste domande sulle opere, sui musei e sugli artisti stessi.
Rispondi in italiano, in modo chiaro e coinvolgente. Basati sulle informazioni presenti 
nel Database per rispondere e se l'informazione non è presente, dillo chiaramente senza inventare. 
"""

def genera_risposta(domanda, messages):
    """
    Recupera il contesto da Neo4j e genera una risposta con LLM.
    """
    # Recupera contesto rilevante
    contesto = recupera_contesto(domanda)

    if contesto:
        contenuto = f"Contesto dal database:\n{contesto}\n\nDomanda: {domanda}"
    else:
        contenuto = f"Domanda: {domanda}\n(Nessuna informazione trovata nel database)"

    # Aggiunge la domanda alla cronologia
    messages.append({"role": "user", "content": contenuto})

    # Genera risposta
    prompt   = TOKENIZER.apply_chat_template(messages, add_generation_prompt=True)
    risposta = generate(MODEL, TOKENIZER, prompt=prompt,
                        max_tokens=500, verbose=False)

    # Salva risposta nella cronologia
    messages.append({"role": "assistant", "content": risposta})

    return risposta, messages


# ── Test rapido ───────────────────────────────────────────────
if __name__ == "__main__":
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    domande_test = [
        "Dove si trova la Flagellazione di Cristo?",
        "Dimmi qualcosa su Caravaggio",
        "Quali opere hanno degli angeli?",
        "Cosa c'è al Pio Monte della Misericordia?"
    ]

    for domanda in domande_test:
        print(f"\n👤 {domanda}")
        risposta, messages = genera_risposta(domanda, messages)
        print(f"🤖 {risposta}")
        print("─" * 60)

    driver.close()