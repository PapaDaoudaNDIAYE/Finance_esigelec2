"""Tests des modules Financier et Risque (module_financier.py).

Lancement depuis la racine du projet : pytest tests/
Aucun accès internet : les données sont fabriquées dans les tests.
"""

import json
import os
import sys

import numpy as np
import pytest

# Permet d'importer module_financier.py, qui est à la racine du projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import module_financier as mf  # noqa: E402

CLES_FORMAT_COMMUN = {"action", "score", "raisons", "disponible"}


def cours_simules(volatilite_annuelle, n=260, graine=1):
    """Fabrique n cours de clôture avec la volatilité annuelle demandée."""
    rng = np.random.default_rng(graine)
    rendements = rng.normal(0, volatilite_annuelle / np.sqrt(252), n)
    return list(100 * np.exp(np.cumsum(rendements)))


# ----------------------------------------------------------------------------- outils

def test_note_lineaire_dans_les_deux_sens():
    assert mf.note_lineaire(12, bon=12, mauvais=30) == 1      # PER bas = bon
    assert mf.note_lineaire(21, bon=12, mauvais=30) == 0      # à mi-chemin
    assert mf.note_lineaire(40, bon=12, mauvais=30) == -1     # au-delà : reste à -1
    assert mf.note_lineaire(0.20, bon=0.20, mauvais=0.05) == 1  # marge haute = bon


def test_pourcentages_acceptes_dans_les_deux_ecritures():
    assert mf.en_fraction(10) == 0.10
    assert mf.en_fraction(0.10) == 0.10


# ----------------------------------------------------------------------------- module Financier

def test_financier_format_commun_et_note_entre_moins_un_et_un():
    res = mf.noter_financier("AI.PA", {"per": 33.9, "croissance": -0.004, "marge": 0.131,
                                       "dette": 2.0, "dividende": 0.018})
    assert set(res) == CLES_FORMAT_COMMUN
    assert res["disponible"] is True
    assert -1 <= res["score"] <= 1
    assert 1 <= len(res["raisons"]) <= mf.NB_RAISONS_FINANCIER


def test_financier_entreprise_saine_note_positive():
    res = mf.noter_financier("X", {"per": 10, "croissance": 0.12, "marge": 0.25, "dette": -0.5,
                                   "dividende": 0.05})
    assert res["score"] == 1
    # Dette nette négative = trésorerie nette : expliquée au client
    seule_dette = mf.noter_financier("X", {"dette": -0.5})
    assert seule_dette["score"] == 1 and "trésorerie" in seule_dette["raisons"][0]


def test_financier_per_negatif_signale_une_perte():
    res = mf.noter_financier("X", {"per": -5})
    assert res["score"] == -1
    assert "perte" in res["raisons"][0]


def test_financier_sans_donnees_indisponible_sans_planter():
    for vide in (None, {}, {"per": None}):
        res = mf.noter_financier("X", vide)
        assert res["disponible"] is False and res["score"] is None


# ----------------------------------------------------------------------------- module Risque

def test_risque_action_calme_note_positive():
    res = mf.noter_risque("X", cours_simules(0.12))
    assert set(res) == CLES_FORMAT_COMMUN
    assert res["score"] > 0
    assert "volatilité" in res["raisons"][0]


def test_risque_action_agitee_note_negative_et_alerte():
    res = mf.noter_risque("X", cours_simules(0.80))
    assert res["score"] <= -0.5
    assert res["raisons"][0].startswith("alerte")


def test_risque_historique_trop_court_indisponible():
    res = mf.noter_risque("X", [100.0] * 10)
    assert res["disponible"] is False


def test_monte_carlo_reproductible():
    c = cours_simules(0.30)
    assert mf.simulation_monte_carlo(c) == mf.simulation_monte_carlo(c)


# ----------------------------------------------------------------------------- base de données

@pytest.fixture
def base(tmp_path):
    """Petite base SQLite de test avec les tables fondamentaux et cours du README."""
    from sqlalchemy import create_engine, text
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with engine.begin() as cx:
        cx.execute(text("CREATE TABLE fondamentaux (ticker TEXT, date TEXT, per REAL, croissance REAL, "
                        "marge REAL, dette REAL, dividende REAL)"))
        cx.execute(text("INSERT INTO fondamentaux VALUES ('AI.PA', '2026-11-24', 33.9, -0.004, 0.131, 2.0, 0.018)"))
        cx.execute(text("CREATE TABLE cours (ticker TEXT, date TEXT, ouverture REAL, haut REAL, bas REAL, "
                        "cloture REAL, volume REAL)"))
        for i, c in enumerate(cours_simules(0.18)):
            cx.execute(text("INSERT INTO cours VALUES ('AI.PA', :d, :c, :c, :c, :c, 0)"),
                       {"d": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "c": c})
    return engine


def test_lecture_en_base_et_ecriture_des_scores(base):
    from sqlalchemy import text
    fin = mf.analyser_financier("AI.PA", base)
    risque = mf.analyser_risque("AI.PA", base)
    assert fin["disponible"] and risque["disponible"]
    mf.enregistrer_score(base, fin, "financier")
    mf.enregistrer_score(base, fin, "financier")            # 2e fois le même jour : pas de doublon
    with base.connect() as cx:
        lignes = cx.execute(text("SELECT * FROM scores")).mappings().all()
    assert len(lignes) == 1
    assert json.loads(lignes[0]["raisons"]) == fin["raisons"]


def test_action_absente_de_la_base_indisponible(base):
    assert mf.analyser_financier("RMS.PA", base)["disponible"] is False
    assert mf.analyser_risque("RMS.PA", base)["disponible"] is False
