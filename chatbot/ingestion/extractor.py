"""Transformation of the SPARQL bindings into dictionaries ready for Neo4j.

Besides normalizing the fields (URI -> QID, ISO dates -> year, WKT coordinates -> lat/lon), it
enriches the works with the introductory descriptions from Wikipedia (often missing on Wikidata),
caching the responses so Wikipedia is not queried again at every run.

Note: the second argument of `_value` (e.g. "artista", "nomeMuseo") is the SPARQL variable name
defined in the `.psql` queries, so it is kept in Italian; only the output dictionary keys are English.
"""
import json
import time
import urllib.parse
import urllib.request

from chatbot import config


class Extractor:
    # fallback art movements, used when Wikidata does not return them for a given artist
    DEFAULT_MOVEMENTS = {
        "Q42207": "Barocco, Controriforma",
        "Q2519261": "Caravaggismo, Barocco napoletano",
    }

    def __init__(self):
        self._wikipedia_cache = self._load_cache()

    def _load_cache(self) -> dict:
        if config.CACHE_WIKIPEDIA.exists():
            with open(config.CACHE_WIKIPEDIA, "r", encoding="utf-8") as f:
                print(" Wikipedia cache found, loading local data...")
                return json.load(f)
        return {}

    def _save_cache(self) -> None:
        with open(config.CACHE_WIKIPEDIA, "w", encoding="utf-8") as f:
            json.dump(self._wikipedia_cache, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _value(binding: dict, key: str, default: str = "") -> str:
        """Extract the 'value' field of a SPARQL variable from the binding, with a default if absent."""
        return binding.get(key, {}).get("value", default)

    def wikipedia_descriptions(self, names: list, batch: int = 20, timeout: int = 20) -> dict:
        """Return {title: intro extract from Wikipedia IT}, using the cache where possible.
        Only queries the titles not yet in cache, in groups of `batch` (MediaWiki API limit).
        """
        missing = [name for name in names if name not in self._wikipedia_cache]

        if not missing:
            print(" Descriptions already in cache, no call to Wikipedia.")
            return {name: self._wikipedia_cache[name] for name in names}

        for i in range(0, len(missing), batch):
            group = missing[i:i + batch]
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": 1,       # intro only
                "explaintext": 1,   # plain text, no HTML
                "exlimit": "max",
                "redirects": 1,     # follow redirects
                "titles": "|".join(group),
            }
            url = config.WIKI_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=config.WIKI_HEADERS)

            time.sleep(1)  # throttling, to avoid Wikipedia's rate limit
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    q = json.load(resp).get("query", {})
            except Exception as e:
                # a single attempt per batch: failed titles stay out of the cache
                # and will be retried automatically on the next run
                print(f"[Wikipedia] batch error: {e}")
                continue

            title2extract = {
                p["title"]: p.get("extract", "")
                for p in q.get("pages", {}).values()
            }

            # the API may normalize or redirect the requested titles: rebuild the map
            # requested-title -> actual-title to find the right extract
            remap = {}
            for m in q.get("normalized", []):
                remap[m["from"]] = m["to"]
            for m in q.get("redirects", []):
                remap[m["from"]] = m["to"]

            for name in group:
                final = remap.get(name, name)
                final = remap.get(final, final)
                self._wikipedia_cache[name] = title2extract.get(final, "")

            self._save_cache()  # save immediately: if a later batch fails, this one is not lost

        return {name: self._wikipedia_cache.get(name, "") for name in names}

    def extract_artists(self, results: list) -> list:
        artists = []
        for r in results:
            qid = self._value(r, "artista").split("/")[-1]
            movements = self._value(r, "movimenti") or self.DEFAULT_MOVEMENTS.get(qid, "")

            artists.append({
                "wikidata_id": qid,
                "name": self._value(r, "nome", "N/D"),
                "birth_date": self._value(r, "dataNascita")[:10],
                "birth_place": self._value(r, "luogoNascitaLabel"),
                "movements": movements,
                "notable_works": self._value(r, "opereNotevoli"),
            })
        return artists

    def extract_works(self, results: list, artist_id: str) -> list:
        works = []
        for r in results:
            museum_uri = self._value(r, "museo")
            year_raw = self._value(r, "anno")

            works.append({
                "wikidata_id": self._value(r, "opera").split("/")[-1],
                "title": self._value(r, "nome", "N/D"),
                "year": year_raw[:4] if year_raw else "",
                "height": self._value(r, "altezza"),
                "width": self._value(r, "larghezza"),
                "technique": self._value(r, "tecnica"),
                "subjects": self._value(r, "soggetti"),
                "museum_name": self._value(r, "museoNome"),
                "museum_id": museum_uri.split("/")[-1] if museum_uri else "",
                "artist_id": artist_id,
                "description": self._value(r, "descrizione"),
                "type": self._value(r, "tipoLabel"),
            })

        titles = [w["title"] for w in works]
        wiki_descriptions = self.wikipedia_descriptions(titles)
        for work in works:
            # the Wikipedia description, more discursive, takes priority over the SPARQL one;
            # if Wikipedia does not have it, the one already taken from Wikidata is kept
            extract = wiki_descriptions.get(work["title"], "")
            if extract:
                work["description"] = extract

        return works

    def extract_museums(self, results: list) -> list:
        museums = []
        for r in results:
            latitude, longitude = self._extract_coordinates(self._value(r, "coordinate"))

            founded = self._value(r, "fondazione")
            if founded:
                founded = founded[:4]  # full ISO date → year only

            museums.append({
                "wikidata_id": self._value(r, "museo").split("/")[-1],
                "name": self._value(r, "nomeMuseo", "N/D"),
                "description": self._value(r, "descrizione"),
                "address": self._value(r, "indirizzo"),
                "website": self._value(r, "sito"),
                "phone": self._value(r, "telefono"),
                "founded": founded,
                "latitude": latitude,
                "longitude": longitude,
                "city": self._value(r, "citta"),
                "ticket": self._value(r, "fee"),
            })
        return museums

    @staticmethod
    def _extract_coordinates(coordinates: str):
        """Convert 'Point(lon lat)' (Wikidata WKT format) into (latitude, longitude).
        In WKT the order is lon-lat, so they are returned swapped."""
        if not coordinates:
            return "", ""
        try:
            lon, lat = coordinates.replace("Point(", "").replace(")", "").split()
            return lat, lon
        except (ValueError, IndexError):
            return "", ""
