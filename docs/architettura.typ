// ============================================================
//  Documentazione tecnica — Chatbot Caravaggio & Caracciolo
// ============================================================

#set document(title: "JammIA — Architettura del chatbot su Caravaggio e Caracciolo", author: "Manuel Mignogna")
#set page(
  paper: "a4",
  margin: (x: 2.4cm, y: 2.6cm),
  numbering: "1",
  number-align: center,
)
#set text(font: "New Computer Modern", lang: "it", size: 10.5pt)
#set par(justify: true, leading: 0.68em)
// Nelle celle delle tabelle il testo giustificato crea spaziature brutte: allineamento a sinistra
#show table: set par(justify: false)
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
  #text(size: 30pt, weight: "bold", fill: accent)[
    JammIA
  ]
  #v(0.3cm)
  #text(size: 15pt)[Chatbot conversazionale su Caravaggio e Caracciolo \ e i musei di Napoli]
  #v(0.4cm)
  #text(size: 14pt)[Documentazione tecnica dell'architettura]
  #v(0.2cm)
  #line(length: 40%, stroke: 0.8pt + accent)
  #v(2.5cm)
  #text(size: 10.5pt, style: "italic")[
    Progetto di Natural Language Processing \
    Corso di Laurea Magistrale
  ]
  #v(1fr)
  #text(size: 10pt, fill: luma(90))[Manuel Mignogna, Alessia Previdente]
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

Il progetto realizza *JammIA*, un assistente conversazionale specializzato sulle opere dei pittori *Michelangelo Merisi da Caravaggio* e *Giovanni Battista Caracciolo* (detto Battistello) e i musei di Napoli che le espongono. L'utente può porre domande sia a voce sia per iscritto, e il sistema risponde con testo e sintesi vocale, attingendo a un grafo di conoscenza costruito a partire da fonti aperte (Wikidata e Wikipedia).

L'architettura si articola in *due sottosistemi indipendenti*, separati nel tempo e nelle responsabilità:

+ *Pipeline di ingestion (offline).* Interroga Wikidata via SPARQL, arricchisce i dati con le descrizioni testuali di Wikipedia e materializza il tutto in un knowledge graph Neo4j. Viene eseguita una tantum (o quando si vuole rigenerare la base dati) tramite `build_database.py`.

+ *Sistema conversazionale (runtime).* All'avvio (`app.py`) espone un'interfaccia Gradio. Ogni turno di dialogo passa attraverso un grafo di stato LangGraph che classifica la richiesta, la scompone in sotto-domande, recupera i dati dal grafo tramite RAG Text-to-Cypher e sintetizza una risposta in linguaggio naturale, infine convertita in voce.

Il principio di fondo è la *separazione tra conoscenza e ragionamento*: i fatti risiedono in modo strutturato nel grafo, mentre l'LLM è usato come traduttore (linguaggio naturale → Cypher) e come sintetizzatore (dati → risposta), non come fonte di verità. Questo riduce le allucinazioni e ancora le risposte a dati verificabili.

== Il flusso di un turno

Un turno attraversa il sistema in questo ordine:

