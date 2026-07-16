// ============================================================
//  Documentazione tecnica — Chatbot Caravaggio & Caracciolo
// ============================================================

#set document(title: "Architettura del Chatbot su Caravaggio e Caracciolo", author: "Manuel Mignogna")
#set page(
  paper: "a4",
  margin: (x: 2.4cm, y: 2.6cm),
  numbering: "1",
  number-align: center,
)
#set text(font: "New Computer Modern", lang: "it", size: 10.5pt)
#set par(justify: true, leading: 0.68em)
#set heading(numbering: "1.1")

// ---- Colori ----
#let accent = rgb("#7a1f1f")
#let softbg = rgb("#f4efe9")
#let codebg = rgb("#f6f7f9")

// ---- Stile heading ----
#show heading.where(level: 1): it => [
  #set text(fill: accent, size: 16pt, weight: "bold")
  #block(above: 1.4em, below: 0.8em)[#it]
]
#show heading.where(level: 2): it => [
  #set text(fill: accent.darken(10%), size: 12.5pt, weight: "bold")
  #block(above: 1.1em, below: 0.6em)[#it]
]
#show heading.where(level: 3): it => [
  #set text(fill: black, size: 11pt, weight: "bold", style: "italic")
  #block(above: 0.9em, below: 0.4em)[#it]
]

// ---- Link ----
#show link: it => text(fill: accent, it)

// ---- Blocchi di codice ----
#show raw.where(block: true): it => block(
  fill: codebg,
  inset: 10pt,
  radius: 4pt,
  width: 100%,
  stroke: 0.5pt + luma(210),
  text(size: 8.7pt, it),
)
#show raw.where(block: false): it => box(
  fill: codebg,
  inset: (x: 3pt, y: 0pt),
  outset: (y: 2pt),
  radius: 2pt,
  text(size: 9pt, it),
)

// ---- Box informativo ----
#let notebox(title, body) = block(
  fill: softbg,
  inset: 11pt,
  radius: 5pt,
  width: 100%,
  stroke: (left: 3pt + accent),
)[
  #text(weight: "bold", fill: accent)[#title] \
  #body
]

// ============================================================
//  FRONTESPIZIO
// ============================================================
#align(center)[
  #v(3cm)
  #text(size: 26pt, weight: "bold", fill: accent)[
    Chatbot conversazionale \ su Caravaggio e Caracciolo
  ]
  #v(0.4cm)
  #text(size: 14pt)[Documentazione tecnica dell'architettura]
  #v(0.2cm)
  #line(length: 40%, stroke: 0.8pt + accent)
  #v(0.4cm)
  #text(size: 11.5pt)[
    Knowledge Graph (Neo4j) · RAG Text-to-Cypher · LangGraph \
    LLM locale (Ollama) · Interfaccia vocale e testuale (Gradio)
  ]
  #v(2.5cm)
  #text(size: 10.5pt, style: "italic")[
    Progetto di Natural Language Processing \
    Corso di Laurea Magistrale
  ]
  #v(1fr)
  #text(size: 10pt, fill: luma(90))[Manuel Mignogna]
]
#pagebreak()

// ============================================================
//  INDICE
// ============================================================
#outline(title: "Indice", depth: 3, indent: auto)
#pagebreak()

// ============================================================
= Panoramica del sistema
// ============================================================

Il progetto realizza un assistente conversazionale specializzato su un dominio ristretto e ben definito: le opere dei pittori *Michelangelo Merisi da Caravaggio* e *Giovanni Battista Caracciolo* (detto Battistello) e i musei di Napoli che le espongono. L'utente può porre domande sia a voce sia per iscritto, e il sistema risponde con testo e sintesi vocale, attingendo a un grafo di conoscenza costruito a partire da fonti aperte (Wikidata e Wikipedia).

L'architettura si articola in *due sottosistemi indipendenti*, separati nel tempo e nelle responsabilità:

+ *Pipeline di ingestion (offline).* Interroga Wikidata via SPARQL, arricchisce i dati con le descrizioni testuali di Wikipedia e materializza il tutto in un knowledge graph Neo4j. Viene eseguita una tantum (o quando si vuole rigenerare la base dati) tramite `build_database.py`.

+ *Sistema conversazionale (runtime).* All'avvio (`app.py`) espone un'interfaccia Gradio. Ogni turno di dialogo passa attraverso un grafo di stato LangGraph che classifica la richiesta, la scompone in sotto-domande, recupera i dati dal grafo tramite RAG Text-to-Cypher e sintetizza una risposta in linguaggio naturale, infine convertita in voce.

