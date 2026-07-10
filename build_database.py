"""Entry point: build/repopulate the Neo4j database from Wikidata.

Usage:  uv run build_database.py
Warning: clears the existing graph before reinserting the data.
"""
from chatbot.ingestion.pipeline import populate_database

if __name__ == "__main__":
    populate_database()
