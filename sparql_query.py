#Bisogna prelevare sia le opere di Caravaggio che di Battistello Caracciolo visitabili a Napoli.
#Sono richieste conoscenze di base come il nome dell'opera, il nome del museo e il luogo, la data di creazione
#Le informazioni dovrebbero essere relative sia all'opera che al museo stesso.

from SPARQLWrapper import SPARQLWrapper, JSON

# Endpoint di DBpedia
sparql = SPARQLWrapper("http://dbpedia.org/sparql")

# Query di esempio: opere di Caravaggio a Napoli
sparql.setQuery("""
    PREFIX dbo: <http://dbpedia.org/ontology/>
    PREFIX dbr: <http://dbpedia.org/resource/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

  SELECT ?opera ?nome ?dove WHERE {
    ?opera dct:subject <http://dbpedia.org/resource/Category:Paintings_by_Caravaggio> .
    ?opera ?prop ?dove .
    FILTER(CONTAINS(STR(?dove), "Naples") || CONTAINS(STR(?dove), "Napoli"))
    OPTIONAL { ?opera rdfs:label ?nome . FILTER(lang(?nome) = "it") }
}
""")

sparql.setReturnFormat(JSON)
results = sparql.query().convert()

for r in results["results"]["bindings"]:
    print("Opera:", r["nome"]["value"])
    print("---")