+ *Input.* L'utente scrive nel campo di testo oppure parla al microfono; in tal caso Whisper trascrive l'audio (normalizzato in mono float32 nell'intervallo $[-1, 1]$, con lingua forzata all'italiano).
+ *Instradamento.* `ChatController` inoltra la domanda al `DialogManager` con il `thread_id` della sessione. Se il turno precedente si era sospeso con una domanda di chiarimento, il messaggio riprende il grafo dal punto di sospensione (`Command(resume=...)`); altrimenti parte una nuova invocazione del grafo.
+ *Classificazione.* Il primo nodo classifica la richiesta in tre esiti: _chitchat_ (il classificatore stesso formula la risposta sociale), _clarification_ (il grafo si sospende e chiede all'utente), _query_ (la richiesta è scomposta in sotto-domande atomiche auto-contenute, ciascuna marcata `in_scope`).
+ *Retrieval RAG.* Ogni sotto-domanda in ambito è tradotta in Cypher dall'LLM, eseguita su Neo4j (in parallelo tra sotto-domande) e produce righe grezze.
+ *Sintesi.* Un'unica chiamata LLM fonde tutte le righe in una risposta italiana coerente; alle parti fuori ambito è concatenata una nota fissa sui confini del dominio.
+ *Chiusura.* Il turno (domanda + risposta) è accodato alla cronologia; la risposta è sintetizzata in voce con gTTS (se il servizio fallisce, resta il solo testo) e restituita alla UI come testo + audio.

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
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Libreria*], [*Ruolo e motivazione*],
  [`langchain-ollama`], [*LLM locale* (`ChatOllama`) — esegue Gemma via Ollama (o backend compatibili) senza costi né chiavi API: è il provider di default.],
  [`langchain-google-genai`], [*LLM cloud* (`ChatGoogleGenerativeAI`) — provider alternativo (Gemini via API key): stessa interfaccia LangChain, selezionabile con `LLM_PROVIDER=gemini` senza modifiche al codice.],
  [`langgraph`], [*Grafo di stato del dialogo* — modella il turno come macchina a stati con nodi, edge condizionali e human-in-the-loop (`interrupt`); include il checkpointer `MemorySaver`.],
  [`MemorySaver` (langgraph)], [*Persistenza dello stato* — checkpointer in memoria che conserva lo stato della conversazione tra i turni, indicizzato per `thread_id`; adeguato a un'app a processo singolo (lo stato si azzera al riavvio).],
  [`langchain-neo4j`], [*RAG sul grafo* — fornisce `Neo4jGraph` e `GraphCypherQAChain` (Text-to-Cypher) pronti all'uso.],
  [`pydantic`], [*Modelli tipizzati* — definisce lo schema dell'output del classificatore (`ModelResponse`) e lo stato del dialogo (`DialogState`); l'output JSON del modello è validato con `model_validate_json`.],
)

== Dati, voce e interfaccia

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Libreria*], [*Ruolo e motivazione*],
  [`sparqlwrapper`], [*Client SPARQL* — interroga l'endpoint di Wikidata; gestione di formato JSON e header.],
  [`neo4j`], [*Driver del grafo* — accesso diretto a Neo4j per la fase di caricamento (MERGE dei nodi/relazioni).],
  [`transformers` + `torch` + `torchaudio`], [*Speech-to-Text* — eseguono Whisper large-v3 in locale per la trascrizione dell'audio.],
  [`gtts`], [*Text-to-Speech* — sintesi vocale semplice e in italiano della risposta finale.],
  [`gradio`], [*Interfaccia web* — UI chat con supporto nativo a microfono, audio e animazioni di caricamento.],
  [`mlx-lm`], [*Backend Apple Silicon* — abilita l'inferenza ottimizzata su GPU Apple (variante `-mlx` del modello).],
)

== Selezione del dispositivo e del modello

La configurazione (`config.py`) sceglie automaticamente l'acceleratore disponibile (CUDA su NVIDIA/Colab, altrimenti MPS su Apple Silicon, altrimenti CPU) e di conseguenza la variante del modello Gemma (`gemma4:e4b-mlx` su Apple, `gemma:e4b` altrove). Tutte le costanti sensibili (URI e credenziali Neo4j, nomi dei modelli, endpoint, API key) sono lette da variabili d'ambiente con valori di default, così da non essere disseminate nel codice.

La creazione dei chat model è centralizzata nella factory `config.make_llm(temperature)`: `RagChain` e `DialogManager` non conoscono il provider, che si seleziona con `LLM_PROVIDER` (`ollama`, default locale, oppure `gemini` con `GOOGLE_API_KEY` e modello configurabile via `GEMINI_MODEL`). Il resto della pipeline (parsing JSON, grafo di stato, RAG) è indifferente al provider, perché usa la sola interfaccia comune dei chat model LangChain. Con il provider cloud si rinuncia all'esecuzione interamente locale (le domande transitano dai server Google), in cambio di una qualità di classificazione e sintesi sensibilmente superiore.

// ============================================================
= La pipeline di ingestion
// ============================================================

L'obiettivo di questa fase è trasformare dati eterogenei e semi-strutturati (Wikidata) e testi discorsivi (Wikipedia) in un grafo pulito e interrogabile. È orchestrata da `pipeline.populate_database()` e si compone di tre stadi: *estrazione*, *trasformazione/arricchimento*, *caricamento* (un classico ETL).

#notebox("Perché Wikidata e non DBpedia")[
  Come sorgente dei dati strutturati era stata inizialmente valutata *DBpedia*, alternativa naturale a Wikidata e anch'essa interrogabile via SPARQL. In pratica, però, per le opere e gli artisti del dominio DBpedia esponeva proprietà *troppo scarne o del tutto assenti* (date, dimensioni, collocazioni, relazioni), insufficienti a costruire un grafo utile e a produrre risposte di qualità accettabile. Si è quindi scelta *Wikidata*, la cui copertura di entità e proprietà per questo dominio è nettamente più completa e regolare, e che offre un identificativo stabile (Q-ID) su cui ancorare i nodi. Le descrizioni testuali, invece, sono attinte alle API di Wikipedia (v. stadio di trasformazione), più ricche degli abstract disponibili altrove.
]

== Estrazione: le query SPARQL

Le quattro query in `query/*.psql` interrogano Wikidata a partire dagli identificatori dei due artisti (`Q42207` per Caravaggio, `Q2519261` per Caracciolo). Sono state scritte con alcune accortezze ricorrenti:

- *Preferenza linguistica con fallback.* Le etichette sono richieste in italiano e, se assenti, in inglese, tramite `COALESCE(?labelIT, ?labelEN, "default")`. Questo evita campi vuoti quando Wikidata non ha la traduzione italiana.
- *Aggregazione per evitare duplicati.* Proprietà multi-valore (soggetti, movimenti, opere notevoli) sono raccolte con `GROUP_CONCAT(DISTINCT ...)`; i valori singoli con `SAMPLE(...)`, così ogni entità produce una sola riga.
- *Fonti alternative unite con `UNION`.* Il luogo di un'opera è cercato sia come "collocazione" (`P276`) sia come "collezione" (`P195`); l'indirizzo del museo attraverso più proprietà. In questo modo si massimizza la copertura di un grafo di conoscenza notoriamente irregolare.

`SparqlExecutor` carica le query, le esegue con *retry sul rate limit* (HTTP 429, attesa e nuovo tentativo) e *memorizza i risultati in cache* (`cache/sparql_cache.json`). Gli errori non transienti seguono invece una politica _fail-loudly_: l'eccezione risale e interrompe la pipeline, così un fallimento non viene mai salvato in cache come risultato vuoto (che al run successivo maschererebbe per sempre il problema). La cache è cruciale: senza di essa ogni ricostruzione del database rifarebbe decine di richieste a Wikidata, lente e soggette a throttling.

== Trasformazione: `Extractor`

`Extractor` converte le _binding_ SPARQL grezze in dizionari Python puliti e le arricchisce:

- Estrae il Q-ID dagli URI Wikidata, tronca le date alla parte utile (anno o data ISO), e traduce le coordinate dal formato WKT `Point(lon lat)` alla coppia `(lat, lon)`.
- Per le opere, *sostituisce la descrizione sintetica di Wikidata con l'introduzione discorsiva della relativa voce Wikipedia*, recuperata in batch dalle API di Wikipedia IT (`prop=extracts`, solo intro, testo semplice). Anche qui interviene una cache dedicata (`wikipedia_cache.json`) con gestione di redirect e normalizzazioni dei titoli, e throttling per rispettare i limiti del servizio.

Questa scelta è deliberata: le descrizioni di Wikipedia sono molto più ricche e utili per la risposta finale rispetto alle stringhe minimali di Wikidata.

== Caricamento: `Neo4jLoader` e lo schema del grafo

`Neo4jLoader` è implementato come *context manager* (`__enter__`/`__exit__`) per garantire la chiusura del driver Neo4j anche in presenza di eccezioni. 

#pagebreak()
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

L'ordine di caricamento (artisti e musei prima delle opere) non è casuale: `insert_work` cerca artista e museo per creare le relazioni, quindi quei nodi devono già esistere. La ricerca usa `OPTIONAL MATCH` con `FOREACH` condizionale invece di un `MATCH` secco: se un riferimento manca (per esempio un'opera senza museo noto), la relazione corrispondente semplicemente non viene creata, senza troncare in silenzio il resto della query.

