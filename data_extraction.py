from Extractor import Extractor
from QueryExecutor import QueryExecutor
from neo4j_connector import Neo4jLoader

if __name__ == "__main__":

    executor = QueryExecutor()
    risultati = executor.esegui_tutte()

    # ── Estrai + arricchisci ──────────────────────────────────
    print("\n📖 Estrazione dati...")
    extractor = Extractor()
    artisti = extractor.estrai_artisti(risultati.artisti)
    opere_caravaggio = extractor.estrai_opere(risultati.opere_caravaggio, artista_id="Q42207")
    opere_caracciolo = extractor.estrai_opere(risultati.opere_caracciolo, artista_id="Q2519261")
    musei = extractor.estrai_musei(risultati.musei)

    # ── Neo4j ─────────────────────────────────────────────────
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
