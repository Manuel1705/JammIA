from sparql_query import (esegui_query, estrai_opere, estrai_artisti,
                             estrai_musei, salva_cache, carica_cache,
                             query_artisti, query_opere_caravaggio,
                             query_opere_caracciolo, query_musei)
from neo4j_connector import Neo4jLoader

if __name__ == "__main__":

    # ── Prova a caricare dalla cache ─────────────────────────
    cache = carica_cache()

    if cache:
        ris_artisti    = cache["artisti"]
        ris_caravaggio = cache["caravaggio"]
        ris_caracciolo = cache["caracciolo"]
        ris_musei      = cache["musei"]
    else:
        # ── Esegui le query SPARQL ────────────────────────────
        print("Query artisti...")
        ris_artisti = esegui_query(query_artisti)
        print(f"   → {len(ris_artisti)} artisti trovati")

        print("Query opere Caravaggio...")
        ris_caravaggio = esegui_query(query_opere_caravaggio)
        print(f"   → {len(ris_caravaggio)} opere trovate")

        print("Query opere Caracciolo...")
        ris_caracciolo = esegui_query(query_opere_caracciolo)
        print(f"   → {len(ris_caracciolo)} opere trovate")

        print("Query musei...")
        ris_musei = esegui_query(query_musei)
        print(f"   → {len(ris_musei)} musei trovati")

        # ── Salva in cache ────────────────────────────────────
        salva_cache({
            "artisti":    ris_artisti,
            "caravaggio": ris_caravaggio,
            "caracciolo": ris_caracciolo,
            "musei":      ris_musei
        })

    # ── Estrai + arricchisci ──────────────────────────────────
    print("\n📖 Estrazione dati...")
    artisti          = estrai_artisti(ris_artisti)
    opere_caravaggio = estrai_opere(ris_caravaggio, artista_id="Q42207")
    opere_caracciolo = estrai_opere(ris_caracciolo, artista_id="Q2519261")
    musei            = estrai_musei(ris_musei)

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