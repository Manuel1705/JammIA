#Bisogna prelevare sia le opere di Caravaggio che di Battistello Caracciolo visitabili a Napoli.
#Sono richieste conoscenze di base come il nome dell'opera, il nome del museo e il luogo, la data di creazione
#Le informazioni dovrebbero essere relative sia all'opera che al museo stesso.

from SPARQLWrapper import SPARQLWrapper, JSON
import time
import json
import urllib.parse
import urllib.request
import os

# Query sugli ARTISTI: vengono prelevati Nome, Data di Nascita, Luogo di Nascita,
# movimento Artistico, Opere Note, numero di Opere create, numero di opere presenti a Napoli
query_artisti="""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?artista ?nome (MIN(?nascita) AS ?dataNascita) ?luogoNascitaLabel
       (GROUP_CONCAT(DISTINCT ?movimentoLabel; SEPARATOR=", ") AS ?movimenti)
       (GROUP_CONCAT(DISTINCT ?operaNotevoleLabel; SEPARATOR=", ") AS ?opereNotevoli)
WHERE {
    VALUES ?artista { wd:Q42207 wd:Q2519261 }

    ?artista rdfs:label ?nome .
    FILTER(lang(?nome) = "it")

    OPTIONAL { ?artista wdt:P569 ?nascita . }
    OPTIONAL {
        ?artista wdt:P19 ?luogoNascita .
        ?luogoNascita rdfs:label ?luogoNascitaLabel .
        FILTER(lang(?luogoNascitaLabel) = "it")
    }
    OPTIONAL {
        { ?artista wdt:P135 ?movimento . }
        UNION
        { ?artista wdt:P136 ?movimento . }
        ?movimento rdfs:label ?movimentoLabel .
        FILTER(lang(?movimentoLabel) = "it")
    }
    OPTIONAL {
        ?artista wdt:P800 ?operaNotevole .
        ?operaNotevole rdfs:label ?operaNotevoleLabel .
        FILTER(lang(?operaNotevoleLabel) = "it")
    }
}
GROUP BY ?artista ?nome ?luogoNascitaLabel
"""

