"""Tests du module Analyse technique (module_technique.py).

Lancement depuis la racine du projet : pytest tests/
Aucun accès internet : les cours sont fabriqués dans les tests.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import module_technique as mt  # noqa: E402

CLES_FORMAT_COMMUN = {"action", "score", "raisons", "disponible"}


def tableau(clotures):
    """Tableau de cours au format de la table « cours » à partir d'une liste de clôtures."""
    c = np.asarray(clotures, dtype=float)
    dates = pd.bdate_range("2025-01-01", periods=len(c)).strftime("%Y-%m-%d")
    return pd.DataFrame({"date": dates, "ouverture": c, "haut": c * 1.005,
                         "bas": c * 0.995, "cloture": c, "volume": 1e6})


def hausse_reguliere(n=260):
    rng = np.random.default_rng(3)
    return 100 * np.exp(np.cumsum(0.003 + rng.normal(0, 0.004, n)))


def baisse_reguliere(n=260):
    rng = np.random.default_rng(4)
    return 100 * np.exp(np.cumsum(-0.003 + rng.normal(0, 0.004, n)))


# ----------------------------------------------------------------------------- indicateurs

def test_rsi_entre_0_et_100():
    df = mt.indicateurs(tableau(hausse_reguliere()))
    valeurs = df["rsi"].dropna()
    assert len(valeurs) > 0
    assert valeurs.between(0, 100).all()


def test_moyennes_mobiles_calculees():
    df = mt.indicateurs(tableau(np.arange(1, 251)))
    assert df["mm20"].iloc[-1] == np.mean(np.arange(231, 251))
    assert pd.isna(df["mm200"].iloc[198]) and not pd.isna(df["mm200"].iloc[199])


def test_bandes_de_bollinger_encadrent_la_moyenne():
    df = mt.indicateurs(tableau(hausse_reguliere())).dropna()
    assert (df["boll_haut"] >= df["mm20"]).all() and (df["boll_bas"] <= df["mm20"]).all()


# ----------------------------------------------------------------------------- notes par famille

def test_rsi_a_25_donne_une_note_positive():
    """Exemple du README : un RSI à 25 donne une note technique positive."""
    df = pd.DataFrame({"rsi": [25.0]})
    note, raison = mt.noter_rsi(df)
    assert note > 0
    assert "survendue" in raison


def test_rsi_a_80_donne_une_note_negative():
    note, raison = mt.noter_rsi(pd.DataFrame({"rsi": [80.0]}))
    assert note < 0 and "surachetée" in raison


def test_cours_sous_la_bande_basse_est_positif():
    df = pd.DataFrame({"cloture": [90.0], "boll_haut": [110.0], "boll_bas": [95.0]})
    note, _ = mt.noter_bollinger(df)
    assert note == 1


def test_cassure_de_resistance_est_positive():
    df = pd.DataFrame({"cloture": [120.0], "support": [90.0], "resistance": [115.0]})
    note, raison = mt.noter_niveaux(df)
    assert note > 0 and "cassure de la résistance" in raison


# ----------------------------------------------------------------------------- note globale

def test_format_commun_et_note_bornee():
    res = mt.noter_technique("AI.PA", tableau(hausse_reguliere()))
    assert set(res) == CLES_FORMAT_COMMUN
    assert res["disponible"] is True
    assert -1 <= res["score"] <= 1
    assert 1 <= len(res["raisons"]) <= mt.NB_RAISONS_TECHNIQUE


def test_tendance_haussiere_et_baissiere():
    hausse = mt.detail_familles(tableau(hausse_reguliere()))
    baisse = mt.detail_familles(tableau(baisse_reguliere()))
    assert hausse["tendance"]["note"] == 1
    assert baisse["tendance"]["note"] == -1


def test_historique_trop_court_rend_indisponible():
    res = mt.noter_technique("AI.PA", tableau(hausse_reguliere(30)))
    assert res["disponible"] is False and res["score"] is None


def test_aucun_cours_rend_indisponible_sans_planter():
    assert mt.noter_technique("AI.PA", None)["disponible"] is False
    assert mt.noter_technique("AI.PA", pd.DataFrame(columns=["date", "cloture"]))["disponible"] is False


def test_moins_de_200_seances_reste_disponible():
    """Avec 100 séances, la MM200 manque mais les autres indicateurs suffisent."""
    res = mt.noter_technique("AI.PA", tableau(hausse_reguliere(100)))
    assert res["disponible"] is True
