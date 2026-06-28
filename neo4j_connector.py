#connessione neo4j db
from neo4j import GraphDatabase

URI      = "neo4j://127.0.0.1:7687"
USER     = "neo4j"
PASSWORD = "CambioManuAle417"

class Neo4jLoader:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    def close(self):
        self.driver.close()

    def svuota_database(self):
        """Cancella tutto il grafo prima di reinserire i dati"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("🗑️  Database svuotato")

    # ── Inserimento Artista ───────────────────────────────────
    def inserisci_artista(self, nome, wikidata_id):
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Artista {wikidataId: $wikidata_id})
                ON CREATE SET a.nome = $nome
            """, nome=nome, wikidata_id=wikidata_id)

    # ── Inserimento Opera ─────────────────────────────────────
    def inserisci_opera(self, opera):
        with self.driver.session() as session:
            session.run("""
                MERGE (o:Opera {wikidataId: $wikidata_id})
                ON CREATE SET o.titolo   = $titolo,
                              o.soggetti = $soggetti

                WITH o

                // Collega all'artista
                MATCH (a:Artista {wikidataId: $artista_id})
                MERGE (o)-[:DIPINTA_DA]->(a)

                WITH o

                // Collega al museo se presente
                FOREACH (_ IN CASE WHEN $museo_id <> '' THEN [1] ELSE [] END |
                    MERGE (m:Museo {wikidataId: $museo_id})
                    MERGE (o)-[:ESPOSTA_IN]->(m)
                )
            """,
            wikidata_id = opera["wikidata_id"],
            titolo      = opera["titolo"],
            soggetti    = opera["soggetti"],
            artista_id  = opera["artista_id"],
            museo_id    = opera["museo_id"]
        )

    # ── Inserimento Museo ─────────────────────────────────────
    def inserisci_museo(self, museo):
        with self.driver.session() as session:
            session.run("""
                MERGE (m:Museo {wikidataId: $wikidata_id})
                ON CREATE SET m.nome       = $nome,
                              m.indirizzo  = $indirizzo,
                              m.sito       = $sito,
                              m.telefono   = $telefono,
                              m.fondazione = $fondazione

                WITH m
                MERGE (c:Città {nome: "Napoli"})
                MERGE (m)-[:SITUATO_IN]->(c)
            """,
            wikidata_id = museo["wikidata_id"],
            nome        = museo["nome"],
            indirizzo   = museo["indirizzo"],
            sito        = museo["sito"],
            telefono    = museo["telefono"],
            fondazione  = museo["fondazione"]
        )