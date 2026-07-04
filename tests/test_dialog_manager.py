"""Test di DialogManager: parsing dell'analisi, retry sulla chain, regressione echo (nessuna rete/LLM)."""
from types import SimpleNamespace

import pytest

from chatbot.dialog.manager import DialogManager


def _llm_che_risponde(testo):
    """Finto LLM: .invoke(prompt) -> oggetto con .content = testo fisso."""
    return SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=testo))


def _dm_solo_analisi(output_llm):
    """DialogManager senza __init__ (niente grafo/SQLite), con solo l'LLM finto impostato."""
    dm = DialogManager.__new__(DialogManager)
    dm._llm_riferimenti = _llm_che_risponde(output_llm)
    return dm


# ── _analizza_domanda: parsing dei tre formati ────────────────

def test_analizza_query_semplice():
    dm = _dm_solo_analisi("QUERY\nIN: Quante opere di Caravaggio a Napoli?")
    r = dm._analizza_domanda("Quante opere di Caravaggio a Napoli?", {"cronologia": []})
    assert r == {"tipo": "query",
                 "sotto_domande": [{"testo": "Quante opere di Caravaggio a Napoli?", "in_ambito": True}]}


def test_analizza_query_composta_con_ambito():
    # una parte in ambito (Caravaggio) e una fuori (Botticelli)
    dm = _dm_solo_analisi("QUERY\nIN: Opere di Caravaggio a Napoli?\nFUORI: Opere di Botticelli?")
    r = dm._analizza_domanda("...", {"cronologia": []})
    assert r["tipo"] == "query"
    assert r["sotto_domande"] == [
        {"testo": "Opere di Caravaggio a Napoli?", "in_ambito": True},
        {"testo": "Opere di Botticelli?", "in_ambito": False},
    ]


def test_analizza_query_etichetta_mancante_default_in_ambito():
    # se il modello omette l'etichetta, la sotto-domanda è considerata in ambito per prudenza
    dm = _dm_solo_analisi("QUERY\nQuante opere di Caravaggio a Napoli?")
    r = dm._analizza_domanda("...", {"cronologia": []})
    assert r["sotto_domande"] == [{"testo": "Quante opere di Caravaggio a Napoli?", "in_ambito": True}]


def test_analizza_chiarimento():
    dm = _dm_solo_analisi("CHIARIMENTO: Di quale opera parli?")
    r = dm._analizza_domanda("chi l'ha dipinta?", {"cronologia": []})
    assert r == {"tipo": "chiarimento", "testo": "Di quale opera parli?"}


def test_analizza_diretta():
    dm = _dm_solo_analisi("DIRETTA: Prego, è stato un piacere!")
    r = dm._analizza_domanda("grazie!", {"cronologia": []})
    assert r == {"tipo": "diretta", "testo": "Prego, è stato un piacere!"}


def test_analizza_fallback_senza_riga_query():
    # se il modello dimentica la riga "QUERY", le righe restano comunque sotto-domande (in ambito)
    dm = _dm_solo_analisi("Quante opere di Caravaggio a Napoli?")
    r = dm._analizza_domanda("Quante opere di Caravaggio a Napoli?", {"cronologia": []})
    assert r["tipo"] == "query"
    assert r["sotto_domande"] == [{"testo": "Quante opere di Caravaggio a Napoli?", "in_ambito": True}]


# ── _invoca_chain_con_retry: recupero e fallback ──────────────

def test_retry_recupera_dopo_errori():
    dm = DialogManager.__new__(DialogManager)
    tentativi = {"n": 0}

    def chain_flaky(params):
        tentativi["n"] += 1
        if tentativi["n"] < 3:
            raise Exception("SyntaxError Cypher")
        return {"result": "Ci sono 2 opere."}

    dm._chain = SimpleNamespace(invoke=chain_flaky)
    assert dm._invoca_chain_con_retry("q", "q", max_retry=3) == "Ci sono 2 opere."
    assert tentativi["n"] == 3


def test_retry_fallback_dopo_esaurimento():
    dm = DialogManager.__new__(DialogManager)
    dm._chain = SimpleNamespace(invoke=lambda p: (_ for _ in ()).throw(Exception("sempre rotto")))
    r = dm._invoca_chain_con_retry("Quali musei?", "Quali musei?", max_retry=2)
    assert "Non sono riuscito" in r and "Quali musei?" in r


# ── regressione echo: reset di `risposta` tra i turni ─────────

def test_risolvi_riferimenti_azzera_risposta_su_query():
    # una nuova QUERY deve azzerare la `risposta` del turno precedente, altrimenti il conditional
    # edge salterebbe genera_risposta e ripeterebbe la risposta vecchia (echo)
    dm = _dm_solo_analisi("QUERY\nIN: Quante opere di Caravaggio?")
    out = dm._risolvi_riferimenti({"domanda": "Quante opere di Caravaggio?", "cronologia": []})
    assert out["risposta"] is None
    assert out["sotto_domande"] == [{"testo": "Quante opere di Caravaggio?", "in_ambito": True}]


def test_genera_risposta_unisce_le_sottodomande():
    dm = DialogManager.__new__(DialogManager)
    dm._chain = SimpleNamespace(invoke=lambda p: {"result": "Due opere di Caravaggio."})
    state = {"sotto_domande": [{"testo": "Opere di Caravaggio a Napoli?", "in_ambito": True}]}
    out = dm._genera_risposta(state)
    assert out["risposta"] == "Due opere di Caravaggio."


def test_genera_risposta_fuori_ambito_non_interroga_la_chain():
    # una sotto-domanda fuori ambito riceve il messaggio fisso senza chiamare la chain
    from chatbot.dialog.manager import MESSAGGIO_FUORI_AMBITO

    dm = DialogManager.__new__(DialogManager)
    chiamate = {"n": 0}

    def chain(params):
        chiamate["n"] += 1
        return {"result": "opere di Caravaggio"}

    dm._chain = SimpleNamespace(invoke=chain)
    state = {"sotto_domande": [
        {"testo": "Opere di Caravaggio a Napoli?", "in_ambito": True},
        {"testo": "Opere di Botticelli?", "in_ambito": False},
    ]}
    out = dm._genera_risposta(state)
    assert "opere di Caravaggio" in out["risposta"]
    assert MESSAGGIO_FUORI_AMBITO in out["risposta"]
    assert chiamate["n"] == 1  # la chain è chiamata SOLO per la sotto-domanda in ambito
