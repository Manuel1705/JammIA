"""Test di SparqlExecutor: caricamento query e round-trip della cache (nessuna rete)."""
import json

from chatbot import config
from chatbot.ingestion.sparql_executor import SparqlExecutor, carica_query


def test_carica_query_esiste():
    testo = carica_query("query_artisti.psql")
    assert "SELECT" in testo.upper()


def test_query_namedtuple_carica_le_quattro_query():
    ex = SparqlExecutor()
    for testo in (ex.query.artisti, ex.query.opere_caravaggio,
                  ex.query.opere_caracciolo, ex.query.musei):
        assert "SELECT" in testo.upper()


def test_cache_round_trip(tmp_path, monkeypatch):
    # reindirizzo la cache su un file temporaneo per non toccare quella reale
    cache_finta = tmp_path / "cache_sparql.json"
    monkeypatch.setattr(config, "CACHE_SPARQL", cache_finta)

    ex = SparqlExecutor()
    originale = ex.Risultati(
        artisti=[{"a": 1}], opere_caravaggio=[], opere_caracciolo=[], musei=[{"m": 2}]
    )
    ex._salva_cache(originale)

    # il file salvato usa i nomi di campo del NamedTuple
    salvato = json.loads(cache_finta.read_text(encoding="utf-8"))
    assert set(salvato.keys()) == {"artisti", "opere_caravaggio", "opere_caracciolo", "musei"}

    ricaricato = ex._carica_cache()
    assert ricaricato == originale


def test_esegui_tutte_usa_la_cache_senza_rete(tmp_path, monkeypatch):
    cache_finta = tmp_path / "cache_sparql.json"
    monkeypatch.setattr(config, "CACHE_SPARQL", cache_finta)

    ex = SparqlExecutor()
    atteso = ex.Risultati(artisti=[{"a": 1}], opere_caravaggio=[], opere_caracciolo=[], musei=[])
    ex._salva_cache(atteso)

    # se _esegui venisse chiamato (rete) il test fallirebbe: la cache deve bastare
    monkeypatch.setattr(ex, "_esegui", lambda q: (_ for _ in ()).throw(AssertionError("rete!")))
    assert ex.esegui_tutte() == atteso
