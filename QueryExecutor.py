import json
import os
import time
from typing import NamedTuple, Optional

from SPARQLWrapper import SPARQLWrapper, JSON

QUERY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "query")


def carica_query(nome_file):
    with open(os.path.join(QUERY_DIR, nome_file), "r", encoding="utf-8") as f:
        return f.read()


class QueryExecutor:
    ENDPOINT = "https://query.wikidata.org/sparql"
    USER_AGENT = "CaravaggioBot/1.0 (progetto universitario NLP; tuaemail@esempio.com)"
    CACHE_FILE = "cache_sparql.json"

    class Query(NamedTuple):
        artisti: str
        opere_caravaggio: str
        opere_caracciolo: str
        musei: str

    class Risultati(NamedTuple):
        artisti: list
        opere_caravaggio: list
        opere_caracciolo: list
        musei: list

    def __init__(self, max_retry: int = 5):
        self.query = self.Query(
            artisti=carica_query("query_artisti.psql"),
            opere_caravaggio=carica_query("query_opere_caravaggio.psql"),
            opere_caracciolo=carica_query("query_opere_caracciolo.psql"),
            musei=carica_query("query_musei.psql"),
        )
        self.max_retry = max_retry

    def _esegui(self, query_sparql):
        sparql = SPARQLWrapper(self.ENDPOINT)
        sparql.addCustomHttpHeader("User-Agent", self.USER_AGENT)
        sparql.setTimeout(60)
        sparql.setQuery(query_sparql)
        sparql.setReturnFormat(JSON)

        for tentativo in range(self.max_retry):
            try:
                time.sleep(5)  # aspetta sempre 5 secondi tra le query
                return sparql.query().convert()["results"]["bindings"]
            except Exception as e:
                if "429" in str(e):
                    print(f"   ⚠️  Rate limit! Attendo 5 secondi...")
                    time.sleep(5)
                else:
                    print(f" Errore: {e}")
                    return []
        return []

    def artisti(self):
        return self._esegui(self.query.artisti)

    def opere_caravaggio(self):
        return self._esegui(self.query.opere_caravaggio)

    def opere_caracciolo(self):
        return self._esegui(self.query.opere_caracciolo)

    def musei(self):
        return self._esegui(self.query.musei)

    def _salva_cache(self, risultati: "QueryExecutor.Risultati") -> None:
        with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(risultati._asdict(), f, ensure_ascii=False, indent=2)
        print(" Cache salvata!")

    def _carica_cache(self) -> Optional["QueryExecutor.Risultati"]:
        if os.path.exists(self.CACHE_FILE):
            with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                print(" Cache trovata, carico dati locali...")
                return self.Risultati(**json.load(f))
        return None

    def esegui_tutte(self) -> "QueryExecutor.Risultati":
        cache = self._carica_cache()
        if cache:
            return cache

        risultati = self.Risultati(
            artisti=self.artisti(),
            opere_caravaggio=self.opere_caravaggio(),
            opere_caracciolo=self.opere_caracciolo(),
            musei=self.musei(),
        )
        self._salva_cache(risultati)
        return risultati
