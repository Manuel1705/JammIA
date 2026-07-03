"""Trasformazione dei binding SPARQL in dizionari pronti per Neo4j.

Oltre a normalizzare i campi (URI -> QID, date ISO -> anno, coordinate WKT -> lat/lon), arricchisce
le opere con le descrizioni introduttive di Wikipedia (che su Wikidata spesso mancano), tenendo in
cache le risposte per non reinterrogare Wikipedia a ogni esecuzione.
"""
import json
import time
import urllib.parse
import urllib.request

from chatbot import config


class Extractor:
    # movimenti artistici di fallback, usati se Wikidata non li restituisce per un dato artista
    MOVIMENTI_DEFAULT = {
        "Q42207": "Barocco, Controriforma",
        "Q2519261": "Caravaggismo, Barocco napoletano",
    }

    def __init__(self):
        self._cache_wikipedia = self._carica_cache()

    def _carica_cache(self) -> dict:
        if config.CACHE_WIKIPEDIA.exists():
            with open(config.CACHE_WIKIPEDIA, "r", encoding="utf-8") as f:
                print(" Cache Wikipedia trovata, carico dati locali...")
                return json.load(f)
        return {}

    def _salva_cache(self) -> None:
        with open(config.CACHE_WIKIPEDIA, "w", encoding="utf-8") as f:
            json.dump(self._cache_wikipedia, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _valore(binding: dict, chiave: str, default: str = "") -> str:
        """Estrae il campo 'value' di una variabile SPARQL dal binding, con default se assente."""
        return binding.get(chiave, {}).get("value", default)

    def descrizioni_wikipedia(self, nomi: list, batch: int = 20, timeout: int = 20) -> dict:
        """Ritorna {titolo: estratto introduttivo da Wikipedia IT}, usando la cache dove possibile.
        Interroga solo i titoli non ancora in cache, a gruppi di `batch` (limite dell'API MediaWiki).
        """
        mancanti = [nome for nome in nomi if nome not in self._cache_wikipedia]

        if not mancanti:
            print(" Descrizioni già in cache, nessuna chiamata a Wikipedia.")
            return {nome: self._cache_wikipedia[nome] for nome in nomi}

        for i in range(0, len(mancanti), batch):
            gruppo = mancanti[i:i + batch]
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": 1,       # solo l'introduzione
                "explaintext": 1,   # testo semplice, no HTML
                "exlimit": "max",
                "redirects": 1,     # segui i redirect
                "titles": "|".join(gruppo),
            }
            url = config.WIKI_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=config.WIKI_HEADERS)

            time.sleep(1)  # throttling, per non incorrere nel rate limit di Wikipedia
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    q = json.load(resp).get("query", {})
            except Exception as e:
                # un solo tentativo per batch: i titoli falliti restano fuori dalla cache
                # e verranno ritentati automaticamente alla prossima esecuzione
                print(f"[Wikipedia] errore batch: {e}")
                continue

            titolo2estratto = {
                p["title"]: p.get("extract", "")
                for p in q.get("pages", {}).values()
            }

            # l'API può normalizzare o redirigere i titoli richiesti: ricostruisco la mappa
            # titolo-richiesto -> titolo-effettivo per ritrovare l'estratto giusto
            rimappa = {}
            for m in q.get("normalized", []):
                rimappa[m["from"]] = m["to"]
            for m in q.get("redirects", []):
                rimappa[m["from"]] = m["to"]

            for nome in gruppo:
                finale = rimappa.get(nome, nome)
                finale = rimappa.get(finale, finale)
                self._cache_wikipedia[nome] = titolo2estratto.get(finale, "")

            self._salva_cache()  # salvo subito: se un batch successivo fallisce, questo non si perde

        return {nome: self._cache_wikipedia.get(nome, "") for nome in nomi}

    def estrai_artisti(self, risultati: list) -> list:
        artisti = []
        for r in risultati:
            qid = self._valore(r, "artista").split("/")[-1]
            movimenti = self._valore(r, "movimenti") or self.MOVIMENTI_DEFAULT.get(qid, "")

            artisti.append({
                "wikidata_id": qid,
                "nome": self._valore(r, "nome", "N/D"),
                "data_nascita": self._valore(r, "dataNascita")[:10],
                "luogo_nascita": self._valore(r, "luogoNascitaLabel"),
                "movimenti": movimenti,
                "opere_notevoli": self._valore(r, "opereNotevoli"),
            })
        return artisti

    def estrai_opere(self, risultati: list, artista_id: str) -> list:
        opere = []
        for r in risultati:
            museo_uri = self._valore(r, "museo")
            anno_raw = self._valore(r, "anno")

            opere.append({
                "wikidata_id": self._valore(r, "opera").split("/")[-1],
                "titolo": self._valore(r, "nome", "N/D"),
                "anno": anno_raw[:4] if anno_raw else "",
                "altezza": self._valore(r, "altezza"),
                "larghezza": self._valore(r, "larghezza"),
                "tecnica": self._valore(r, "tecnica"),
                "soggetti": self._valore(r, "soggetti"),
                "museo_nome": self._valore(r, "museoNome"),
                "museo_id": museo_uri.split("/")[-1] if museo_uri else "",
                "artista_id": artista_id,
                "descrizione": self._valore(r, "descrizione"),
                "tipo": self._valore(r, "tipoLabel"),
            })

        titoli = [o["titolo"] for o in opere]
        descrizioni_wiki = self.descrizioni_wikipedia(titoli)
        for opera in opere:
            # la descrizione Wikipedia, più discorsiva, ha priorità su quella SPARQL;
            # se Wikipedia non la trova si mantiene quella già presa da Wikidata
            estratto = descrizioni_wiki.get(opera["titolo"], "")
            if estratto:
                opera["descrizione"] = estratto

        return opere

    def estrai_musei(self, risultati: list) -> list:
        musei = []
        for r in risultati:
            latitudine, longitudine = self._estrai_coordinate(self._valore(r, "coordinate"))

            fondazione = self._valore(r, "fondazione")
            if fondazione:
                fondazione = fondazione[:4]  # data ISO completa → solo l'anno

            musei.append({
                "wikidata_id": self._valore(r, "museo").split("/")[-1],
                "nome": self._valore(r, "nomeMuseo", "N/D"),
                "descrizione": self._valore(r, "descrizione"),
                "indirizzo": self._valore(r, "indirizzo"),
                "sito": self._valore(r, "sito"),
                "telefono": self._valore(r, "telefono"),
                "fondazione": fondazione,
                "latitudine": latitudine,
                "longitudine": longitudine,
                "citta": self._valore(r, "citta"),
                "biglietto": self._valore(r, "fee"),
            })
        return musei

    @staticmethod
    def _estrai_coordinate(coordinate: str):
        """Converte 'Point(lon lat)' (formato WKT di Wikidata) in (latitudine, longitudine).
        Nel WKT l'ordine è lon-lat, quindi vengono restituiti invertiti."""
        if not coordinate:
            return "", ""
        try:
            lon, lat = coordinate.replace("Point(", "").replace(")", "").split()
            return lat, lon
        except (ValueError, IndexError):
            return "", ""