Il principio di fondo è la *separazione tra conoscenza e ragionamento*: i fatti risiedono in modo strutturato nel grafo, mentre l'LLM è usato come traduttore (linguaggio naturale → Cypher) e come sintetizzatore (dati → risposta), non come fonte di verità. Questo riduce le allucinazioni e ancora le risposte a dati verificabili.

#notebox("Flusso end-to-end di un turno")[
  Voce/testo utente → (Whisper STT) → classificazione e scomposizione (LLM) → per ogni sotto-domanda in ambito: generazione Cypher (LLM) → query su Neo4j → righe grezze → sintesi unica della risposta (LLM) → (gTTS) → testo + audio all'utente.
]

== Struttura del progetto

Il codice è organizzato in package Python per responsabilità:

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Package / file*], [*Responsabilità*],
  [`chatbot/ingestion/`], [Costruzione del knowledge graph: query SPARQL, estrazione, caricamento in Neo4j.],
  [`chatbot/rag/`], [Catena RAG Text-to-Cypher su Neo4j e prompt di generazione query / sintesi.],
  [`chatbot/dialog/`], [Gestione del dialogo: grafo di stato LangGraph, classificazione, stati, prompt di routing.],
  [`chatbot/ui/`], [Interfaccia Gradio e stato di sessione.],
  [`chatbot/speech/`], [Riconoscimento vocale (Whisper) e sintesi vocale (gTTS).],
  [`chatbot/config.py`], [Configurazione centralizzata: credenziali, modelli, percorsi, costanti.],
  [`query/*.psql`], [Le quattro query SPARQL parametriche (artisti, opere, musei).],
  [`app.py`, `build_database.py`], [Entry point: avvio UI e popolamento del database.],
)

// ============================================================
= Stack tecnologico e librerie
// ============================================================

