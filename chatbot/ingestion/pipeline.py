"""Database population pipeline: Wikidata → extraction → Neo4j.

Orchestrates the three ingestion components: queries Wikidata (with cache), normalizes and enriches
the data with Wikipedia, then clears and repopulates the Neo4j graph.
"""
from chatbot.ingestion.Extractor import Extractor
from chatbot.ingestion.Neo4jLoader import Neo4jLoader
from chatbot.ingestion.SparqlExecutor import SparqlExecutor

# Wikidata QIDs of the two artists covered
CARAVAGGIO_ID = "Q42207"
CARACCIOLO_ID = "Q2519261"


def populate_database():
    """Run the whole ingestion pipeline and repopulate Neo4j from scratch."""
    executor = SparqlExecutor()
    results = executor.execute_all()

    print("\n📖 Extracting data...")
    extractor = Extractor()
    artists = extractor.extract_artists(results.artists)
    works_caravaggio = extractor.extract_works(results.works_caravaggio, artist_id=CARAVAGGIO_ID)
    works_caracciolo = extractor.extract_works(results.works_caracciolo, artist_id=CARACCIOLO_ID)
    museums = extractor.extract_museums(results.museums)

    loader = Neo4jLoader()
    loader.clear_database()

    print("\n Inserting artists...")
    for artist in artists:
        loader.insert_artist(artist)

    print("Inserting museums...")
    for museum in museums:
        loader.insert_museum(museum)

    print("Inserting Caravaggio works...")
    for work in works_caravaggio:
        loader.insert_work(work)

    print("Inserting Caracciolo works...")
    for work in works_caracciolo:
        loader.insert_work(work)

    loader.close()
    print("\n Neo4j database populated successfully!")
