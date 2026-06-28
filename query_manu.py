
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from SPARQLWrapper import SPARQLWrapper, JSON

# Dati strutturati da DBpedia
sparql = SPARQLWrapper("https://dbpedia.org/sparql")
sparql.setReturnFormat(JSON)

# Dati strutturati da Wikidata (richiede uno User-Agent)
wikidata = SPARQLWrapper("https://query.wikidata.org/sparql",
                         agent="ChatbotNapoli/0.1 (progetto universitario NLP)")
wikidata.setReturnFormat(JSON)

# Schema comune dei campi di un'opera (usato per fondere le due fonti)
CAMPI = ("nome", "anno", "tecnica", "altezza", "larghezza", "museo", "citta")

# Descrizioni testuali da Wikipedia italiana (richiede un User-Agent, altrimenti 403)
WIKI_API = "https://it.wikipedia.org/w/api.php"
WIKI_HEADERS = {"User-Agent": "ChatbotNapoli/0.1 (progetto universitario NLP)"}


def descrizioni_wikipedia(nomi, batch=20, timeout=20):
    """Restituisce {nome: estratto introduttivo da Wikipedia IT} per una lista di titoli.

    Usa l'API batch di MediaWiki (max 20 titoli/richiesta) per evitare il rate-limit (429)
    e segue automaticamente redirect e normalizzazioni dei titoli.
    """
    risultati = {}
    for i in range(0, len(nomi), batch):
        gruppo = nomi[i:i + batch]
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "exlimit": "max",
            "redirects": 1,
            "titles": "|".join(gruppo),
        }
        url = WIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=WIKI_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                q = json.load(resp).get("query", {})
        except Exception as e:
            print(f"[Wikipedia] errore batch: {e}")
            continue

        # titolo (eventualmente normalizzato/redirect) -> estratto
        titolo2estratto = {p["title"]: p.get("extract", "")
                           for p in q.get("pages", {}).values()}
        # mappa per risalire dal titolo richiesto a quello finale
        rimappa = {}
        for m in q.get("normalized", []):
            rimappa[m["from"]] = m["to"]
        for m in q.get("redirects", []):
            rimappa[m["from"]] = m["to"]

        for nome in gruppo:
            finale = rimappa.get(nome, nome)
            finale = rimappa.get(finale, finale)  # normalizzazione + eventuale redirect
            risultati[nome] = titolo2estratto.get(finale, "")
    return risultati


def membri_categoria(categoria, timeout=20):
    """Restituisce i titoli delle pagine-articolo in una categoria di Wikipedia IT."""
    titoli = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": categoria,
            "cmtype": "page",
            "cmlimit": "max",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        url = WIKI_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=WIKI_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                dati = json.load(resp)
        except Exception as e:
            print(f"[Wikipedia] errore categoria '{categoria}': {e}")
            break
        for m in dati.get("query", {}).get("categorymembers", []):
            if not m["title"].startswith("Opere di"):  # esclude le pagine-lista
                titoli.append(m["title"])
        cmcontinue = dati.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titoli


def cerca_opere_categoria(categoria):
    """Opere da una categoria Wikipedia IT (solo nome + descrizione). Usato come fallback."""
    nomi = membri_categoria(categoria)
    estratti = descrizioni_wikipedia(nomi)
    opere = []
    for nome in nomi:
        opera = {campo: "" for campo in CAMPI}
        opera["nome"] = nome
        opera["descrizione"] = estratti.get(nome, "")
        opere.append(opera)
    return opere


def _pulisci(valore):
    """Se il valore è un URI DBpedia ne estrae il nome leggibile, altrimenti lo restituisce com'è."""
    if valore.startswith("http://dbpedia.org/resource/"):
        nome = valore.rsplit("/", 1)[-1]
        return urllib.parse.unquote(nome).replace("_", " ")
    return valore


def _qid(uri):
    """Estrae il QID Wikidata (es. Q12345) da un URI, o '' se assente."""
    return uri.rsplit("/", 1)[-1] if uri else ""


def _titolo_articolo(url):
    """Da un URL di Wikipedia (.../wiki/Titolo) ricava il titolo dell'articolo."""
    if not url:
        return ""
    return urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1]).replace("_", " ")