La scelta delle librerie riflette due priorità: eseguire tutto *in locale* (nessuna dipendenza da API a pagamento per l'LLM) e appoggiarsi ad *astrazioni consolidate* (LangChain/LangGraph) per non reimplementare orchestrazione e integrazione con il grafo.

== Modello linguistico e orchestrazione

#table(
  columns: (auto, auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Libreria*], [*Ruolo*], [*Motivazione della scelta*],
  [`langchain-ollama`], [LLM locale (`ChatOllama`)], [Esegue Gemma via Ollama senza costi né chiavi API; espone `with_structured_output` per l'output tipizzato.],
  [`langgraph`], [Grafo di stato del dialogo], [Modella il turno come macchina a stati con nodi, edge condizionali e human-in-the-loop (`interrupt`).],
  [`langgraph-checkpoint-sqlite`], [Persistenza dello stato], [Checkpointer per conservare lo stato di conversazione tra i turni, indicizzato per `thread_id`.],
  [`langchain-neo4j`], [RAG sul grafo], [Fornisce `Neo4jGraph` e `GraphCypherQAChain` (Text-to-Cypher) pronti all'uso.],
  [`pydantic`], [Modelli tipizzati], [Definisce lo schema dell'output del classificatore e lo stato del dialogo con validazione automatica.],
)

== Dati, voce e interfaccia

#table(
  columns: (auto, auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Libreria*], [*Ruolo*], [*Motivazione della scelta*],
  [`sparqlwrapper`], [Client SPARQL], [Interroga l'endpoint di Wikidata; gestione di formato JSON e header.],
  [`neo4j`], [Driver del grafo], [Accesso diretto a Neo4j per la fase di caricamento (MERGE dei nodi/relazioni).],
  [`transformers` + `torch` + `torchaudio`], [Speech-to-Text], [Eseguono Whisper large-v3 in locale per la trascrizione dell'audio.],
  [`gtts`], [Text-to-Speech], [Sintesi vocale semplice e in italiano della risposta finale.],
  [`gradio`], [Interfaccia web], [UI chat con supporto nativo a microfono, audio e animazioni di caricamento.],
  [`mlx-lm`], [Backend Apple Silicon], [Abilita l'inferenza ottimizzata su GPU Apple (variante `-mlx` del modello).],
)

== Selezione del dispositivo e del modello

La configurazione (`config.py`) sceglie automaticamente l'acceleratore disponibile — CUDA (NVIDIA/Colab), altrimenti MPS (Apple Silicon), altrimenti CPU — e di conseguenza la variante del modello Gemma (`gemma4:e4b-mlx` su Apple, `gemma:e4b` altrove). Tutte le costanti sensibili (URI e credenziali Neo4j, nomi dei modelli, endpoint) sono lette da variabili d'ambiente con valori di default, così da non essere disseminate nel codice.

// ============================================================
= La pipeline di ingestion
// ============================================================

L'obiettivo di questa fase è trasformare dati eterogenei e semi-strutturati (Wikidata) e testi discorsivi (Wikipedia) in un grafo pulito e interrogabile. È orchestrata da `pipeline.populate_database()` e si compone di tre stadi: *estrazione*, *trasformazione/arricchimento*, *caricamento* (un classico ETL).

== Estrazione: le query SPARQL

Le quattro query in `query/*.psql` interrogano Wikidata a partire dagli identificatori dei due artisti (`Q42207` per Caravaggio, `Q2519261` per Caracciolo). Sono state scritte con alcune accortezze ricorrenti:

- *Preferenza linguistica con fallback.* Le etichette sono richieste in italiano e, se assenti, in inglese, tramite `COALESCE(?labelIT, ?labelEN, "default")`. Questo evita campi vuoti quando Wikidata non ha la traduzione italiana.
- *Aggregazione per evitare duplicati.* Proprietà multi-valore (soggetti, movimenti, opere notevoli) sono raccolte con `GROUP_CONCAT(DISTINCT ...)`; i valori singoli con `SAMPLE(...)`, così ogni entità produce una sola riga.
- *Fonti alternative unite con `UNION`.* Il luogo di un'opera è cercato sia come "collocazione" (`P276`) sia come "collezione" (`P195`); l'indirizzo del museo attraverso più proprietà. In questo modo si massimizza la copertura di un grafo di conoscenza notoriamente irregolare.

`SparqlExecutor` carica le query, le esegue con *retry esponenziale sul rate limit* (HTTP 429, attesa e nuovo tentativo) e *memorizza i risultati in cache* (`cache/sparql_cache.json`). La cache è cruciale: senza di essa ogni ricostruzione del database rifarebbe decine di richieste a Wikidata, lente e soggette a throttling.

#notebox("Nota sulla cache")[
  La cache SPARQL contiene i dati Wikidata (date, dimensioni, relazioni); la cache Wikipedia contiene solo le descrizioni testuali. Modificando una query SPARQL occorre invalidare `sparql_cache.json`, altrimenti la pipeline continua a leggere i risultati vecchi.
]

== Trasformazione: `Extractor`

`Extractor` converte le _binding_ SPARQL grezze in dizionari Python puliti e le arricchisce:

- Estrae il Q-ID dagli URI Wikidata, tronca le date alla parte utile (anno o data ISO), e traduce le coordinate dal formato WKT `Point(lon lat)` alla coppia `(lat, lon)`.
- Per le opere, *sostituisce la descrizione sintetica di Wikidata con l'introduzione discorsiva della relativa voce Wikipedia*, recuperata in batch dalle API di Wikipedia IT (`prop=extracts`, solo intro, testo semplice). Anche qui interviene una cache dedicata (`wikipedia_cache.json`) con gestione di redirect e normalizzazioni dei titoli, e throttling per rispettare i limiti del servizio.

Questa scelta è deliberata: le descrizioni di Wikipedia sono molto più ricche e utili per la risposta finale rispetto alle stringhe minimali di Wikidata.

== Caricamento: `Neo4jLoader` e lo schema del grafo

`Neo4jLoader` è implementato come *context manager* (`__enter__`/`__exit__`) per garantire la chiusura del driver Neo4j anche in presenza di eccezioni. Ogni scrittura avviene in una sessione gestita con `with`, e le query Cypher sono tipizzate come `LiteralString` — una scelta di sicurezza che segnala staticamente l'intenzione di non costruire query da input dinamico.

I nodi sono inseriti con `MERGE ... ON CREATE SET`, idempotente: rieseguire il caricamento non duplica i nodi. Lo schema risultante è il seguente:

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Nodo*], [*Proprietà principali*],
  [`Artista`], [`name`, `data_nascita`, `data_morte`, `luogo_nascita`, `movimenti`, `opere_notevoli`, `wikidataId`],
  [`Opera`], [`name`, `anno`, `altezza`, `larghezza`, `tecnica`, `soggetti`, `descrizione`, `tipo`, `wikidataId`],
  [`Museo`], [`name`, `descrizione`, `indirizzo`, `sito`, `telefono`, `fondazione`, `latitudine`, `longitudine`, `biglietto`],
  [`Città`], [`name`],
)

Le relazioni collegano le entità secondo la semantica del dominio:

```cypher
(Opera)-[:DIPINTA_DA]->(Artista)
(Opera)-[:ESPOSTA_IN]->(Museo)
(Museo)-[:SITUATO_IN]->(Città)
```

L'ordine di caricamento (artisti e musei prima delle opere) non è casuale: `insert_work` esegue un `MATCH` su artista e museo per creare le relazioni, quindi quei nodi devono già esistere.

// ============================================================
= Il sistema conversazionale: grafo di stato LangGraph
// ============================================================

Il cuore del runtime è `DialogManager`, che modella un turno di dialogo come un *grafo di stato* (`StateGraph`) di LangGraph. Questa scelta permette di rappresentare esplicitamente il flusso decisionale — classificare, eventualmente chiedere chiarimenti, recuperare e rispondere — con edge condizionali invece che con una cascata di `if` annidati.

== Lo stato: `DialogState`

Lo stato che attraversa il grafo è un modello Pydantic con i campi essenziali del turno:

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Campo*], [*Significato*],
  [`question`], [La domanda corrente dell'utente (eventualmente arricchita col chiarimento).],
  [`sub_questions`], [Elenco di sotto-domande atomiche, ciascuna con un flag `in_scope`.],
  [`clarification_question`], [La domanda di chiarimento da porre all'utente, se necessaria.],
  [`clarification_attempts`], [Contatore dei tentativi di chiarimento (per evitare loop infiniti).],
  [`history`], [Gli ultimi turni della conversazione, come lista di `Turn` (domanda + risposta).],
  [`response`], [La risposta finale (usata anche per il chitchat).],
)

Gli aggiornamenti allo stato usano un `TypedDict` parziale (`DialogStateUpdate`): ogni nodo restituisce solo i campi che modifica, e LangGraph li fonde nello stato. La cronologia è mantenuta *limitata* (ultimi 10 turni salvati, ultimi 3 passati come contesto al classificatore) per contenere la dimensione del prompt.

== I nodi del grafo

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Nodo*], [*Funzione*],
  [`USER_PROMPT_CLASSIFICATION`], [Classifica e scompone la richiesta chiamando l'LLM con output strutturato.],
  [`USER_INTENT_CLARIFICATION`], [Sospende il grafo (`interrupt`) e chiede un chiarimento all'utente.],
  [`RESPONSE_GENERATION`], [Esegue il RAG sulle sotto-domande in ambito e sintetizza la risposta.],
  [`HISTORY_UPDATE`], [Accoda il turno corrente alla cronologia e termina.],
)

== Il routing condizionale

Dopo la classificazione, una funzione di routing (`_route_after_resolve`) decide il nodo successivo in base a *quali campi dello stato sono valorizzati*, con una precisa priorità:

+ se è presente una `response` (caso chitchat) → si va direttamente all'aggiornamento cronologia, saltando del tutto il grafo;
+ se è presente una `clarification_question` → si va al nodo di chiarimento;
+ se sono presenti `sub_questions` → si va alla generazione della risposta.

Il nodo di chiarimento ha a sua volta un edge condizionale: se dopo la risposta dell'utente la richiesta è ancora ambigua e non si sono superati i *3 tentativi*, si richiede un nuovo chiarimento; altrimenti si procede comunque alla generazione. Questo limite evita che l'utente resti intrappolato in un ciclo di domande.

#figure(
  block(
    fill: codebg,
    inset: 12pt,
    radius: 5pt,
    stroke: 0.5pt + luma(200),
    width: 100%,
    align(left, text(size: 9pt)[
      `START` \
      `  └─▶ USER_PROMPT_CLASSIFICATION` \
      `         ├─ (response)          ─▶ HISTORY_UPDATE ─▶ END` \
      `         ├─ (clarification)     ─▶ USER_INTENT_CLARIFICATION` \
      `         │                           ├─ (ancora ambiguo, <3) ─▶ (loop)` \
      `         │                           └─ (risolto / ≥3)       ─▶ RESPONSE_GENERATION` \
      `         └─ (sub_questions)     ─▶ RESPONSE_GENERATION ─▶ HISTORY_UPDATE ─▶ END`
    ]),
  ),
  caption: [Flusso del grafo di stato del dialogo.],
)

== Human-in-the-loop e persistenza

Il chiarimento sfrutta il meccanismo `interrupt` di LangGraph: il grafo si *sospende* restituendo la domanda all'interfaccia e riprende esattamente da quel punto quando arriva la risposta dell'utente (`Command(resume=...)`). Perché questo funzioni tra due invocazioni HTTP distinte serve un *checkpointer*: lo stato è serializzato e indicizzato per `thread_id`, cioè per conversazione. Ogni sessione Gradio genera un `thread_id` (UUID) nuovo, così conversazioni diverse non si mescolano.

// ============================================================
= Classificazione e scomposizione della richiesta
// ============================================================

Il primo nodo è anche il più delicato: deve decidere *cosa* fare con il messaggio dell'utente prima ancora di toccare il grafo. Usa l'LLM in modalità *output strutturato* (`with_structured_output(ModelResponse)`), che vincola la risposta del modello allo schema Pydantic.

== Lo schema di output: `ModelResponse`

```python
class ModelResponse(BaseModel):
    type: Literal["query", "clarification", "chitchat"]
    sub_questions: Optional[list[SubQuestion]] = None   # se type == query
    clarification_question: Optional[str] = None        # se type == clarification
    response: Optional[str] = None                       # se type == chitchat
```

Ogni tipo usa *un solo campo payload*, senza combinazioni ambigue: questo mantiene la logica di routing pulita (uno switch sul `type` decide quale campo leggere). È stato preferito ad avere un campo separato per il chitchat proprio per non introdurre stati ridondanti da disambiguare.

== Le tre categorie

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Categoria*], [*Quando scatta e cosa produce*],
  [*QUERY*], [La richiesta contiene almeno una domanda su opere/artisti/musei. Viene scomposta in sotto-domande atomiche, ciascuna auto-contenuta e con un flag `in_scope`.],
  [*CLARIFICATION*], [La richiesta richiederebbe una query ma contiene un riferimento implicito che né il messaggio né la storia risolvono (es. "Chi l'ha dipinta?" senza opera nominata).],
  [*CHITCHAT*], [Messaggi puramente sociali (saluti, ringraziamenti) senza alcuna richiesta di informazioni. La risposta cordiale è generata direttamente nel campo `response`.],
)

