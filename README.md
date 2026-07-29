# 🎨 JammIA

JammIA ("jamme jà" + IA) is a chatbot with a voice and text interface that acts as a Neapolitan guide to the works of Caravaggio and Battistello Caracciolo held in Naples and to the museums that display them. Project for the NLP course.

The architecture is documented in [`docs/architettura.pdf`](docs/architettura.pdf).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** to manage dependencies and the virtual environment (Python ≥ 3.14).
- **Neo4j** running locally (default `neo4j://127.0.0.1:7687`, user `neo4j`).
- An **LLM**: [Ollama](https://ollama.com) running locally (default) or a Google Gemini API key.

Install uv, if not already present:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 1. Dependencies

```bash
uv sync
```

Creates the virtual environment and installs everything needed. You don't need to activate it: just run commands with `uv run`.

## 2. Neo4j database

The app **requires** a running Neo4j instance: that is where the knowledge graph queried on every question lives. Two ways to get one.

### Option A — Neo4j Desktop (simplest)

Download [Neo4j Desktop](https://neo4j.com/download/), create a new local DBMS, set a password and start it. Then align the app's credentials (defaults are user `neo4j`, password `password`):

```bash
export NEO4J_PASSWORD=your-password
```

or add `NEO4J_PASSWORD=...` to the `.env` file.

### Option B — Docker

```bash
docker run -d --name neo4j-jammia \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

The web console is at <http://localhost:7474>, the bolt endpoint at `neo4j://127.0.0.1:7687` (the app defaults). To stop/restart it: `docker stop neo4j-jammia` / `docker start neo4j-jammia`.

> The database must be started **before** the population step and must stay up while the app is running.

## 3. LLM model

### Option A — Ollama locally (default)

Install Ollama from [ollama.com/download](https://ollama.com/download), then pull the model:

```bash
ollama pull gemma3n:e4b     # or: ollama pull gemma4:e4b
```

Make sure the server is up (Ollama starts on its own after installation; otherwise run `ollama serve`) and that the model answers:

```bash
ollama list
ollama run gemma3n:e4b "hello"
```

The model name used by the app is defined in `chatbot/config.py` (`LLM_MODEL`) and must **match the pulled tag**. If you pulled a different tag, set it via environment variable:

```bash
export LLM_MODEL=gemma3n:e4b
```

### Option B — Gemini via API

Get a key from [Google AI Studio](https://aistudio.google.com/apikey), then create the `.env` file in the project root from the template:

```bash
cp .env.example .env
```

and fill it in:

```
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-key
```

The `.env` file is in `.gitignore`: the key never ends up on git.

## 4. Populate the knowledge graph

Downloads the data from Wikidata/Wikipedia and builds the knowledge graph in Neo4j (the SPARQL results are already in `cache/`, so the first run is fast):

```bash
uv run python build_database.py
```

It also creates the full-text indexes used for fuzzy title search.

## 5. Run the app

```bash
uv run python app.py
```

The Gradio interface is reachable at <http://127.0.0.1:7860>; a temporary public link is also generated (`share=True` in `app.py`).

## Configuration

All variables are read from the environment or the `.env` file, with defaults in `chatbot/config.py`:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` (local) or `gemini` (API) |
| `LLM_MODEL` | `gemma4:e4b-mlx` on Apple Silicon, `gemma:e4b` elsewhere | Ollama model tag |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Model used with `LLM_PROVIDER=gemini` |
| `GOOGLE_API_KEY` | — | Required with `LLM_PROVIDER=gemini` |
| `NEO4J_URI` | `neo4j://127.0.0.1:7687` | Neo4j endpoint |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `password` | Neo4j credentials |

## Project structure

```
app.py                 launches the Gradio interface
build_database.py      populates the knowledge graph
chatbot/ingestion/     SPARQL queries, extraction, loading into Neo4j
chatbot/dialog/        LangGraph state graph, classification, prompts
chatbot/rag/           Text-to-Cypher RAG chain and prompts
chatbot/speech/        Whisper (STT) and gTTS (TTS)
chatbot/ui/            Gradio interface and session state
query/                 the four SPARQL queries
docs/                  technical architecture documentation
```
