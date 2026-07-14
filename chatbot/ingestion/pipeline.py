from collections.abc import Callable
from chatbot.ingestion.Extractor import Extractor
from chatbot.ingestion.Neo4jLoader import Neo4jLoader
from chatbot.ingestion.SparqlExecutor import SparqlExecutor

# Wikidata QIDs of the two artists covered
CARAVAGGIO_ID = "Q42207"
CARACCIOLO_ID = "Q2519261"


def _insert(insert_fn: Callable[[dict], None], items: list[dict], label: str) -> None:
    print(f"Inserting {label}...")
    for item in items:
        insert_fn(item)


def populate_database() -> None:
    """Run the whole ingestion pipeline and repopulate Neo4j from scratch."""
    results = SparqlExecutor().execute_all()

    print("\n📖 Extracting data...")
    extractor = Extractor()
    artists = extractor.extract_artists(results.artists)
    works_caravaggio = extractor.extract_works(results.works_caravaggio, artist_id=CARAVAGGIO_ID)
    works_caracciolo = extractor.extract_works(results.works_caracciolo, artist_id=CARACCIOLO_ID)
    museums = extractor.extract_museums(results.museums)

    with Neo4jLoader() as loader:
        loader.clear_database()
        _insert(loader.insert_artist, artists, "artists")
        _insert(loader.insert_museum, museums, "museums")
        _insert(loader.insert_work, works_caravaggio, "Caravaggio works")
        _insert(loader.insert_work, works_caracciolo, "Caracciolo works")

    print("\n✅ Neo4j database populated successfully!")
