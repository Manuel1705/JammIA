"""Esecuzione delle query SPARQL su Wikidata, con cache locale dei risultati.

Le quattro query (`.psql`) vivono nella cartella `query/`; qui vengono caricate, eseguite
sull'endpoint di Wikidata con gestione del rate-limit, e i risultati grezzi salvati in cache
per non dover reinterrogare Wikidata (lento e soggetto a throttling) a ogni avvio.
"""
import json
import time
from typing import NamedTuple, Optional

from SPARQLWrapper import SPARQLWrapper, JSON

from chatbot import config


def carica_query(nome_file: str) -> str:
    """Legge il testo di una query SPARQL dalla cartella query/."""
    with open(config.QUERY_DIR / nome_file, "r", encoding="utf-8") as f:
        return f.read()


class SparqlExecutor:
    """Carica le query SPARQL, le esegue su Wikidata e mette in cache i risultati."""

    class Query(NamedTuple):
        """Testo SPARQL delle quattro query del progetto."""
        artisti: str
        opere_caravaggio: str
        opere_caracciolo: str
        musei: str

    class Risultati(NamedTuple):
        """Binding grezzi restituiti da Wikidata per ciascuna query."""
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

    def _esegui(self, query_sparql: str) -> list:
        sparql = SPARQLWrapper(config.SPARQL_ENDPOINT)
        sparql.addCustomHttpHeader("User-Agent", config.USER_AGENT)
        sparql.setTimeout(60)
        sparql.setQuery(query_sparql)
        sparql.setReturnFormat(JSON)

        for _ in range(self.max_retry):
            try:
                time.sleep(5)  # attesa fissa tra le query per non sovraccaricare Wikidata
                return sparql.query().convert()["results"]["bindings"]
            except Exception as e:
                # su rate-limit (HTTP 429) attende e riprova; su ogni altro errore si arrende
                if "429" in str(e):
                    print("   ⚠️  Rate limit! Attendo 5 secondi...")
                    time.sleep(5)
                else:
                    print(f" Errore: {e}")
                    return []
        return []

    def artisti(self) -> list:
        return self._esegui(self.query.artisti)

    def opere_caravaggio(self) -> list:
        return self._esegui(self.query.opere_caravaggio)

    def opere_caracciolo(self) -> list:
        return self._esegui(self.query.opere_caracciolo)

    def musei(self) -> list:
        return self._esegui(self.query.musei)

    def _salva_cache(self, risultati: "SparqlExecutor.Risultati") -> None:
        with open(config.CACHE_SPARQL, "w", encoding="utf-8") as f:
            json.dump(risultati._asdict(), f, ensure_ascii=False, indent=2)
        print(" Cache salvata!")

    def _carica_cache(self) -> Optional["SparqlExecutor.Risultati"]:
        if config.CACHE_SPARQL.exists():
            with open(config.CACHE_SPARQL, "r", encoding="utf-8") as f:
                print(" Cache trovata, carico dati locali...")
                return self.Risultati(**json.load(f))
        return None

    def esegui_tutte(self) -> "SparqlExecutor.Risultati":
        """Ritorna i risultati delle quattro query, dalla cache se presente, altrimenti
        interrogando Wikidata e salvando la cache per le esecuzioni successive."""
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