// ============================================================
= Il sistema conversazionale: grafo di stato LangGraph
// ============================================================

Il cuore del runtime è `DialogManager`, che modella un turno di dialogo come un *grafo di stato* (`StateGraph`) di LangGraph. Questa scelta permette di rappresentare esplicitamente il flusso decisionale (classificare, eventualmente chiedere chiarimenti, recuperare e rispondere) con edge condizionali invece che con una cascata di `if` annidati.

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

Gli aggiornamenti allo stato usano un `TypedDict` parziale (`DialogStateUpdate`): ogni nodo restituisce solo i campi che modifica, e LangGraph li fonde nello stato. La cronologia è mantenuta *limitata* (ultimi 10 turni salvati, ultimi 3 passati come contesto ai prompt) per contenere la dimensione del prompt; ogni `Turn` è serializzato nel prompt con *ruoli espliciti* ("Utente: ..." / "Assistente (tu): ..."), così il modello riconosce che le risposte precedenti, comprese le offerte del tipo "Se vuoi posso darti informazioni anche su...", sono le sue, e può usarle per risolvere riferimenti impliciti e accettazioni ("sì", "fallo").

Il ciclo di vita dello stato è legato al *checkpointer*: a ogni invocazione LangGraph ricarica lo stato salvato per quel `thread_id`, esegue i nodi fondendo i `DialogStateUpdate`, e alla fine (o alla sospensione per `interrupt`) lo ripersiste. La conversazione è quindi interamente ricostruibile dal solo `thread_id`, e la UI non deve trasportare la cronologia a ogni chiamata.

