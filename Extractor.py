import json
import urllib.parse
import urllib.request


class Extractor:
    # WIKI API utilizzato per ottenere le descrizioni dalle pagine Wiki dato che sia su DBpedia
    # che Wikidata alcune informazioni sono mancanti
    WIKI_API = "https://it.wikipedia.org/w/api.php"
    WIKI_HEADERS = {"User-Agent": "CaravaggioBot/1.0 (progetto universitario NLP)"}

    MOVIMENTI_DEFAULT = {
        "Q42207": "Barocco, Controriforma",
        "Q2519261": "Caravaggismo, Barocco napoletano"
    }

    @staticmethod
    def _valore(binding, chiave, default=""):
        """Estrae il campo 'value' di una variabile SPARQL dal binding, con default se assente."""
        return binding.get(chiave, {}).get("value", default)

    def descrizioni_wikipedia(self, nomi, batch=20, timeout=20):
        risultati = {}
        for i in range(0, len(nomi), batch):
            gruppo = nomi[i:i + batch]
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": 1,  # solo l'introduzione
                "explaintext": 1,  # testo semplice, no HTML
                "exlimit": "max",
                "redirects": 1,  # segui i redirect
                "titles": "|".join(gruppo),
            }
            url = self.WIKI_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=self.WIKI_HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    q = json.load(resp).get("query", {})
            except Exception as e:
                print(f"[Wikipedia] errore batch: {e}")
                continue

            # mappa titolo → estratto
            titolo2estratto = {
                p["title"]: p.get("extract", "")
                for p in q.get("pages", {}).values()
            }

            # gestisci normalizzazioni e redirect
            rimappa = {}
            for m in q.get("normalized", []):
                rimappa[m["from"]] = m["to"]
            for m in q.get("redirects", []):
                rimappa[m["from"]] = m["to"]

            for nome in gruppo:
                finale = rimappa.get(nome, nome)
                finale = rimappa.get(finale, finale)
                risultati[nome] = titolo2estratto.get(finale, "")

        return risultati

    # Estrazione ARTISTI
    def estrai_artisti(self, risultati):
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
                "opere_notevoli": self._valore(r, "opereNotevoli")
            })
        return artisti

    # Estrazione OPERE
    def estrai_opere(self, risultati, artista_id):
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
                "tipo": self._valore(r, "tipoLabel")
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

    # ESTRAZIONE MUSEI
    def estrai_musei(self, risultati):
        """Converte i risultati SPARQL in dizionari pronti per Neo4j"""
        musei = []
        for r in risultati:
            latitudine, longitudine = self._estrai_coordinate(self._valore(r, "coordinate"))

            fondazione = self._valore(r, "fondazione")
            if fondazione:
                fondazione = fondazione[:4]  # data ISO completa → solo anno

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
                "biglietto": self._valore(r, "fee")
            })
        return musei

    @staticmethod
    def _estrai_coordinate(coordinate):
        """Converte 'Point(lon lat)' (formato WKT di Wikidata) in (latitudine, longitudine)."""
        if not coordinate:
            return "", ""
        try:
            lon, lat = coordinate.replace("Point(", "").replace(")", "").split()
            return lat, lon
        except (ValueError, IndexError):
            return "", ""
