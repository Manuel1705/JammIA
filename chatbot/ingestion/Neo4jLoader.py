"""Writing of artists, works and museums into the Neo4j graph database.

The graph models three node types (Artista, Opera, Museo, plus Città) connected by the relationships
DIPINTA_DA (Opera→Artista), ESPOSTA_IN (Opera→Museo) and SITUATO_IN (Museo→Città).

Note: the Cypher node labels, relationships and property names are kept in Italian because they are
the graph schema referenced by the (Italian) Cypher-generation prompt and by the already-populated
database; only the Python-side identifiers and query parameter names are in English.
"""
from neo4j import GraphDatabase

from chatbot import config


class Neo4jLoader:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def clear_database(self):
        """Delete the whole graph before reinserting the data."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("Database cleared")

    def insert_artist(self, artist: dict):
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Artista {wikidataId: $wikidata_id})
                ON CREATE SET
                    a.name          = $name,
                    a.data_nascita  = $birth_date,
                    a.luogo_nascita = $birth_place,
                    a.movimenti     = $movements,
                    a.opere_notevoli = $notable_works
            """,
                        wikidata_id=artist["wikidata_id"],
                        name=artist["name"],
                        birth_date=artist["birth_date"],
                        birth_place=artist["birth_place"],
                        movements=artist["movements"],
                        notable_works=artist["notable_works"],
                        )

    def insert_work(self, work: dict):
        # link the work to the artist (always) and to the museum (only if present, via a conditional FOREACH)
        with self.driver.session() as session:
            session.run("""
                MERGE (o:Opera {wikidataId: $wikidata_id})
                ON CREATE SET
                    o.name      = $title,
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

                FOREACH (_ IN CASE WHEN $museum_id <> '' THEN [1] ELSE [] END |
                    MERGE (m:Museo {wikidataId: $museum_id})
                    MERGE (o)-[:ESPOSTA_IN]->(m)
                )
            """,
                        wikidata_id=work["wikidata_id"],
                        title=work["title"],
                        year=work["year"],
                        height=work["height"],
                        width=work["width"],
                        technique=work["technique"],
                        subjects=work["subjects"],
                        description=work["description"],
                        type=work["type"],
                        artist_id=work["artist_id"],
                        museum_id=work["museum_id"],
                        )

    def insert_museum(self, museum: dict):
        with self.driver.session() as session:
            session.run("""
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
            """,
                        wikidata_id=museum["wikidata_id"],
                        name=museum["name"],
                        description=museum["description"],
                        address=museum["address"],
                        website=museum["website"],
                        phone=museum["phone"],
                        founded=museum["founded"],
                        latitude=museum["latitude"],
                        longitude=museum["longitude"],
                        city=museum["city"],
                        ticket=museum["ticket"],
                        )