== I nodi del grafo

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Nodo*], [*Funzione*],
  [`USER_PROMPT_CLASSIFICATION`], [Classifica e scompone la richiesta chiamando l'LLM e validando il JSON prodotto con Pydantic.],
  [`USER_INTENT_CLARIFICATION`], [Sospende il grafo (`interrupt`) e chiede un chiarimento all'utente.],
  [`RESPONSE_GENERATION`], [Esegue il RAG sulle sotto-domande in ambito e sintetizza la risposta.],
  [`HISTORY_UPDATE`], [Accoda il turno corrente alla cronologia e termina.],
)

// ---- Diagramma del grafo di stato (nodi + archi) ----
#let gnode(x, y, w, body, fill) = place(top + left, dx: x * 1cm, dy: y * 1cm,
  box(width: w * 1cm, height: 0.85cm, fill: fill, radius: 4pt,
      stroke: 0.6pt + accent.lighten(30%), inset: 4pt,
      align(center + horizon, text(size: 7.5pt, weight: "bold", fill: black, body))))

#let garrow(x1, y1, x2, y2) = {
  place(top + left, line(start: (x1 * 1cm, y1 * 1cm), end: (x2 * 1cm, y2 * 1cm),
    stroke: 0.8pt + accent))
  let ang = calc.atan2(x2 - x1, y2 - y1)
  place(top + left, dx: x2 * 1cm - 4pt, dy: y2 * 1cm - 4pt,
    rotate(ang, origin: center, text(size: 9pt, fill: accent, [▶])))
}

#let glabel(x, y, body) = place(top + left, dx: x * 1cm, dy: y * 1cm,
  text(size: 6.5pt, style: "italic", fill: luma(90), body))