== Scelte di prompting

Il prompt del classificatore concentra diverse istruzioni non banali:

- *Risoluzione dei riferimenti (coreference).* Ogni sotto-domanda deve essere riscritta in forma completamente auto-contenuta: dimostrativi e pronomi ("questi quadri", "lui", "lì") vanno sostituiti con il nome esplicito dell'entità, preso dagli scambi precedenti. Chi legge la sotto-domanda non deve aver bisogno della conversazione per capirla — requisito essenziale perché la generazione Cypher a valle riceve le sotto-domande isolate.
- *Scomposizione di richieste composte.* Una domanda che ne contiene più di una viene spezzata in unità atomiche su un solo argomento. Ciò consente di recuperare e poi ricombinare i dati in modo controllato.
- *Marcatura dell'ambito (`in_scope`).* Ogni sotto-domanda è etichettata come dentro o fuori dominio (Caravaggio/Caracciolo, loro opere, musei di Napoli). Le parti fuori ambito non vengono interrogate sul grafo ma gestite con una nota esplicita, così una richiesta mista ("...e quante ne ha fatte Botticelli?") viene comunque servita per la parte pertinente.
- *Bias verso QUERY in caso di dubbio*, per non rifiutare domande legittime, e disambiguazione esplicita tra i due artisti.

