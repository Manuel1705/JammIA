#Bisogna prelevare sia le opere di Caravaggio che di Battistello Caracciolo visitabili a Napoli.
#Sono richieste conoscenze di base come il nome dell'opera, il nome del museo e il luogo, la data di creazione
#Le informazioni dovrebbero essere relative sia all'opera che al museo stesso.

from SPARQLWrapper import SPARQLWrapper, JSON
import time

# Query 1: Opere di Caravaggio a Napoli
query_caravaggio= """
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?opera ?nome ?museoNome
           (GROUP_CONCAT(DISTINCT ?depictsNome; SEPARATOR=", ") AS ?soggetti)
    WHERE {
        # Opere napoletane note con ID espliciti
        {   VALUES ?opera {
                wd:Q702067    # Sette opere di misericordia
                wd:Q739285    # Flagellazione di Cristo
                wd:Q3810868   # Martirio di Sant'Orsola
            }
            ?opera wdt:P170 wd:Q42207 .
            ?opera wdt:P31  wd:Q3305213 .
        }
        UNION
        # Altre eventuali opere con P131 = Napoli
        {   ?opera wdt:P170 wd:Q42207 .
            ?opera wdt:P31  wd:Q3305213 .
            ?opera wdt:P131 wd:Q2634 .
        }
        UNION
        # Opere nei musei napoletani noti
        {   ?opera wdt:P170 wd:Q42207 .
            ?opera wdt:P31  wd:Q3305213 .
            ?opera wdt:P276 ?museo .
            VALUES ?museo {
                wd:Q1191732   # Capodimonte
                wd:Q27237661  # Gallerie d'Italia
            }
        }

        OPTIONAL { ?opera rdfs:label ?nomeIT . FILTER(lang(?nomeIT) = "it") }
        OPTIONAL { ?opera rdfs:label ?nomeEN . FILTER(lang(?nomeEN) = "en") }
        BIND(COALESCE(?nomeIT, ?nomeEN, "N/D") AS ?nome)

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
    GROUP BY ?opera ?nome ?museoNome
"""
# query 2: per le opere di caracciolo a napoli
query_caracciolo="""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?opera ?nome ?museoNome
       (GROUP_CONCAT(DISTINCT ?depictsNome; SEPARATOR=", ") AS ?soggetti)
WHERE {
    ?opera wdt:P170 wd:Q2519261 .
    ?opera wdt:P31  wd:Q3305213 .

    {   ?opera wdt:P131 wd:Q2634 . }
    UNION
    {   ?opera wdt:P276 ?museo .
        ?museo wdt:P131 wd:Q2634 . }

    FILTER NOT EXISTS { ?opera wdt:P276 wd:Q768717 }

    OPTIONAL { ?opera rdfs:label ?nomeIT . FILTER(lang(?nomeIT) = "it") }
    OPTIONAL { ?opera rdfs:label ?nomeEN . FILTER(lang(?nomeEN) = "en") }
    BIND(COALESCE(?nomeIT, ?nomeEN, "N/D") AS ?nome)

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
GROUP BY ?opera ?nome ?museoNome
"""
# Query 3: per info sui musei di Napoli
query_musei= """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?museo ?nomeMuseo ?indirizzo ?sito 
                ?telefono ?fondazione
WHERE {
    {   ?opera wdt:P170 wd:Q42207 .
        ?opera wdt:P276 ?museo . }
    UNION
    {   ?opera wdt:P170 wd:Q2519261 .
        ?opera wdt:P276 ?museo . }

    ?museo rdfs:label ?nomeMuseo .
    FILTER(lang(?nomeMuseo) = "it")

    OPTIONAL { ?museo wdt:P969 ?indirizzo . }
    OPTIONAL { ?museo wdt:P856 ?sito .      }
    OPTIONAL { ?museo wdt:P1329 ?telefono . }
    OPTIONAL { ?museo wdt:P571 ?fondazione .}
}
"""
#esecuzione query
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

def estrai_opere(risultati, artista_id):
    """Converte i risultati SPARQL in dizionari pronti per Neo4j"""
    opere = []
    for r in risultati:
        opera_uri = r.get("opera",    {}).get("value", "")
        museo_uri = r.get("museo",    {}).get("value", "")

        opere.append({
            "wikidata_id": opera_uri.split("/")[-1],  # es. Q702067
            "titolo":      r.get("nome",      {}).get("value", "N/D"),
            "soggetti":    r.get("soggetti",  {}).get("value", ""),
            "artista_id":  artista_id,
            "museo_id":    museo_uri.split("/")[-1] if museo_uri else ""
        })
    return opere

def estrai_musei(risultati):
    """Converte i risultati SPARQL in dizionari pronti per Neo4j"""
    musei = []
    for r in risultati:
        museo_uri = r.get("museo", {}).get("value", "")
        musei.append({
            "wikidata_id": museo_uri.split("/")[-1],
            "nome":        r.get("nomeMuseo",  {}).get("value", "N/D"),
            "indirizzo":   r.get("indirizzo",  {}).get("value", ""),
            "sito":        r.get("sito",       {}).get("value", ""),
            "telefono":    r.get("telefono",   {}).get("value", ""),
            "fondazione":  r.get("fondazione", {}).get("value", "")
        })
    return musei

if __name__ == "__main__":
    print("1️⃣  Query opere Caravaggio...")
    opere_caravaggio = esegui_query(query_caravaggio)
    print(f"   → {len(opere_caravaggio)} opere trovate")

    print("2️⃣  Query opere Caracciolo...")
    opere_caracciolo = esegui_query(query_caracciolo)
    print(f"   → {len(opere_caracciolo)} opere trovate")

    print("3️⃣  Query musei...")
    musei = esegui_query(query_musei)
    print(f"   → {len(musei)} musei trovati")