#figure(
  box(width: 100%, height: 6cm)[
    // archi (disegnati prima dei nodi, così i box li coprono ai bordi)
    #garrow(1.7, 2.9, 2.2, 2.88)                       // START -> classificazione
    #garrow(5.3, 2.68, 6.4, 1.2)                        // classificazione -> cronologia (chitchat)
    #garrow(5.3, 3.02, 6.4, 3.35)                       // classificazione -> generazione
    #garrow(3.75, 3.3, 3.75, 4.6)                       // classificazione -> chiarimento
    #garrow(5.3, 4.9, 6.4, 3.78)                        // chiarimento -> generazione
    #garrow(7.95, 2.9, 7.95, 1.62)                      // generazione -> cronologia
    #garrow(9.5, 1.15, 10.7, 1.15)                      // cronologia -> END
    // etichette
    #glabel(4.75, 1.75, [chitchat])
    #glabel(4.9, 3.5, [sub-questions])
    #glabel(3.9, 3.75, [necessita #linebreak() chiarimento])
    #glabel(2.3, 5.55, [loop ≤ 3 tentativi])
    // nodi
    #gnode(0.2, 2.5, 1.5, [START], luma(230))
    #gnode(2.2, 2.4, 3.1, [USER\_PROMPT\_ #linebreak() CLASSIFICATION], accent.lighten(78%))
    #gnode(6.4, 0.7, 3.1, [HISTORY\_UPDATE], accent.lighten(85%))
    #gnode(6.4, 2.9, 3.1, [RESPONSE\_ #linebreak() GENERATION], accent.lighten(82%))
    #gnode(2.2, 4.6, 3.1, [USER\_INTENT\_ #linebreak() CLARIFICATION], rgb("#efe3cf"))
    #gnode(10.7, 0.75, 1.5, [END], luma(230))
  ],
  caption: [Nodi e archi del grafo di stato del dialogo.],
)

== Il routing condizionale

Dopo la classificazione, una funzione di routing (`_route_after_resolve`) decide il nodo successivo in base a *quali campi dello stato sono valorizzati*, con una precisa priorità:

+ se è presente una `response` (caso chitchat) → si va direttamente all'aggiornamento cronologia, saltando del tutto il grafo;
+ se è presente una `clarification_question` → si va al nodo di chiarimento;
+ se sono presenti `sub_questions` → si va alla generazione della risposta.

Il nodo di chiarimento ha a sua volta un edge condizionale con tre uscite: se dopo la risposta dell'utente la richiesta è ancora ambigua e non si sono superati i *3 tentativi*, si richiede un nuovo chiarimento; se la risposta dell'utente si rivela chitchat (es. "grazie, lascia stare"), la risposta sociale è già pronta nello stato e si passa direttamente all'aggiornamento della cronologia; altrimenti si procede alla generazione. Il limite sui tentativi evita che l'utente resti intrappolato in un ciclo di domande: al terzo fallimento si tenta comunque una risposta con la domanda così com'è.

#figure(
  block(
    fill: codebg,
    inset: 12pt,
    radius: 5pt,
    stroke: 0.5pt + luma(200),
    width: 100%,
    align(left, text(size: 8pt)[
      `START` \
      `  └─▶ USER_PROMPT_CLASSIFICATION` \
      `        ├─ (response, chitchat) ─▶ HISTORY_UPDATE ─▶ END` \
      `        ├─ (clarification) ─▶ USER_INTENT_CLARIFICATION` \
      `        │      ├─ (ancora ambiguo, <3) ─▶ (loop)` \
      `        │      ├─ (chitchat) ─▶ HISTORY_UPDATE ─▶ END` \
      `        │      └─ (risolto / ≥3) ─▶ RESPONSE_GENERATION` \
      `        └─ (sub_questions) ─▶ RESPONSE_GENERATION ─▶ HISTORY_UPDATE ─▶ END`
    ]),
  ),
  caption: [Flusso del grafo di stato del dialogo.],
)

== Human-in-the-loop e persistenza