#notebox("Coerenza tra prompt e schema")[
  Poiché l'output è vincolato allo schema Pydantic, le chiavi indicate negli esempi del prompt devono coincidere esattamente con i nomi dei campi (`response`, `clarification_question`, `sub_questions`). Un disallineamento — per esempio suggerire una chiave `text` inesistente nello schema — porta il modello a produrre un campo che viene scartato, lasciando il valore atteso a `None`.
]

== Robustezza

Con modelli locali di piccola taglia l'output strutturato può occasionalmente fallire (stringa vuota o JSON malformato). È previsto — o comunque consigliato — un *fallback difensivo*: intercettare l'errore di parsing e degradare verso una richiesta di chiarimento, invece di far crashare l'intero turno. La `temperature` bassa (0 per la classificazione) riduce la variabilità e rende l'output più deterministico.

// ============================================================
= Il modulo RAG: da linguaggio naturale a Cypher
// ============================================================

Il recupero delle informazioni segue il paradigma *RAG Text-to-Cypher*: invece di cercare in un indice vettoriale, l'LLM traduce la domanda in una query Cypher che viene eseguita sul grafo Neo4j. `RagChain` incapsula la connessione al grafo, l'LLM e la `GraphCypherQAChain` di LangChain.

== Configurazione della catena

