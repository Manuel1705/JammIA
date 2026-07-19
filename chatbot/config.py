"""Centralized project configuration.

All constants (credentials, model names, endpoints, file paths) live here, so they are not
duplicated across modules. Paths are computed from BASE_DIR (the repository root) rather than the
working directory: this way cache and queries always end up in the same location, regardless of
where the script is launched from.
"""
import os
from pathlib import Path

import torch
from dotenv import load_dotenv

# Repository root = the folder containing the `chatbot` package
BASE_DIR = Path(__file__).resolve().parent.parent

# Carica le variabili da un eventuale file .env nella root del repo (es. GOOGLE_API_KEY,
# LLM_PROVIDER): le variabili già presenti nell'ambiente hanno la precedenza.
load_dotenv(BASE_DIR / ".env")

# ── Neo4j ─────────────────────────────────────────────────────
# In a real project these credentials should be read from environment variables.
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# ── LLM ───────────────────────────────────────────────────────
# Provider selezionabile via env var: "ollama" (default, locale) oppure "gemini" (API Google).
# Per Gemini serve la variabile d'ambiente GOOGLE_API_KEY (letta dalla libreria).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e4b-mlx" if torch.backends.mps.is_available() else "gemma:e4b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
LLM_TEMPERATURE = 0.2


def make_llm(temperature: float):
    """Factory unica per i chat model: tutto il codice crea l'LLM da qui, così il cambio di
    provider non tocca RagChain/DialogManager. Import lazy per non richiedere la libreria
    del provider non usato."""
    if LLM_PROVIDER == "gemini":
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("LLM_PROVIDER=gemini ma GOOGLE_API_KEY non è impostata")
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=GEMINI_MODEL, temperature=temperature)
    if LLM_PROVIDER != "ollama":
        raise ValueError(f"LLM_PROVIDER sconosciuto: {LLM_PROVIDER!r} (usa 'ollama' o 'gemini')")
    from langchain_ollama import ChatOllama
    return ChatOllama(model=LLM_MODEL, temperature=temperature)

# ── Paths (relative to the repo root) ─────────────────────────
QUERY_DIR = BASE_DIR / "query"
CACHE_SPARQL = BASE_DIR / "cache/sparql_cache.json"
CACHE_WIKIPEDIA = BASE_DIR / "cache/wikipedia_cache.json"

# ── Wikidata (SPARQL) ─────────────────────────────────────────
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "CaravaggioBot/1.0 (progetto universitario NLP; manuelmignogna5@gmail.com)"

# ── Wikipedia (text descriptions) ─────────────────────────────
WIKI_API = "https://it.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "CaravaggioBot/1.0 (progetto universitario NLP)"}

# Wikidata QIDs of the two artists covered
CARAVAGGIO_ID = "Q42207"
CARACCIOLO_ID = "Q2519261"

# Fallback art movements, used when Wikidata does not return them for a given artist
DEFAULT_MOVEMENTS = {
    CARAVAGGIO_ID: "Barocco, Controriforma",
    CARACCIOLO_ID: "Caravaggismo, Barocco napoletano",
}

# ── Speech (recognition and synthesis) ────────────────────────
WHISPER_MODEL = "openai/whisper-large-v3"
TTS_LANG = "it"

# Pick the available accelerator: CUDA (Colab/NVIDIA), else MPS (Apple), else CPU
DEVICE = "cuda" if torch.cuda.is_available() \
    else "mps" if torch.backends.mps.is_available() \
    else "cpu"
