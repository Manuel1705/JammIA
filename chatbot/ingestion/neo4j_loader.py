"""Scrittura di artisti, opere e musei nel database a grafo Neo4j.

Il grafo modella tre tipi di nodo (Artista, Opera, Museo, più Città) collegati dalle relazioni
DIPINTA_DA (Opera→Artista), ESPOSTA_IN (Opera→Museo) e SITUATO_IN (Museo→Città).
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

    def svuota_database(self):
        """Cancella tutto il grafo prima di reinserire i dati."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("Database svuotato")

    def inserisci_artista(self, artista: dict):
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Artista {wikidataId: $wikidata_id})
                ON CREATE SET
                    a.name          = $nome,
                    a.data_nascita  = $data_nascita,
                    a.luogo_nascita = $luogo_nascita,
                    a.movimenti     = $movimenti,
                    a.opere_notevoli = $opere_notevoli
            """,
                        wikidata_id=artista["wikidata_id"],
                        nome=artista["nome"],
                        data_nascita=artista["data_nascita"],
                        luogo_nascita=artista["luogo_nascita"],
                        movimenti=artista["movimenti"],
                        opere_notevoli=artista["opere_notevoli"],
                        )

    def inserisci_opera(self, opera: dict):
        # collega l'opera all'artista (sempre) e al museo (solo se presente, via FOREACH condizionale)
        with self.driver.session() as session:
            session.run("""
                MERGE (o:Opera {wikidataId: $wikidata_id})
                ON CREATE SET
                    o.name      = $titolo,
                    o.anno        = $anno,
                    o.altezza     = $altezza,
                    o.larghezza   = $larghezza,
                    o.tecnica     = $tecnica,
                    o.soggetti    = $soggetti,
                    o.descrizione = $descrizione,
                    o.tipo        = $tipo

                WITH o

                MATCH (a:Artista {wikidataId: $artista_id})
                MERGE (o)-[:DIPINTA_DA]->(a)

                WITH o

                FOREACH (_ IN CASE WHEN $museo_id <> '' THEN [1] ELSE [] END |
                    MERGE (m:Museo {wikidataId: $museo_id})
                    MERGE (o)-[:ESPOSTA_IN]->(m)
                )
            """,
                        wikidata_id=opera["wikidata_id"],
                        titolo=opera["titolo"],
                        anno=opera["anno"],
                        altezza=opera["altezza"],
                        larghezza=opera["larghezza"],
                        tecnica=opera["tecnica"],
                        soggetti=opera["soggetti"],
                        descrizione=opera["descrizione"],
                        tipo=opera["tipo"],
                        artista_id=opera["artista_id"],
                        museo_id=opera["museo_id"],
                        )

    def inserisci_museo(self, museo: dict):
        with self.driver.session() as session:
            session.run("""
                MERGE (m:Museo {wikidataId: $wikidata_id})
                ON CREATE SET
                    m.name        = $nome,
                    m.descrizione = $descrizione,
                    m.indirizzo   = $indirizzo,
                    m.sito        = $sito,
                    m.telefono    = $telefono,
                    m.fondazione  = $fondazione,
                    m.latitudine  = $latitudine,
                    m.longitudine = $longitudine,
                    m.biglietto   = $biglietto

                WITH m
                FOREACH (_ IN CASE WHEN $citta <> '' THEN [1] ELSE [] END |
                    MERGE (c:Città {name: $citta})
                    MERGE (m)-[:SITUATO_IN]->(c)
                )
            """,
                        wikidata_id=museo["wikidata_id"],
                        nome=museo["nome"],
                        descrizione=museo["descrizione"],
                        indirizzo=museo["indirizzo"],
                        sito=museo["sito"],
                        telefono=museo["telefono"],
                        fondazione=museo["fondazione"],
                        latitudine=museo["latitudine"],
                        longitudine=museo["longitudine"],
                        citta=museo["citta"],
                        biglietto=museo["biglietto"],
                        )