```python
GraphCypherQAChain.from_llm(
    llm=self.llm,
    graph=Neo4jGraph(...),
    cypher_prompt=CYPHER_PROMPT,
    return_direct=True,     # restituisce le righe grezze, salta la sintesi interna
    validate_cypher=True,   # corregge la direzione delle relazioni secondo lo schema
    allow_dangerous_requests=True,
)
```

Due scelte meritano una spiegazione:

- *`return_direct=True`.* Di norma `GraphCypherQAChain` fa *due* chiamate all'LLM: una per generare il Cypher, una per trasformare i risultati in prosa. Qui la seconda è disattivata: la catena è usata *solo per il retrieval* e restituisce le righe grezze. La trasformazione in risposta discorsiva è centralizzata altrove, in *un'unica* chiamata di sintesi per l'intero turno. Così una domanda composta da tre sotto-domande costa una sola sintesi invece di tre, risparmiando chiamate.
- *`validate_cypher=True`.* Corregge automaticamente le direzioni delle frecce nelle relazioni per farle combaciare con lo schema, evitando che un arco orientato al contrario restituisca silenziosamente un risultato vuoto.

Lo *schema del grafo viene iniettato automaticamente* nel prompt da `Neo4jGraph`, che lo introspetta: il modello conosce quindi etichette, proprietà e relazioni disponibili quando genera la query.

== Progettazione del prompt Cypher

Il prompt di generazione (`CYPHER_GENERATION_TEMPLATE`) codifica una serie di regole nate dagli errori tipici dei modelli piccoli su Text-to-Cypher:

- *Relazioni bidirezionali senza frecce.* Si impone la sintassi piatta `-[:REL]-` senza `<`/`>`. Un modello che indovina la direzione sbagliata produrrebbe risultati vuoti; togliendo l'orientamento il match funziona a prescindere.
- *Case-insensitive.* Confronti sempre con `toLower(...)` su entrambi i lati, per non fallire su differenze di maiuscole.
- *Ricerca per contenimento.* Musei e opere sono cercati con `CONTAINS` sul nome anziché per uguaglianza esatta, per tollerare titoli parziali ("Flagellazione", "Capodimonte").
- *Disambiguazione degli artisti.* Istruzioni esplicite per non confondere Caravaggio (`Merisi`) e Caracciolo (`Battistello`), che restano due nodi distinti.
- *Alias obbligatori sugli aggregati.* Ogni `count`/`collect`/`sum` deve avere un `AS` leggibile, così le righe restituite hanno chiavi comprensibili per la sintesi.
- *Gestione di entità multiple.* Quando la domanda riguarda più opere, si impone un unico pattern con `WHERE ... IN [...]` restituendo ogni entità col proprio valore, anziché legarle tutte allo stesso nodo (errore che spesso produce risultati vuoti).

== Esecuzione parallela e resilienza

Nel nodo di generazione, le sotto-domande *in ambito* sono deduplicate e interrogate *in parallelo* con un `ThreadPoolExecutor` (fino a 5 worker): poiché ogni query è indipendente e passa gran parte del tempo in attesa di rete/DB, il parallelismo abbatte la latenza del turno. Ogni query ha inoltre una *politica di retry* (fino a 3 tentativi) sui risultati vuoti o sulle eccezioni, per assorbire la variabilità del Cypher generato dall'LLM.

// ============================================================
= Sintesi della risposta
// ============================================================

Recuperate le righe dal grafo, un'*unica* chiamata all'LLM (`COMBINE_PROMPTS_TEMPLATE`) le fonde in una risposta coerente in italiano. Il prompt di sintesi è fortemente vincolato nello stile, per contrastare le tendenze indesiderate dei modelli generativi:

