"""Tests de l'API web (api.py), sur une base temporaire remplie de données fabriquées.

Lancement depuis la racine du projet : pytest tests/
"""

import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La base de test doit être choisie AVANT d'importer serveur.py (il s'y connecte à l'import).
_dossier = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_dossier, 'test.db')}"

from fastapi.testclient import TestClient  # noqa: E402

import serveur as api  # noqa: E402
import db  # noqa: E402
import decision  # noqa: E402

client = TestClient(api.app)


def remplir_base():
    rng = np.random.default_rng(7)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 260)))
    dates = pd.bdate_range("2025-11-01", periods=260).strftime("%Y-%m-%d")
    db.enregistrer_cours(api.ENGINE, "AI.PA", [
        {"date": d, "ouverture": x, "haut": x * 1.01, "bas": x * 0.99, "cloture": x, "volume": 1e5}
        for d, x in zip(dates, c)])
    db.enregistrer_fondamentaux(api.ENGINE, "AI.PA", {"per": 20, "croissance": 0.05, "marge": 0.12,
                                                      "dette": 1.5, "dividende": 0.02})
    decision.calculer_notes(api.ENGINE, "AI.PA")


remplir_base()


def test_etat():
    r = client.get("/api/py/etat").json()
    assert {"client", "marche_ouvert", "derniere_mise_a_jour", "seuils", "mise_a_jour"} <= set(r)


def test_liste_des_5_actions():
    r = client.get("/api/py/actions").json()
    assert [a["ticker"] for a in r] == sorted(db.TICKERS)
    ai = next(a for a in r if a["ticker"] == "AI.PA")
    assert ai["dernier"] is not None and len(ai["sparkline"]) == api.JOURS_SPARKLINE
    assert ai["signal"] in ("ACHETER", "VENDRE", "NE RIEN FAIRE")


def test_action_sans_donnees_ne_plante_pas():
    """UC6 : une action sans aucune donnée renvoie une page vide, pas une erreur."""
    r = client.get("/api/py/actions/CAP.PA")
    assert r.status_code == 200
    assert r.json()["historique"] == [] and r.json()["dernier"] is None


def test_detail_complet():
    r = client.get("/api/py/actions/ai.pa").json()        # la casse n'a pas d'importance
    assert len(r["historique"]) == 260
    assert r["historique"][-1]["mm20"] is not None
    assert r["historique"][0]["mm20"] is None          # NaN converti en null
    assert set(r["scores"]) == {"information", "technique", "financier", "risque"}
    assert r["conseil"]["signal"] in ("ACHETER", "VENDRE", "NE RIEN FAIRE")
    assert "technique" in r["conseil"]["poids"]


def test_action_inconnue():
    assert client.get("/api/py/actions/XXX").status_code == 404


def test_actualisation_github_sans_jeton_ne_plante_pas(monkeypatch):
    """Sur Vercel sans GITHUB_TOKEN : message clair au lieu d'une erreur (UC6)."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    r = api._lancer_github()
    assert r["lance"] is False and "GITHUB_TOKEN" in r["erreur"]