# Query OPERE CARAVAGGIO, tutte indipendentemente da se sono a Napoli o meno. Il filtro lo applichiamo poi su Neo4j.
query_opere_caravaggio= """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?opera ?museo ?nome ?descrizione ?anno
       ?altezza ?larghezza ?tecnica ?museoNome ?tipoLabel
       (GROUP_CONCAT(DISTINCT ?depictsNome; SEPARATOR=", ") AS ?soggetti)
WHERE {
    ?opera wdt:P170 wd:Q42207 .

    VALUES ?tipo {
        wd:Q3305213   # dipinto
        wd:Q15727816  # serie di dipinti
        wd:Q18573970  # gruppo di dipinti
        wd:Q93184     # disegno
        wd:Q848330    # tondo
    }
    ?opera wdt:P31 ?tipo .
    ?tipo rdfs:label ?tipoLabel .
    FILTER(lang(?tipoLabel) = "it")

    OPTIONAL { ?opera rdfs:label ?nomeIT . FILTER(lang(?nomeIT) = "it") }
    OPTIONAL { ?opera rdfs:label ?nomeEN . FILTER(lang(?nomeEN) = "en") }
    BIND(COALESCE(?nomeIT, ?nomeEN, "N/D") AS ?nome)

    OPTIONAL {
        ?opera schema:description ?descrizione .
        FILTER(lang(?descrizione) = "it")
    }
    OPTIONAL { ?opera wdt:P571 ?anno . }
    OPTIONAL { ?opera wdt:P2048 ?altezza . }
    OPTIONAL { ?opera wdt:P2049 ?larghezza . }
    OPTIONAL {
        ?opera wdt:P186 ?mat .
        ?mat rdfs:label ?tecnica .
        FILTER(lang(?tecnica) = "it")
    }
    OPTIONAL {
        ?opera wdt:P276 ?museo .
        ?museo rdfs:label ?museoNome .
        FILTER(lang(?museoNome) = "it")
    }
    OPTIONAL {
        ?opera wdt:P180 ?depicts .
        ?depicts rdfs:label ?depictsNome .
        FILTER(lang(?depictsNome) = "it")
    }
}
GROUP BY ?opera ?museo ?nome ?descrizione ?anno ?altezza ?larghezza ?tecnica ?museoNome ?tipoLabel
"""
# Query OPERE CARACCIOLO, come prima sono tutte non solo quelle di Napoli
query_opere_caracciolo="""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?opera ?museo ?nome ?descrizione ?anno
       ?altezza ?larghezza ?tecnica ?museoNome ?tipoLabel
       (GROUP_CONCAT(DISTINCT ?depictsNome; SEPARATOR=", ") AS ?soggetti)
WHERE {
    ?opera wdt:P170 wd:Q2519261 .

    # Includi dipinti, disegni e cicli di dipinti
    VALUES ?tipo {
        wd:Q3305213   # dipinto
        wd:Q93184     # disegno
        wd:Q1278452   # ciclo di dipinti
    }
    ?opera wdt:P31 ?tipo .
    ?tipo rdfs:label ?tipoLabel .
    FILTER(lang(?tipoLabel) = "it")

    OPTIONAL { ?opera rdfs:label ?nomeIT . FILTER(lang(?nomeIT) = "it") }
    OPTIONAL { ?opera rdfs:label ?nomeEN . FILTER(lang(?nomeEN) = "en") }
    BIND(COALESCE(?nomeIT, ?nomeEN, "N/D") AS ?nome)

    OPTIONAL {
        ?opera schema:description ?descrizione .
        FILTER(lang(?descrizione) = "it")
    }
    OPTIONAL { ?opera wdt:P571 ?anno . }
    OPTIONAL { ?opera wdt:P2048 ?altezza . }
    OPTIONAL { ?opera wdt:P2049 ?larghezza . }
    OPTIONAL {
        ?opera wdt:P186 ?mat .
        ?mat rdfs:label ?tecnica .
        FILTER(lang(?tecnica) = "it")
    }
    OPTIONAL {
        ?opera wdt:P276 ?museo .
        ?museo rdfs:label ?museoNome .
        FILTER(lang(?museoNome) = "it")
    }
    OPTIONAL {
        ?opera wdt:P180 ?depicts .
        ?depicts rdfs:label ?depictsNome .
        FILTER(lang(?depictsNome) = "it")
    }
}
GROUP BY ?opera ?museo ?nome ?descrizione ?anno ?altezza ?larghezza ?tecnica ?museoNome ?tipoLabel
"""
# Query MUSEI, sono le info su tutti i musei in cui ci sono le opere di Caravaggio e Caracciolo. Per quelle di Napoli filtriamo sul db
query_musei= """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>

SELECT DISTINCT ?museo ?nomeMuseo
       (SAMPLE(?descrizione) AS ?descrizione)
       (SAMPLE(?indirizzo)   AS ?indirizzo)
       (SAMPLE(?sito)        AS ?sito)
       (SAMPLE(?telefono)    AS ?telefono)
       (SAMPLE(?fondazione)  AS ?fondazione)
       (SAMPLE(?coordinate)  AS ?coordinate)
       (SAMPLE(?cittaNome)   AS ?citta)
       (SAMPLE(?fee)         AS ?fee)
WHERE {
    {   ?opera wdt:P170 wd:Q42207 .
        ?opera wdt:P276 ?museo . }
    UNION
    {   ?opera wdt:P170 wd:Q2519261 .
        ?opera wdt:P276 ?museo . }

    ?museo rdfs:label ?nomeMuseo .
    FILTER(lang(?nomeMuseo) = "it")

    OPTIONAL {
        ?museo schema:description ?descrizione .
        FILTER(lang(?descrizione) = "it")
    }
    OPTIONAL { ?museo wdt:P6375 ?indirizzoIT . FILTER(lang(?indirizzoIT) = "it") }
    OPTIONAL { ?museo wdt:P6375 ?indirizzoEN . FILTER(lang(?indirizzoEN) = "en") }
    OPTIONAL { ?museo wdt:P969  ?indirizzoIT2 . FILTER(lang(?indirizzoIT2) = "it") }
    BIND(COALESCE(?indirizzoIT, ?indirizzoIT2, ?indirizzoEN, "") AS ?indirizzo)

    OPTIONAL { ?museo wdt:P856 ?sito .      }
    OPTIONAL { ?museo wdt:P1329 ?telefono . }
    OPTIONAL { ?museo wdt:P571 ?fondazione .}
    OPTIONAL { ?museo wdt:P625 ?coordinate .}
    OPTIONAL { ?museo wdt:P2555 ?fee .      }
    OPTIONAL {
        ?museo wdt:P131 ?citta .
        ?citta rdfs:label ?cittaNome .
        FILTER(lang(?cittaNome) = "it")
    }
}
GROUP BY ?museo ?nomeMuseo
"""
# Esecuzione query, con time limit di wikidata
USER_AGENT = "CaravaggioBot/1.0 (progetto universitario NLP; tuaemail@esempio.com)"