- risposta *concisa* (3–4 frasi), diretta al dato, senza premesse né inviti finali;
- *divieto di citare la fonte* ("secondo il database", "nel mio archivio"): il modello deve rispondere come se conoscesse i fatti;
- *divieto di disclaimer* quando i dati ci sono, e uso di *tutti e soli* i valori presenti (se è una lista, elencarli tutti senza inventarne);
- se i dati di una sotto-domanda sono vuoti, quella informazione è dichiarata non disponibile senza inventare, rispondendo comunque alle altre.

Alle sotto-domande *fuori ambito* è riservata una nota fissa che ricorda i confini del dominio, concatenata alla risposta in-ambito. In questo modo una richiesta mista riceve una risposta completa e onesta: dati reali dove il grafo li ha, delimitazione esplicita dove no.

#notebox("Perché sintesi separata dal retrieval")[
  Separare il recupero (una query per sotto-domanda) dalla sintesi (una sola chiamata per turno) è la scelta architetturale che tiene basso il numero di invocazioni dell'LLM e centralizza il controllo dello stile in un unico prompt, invece di disperderlo nella generazione interna della catena.
]

// ============================================================
= Interfaccia e canale vocale
// ============================================================

== Interfaccia Gradio

`ChatController` costruisce l'interfaccia e ne espone gli handler. Ogni turno è diviso in *due eventi concatenati* (`step 1 .then(step 2)`): il primo aggiunge subito il messaggio dell'utente alla chat (feedback immediato), il secondo calcola la risposta mostrando l'animazione di caricamento nativa. Sono supportati due ingressi — testo e microfono — che convergono sullo stesso passo di generazione.

Lo stato di sessione (`SessionState`, in `gr.State`) conserva due informazioni: il `thread_id` della conversazione e un flag `awaiting_clarification`, che indica se il messaggio successivo va instradato come *risposta a un chiarimento* anziché come nuova domanda. Il pulsante "Nuova conversazione" rigenera il `thread_id`, ripulendo di fatto la storia.

== Voce: Whisper e gTTS

Il riconoscimento vocale (`SpeechToText`) usa *Whisper large-v3* tramite la pipeline di `transformers`, forzando la lingua italiana e adattando il formato audio `(sample_rate, ndarray)` prodotto dal microfono di Gradio. La sintesi vocale (`TextToSpeech`) usa *gTTS* per generare l'mp3 della risposta. La sintesi è *tollerante ai guasti*: se il servizio TTS fallisce, il turno mostra comunque la risposta testuale, semplicemente senza audio.

// ============================================================
= Sintesi delle scelte architetturali
// ============================================================

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 8pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Scelta*], [*Motivazione*],
  [Knowledge graph invece di RAG vettoriale], [Il dominio è fattuale e relazionale (chi ha dipinto cosa, esposta dove): un grafo risponde con precisione a conteggi e relazioni, dove l'embedding sarebbe approssimativo.],
  [LLM come traduttore/sintetizzatore], [Ancora le risposte a dati verificabili nel grafo, riducendo le allucinazioni; il modello non è la fonte di verità.],
  [LLM locale via Ollama], [Nessun costo per token né chiave API; esecuzione interamente in locale, adatta a un progetto didattico.],
  [Grafo di stato LangGraph], [Rende esplicito e manutenibile il flusso decisionale del turno, con chiarimenti human-in-the-loop e persistenza per conversazione.],
  [Output strutturato Pydantic], [Trasforma la classificazione in un contratto tipizzato, eliminando il parsing fragile di testo libero.],
  [Scomposizione + risoluzione riferimenti], [Permette di gestire domande composte e conversazionali, isolando sotto-domande auto-contenute per il retrieval.],
  [Retrieval parallelo + sintesi unica], [Minimizza latenza e numero di chiamate LLM, centralizzando lo stile in un solo prompt.],
  [Cache SPARQL e Wikipedia], [Rende la ricostruzione del database rapida e rispettosa dei rate limit delle fonti.],
  [Degradazione elegante (voce, retry, fallback)], [Il sistema resta utilizzabile anche quando un componente esterno o l'LLM falliscono transitoriamente.],
)

#v(1cm)
#align(center)[
  #line(length: 30%, stroke: 0.6pt + accent)
  #v(0.3cm)
  #text(size: 9pt, style: "italic", fill: luma(100))[
    Documento generato come descrizione tecnica dell'architettura del progetto.
  ]
]
