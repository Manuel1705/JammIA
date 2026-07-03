"""Pipeline di popolamento del database: Wikidata → estrazione → Neo4j.

Orchestra i tre componenti di ingestion: interroga Wikidata (con cache), normalizza e arricchisce
i dati con Wikipedia, poi svuota e ripopola il grafo Neo4j.
"""
from chatbot.ingestion.extractor import Extractor
from chatbot.ingestion.neo4j_loader import Neo4jLoader
from chatbot.ingestion.sparql_executor import SparqlExecutor

# QID Wikidata dei due artisti trattati
CARAVAGGIO_ID = "Q42207"
CARACCIOLO_ID = "Q2519261"


def popola_database():
    """Esegue l'intera pipeline di ingestion e ripopola Neo4j da zero."""
    executor = SparqlExecutor()
    risultati = executor.esegui_tutte()

    print("\n📖 Estrazione dati...")
    extractor = Extractor()
    artisti = extractor.estrai_artisti(risultati.artisti)
    opere_caravaggio = extractor.estrai_opere(risultati.opere_caravaggio, artista_id=CARAVAGGIO_ID)
    opere_caracciolo = extractor.estrai_opere(risultati.opere_caracciolo, artista_id=CARACCIOLO_ID)
    musei = extractor.estrai_musei(risultati.musei)

    loader = Neo4jLoader()
    loader.svuota_database()

    print("\n Inserisco artisti...")
    for artista in artisti:
        loader.inserisci_artista(artista)

    print("Inserisco musei...")
    for museo in musei:
        loader.inserisci_museo(museo)

    print("Inserisco opere Caravaggio...")
    for opera in opere_caravaggio:
        loader.inserisci_opera(opera)

    print("Inserisco opere Caracciolo...")
    for opera in opere_caracciolo:
        loader.inserisci_opera(opera)

    loader.close()
    print("\n Database Neo4j popolato con successo!")
