"""Configurazione centralizzata del progetto.

Tutte le costanti (credenziali, nomi dei modelli, endpoint, percorsi di file) vivono qui,
così da non essere duplicate nei vari moduli. I percorsi sono calcolati a partire da BASE_DIR
(la radice del repository) e non dalla working directory: in questo modo cache, query e database
SQLite finiscono sempre nella stessa posizione, indipendentemente da dove viene lanciato lo script.
"""
import os
from pathlib import Path

# Radice del repository = cartella che contiene il package `chatbot`
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Neo4j ─────────────────────────────────────────────────────
# Per un progetto reale queste credenziali andrebbero lette da variabili d'ambiente.
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ── Modello LLM (Ollama) ──────────────────────────────────────
MODELLO_LLM = os.getenv("MODELLO_LLM", "gemma4:e4b")
LLM_TEMPERATURE = 0.1

# ── Percorsi (relativi alla radice del repo) ──────────────────
QUERY_DIR = BASE_DIR / "query"
CACHE_SPARQL = BASE_DIR / "cache_sparql.json"
CACHE_WIKIPEDIA = BASE_DIR / "cache_wikipedia.json"
DIALOG_DB = BASE_DIR / "dialog_state.sqlite"

# ── Wikidata (SPARQL) ─────────────────────────────────────────
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "CaravaggioBot/1.0 (progetto universitario NLP; tuaemail@esempio.com)"

# ── Wikipedia (descrizioni testuali) ──────────────────────────
WIKI_API = "https://it.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "CaravaggioBot/1.0 (progetto universitario NLP)"}

# ── Speech (riconoscimento e sintesi vocale) ──────────────────
WHISPER_MODEL = "openai/whisper-large-v3"
SAMPLE_RATE = 16000  # frequenza attesa da Whisper
TTS_LANG = "it"
TTS_VELOCITA = 1.3  # velocità di riproduzione della risposta (afplay -r)
