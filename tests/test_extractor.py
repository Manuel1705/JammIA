"""Test di Extractor: normalizzazione dei binding SPARQL (nessuna rete)."""
from chatbot.ingestion.extractor import Extractor


def _binding(campi: dict) -> dict:
    """Costruisce un binding SPARQL {chiave: {"value": ...}} dai campi dati."""
    return {k: {"value": v} for k, v in campi.items()}


def test_valore_default_su_campo_assente():
    assert Extractor._valore({}, "assente") == ""
    assert Extractor._valore({}, "assente", "N/D") == "N/D"
    assert Extractor._valore(_binding({"x": "ciao"}), "x") == "ciao"


def test_estrai_artisti_fallback_movimenti():
    # Wikidata non restituisce i movimenti -> deve subentrare MOVIMENTI_DEFAULT
    e = Extractor.__new__(Extractor)  # senza __init__ per non toccare la cache su disco
    risultati = [_binding({
        "artista": "http://www.wikidata.org/entity/Q42207",
        "nome": "Caravaggio",
        "dataNascita": "1571-09-29T00:00:00Z",
        "luogoNascitaLabel": "Milano",
        "movimenti": "",
        "opereNotevoli": "",
    })]
    artisti = e.estrai_artisti(risultati)
    assert artisti[0]["wikidata_id"] == "Q42207"
    assert artisti[0]["data_nascita"] == "1571-09-29"  # troncata a YYYY-MM-DD
    assert artisti[0]["movimenti"] == "Barocco, Controriforma"


def test_estrai_coordinate_valide_e_invalide():
    # WKT valido: 'Point(lon lat)' -> (lat, lon)
    assert Extractor._estrai_coordinate("Point(14.2681 40.8518)") == ("40.8518", "14.2681")
    # input vuoto o malformato -> ("", "") senza sollevare eccezioni
    assert Extractor._estrai_coordinate("") == ("", "")
    assert Extractor._estrai_coordinate("roba non valida") == ("", "")


def test_estrai_opere_descrizione_fallback_su_sparql(monkeypatch):
    # se Wikipedia non trova la descrizione, va mantenuta quella presa da Wikidata (SPARQL)
    e = Extractor.__new__(Extractor)
    e._cache_wikipedia = {}
    monkeypatch.setattr(e, "descrizioni_wikipedia", lambda titoli: {t: "" for t in titoli})

    risultati = [_binding({
        "opera": "http://www.wikidata.org/entity/Q999",
        "nome": "Opera Senza Pagina Wiki",
        "descrizione": "Descrizione da Wikidata",
    })]
    opere = e.estrai_opere(risultati, artista_id="Q42207")
    assert opere[0]["descrizione"] == "Descrizione da Wikidata"


def test_estrai_opere_descrizione_wikipedia_ha_priorita(monkeypatch):
    # se Wikipedia trova la descrizione, sovrascrive quella di Wikidata
    e = Extractor.__new__(Extractor)
    e._cache_wikipedia = {}
    monkeypatch.setattr(e, "descrizioni_wikipedia",
                        lambda titoli: {t: "Estratto da Wikipedia" for t in titoli})

    risultati = [_binding({
        "opera": "http://www.wikidata.org/entity/Q1",
        "nome": "Opera Con Pagina Wiki",
        "descrizione": "Descrizione da Wikidata",
    })]
    opere = e.estrai_opere(risultati, artista_id="Q42207")
    assert opere[0]["descrizione"] == "Estratto da Wikipedia"
