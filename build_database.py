"""Entry point: costruisce/ripopola il database Neo4j a partire da Wikidata.

Uso:  uv run build_database.py
Attenzione: svuota il grafo esistente prima di reinserire i dati.
"""
from chatbot.ingestion.pipeline import popola_database

if __name__ == "__main__":
    popola_database()