Il chiarimento sfrutta il meccanismo `interrupt` di LangGraph: il grafo si *sospende* restituendo la domanda all'interfaccia e riprende esattamente da quel punto quando arriva la risposta dell'utente (`Command(resume=...)`). Perché questo funzioni tra due invocazioni HTTP distinte serve un *checkpointer*: lo stato è serializzato (con `JsonPlusSerializer`, istruito sui modelli Pydantic `Turn` e `SubQuestion`) e indicizzato per `thread_id`, cioè per conversazione. Il checkpointer è un `MemorySaver` in memoria: sufficiente per un'app a processo singolo, con l'ovvio compromesso che le conversazioni si azzerano al riavvio.

Il `thread_id` (UUID) è creato *pigramente al primo turno di ogni sessione* Gradio, non alla costruzione della UI: il valore iniziale di `gr.State` viene infatti valutato una sola volta all'avvio e copiato in ogni sessione, quindi generarlo lì significherebbe far condividere a tutti gli utenti la stessa conversazione. Il pulsante di reset genera un nuovo `thread_id`, ripulendo di fatto la storia.

// ============================================================
= Classificazione e scomposizione della richiesta
// ============================================================

Il primo nodo è anche il più delicato: deve decidere *cosa* fare con il messaggio dell'utente prima ancora di toccare il grafo. Chiede all'LLM di produrre un JSON conforme allo schema Pydantic `ModelResponse`, che viene poi validato con `model_validate_json` (la gestione degli output malformati è descritta più avanti, nel paragrafo sulla robustezza). Questo approccio è stato preferito a `with_structured_output` perché la decodifica vincolata (parametro `format` di Ollama) non è garantita da tutti i backend compatibili.

== Lo schema di output: `ModelResponse`

```python
class ModelResponse(BaseModel):
    type: Literal["query", "clarification", "chitchat"]
    sub_questions: Optional[list[SubQuestion]] = None   # se type == query
    clarification_question: Optional[str] = None        # se type == clarification
    response: Optional[str] = None                       # se type == chitchat
```

Ogni tipo usa *un solo campo payload*, senza combinazioni ambigue: questo mantiene la logica di routing pulita (uno switch sul `type` decide quale campo leggere). Per il chitchat il classificatore compila direttamente il campo `response` con la risposta sociale già formulata, così un saluto o un ringraziamento si risolve in *una sola chiamata* all'LLM, senza un secondo passaggio di generazione.

== Le tre categorie

#table(
  columns: (auto, 1fr),
  stroke: 0.5pt + luma(210),
  inset: 7pt,
  fill: (_, y) => if y == 0 { softbg },
  [*Categoria*], [*Quando scatta e cosa produce*],
  [*QUERY*], [La richiesta contiene almeno una domanda su opere/artisti/musei. Viene scomposta in sotto-domande atomiche, ciascuna auto-contenuta e con un flag `in_scope`.],
  [*CLARIFICATION*], [La richiesta richiederebbe una query ma contiene un riferimento implicito che né il messaggio né la storia risolvono (es. "Chi l'ha dipinta?" senza opera nominata).],
  [*CHITCHAT*], [Messaggi puramente sociali (saluti, ringraziamenti) senza alcuna richiesta di informazioni. La risposta è prodotta dallo stesso classificatore nel campo `response`.],
)

== Un prompt per ogni ruolo

Il dialogo usa *tre prompt distinti*, ognuno con una sola responsabilità: il *classificatore* (instradamento, scomposizione delle query e, per il chitchat, formulazione diretta della risposta sociale, con la cronologia a disposizione per presentarsi come JammIA solo al primo scambio e non ripetersi), il *prompt Cypher* (generazione della query dal linguaggio naturale) e il *prompt di sintesi* (dai dati alla risposta discorsiva). Tenerli separati evita che le regole di stile di un ruolo "inquinino" gli altri (per esempio, le istruzioni sul tono della risposta non hanno motivo di comparire nel prompt che genera Cypher) e permette di iterare su ciascuno in isolamento.

== Scelte di prompting

Il prompt del classificatore concentra diverse istruzioni non banali:

