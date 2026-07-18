import json
import time
from typing import NamedTuple, Optional, cast
from SPARQLWrapper import SPARQLWrapper, JSON
from chatbot import config


class SparqlExecutor:
    """Loads the SPARQL queries, runs them against Wikidata and caches the results."""

    class Query(NamedTuple):
        artists: str
        works_caravaggio: str
        works_caracciolo: str
        museums: str

    class Results(NamedTuple):
        artists: list
        works_caravaggio: list
        works_caracciolo: list
        museums: list

    def __init__(self):
        self._sparql = SPARQLWrapper(config.SPARQL_ENDPOINT)
        self._query = self.Query(
            artists=self._load_query_from_file("query_artisti.psql"),
            works_caravaggio=self._load_query_from_file("query_opere_caravaggio.psql"),
            works_caracciolo=self._load_query_from_file("query_opere_caracciolo.psql"),
            museums=self._load_query_from_file("query_musei.psql"),
        )

    @staticmethod
    def _load_query_from_file(filename: str) -> str:
        return (config.QUERY_DIR / filename).read_text(encoding="utf-8")

    @staticmethod
    def _save_cache(results: Results) -> None:
        config.CACHE_SPARQL.parent.mkdir(parents=True, exist_ok=True)
        with open(config.CACHE_SPARQL, "w", encoding="utf-8") as f:
            json.dump(results._asdict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def _load_cache() -> Optional[Results]:
        if config.CACHE_SPARQL.exists():
            with open(config.CACHE_SPARQL, "r", encoding="utf-8") as f:
                print("\nCache found!!")
                return SparqlExecutor.Results(**json.load(f))
        return None

    def _execute_query(self, sparql_query: str, max_retry: int = 5) -> list:
        """Fail LOUDLY: se una query fallisce, l'eccezione risale invece di restituire [] in
        silenzio — altrimenti il risultato vuoto finirebbe in cache mascherando per sempre
        l'errore. Il retry vale solo per il rate limit (HTTP 429)."""
        sparql = self._sparql
        sparql.addCustomHttpHeader("User-Agent", config.USER_AGENT)
        sparql.setTimeout(60)
        sparql.setQuery(sparql_query)
        sparql.setReturnFormat(JSON)

        last_error: Exception | None = None
        for _ in range(max_retry):
            try:
                result = cast(dict, sparql.query().convert())
                return result["results"]["bindings"]
            except Exception as e:
                if "429" not in str(e):  # errore non transiente: inutile ritentare
                    raise RuntimeError(f"Query SPARQL fallita: {e}") from e
                last_error = e
                print("\n ⚠️ Rate limit! Waiting 5 seconds...")
                time.sleep(5)
        raise RuntimeError(f"Rate limit persistente dopo {max_retry} tentativi") from last_error

    def execute_all(self) -> Results:
        if cache := self._load_cache():
            return cache

        results = self.Results(
            artists=self._execute_query(self._query.artists),
            works_caravaggio=self._execute_query(self._query.works_caravaggio),
            works_caracciolo=self._execute_query(self._query.works_caracciolo),
            museums=self._execute_query(self._query.museums),
        )
        self._save_cache(results)
        return results
