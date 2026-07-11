"""Execution of SPARQL queries on Wikidata, with a local cache of the results.

The four queries (`.psql`) live in the `query/` folder; here they are loaded, executed against the
Wikidata endpoint with rate-limit handling, and the raw results are cached so Wikidata (slow and
subject to throttling) does not need to be queried again at every startup.
"""
import json
import time
from typing import NamedTuple, Optional

from SPARQLWrapper import SPARQLWrapper, JSON

from chatbot import config


def load_query(filename: str) -> str:
    """Read the text of a SPARQL query from the query/ folder."""
    with open(config.QUERY_DIR / filename, "r", encoding="utf-8") as f:
        return f.read()


class SparqlExecutor:
    """Loads the SPARQL queries, runs them against Wikidata and caches the results."""

    class Query(NamedTuple):
        """SPARQL text of the project's four queries."""
        artists: str
        works_caravaggio: str
        works_caracciolo: str
        museums: str

    class Results(NamedTuple):
        """Raw bindings returned by Wikidata for each query."""
        artists: list
        works_caravaggio: list
        works_caracciolo: list
        museums: list

    def __init__(self, max_retry: int = 5):
        self.query = self.Query(
            artists=load_query("query_artisti.psql"),
            works_caravaggio=load_query("query_opere_caravaggio.psql"),
            works_caracciolo=load_query("query_opere_caracciolo.psql"),
            museums=load_query("query_musei.psql"),
        )
        self.max_retry = max_retry

    def _execute(self, sparql_query: str) -> list:
        sparql = SPARQLWrapper(config.SPARQL_ENDPOINT)
        sparql.addCustomHttpHeader("User-Agent", config.USER_AGENT)
        sparql.setTimeout(60)
        sparql.setQuery(sparql_query)
        sparql.setReturnFormat(JSON)

        for _ in range(self.max_retry):
            try:
                time.sleep(5)  # fixed wait between queries to avoid overloading Wikidata
                return sparql.query().convert()["results"]["bindings"]
            except Exception as e:
                # on rate-limit (HTTP 429) wait and retry; on any other error give up
                if "429" in str(e):
                    print("   ⚠️  Rate limit! Waiting 5 seconds...")
                    time.sleep(5)
                else:
                    print(f" Error: {e}")
                    return []
        return []

    def artists(self) -> list:
        return self._execute(self.query.artists)

    def works_caravaggio(self) -> list:
        return self._execute(self.query.works_caravaggio)

    def works_caracciolo(self) -> list:
        return self._execute(self.query.works_caracciolo)

    def museums(self) -> list:
        return self._execute(self.query.museums)

    def _save_cache(self, results: "SparqlExecutor.Results") -> None:
        with open(config.CACHE_SPARQL, "w", encoding="utf-8") as f:
            json.dump(results._asdict(), f, ensure_ascii=False, indent=2)
        print(" Cache saved!")

    def _load_cache(self) -> Optional["SparqlExecutor.Results"]:
        if config.CACHE_SPARQL.exists():
            with open(config.CACHE_SPARQL, "r", encoding="utf-8") as f:
                print(" Cache found, loading local data...")
                return self.Results(**json.load(f))
        return None

    def execute_all(self) -> "SparqlExecutor.Results":
        """Return the results of the four queries, from cache if present, otherwise by querying
        Wikidata and saving the cache for subsequent runs."""
        cache = self._load_cache()
        if cache:
            return cache

        results = self.Results(
            artists=self.artists(),
            works_caravaggio=self.works_caravaggio(),
            works_caracciolo=self.works_caracciolo(),
            museums=self.museums(),
        )
        self._save_cache(results)
        return results