def esegui_query(query, max_retry=5):
    sparql = SPARQLWrapper("https://query.wikidata.org/sparql")
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)
    sparql.setTimeout(60)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)

    for tentativo in range(max_retry):
        try:
            time.sleep(5)  # aspetta sempre 5 secondi tra le query
            return sparql.query().convert()["results"]["bindings"]
        except Exception as e:
            if "429" in str(e):
                attesa = (tentativo + 1) * 60
                print(f"   ⚠️  Rate limit! Attendo {attesa} secondi...")
                time.sleep(attesa)
            else:
                print(f"   ❌ Errore: {e}")
                return []
    return []


# Salvo i dati in cache, così da evitare di richiamare ogni volta wiki che ci mette 3 anni...
CACHE_FILE = "cache_sparql.json"

def salva_cache(dati):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    print("💾 Cache salvata!")

def carica_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            print("📂 Cache trovata, carico dati locali...")
            return json.load(f)
    return None

# WIKI API utilizzato per ottenere le descrizioni dalle pagine Wiki dato che sia su DBpedia
# che Wikidata alcune informazioni sono mancanti
WIKI_API     = "https://it.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "CaravaggioBot/1.0 (progetto universitario NLP)"}

def descrizioni_wikipedia(nomi, batch=20, timeout=20):
    risultati = {}
    for i in range(0, len(nomi), batch):
        gruppo = nomi[i:i + batch]
        params = {
            "action":    "query",
            "format":    "json",
            "prop":      "extracts",
            "exintro":   1,          # solo l'introduzione
            "explaintext": 1,        # testo semplice, no HTML
            "exlimit":   "max",
            "redirects": 1,          # segui i redirect
            "titles":    "|".join(gruppo),
        }
        url = WIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=WIKI_HEADERS)
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
MOVIMENTI_DEFAULT = {
    "Q42207":   "Barocco, Controriforma",
    "Q2519261": "Caravaggismo, Barocco napoletano"
}

def estrai_artisti(risultati):
    artisti = []
    for r in risultati:
        artista_uri    = r.get("artista",  {}).get("value", "")
        qid            = artista_uri.split("/")[-1]
        movimenti      = r.get("movimenti",     {}).get("value", "")
        opere_notevoli = r.get("opereNotevoli", {}).get("value", "")

        if not movimenti:
            movimenti = MOVIMENTI_DEFAULT.get(qid, "")

        artisti.append({
            "wikidata_id":   qid,
            "nome":          r.get("nome",             {}).get("value", "N/D"),
            "data_nascita":  r.get("dataNascita",       {}).get("value", "")[:10],
            "luogo_nascita": r.get("luogoNascitaLabel", {}).get("value", ""),
            "movimenti":     movimenti,
            "opere_notevoli": opere_notevoli
        })
    return artisti

