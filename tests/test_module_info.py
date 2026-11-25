"""Tests du module Information (module_info.py), SANS Ollama : le LLM est simulé.

Lancement depuis la racine du projet : pytest tests/
"""

import json
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import module_info as mi  # noqa: E402

MAINTENANT = datetime(2026, 11, 25, 12, 0)
REGLAGES = {"url": "http://localhost:11434", "modele": "test", "actif": True}


def article(titre, heures=2, lien=None, score=None):
    return {"titre": titre, "source": "Les Echos", "lien": lien or titre,
            "date": (MAINTENANT - timedelta(hours=heures)).strftime("%Y-%m-%d %H:%M"),
            "score_sentiment": score}


def faux_llm(scores):
    """Remplace l'appel à Ollama : renvoie les scores donnés, dans le format imposé."""
    def appeler(messages, reglages):
        return json.dumps({"notes": [{"numero": i, "score": s, "raison": f"raison {i}"}
                                     for i, s in enumerate(scores, start=1)]})
    return appeler


def test_pas_d_actualite_recente_indisponible():
    note, _ = mi.noter_info("AI.PA", [], REGLAGES, MAINTENANT)
    assert note == {"action": "AI.PA", "score": None, "disponible": False,
                    "raisons": ["aucune actualité de moins de 7 jours"]}


def test_note_par_le_llm_format_commun(monkeypatch):
    monkeypatch.setattr(mi, "appeler_ollama", faux_llm([0.8, 0.4]))
    note, articles = mi.noter_info("AI.PA", [article("Air Liquide relève ses objectifs"),
                                             article("Air Liquide signe un contrat", heures=30)],
                                   REGLAGES, MAINTENANT)
    assert set(note) == {"action", "score", "raisons", "disponible"} and note["disponible"]
    assert 0.4 < note["score"] < 0.8                       # l'article le plus récent pèse plus
    assert note["raisons"][0].startswith("bonne nouvelle : « Air Liquide relève ses objectifs »")
    assert "raison 1" in note["raisons"][0]
    assert [a["score_sentiment"] for a in articles] == [0.8, 0.4]


def test_llm_absent_bascule_sur_le_lexique(monkeypatch):
    def ollama_eteint(messages, reglages):
        raise mi.LLMIndisponible("Ollama injoignable")
    monkeypatch.setattr(mi, "appeler_ollama", ollama_eteint)
    note, _ = mi.noter_info("AI.PA", [article("Air Liquide : chute après un avertissement")],
                            REGLAGES, MAINTENANT)
    assert note["disponible"] and note["score"] == -1
    assert note["raisons"][0].startswith("mauvaise nouvelle")


def test_reponse_incomplete_du_llm_refusee(monkeypatch):
    monkeypatch.setattr(mi, "appeler_ollama", faux_llm([0.5]))          # 1 note pour 2 titres
    with pytest.raises(mi.LLMIndisponible):
        mi.noter_avec_llm("Air Liquide", ["titre 1", "titre 2"], REGLAGES)


def test_titre_deja_note_pas_renvoye_au_llm(monkeypatch):
    def interdit(messages, reglages):
        raise AssertionError("le LLM ne doit pas être appelé")
    monkeypatch.setattr(mi, "appeler_ollama", interdit)
    note, _ = mi.noter_info("AI.PA", [article("déjà noté", score=0.5)], REGLAGES, MAINTENANT)
    assert note["score"] == 0.5


def test_lexique():
    assert mi.noter_avec_lexique("Capgemini bondit, résultats supérieurs aux attentes")[0] > 0
    assert mi.noter_avec_lexique("Hermès recule en Bourse")[0] < 0
    assert mi.noter_avec_lexique("Assemblée générale de TotalEnergies")[0] == 0


def test_analyser_lit_la_base_et_enregistre_les_sentiments(tmp_path, monkeypatch):
    engine = db.creer_base(db.get_engine(f"sqlite:///{tmp_path / 'test.db'}"))
    recent = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    db.enregistrer_actualites(engine, "AI.PA", [{"titre": "Air Liquide en hausse", "lien": "l1",
                                                 "date": recent, "source": "Boursorama"}])
    monkeypatch.setattr(mi, "appeler_ollama", faux_llm([0.6]))
    note = mi.analyser("AI.PA", engine)
    assert note["score"] == 0.6
    assert db.lire_actualites(engine, "AI.PA")[0]["score_sentiment"] == 0.6
