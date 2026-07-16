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

    def insert_artist(self, artist: dict) -> None:
        self._run("""
            MERGE (a:Artista {wikidataId: $wikidata_id})
            ON CREATE SET
                a.name           = $name,
                a.data_nascita   = $birth_date,
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
        """NOTE: Run only after inserting artists and museums """
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
            MATCH (a:Artista {wikidataId: $artist_id})
            MERGE (o)-[:DIPINTA_DA]->(a)

            WITH o
            MATCH (m:Museo {wikidataId: $museum_id})
            MERGE (0)-[:ESPOSTA_IN]->(m)
            )
        """, work)