# Estrazione OPERE
def estrai_opere(risultati, artista_id):
    opere = []
    for r in risultati:
        opera_uri = r.get("opera",    {}).get("value", "")
        museo_uri = r.get("museo",    {}).get("value", "")

        anno_raw = r.get("anno", {}).get("value", "")
        anno     = anno_raw[:4] if anno_raw else ""

        tipo = r.get("tipoLabel", {}).get("value", "")

        opere.append({
            "wikidata_id": opera_uri.split("/")[-1],
            "titolo":      r.get("nome",      {}).get("value", "N/D"),
            "anno":        anno,
            "altezza":     r.get("altezza",   {}).get("value", ""),
            "larghezza":   r.get("larghezza", {}).get("value", ""),
            "tecnica":     r.get("tecnica",   {}).get("value", ""),
            "soggetti":    r.get("soggetti",  {}).get("value", ""),
            "museo_nome":  r.get("museoNome", {}).get("value", ""),
            "museo_id":    museo_uri.split("/")[-1] if museo_uri else "",
            "artista_id":  artista_id,
            "descrizione": "",
            "tipo":        tipo        # ← aggiunto
        })

    titoli      = [o["titolo"] for o in opere]
    descrizioni = descrizioni_wikipedia(titoli)
    for opera in opere:
        opera["descrizione"] = descrizioni.get(opera["titolo"], "")

    return opere

#ESTRAZIONE MUSEI
def estrai_musei(risultati):
    """Converte i risultati SPARQL in dizionari pronti per Neo4j"""
    musei = []
    for r in risultati:
        museo_uri = r.get("museo", {}).get("value", "")

        # Le coordinate arrivano come "Point(lon lat)" da Wikidata
        # le convertiamo in latitudine e longitudine separate
        coordinate = r.get("coordinate", {}).get("value", "")
        latitudine, longitudine = "", ""
        if coordinate:
            try:
                # formato: "Point(14.2681 40.8518)"
                coord = coordinate.replace("Point(", "").replace(")", "")
                lon, lat = coord.split()
                latitudine = lat
                longitudine = lon
            except:
                pass

        # La fondazione arriva come data ISO completa, prendiamo solo l'anno
        fondazione = r.get("fondazione", {}).get("value", "")
        if fondazione:
            fondazione = fondazione[:4]

        musei.append({
            "wikidata_id": museo_uri.split("/")[-1],
            "nome": r.get("nomeMuseo", {}).get("value", "N/D"),
            "descrizione": r.get("descrizione", {}).get("value", ""),
            "indirizzo": r.get("indirizzo", {}).get("value", ""),
            "sito": r.get("sito", {}).get("value", ""),
            "telefono": r.get("telefono", {}).get("value", ""),
            "fondazione": fondazione,
            "latitudine": latitudine,
            "longitudine": longitudine,
            "citta": r.get("citta", {}).get("value", ""),
            "biglietto": r.get("fee", {}).get("value", "")
        })
    return musei


if __name__ == "__main__":
    print("1. Query Artisti...")
    artisti = esegui_query(query_artisti)
    print(f"   → {len(artisti)} artisti trovati")

    print("2. Query opere Caravaggio...")
    opere_caravaggio = esegui_query(query_opere_caravaggio)
    print(f"   → {len(opere_caravaggio)} opere trovate")

    print("3.  Query opere Caracciolo...")
    opere_caracciolo = esegui_query(query_opere_caracciolo)
    print(f"   → {len(opere_caracciolo)} opere trovate")

    print("4.  Query musei...")
    musei = esegui_query(query_musei)
    print(f"   → {len(musei)} musei trovati")