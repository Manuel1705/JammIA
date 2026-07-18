from collections.abc import Callable

from chatbot import config
from chatbot.ingestion.extractor import Extractor
from chatbot.ingestion.neo4j_loader import Neo4jLoader
from chatbot.ingestion.sparql_executor import SparqlExecutor


def populate_database() -> None:
    """Runs the whole db ingestion pipeline repopulating Neo4j from scratch."""
    results = SparqlExecutor().execute_all()

    print("\n📖 Extracting data...")
    extractor = Extractor()
    artists = extractor.extract_artists(results.artists)
    works_caravaggio = extractor.extract_works(results.works_caravaggio, artist_id=config.CARAVAGGIO_ID)
    works_caracciolo = extractor.extract_works(results.works_caracciolo, artist_id=config.CARACCIOLO_ID)
    museums = extractor.extract_museums(results.museums)

    def _insert(insert_fn: Callable[[dict], None], items: list[dict], label: str) -> None:
        print(f"Inserting {label}...")
        for item in items:
            insert_fn(item)

    with Neo4jLoader() as loader:
        loader.clear_database()
        _insert(loader.insert_artist, artists, "artists")
        _insert(loader.insert_museum, museums, "museums")
        _insert(loader.insert_work, works_caravaggio, "Caravaggio works")
        _insert(loader.insert_work, works_caracciolo, "Caracciolo works")

    print("\n✅ Neo4j database populated successfully!")