def cerca_opere_dbpedia(autore):
    """Opere di un autore da DBpedia, indicizzate per QID Wikidata (chiave di merge)."""
    autore_uri = autore.replace(" ", "_")
    sparql.setQuery(f"""
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dbr: <http://dbpedia.org/resource/>
        PREFIX dbp: <http://dbpedia.org/property/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>

        SELECT ?opera
               (SAMPLE(?nome_it)  AS ?nome_it)
               (SAMPLE(?nome_en)  AS ?nome_en)
               (SAMPLE(?museo)    AS ?museo)
               (SAMPLE(?citta)    AS ?citta)
               (SAMPLE(?anno)     AS ?anno)
               (SAMPLE(?tecnica)  AS ?tecnica)
               (SAMPLE(?h)        AS ?h)
               (SAMPLE(?w)        AS ?w)
               (SAMPLE(?descr)    AS ?descr)
               (SAMPLE(?wd)       AS ?wd)
        WHERE {{
            ?opera dbo:author dbr:{autore_uri} .
            OPTIONAL {{ ?opera rdfs:label ?nome_it . FILTER(lang(?nome_it) = "it") }}
            OPTIONAL {{ ?opera rdfs:label ?nome_en . FILTER(lang(?nome_en) = "en") }}
            OPTIONAL {{ ?opera dbo:museum ?mr . ?mr rdfs:label ?museo . FILTER(lang(?museo) = "it") }}
            OPTIONAL {{ ?opera dbp:city ?citta }}
            OPTIONAL {{ ?opera dbp:year ?anno }}
            OPTIONAL {{ ?opera dbp:medium ?tecnica }}
            OPTIONAL {{ ?opera dbp:heightMetric ?h }}
            OPTIONAL {{ ?opera dbp:widthMetric ?w }}
            OPTIONAL {{ ?opera dbo:description ?descr . FILTER(lang(?descr) = "it") }}
            OPTIONAL {{ ?opera owl:sameAs ?wd .
                       FILTER(STRSTARTS(STR(?wd), "http://www.wikidata.org/entity/")) }}
        }}
        GROUP BY ?opera
    """)
    results = sparql.query().convert()

    opere = {}
    for r in results["results"]["bindings"]:
        g = lambda k: r.get(k, {}).get("value", "")
        qid = _qid(g("wd")) or g("opera")  # se manca il QID, usa l'URI DBpedia come chiave
        opere[qid] = {
            "nome": g("nome_it") or g("nome_en") or _pulisci(g("opera")),
            "anno": g("anno"),
            "tecnica": _pulisci(g("tecnica")),
            "altezza": g("h"),
            "larghezza": g("w"),
            "museo": g("museo"),
            "citta": _pulisci(g("citta")),
            "descr_dbpedia": g("descr"),
            "articolo": "",
        }
    return opere


def _interroga_wikidata(query, tentativi=4, attesa=20):
    """Esegue una query su Wikidata con retry/backoff sul rate-limit (HTTP 429)."""
    wikidata.setQuery(query)
    for n in range(tentativi):
        try:
            return wikidata.query().convert()
        except urllib.error.HTTPError as e:
            if e.code == 429 and n < tentativi - 1:
                pausa = attesa * (n + 1)
                print(f"[Wikidata] rate-limit (429): nuovo tentativo tra {pausa}s...")
                time.sleep(pausa)
            else:
                raise
    return {"results": {"bindings": []}}


def cerca_opere_wikidata(qid_autore):
    """Opere di un autore (per QID) da Wikidata, indicizzate per QID dell'opera."""
    results = _interroga_wikidata(f"""
        SELECT ?opera ?operaLabel ?inception ?museoLabel ?materialLabel
               ?height ?width ?cityLabel ?article ?aNapoli
        WHERE {{
            ?opera wdt:P170 wd:{qid_autore} .
            OPTIONAL {{ ?opera wdt:P571 ?inception }}
            OPTIONAL {{ ?opera wdt:P195 ?museo . }}
            OPTIONAL {{ ?opera wdt:P186 ?material . }}
            OPTIONAL {{ ?opera wdt:P2048 ?height }}
            OPTIONAL {{ ?opera wdt:P2049 ?width }}
            OPTIONAL {{ ?opera wdt:P276 ?city . }}
            OPTIONAL {{ ?article schema:about ?opera ;
                       schema:isPartOf <https://it.wikipedia.org/> }}
            # posizione esatta: l'ubicazione o la collezione si trova a Napoli (Q2634)?
            BIND(EXISTS {{
                {{ ?opera wdt:P276 ?ubic }} UNION {{ ?opera wdt:P195 ?ubic }}
                ?ubic wdt:P131* wd:Q2634 .
            }} AS ?aNapoli)
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
        }}
    """)

    opere = {}
    for r in results["results"]["bindings"]:
        # i valori "sconosciuti" (somevalue) tornano come nodi-blank genid: trattali come vuoti
        def g(k):
            v = r.get(k, {}).get("value", "")
            return "" if ".well-known/genid" in v else v
        qid = _qid(g("opera"))
        anno = g("inception")[:4]  # ISO date -> solo l'anno
        # più valori (es. tecnica multipla) collassano sull'ultima riga: va bene per il contesto
        prec = opere.get(qid, {})
        opere[qid] = {
            "nome": g("operaLabel") or prec.get("nome", ""),
            "anno": anno or prec.get("anno", ""),
            "tecnica": g("materialLabel") or prec.get("tecnica", ""),
            "altezza": g("height") or prec.get("altezza", ""),
            "larghezza": g("width") or prec.get("larghezza", ""),
            "museo": g("museoLabel") or prec.get("museo", ""),
            "citta": g("cityLabel") or prec.get("citta", ""),
            "articolo": _titolo_articolo(g("article")) or prec.get("articolo", ""),
            # flag geografico autorevole da Wikidata (True se confermata a Napoli)
            "napoli_wd": (g("aNapoli") == "true") or prec.get("napoli_wd", False),
        }
    return opere


