from typing import LiteralString
from neo4j import GraphDatabase
from chatbot import config


class Neo4jLoader:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )

    def __enter__(self) -> Neo4jLoader:
        return self

    def __exit__(self, *exc) -> None:
        self.driver.close()

    def _run(self, query: LiteralString, params: dict) -> None:
        with self.driver.session() as session:
            session.run(query, params)

    def clear_database(self) -> None:
        """Delete the whole graph before reinserting the data."""
        self._run("MATCH (n) DETACH DELETE n", {})
        print("Database cleared")

    def create_fulltext_indexes(self) -> None:
        """Full-text index (Lucene) on artwork and museum names: enables fuzzy search (~), which
        tolerates typos, different prepositions/articles and partial title forms. `IF NOT EXISTS`
        makes creation idempotent (DETACH DELETE does not remove the indexes)."""
        self._run("CREATE FULLTEXT INDEX operaNameIndex IF NOT EXISTS FOR (o:Opera) ON EACH [o.name]", {})
        self._run("CREATE FULLTEXT INDEX museoNameIndex IF NOT EXISTS FOR (m:Museo) ON EACH [m.name]", {})
        print("Full-text indexes ready (operaNameIndex, museoNameIndex)")

    def insert_artist(self, artist: dict) -> None:
        self._run("""
            MERGE (a:Artista {wikidataId: $wikidata_id})
            ON CREATE SET
                a.name           = $name,
                a.data_nascita   = $birth_date,
                a.data_morte     = $death_date,
                a.luogo_nascita  = $birth_place,
                a.movimenti      = $movements,
                a.opere_notevoli = $notable_works
        """, artist)

    def insert_museum(self, museum: dict) -> None:
        self._run("""
            MERGE (m:Museo {wikidataId: $wikidata_id})
            ON CREATE SET
                m.name        = $name,
                m.descrizione = $description,
                m.indirizzo   = $address,
                m.sito        = $website,
                m.telefono    = $phone,
                m.fondazione  = $founded,
                m.latitudine  = $latitude,
                m.longitudine = $longitude,
                m.biglietto   = $ticket

            WITH m
            FOREACH (_ IN CASE WHEN $city <> '' THEN [1] ELSE [] END |
                MERGE (c:Città {name: $city})
                MERGE (m)-[:SITUATO_IN]->(c)
            )
        """, museum)

    def insert_work(self, work: dict) -> None:
        """NOTE: Run only after inserting artists and museums.

        OPTIONAL MATCH + FOREACH instead of MATCH: if the artist or museum is missing, an inner MATCH
        would silently terminate the query halfway (later relationships never created). This way each
        relationship is created only if the node exists, without truncating the rest."""
        self._run("""
            MERGE (o:Opera {wikidataId: $wikidata_id})
            ON CREATE SET
                o.name        = $title,
                o.anno        = $year,
                o.altezza     = $height,
                o.larghezza   = $width,
                o.tecnica     = $technique,
                o.soggetti    = $subjects,
                o.descrizione = $description,
                o.tipo        = $type

            WITH o
            OPTIONAL MATCH (a:Artista {wikidataId: $artist_id})
            FOREACH (_ IN CASE WHEN a IS NOT NULL THEN [1] ELSE [] END |
                MERGE (o)-[:DIPINTA_DA]->(a)
            )

            WITH o
            OPTIONAL MATCH (m:Museo {wikidataId: $museum_id})
            FOREACH (_ IN CASE WHEN m IS NOT NULL THEN [1] ELSE [] END |
                MERGE (o)-[:ESPOSTA_IN]->(m)
            )
        """, work)
