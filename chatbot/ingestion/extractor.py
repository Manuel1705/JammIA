import json
import time
import urllib.parse
import urllib.request
from typing import Any
from chatbot import config


class Extractor:
    """Parses SPARQL results and enriches them with data from Wikipedia APIs."""

    def __init__(self) -> None:
        self._wikipedia_cache = self._load_wikipedia_cache()

    @staticmethod
    def _load_wikipedia_cache() -> dict[str, str]:
        cache = config.CACHE_WIKIPEDIA
        if cache.exists():
            with open(cache, "r", encoding="utf-8") as f:
                print(" Wikipedia cache found, loading local data...")
                return json.load(f)
        return {}

    def _append_to_wikipedia_cache(self, cache: dict[str, str]) -> None:
        self._wikipedia_cache.update(cache)
        with open(config.CACHE_WIKIPEDIA, "w", encoding="utf-8") as f:
            json.dump(self._wikipedia_cache, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _get_key_value_from_binding(binding: dict[str, Any], key: str, default: str = "") -> str:
        return binding.get(key, {}).get("value", default)

    @staticmethod
    def _extract_wikidata_id_from_uri(uri: str) -> str:
        """Extracts the Q-ID from a full Wikidata URI (e.g. http://.../entity/Q42207 -> Q42207)."""
        return uri.split("/")[-1] if uri else ""

    def _get_wikipedia_descriptions_from_titles(self, titles: list[str], batch_size: int = 20, timeout: int = 20) -> \
            dict[str, str]:
        missing = [title for title in titles if title not in self._wikipedia_cache]
        if not missing:  # return immediately if all is cached
            return {title: self._wikipedia_cache[title] for title in titles}

        # Retrieve missing titles from Wikipedia in batches and save to cache
        for i in range(0, len(missing), batch_size):
            group = missing[i: i + batch_size]
            batch = self._fetch_batch_from_wikipedia(group, timeout)
            self._append_to_wikipedia_cache(batch)

        return {title: self._wikipedia_cache.get(title, "") for title in titles}

    @staticmethod
    def _fetch_batch_from_wikipedia(titles: list[str], timeout: int) -> dict[str, str]:
        """Query Wikipedia IT for one batch of titles and return {{requested_title}: extracted description intro}."""
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": 1,  # Intro only
            "explaintext": 1,  # Plain text, no HTML
            "exlimit": "max",
            "redirects": 1,  # Follow redirects
            "titles": "|".join(titles),
        }
        url = config.WIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=config.WIKI_HEADERS)

        time.sleep(1)  # Throttling to respect Wikipedia's rate limits
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                query = json.load(resp).get("query", {})
        except Exception as e:
            print(f"[Wikipedia] batch error: {e}")
            return {}

        extract_by_title = {p["title"]: p.get("extract", "") for p in query.get("pages", {}).values()}

        # Wikipedia may normalize and/or redirect the requested titles.
        # Map requested -> actual title.
        remap = {}
        for m in query.get("normalized", []) + query.get("redirects", []):
            remap[m["from"]] = m["to"]

        result = {}
        for title in titles:
            # Resolve possible double redirect/normalization
            actual = remap.get(title, title)
            actual = remap.get(actual, actual)
            result[title] = extract_by_title.get(actual, "")

        return result

    def extract_artists(self, results: list[dict[str, Any]]) -> list[dict[str, str]]:
        artists = []
        for r in results:
            qid = self._extract_wikidata_id_from_uri(self._get_key_value_from_binding(r, "artista"))
            movements = self._get_key_value_from_binding(r, "movimenti") or config.DEFAULT_MOVEMENTS.get(qid, "")

            artists.append({
                "wikidata_id": qid,
                "name": self._get_key_value_from_binding(r, "nome", "N/D"),
                "birth_date": self._get_key_value_from_binding(r, "dataNascita")[:10],
                "birth_place": self._get_key_value_from_binding(r, "luogoNascitaLabel"),
                "movements": movements,
                "notable_works": self._get_key_value_from_binding(r, "opereNotevoli"),
            })
        return artists

    def extract_works(self, results: list[dict[str, Any]], artist_id: str) -> list[dict[str, str]]:
        works = []
        for r in results:
            year_raw = self._get_key_value_from_binding(r, "anno")

            works.append({
                "wikidata_id": self._extract_wikidata_id_from_uri(self._get_key_value_from_binding(r, "opera")),
                "title": self._get_key_value_from_binding(r, "nome", "N/D"),
                "year": year_raw[:4] if year_raw else "",
                "height": self._get_key_value_from_binding(r, "altezza"),
                "width": self._get_key_value_from_binding(r, "larghezza"),
                "technique": self._get_key_value_from_binding(r, "tecnica"),
                "subjects": self._get_key_value_from_binding(r, "soggetti"),
                "museum_name": self._get_key_value_from_binding(r, "museoNome"),
                "museum_id": self._extract_wikidata_id_from_uri(self._get_key_value_from_binding(r, "museo")),
                "artist_id": artist_id,
                "description": self._get_key_value_from_binding(r, "descrizione"),
                "type": self._get_key_value_from_binding(r, "tipoLabel"),
            })

        # Enrich with Wikipedia descriptions
        titles = [w["title"] for w in works]
        wiki_descriptions = self._get_wikipedia_descriptions_from_titles(titles)

        for work in works:
            # Wikipedia description (more discursive) takes priority over Wikidata description
            extract = wiki_descriptions.get(work["title"], "")
            if extract:
                work["description"] = extract

        return works

    def extract_museums(self, results: list[dict[str, Any]]) -> list[dict[str, str]]:
        museums = []
        for r in results:
            latitude, longitude = self._extract_coordinates(self._get_key_value_from_binding(r, "coordinate"))
            founded = self._get_key_value_from_binding(r, "fondazione")

            if founded:
                founded = founded[:4]  # Full ISO date → year only

            museums.append({
                "wikidata_id": self._extract_wikidata_id_from_uri(self._get_key_value_from_binding(r, "museo")),
                "name": self._get_key_value_from_binding(r, "nomeMuseo", "N/D"),
                "description": self._get_key_value_from_binding(r, "descrizione"),
                "address": self._get_key_value_from_binding(r, "indirizzo"),
                "website": self._get_key_value_from_binding(r, "sito"),
                "phone": self._get_key_value_from_binding(r, "telefono"),
                "founded": founded,
                "latitude": latitude,
                "longitude": longitude,
                "city": self._get_key_value_from_binding(r, "citta"),
                "ticket": self._get_key_value_from_binding(r, "fee"),
            })
        return museums

    @staticmethod
    def _extract_coordinates(coordinates: str) -> tuple[str, str]:
        """
        Converts 'Point(lon lat)' (Wikidata WKT format) into (latitude, longitude).
        Note: WKT order is lon-lat, so they are returned swapped.
        """
        if not coordinates:
            return "", ""
        try:
            lon, lat = coordinates.replace("Point(", "").replace(")", "").split()
            return lat, lon
        except (ValueError, IndexError):
            return "", ""