def _fondi(dbpedia, wd):
    """Fonde due insiemi di opere (indicizzati per QID): DBpedia ha priorità, Wikidata riempie i buchi."""
    opere = []
    for qid in list(dbpedia.keys()) + [k for k in wd if k not in dbpedia]:
        a = dbpedia.get(qid, {})
        b = wd.get(qid, {})
        opera = {campo: a.get(campo) or b.get(campo) or "" for campo in CAMPI}
        opera["articolo"] = a.get("articolo") or b.get("articolo") or ""
        opera["descr_dbpedia"] = a.get("descr_dbpedia", "")
        opera["napoli_wd"] = a.get("napoli_wd", False) or b.get("napoli_wd", False)
        opere.append(opera)
    return opere


def cerca_opere(autore_dbpedia, qid_autore):
    """Unisce le opere di un autore da DBpedia e Wikidata e aggiunge le descrizioni da Wikipedia IT."""
    try:
        db = cerca_opere_dbpedia(autore_dbpedia) if autore_dbpedia else {}
    except Exception as e:
        print(f"[DBpedia] errore su {autore_dbpedia}: {e}")
        db = {}
    try:
        wd = cerca_opere_wikidata(qid_autore)
    except Exception as e:
        print(f"[Wikidata] errore su {qid_autore}: {e}")
        wd = {}

    opere = _fondi(db, wd)

    # Descrizioni da Wikipedia IT: usa il titolo dell'articolo (da Wikidata) o il nome dell'opera
    titoli = [o["articolo"] or o["nome"] for o in opere]
    estratti = descrizioni_wikipedia(titoli)
    for o in opere:
        chiave = o["articolo"] or o["nome"]
        o["descrizione"] = estratti.get(chiave, "") or o["descr_dbpedia"]

    return opere


def _a_napoli(o):
    """Indica se l'opera si trova a Napoli.

    Fonte primaria: il flag geografico autorevole di Wikidata (ubicazione/collezione
    con P131* = Napoli). Se assente (opere da DBpedia o dal fallback Wikipedia), ripiega
    sull'euristica testuale su città/museo/descrizione.
    """
    if o.get("napoli_wd"):
        return True
    testo = " ".join([o.get("citta", ""), o.get("museo", ""),
                      o.get("descrizione", "")]).lower()
    return "napoli" in testo or "naples" in testo


def _riga_opera(o):
    """Formatta una singola opera in una riga di testo con tutte le informazioni disponibili."""
    dettagli = []
    if o["anno"]:
        dettagli.append(f"anno {o['anno']}")
    if o["tecnica"]:
        dettagli.append(o["tecnica"].lower())
    if o["altezza"] and o["larghezza"]:
        dettagli.append(f"{o['altezza']}x{o['larghezza']} cm")
    if o["museo"]:
        dettagli.append(f"conservato presso {o['museo']}")
    if o["citta"]:
        dettagli.append(o["citta"])
    stato = "A NAPOLI" if _a_napoli(o) else "NON a Napoli"
    riga = f"- {o['nome']} [{stato}]"
    if dettagli:
        riga += " (" + ", ".join(dettagli) + ")"
    if o["descrizione"]:
        riga += f": {o['descrizione']}"
    return riga


def costruisci_contesto():
    """Costruisce il blocco di contesto (RAG) da iniettare nel system prompt.

    Le opere sono prese da DBpedia e Wikidata (fuse per QID) e le descrizioni
    da Wikipedia IT. Per Caravaggio entrambe le fonti hanno dati; per Battistello
    Caracciolo i dati strutturati arrivano da Wikidata (DBpedia non lo modella).
    """
    # (titolo, autore su DBpedia o None, QID Wikidata, categoria Wikipedia di fallback)
    fonti = [
        ("Opere di Caravaggio", "Caravaggio", "Q42207",
         "Categoria:Dipinti di Caravaggio"),
        ("Opere di Battistello Caracciolo", None, "Q2519261",
         "Categoria:Dipinti di Battistello Caracciolo"),
    ]
    blocchi = []
    for titolo, autore_dbpedia, qid, categoria in fonti:
        opere = cerca_opere(autore_dbpedia, qid)
        if not opere and categoria:
            # Wikidata/DBpedia non hanno restituito nulla: ripiego sulla categoria Wikipedia
            print(f"[contesto] fallback su categoria Wikipedia per '{titolo}'")
            opere = cerca_opere_categoria(categoria)
        if not opere:
            print(f"[contesto] nessuna opera trovata per '{titolo}'")
            continue
        righe = "\n".join(_riga_opera(o) for o in opere)
        blocchi.append(f"{titolo}:\n{righe}")
    return "\n\n".join(blocchi)


if __name__ == "__main__":
    print(costruisci_contesto())