- *Risoluzione dei riferimenti (coreference).* Ogni sotto-domanda deve essere riscritta in forma completamente auto-contenuta: dimostrativi e pronomi ("questi quadri", "lui", "lì") vanno sostituiti con il nome esplicito dell'entità, preso dagli scambi precedenti. Chi legge la sotto-domanda non deve aver bisogno della conversazione per capirla, requisito essenziale perché la generazione Cypher a valle riceve le sotto-domande isolate.
- *Scomposizione di richieste composte.* Una domanda che ne contiene più di una viene spezzata in unità atomiche su un solo argomento. Ciò consente di recuperare e poi ricombinare i dati in modo controllato.
- *Marcatura dell'ambito (`in_scope`).* Ogni sotto-domanda è etichettata come dentro o fuori dominio (Caravaggio/Caracciolo, loro opere, musei di Napoli). Le parti fuori ambito non vengono interrogate sul grafo ma gestite con una nota esplicita, così una richiesta mista ("...e quante ne ha fatte Botticelli?") viene comunque servita per la parte pertinente.
- *Bias verso QUERY in caso di dubbio*, per non rifiutare domande legittime, e disambiguazione esplicita tra i due artisti.
- *Offerte accettate.* Se l'ultima risposta dell'assistente si chiudeva con un'offerta concreta ("Se vuoi posso darti informazioni anche su Caracciolo") e l'utente accetta anche genericamente ("sì", "fallo", "vai"), la richiesta è sempre QUERY: l'offerta viene riscritta come domanda esplicita, applicando all'argomento offerto la forma dell'ultima richiesta dell'utente.
- *Chiarimento come ultima risorsa.* CLARIFICATION scatta solo se il riferimento è davvero irrisolvibile; è vietato chiedere conferma di una domanda già capita ("Vuoi sapere X?" implica che X è già la sotto-domanda). Questa regola, insieme alla precedente, evita catene di chiarimenti superflui.

#notebox("Coerenza tra prompt e schema")[
  Poiché l'output è vincolato allo schema Pydantic, le chiavi indicate negli esempi del prompt devono coincidere esattamente con i nomi dei campi (`response`, `clarification_question`, `sub_questions`). Un disallineamento (per esempio suggerire una chiave `text` inesistente nello schema) porta il modello a produrre un campo che viene scartato, lasciando il valore atteso a `None`.
]

== Robustezza

Con modelli locali di piccola taglia l'output JSON può occasionalmente essere malformato o avvolto in testo spurio. La difesa è a due livelli: l'*estrazione tollerante* (`_extract_json`) isola la porzione tra la prima `{` e l'ultima `}`, recuperando i casi più comuni (fence markdown, prefissi come `json`, testo anteposto); per i casi irrecuperabili un *fallback difensivo* intercetta l'errore e degrada verso una richiesta di chiarimento, invece di far crashare l'intero turno. La `temperature` contenuta (0.2) mantiene l'output ragionevolmente stabile senza irrigidirlo del tutto. Analogamente, se il grafo dovesse terminare senza risposta, la UI riceve un messaggio di cortesia invece di un'eccezione.

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
- *Alias obbligatori sugli aggregati.* Ogni `count`/`collect`/`sum` deve avere un `AS` leggibile, così le righe restituite hanno chiavi comprensibili per la sintesi.
- *Gestione di entità multiple.* Quando la domanda riguarda più opere, si impone un unico pattern con `WHERE ... IN [...]` restituendo ogni entità col proprio valore, anziché legarle tutte allo stesso nodo (errore che spesso produce risultati vuoti).

== Esecuzione parallela e resilienza

Nel nodo di generazione, le sotto-domande *in ambito* sono deduplicate e interrogate *in parallelo* con un `ThreadPoolExecutor` (fino a 5 worker): poiché ogni query è indipendente e passa gran parte del tempo in attesa di rete/DB, il parallelismo abbatte la latenza del turno. Ogni query ha inoltre una *politica di retry* (fino a 3 tentativi) *sulle sole eccezioni* (Cypher non valido, errori di connessione): un risultato vuoto su query riuscita è una risposta legittima ("non c'è") e viene restituito subito, senza sprecare chiamate LLM in tentativi inutili.

