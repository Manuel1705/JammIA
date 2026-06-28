from sparql_query import esegui_query, estrai_opere, estrai_musei
from sparql_query import query_caravaggio, query_caracciolo, query_musei
from neo4j_connector import Neo4jLoader

if __name__ == "__main__":
    # ── Step 1: esegui le query SPARQL ───────────────────────
    print("1️⃣  Query opere Caravaggio...")
    ris_caravaggio = esegui_query(query_caravaggio)
    print(f"   → {len(ris_caravaggio)} opere trovate")

    print("2️⃣  Query opere Caracciolo...")
    ris_caracciolo = esegui_query(query_caracciolo)
    print(f"   → {len(ris_caracciolo)} opere trovate")

    print("3️⃣  Query musei...")
    ris_musei = esegui_query(query_musei)
    print(f"   → {len(ris_musei)} musei trovati")

    # ── Step 2: estrai i dati ─────────────────────────────────
    opere_caravaggio = estrai_opere(ris_caravaggio, artista_id="Q42207")
    opere_caracciolo = estrai_opere(ris_caracciolo, artista_id="Q2519261")
    musei            = estrai_musei(ris_musei)

    # ── Step 3: inserisci in Neo4j ────────────────────────────
    loader = Neo4jLoader()
    loader.svuota_database()

    print("\n🎨 Inserisco artisti...")
    loader.inserisci_artista("Caravaggio",             "Q42207")
    loader.inserisci_artista("Battistello Caracciolo", "Q2519261")

    print("🖼️  Inserisco musei...")
    for museo in musei:
        loader.inserisci_museo(museo)
    print(f"   → {len(musei)} musei inseriti")

    print("🎨 Inserisco opere Caravaggio...")
    for opera in opere_caravaggio:
        loader.inserisci_opera(opera)
    print(f"   → {len(opere_caravaggio)} opere inserite")

    print("🎨 Inserisco opere Caracciolo...")
    for opera in opere_caracciolo:
        loader.inserisci_opera(opera)
    print(f"   → {len(opere_caracciolo)} opere inserite")

    loader.close()
    print("\n✅ Database Neo4j popolato con successo!")
    print("   Apri Neo4j Browser e lancia: MATCH (n) RETURN n")