"""Tests de l'API web (api.py), sur une base temporaire remplie de données fabriquées.

Lancement depuis la racine du projet : pytest tests/
"""

import os
import sys
import tempfile

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La base de test doit être choisie AVANT d'importer api.py (il s'y connecte à l'import).
_dossier = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_dossier, 'test.db')}"

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
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
    r = client.get("/api/etat").json()
    assert {"client", "marche_ouvert", "derniere_mise_a_jour", "seuils", "mise_a_jour"} <= set(r)


def test_liste_des_5_actions():
    r = client.get("/api/actions").json()
    assert [a["ticker"] for a in r] == sorted(db.TICKERS)
    ai = next(a for a in r if a["ticker"] == "AI.PA")
    assert ai["dernier"] is not None and len(ai["sparkline"]) == api.JOURS_SPARKLINE
    assert ai["signal"] in ("ACHETER", "VENDRE", "NE RIEN FAIRE")


def test_action_sans_donnees_ne_plante_pas():
    """UC6 : une action sans aucune donnée renvoie une page vide, pas une erreur."""
    r = client.get("/api/actions/CAP.PA")
    assert r.status_code == 200
    assert r.json()["historique"] == [] and r.json()["dernier"] is None


def test_detail_complet():
    r = client.get("/api/actions/ai.pa").json()        # la casse n'a pas d'importance
    assert len(r["historique"]) == 260
    assert r["historique"][-1]["mm20"] is not None
    assert r["historique"][0]["mm20"] is None          # NaN converti en null
    assert set(r["scores"]) == {"information", "technique", "financier", "risque"}
    assert r["conseil"]["signal"] in ("ACHETER", "VENDRE", "NE RIEN FAIRE")
    assert "technique" in r["conseil"]["poids"]


def test_action_inconnue():
    assert client.get("/api/actions/XXX").status_code == 404


# ----------------------------------------------------------------------------- /api/refresh

def _sans_reseau(monkeypatch):
    """Remplace la récupération des données et le calcul des conseils par des versions
    instantanées : le test ne dépend ni d'internet, ni de l'heure (marché ouvert ou non)."""
    monkeypatch.setattr(api.data, "mettre_a_jour",
                        lambda engine, tickers: {t: {"cours": "ok (1 jours)", "actualites": "Google Actualités ne répond pas"}
                                                 for t in tickers})
    monkeypatch.setattr(api.decision, "calculer_conseil",
                        lambda engine, ticker, client=None: {"action": ticker, "signal": "NE RIEN FAIRE", "score_final": 0.1})
    monkeypatch.setattr(api, "seance_ou_cloture", lambda moment=None: True)


def test_refresh_refuse_sans_secret(monkeypatch):
    monkeypatch.setenv("REFRESH_SECRET", "secret-de-test")
    _sans_reseau(monkeypatch)
    assert client.post("/api/refresh").status_code == 401
    assert client.get("/api/refresh", headers={"Authorization": "Bearer mauvais"}).status_code == 401


def test_refresh_refuse_si_aucun_secret_configure(monkeypatch):
    monkeypatch.setenv("REFRESH_SECRET", "")
    assert client.post("/api/refresh", headers={"Authorization": "Bearer "}).status_code == 401


def test_refresh_avec_secret(monkeypatch):
    monkeypatch.setenv("REFRESH_SECRET", "secret-de-test")
    _sans_reseau(monkeypatch)
    for methode in (client.get, client.post):
        r = methode("/api/refresh", headers={"Authorization": "Bearer secret-de-test"})
        assert r.status_code == 200
        corps = r.json()
        assert corps["ok"] is True and "duree_s" in corps
        assert [m["action"] for m in corps["maj"]] == db.TICKERS
        # une source en panne est signalée sans bloquer les autres actions
        assert len(corps["erreurs"]) == len(db.TICKERS)
        assert {e["etape"] for e in corps["erreurs"]} == {"actualites"}


def test_refresh_marche_ferme_ne_fait_rien(monkeypatch):
    monkeypatch.setenv("REFRESH_SECRET", "secret-de-test")
    _sans_reseau(monkeypatch)
    monkeypatch.setattr(api, "seance_ou_cloture", lambda moment=None: False)
    entete = {"Authorization": "Bearer secret-de-test"}
    assert client.post("/api/refresh", headers=entete).json()["maj"] == []
    assert len(client.post("/api/refresh?force=1", headers=entete).json()["maj"]) == len(db.TICKERS)


def test_seance_ou_cloture():
    from datetime import datetime
    paris = api.data.PARIS
    assert api.seance_ou_cloture(datetime(2026, 11, 26, 10, 0, tzinfo=paris))       # jeudi, séance
    assert api.seance_ou_cloture(datetime(2026, 11, 26, 17, 45, tzinfo=paris))      # relevé de clôture
    assert not api.seance_ou_cloture(datetime(2026, 11, 26, 18, 30, tzinfo=paris))
    assert not api.seance_ou_cloture(datetime(2026, 11, 28, 11, 0, tzinfo=paris))   # samedi
    assert not api.seance_ou_cloture(datetime(2026, 12, 25, 11, 0, tzinfo=paris))   # Noël


def test_le_site_est_servi_apres_les_routes_api():
    """Les routes /api/ ne sont pas masquées par le montage du site sur « / »."""
    assert client.get("/api/etat").headers["content-type"].startswith("application/json")
    if os.path.isdir(api.DOSSIER_SITE):            # web/out/ existe après « npm run build »
        accueil = client.get("/")
        assert accueil.status_code == 200 and "text/html" in accueil.headers["content-type"]
        assert client.get("/action/AI.PA/").status_code == 200


def test_bouton_actualiser_sur_vercel_ne_lance_rien(monkeypatch):
    """Sur Vercel, pas de mise à jour en arrière-plan (elle serait coupée) : message clair."""
    monkeypatch.setattr(api.db, "SUR_VERCEL", True)
    r = client.post("/api/actualiser").json()
    assert r["lance"] is False and r["en_cours"] is False and "15 minutes" in r["etape"]