// ============================================================
= Sintesi della risposta
// ============================================================

Recuperate le righe dal grafo, un'*unica* chiamata all'LLM (`COMBINE_PROMPTS_TEMPLATE`) le fonde in una risposta coerente in italiano. Il prompt di sintesi è fortemente vincolato nello stile, per contrastare le tendenze indesiderate dei modelli generativi:

- risposta *concisa* (3–4 frasi), diretta al dato, senza premesse né inviti finali;
- *divieto di citare la fonte* ("secondo il database", "nel mio archivio"): il modello deve rispondere come se conoscesse i fatti;
- *divieto di disclaimer* quando i dati ci sono, e uso di *tutti e soli* i valori presenti (se è una lista, elencarli tutti senza inventarne);
- se i dati di una sotto-domanda sono vuoti, quella informazione è dichiarata non disponibile senza inventare, rispondendo comunque alle altre;
- tono cordiale e diretto, in italiano chiaro, adatto anche alla sintesi vocale;
- *suggerimento finale vincolato*: la risposta può chiudersi con un'offerta ("Se vuoi posso darti informazioni anche su..."), ma solo su entità in ambito, nominate esplicitamente e non ancora approfondite. Il vincolo di concretezza non è cosmetico: un'offerta esplicita è ciò che permette al classificatore, al turno successivo, di risolvere un'accettazione generica ("sì", "fallo") senza chiedere chiarimenti.

Alle sotto-domande *fuori ambito* è riservata una nota fissa che ricorda i confini del dominio, concatenata alla risposta in-ambito. In questo modo una richiesta mista riceve una risposta completa e onesta: dati reali dove il grafo li ha, delimitazione esplicita dove no.

#notebox("Perché sintesi separata dal retrieval")[
  Separare il recupero (una query per sotto-domanda) dalla sintesi (una sola chiamata per turno) è la scelta architetturale che tiene basso il numero di invocazioni dell'LLM e centralizza il controllo dello stile in un unico prompt, invece di disperderlo nella generazione interna della catena.
]

// ============================================================
= Interfaccia e canale vocale
// ============================================================

== Interfaccia Gradio

`ChatController` costruisce l'interfaccia, brandizzata JammIA, con tema Gradio sui toni dell'azzurro Napoli (passato a `launch()`, come richiesto da Gradio 6), e ne espone gli handler. Ogni turno è diviso in *due eventi concatenati* (`step 1 .then(step 2)`): il primo aggiunge subito il messaggio dell'utente alla chat (feedback immediato), il secondo calcola la risposta. Sono supportati due ingressi, testo e microfono, che convergono sullo stesso passo di generazione.

Lo stato di sessione (`SessionState`, in `gr.State`) conserva due informazioni: il `thread_id` della conversazione (creato pigramente al primo turno, v. sopra) e un flag `awaiting_clarification`, che indica se il messaggio successivo va instradato come *risposta a un chiarimento* anziché come nuova domanda. Il pulsante di reset rigenera il `thread_id`, ripulendo di fatto la storia.

== Voce: Whisper e gTTS

Il riconoscimento vocale (`SpeechToText`) usa *Whisper large-v3* tramite la pipeline di `transformers`, forzando la lingua italiana. L'audio `(sample_rate, ndarray)` prodotto dal microfono di Gradio arriva come interi (tipicamente int16, eventualmente stereo) e viene *normalizzato* nel formato atteso da Whisper (mono, float32, valori in $[-1, 1]$); senza questa normalizzazione la trascrizione degrada sensibilmente. La sintesi vocale (`TextToSpeech`) usa *gTTS* e scrive ogni risposta in un *file temporaneo distinto* (niente file condiviso: eviterebbe race condition tra sessioni concorrenti e audio obsoleto in cache al browser). La sintesi è *tollerante ai guasti*: se il servizio TTS fallisce, il turno mostra comunque la risposta testuale, semplicemente senza audio.
