"""Tests du portefeuille simulé (portefeuille.py) et de ses routes (api.py)."""

import os
import sys
import tempfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# api.py se connecte à la base dès son import : jamais la vraie base pendant les tests.
if "api" not in sys.modules:
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'api.db')}"

import db  # noqa: E402
import portefeuille as pf  # noqa: E402
from data import PARIS  # noqa: E402

SEANCE = datetime(2026, 11, 26, 11, 0, tzinfo=PARIS)        # jeudi, marché ouvert
SOIR = datetime(2026, 11, 26, 20, 0, tzinfo=PARIS)          # marché fermé


def o(sens, quantite, prix, frais=0.0, ticker="AI.PA", date="2026-11-26 10:00:00", id=0):
    return {"id": id, "date": date, "ticker": ticker, "sens": sens, "quantite": quantite, "prix": prix, "frais": frais}


# ---------------------------------------------------------------- calcul pur

def test_portefeuille_vide():
    r = pf.calculer([], {}, capital=1000)
    assert r["liquidites"] == 1000 and r["valeur_totale"] == 1000 and r["positions"] == [] and r["gain"] == 0


def test_achats_prix_de_revient_et_plus_value_latente():
    r = pf.calculer([o("ACHAT", 10, 100, 1, id=1), o("ACHAT", 10, 120, 1, id=2)], {"AI.PA": 130}, capital=10_000)
    p = r["positions"][0]
    assert p["quantite"] == 20 and p["pru"] == pytest.approx(2202 / 20)          # frais compris
    assert r["liquidites"] == pytest.approx(10_000 - 2202)
    assert p["valeur"] == 2600 and p["plus_value"] == pytest.approx(2600 - 2202)
    assert r["valeur_totale"] == pytest.approx(10_000 - 2202 + 2600)


def test_vente_plus_value_realisee_et_pru_inchange():
    ordres = [o("ACHAT", 10, 100, id=1), o("VENTE", 4, 150, 2, date="2026-11-26 11:00:00", id=2)]
    r = pf.calculer(ordres, {"AI.PA": 150}, capital=10_000)
    p = r["positions"][0]
    assert p["quantite"] == 6 and p["pru"] == pytest.approx(100)
    assert r["plus_value_realisee"] == pytest.approx(4 * 50 - 2)
    assert r["liquidites"] == pytest.approx(10_000 - 1000 + 600 - 2)
    assert r["frais_payes"] == 2


def test_tout_vendre_retire_la_position():
    r = pf.calculer([o("ACHAT", 5, 100, id=1), o("VENTE", 5, 90, id=2, date="2026-11-26 12:00:00")], {}, capital=1000)
    assert r["positions"] == [] and r["plus_value_realisee"] == pytest.approx(-50) and r["valeur_totale"] == 950


def test_verifier_refuse_les_ordres_impossibles():
    etat = pf.calculer([o("ACHAT", 3, 100, id=1)], {}, capital=1000)
    with pytest.raises(pf.OrdreRefuse, match="Liquidités insuffisantes"):
        pf.verifier(etat, "AI.PA", "ACHAT", 8, 100)                      # 800 + frais > 700
    with pytest.raises(pf.OrdreRefuse, match="ne détenez que 3"):
        pf.verifier(etat, "AI.PA", "VENTE", 4, 100)
    with pytest.raises(pf.OrdreRefuse, match="entier"):
        pf.verifier(etat, "AI.PA", "ACHAT", 0, 100)
    assert pf.verifier(etat, "AI.PA", "VENTE", 3, 100) == pytest.approx(0.3)   # frais 0,1 %


# ---------------------------------------------------------------- avec une base

@pytest.fixture
def engine():
    e = db.get_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'p.db')}")
    db.creer_base(e)
    db.enregistrer_cours(e, "AI.PA", [{"date": "2026-11-26", "ouverture": 99, "haut": 101, "bas": 98,
                                       "cloture": 100.0, "volume": 1000}])
    pf.choisir_niveau(e, "professionnel", risques_acceptes=True)   # pas de limite gênante ici
    return e


def test_passer_ordre_achat_puis_vente(engine):
    achat = pf.passer_ordre(engine, "ai.pa", "achat", 10, moment=SEANCE)
    assert achat["prix"] == 100 and achat["frais"] == 1.0 and achat["sens"] == "ACHAT" and achat["id"]
    vente = pf.passer_ordre(engine, "AI.PA", "vente", 4, moment=SEANCE)
    assert vente["id"] != achat["id"]
    etat = pf.etat(engine)
    assert etat["positions"][0]["quantite"] == 6
    assert etat["liquidites"] == pytest.approx(pf.CAPITAL_DEPART - 1001 + 400 - 0.4)
    assert [x["sens"] for x in etat["ordres"]] == ["VENTE", "ACHAT"]               # plus récent d'abord
    assert next(a for a in etat["actions"] if a["ticker"] == "AI.PA")["detenues"] == 6


def test_ordre_refuse_marche_ferme(engine):
    with pytest.raises(pf.OrdreRefuse, match="Marché fermé"):
        pf.passer_ordre(engine, "AI.PA", "achat", 1, moment=SOIR)


def test_ordre_refuse_sans_cours_ou_action_inconnue(engine):
    with pytest.raises(pf.OrdreRefuse, match="indisponible"):
        pf.passer_ordre(engine, "TTE.PA", "achat", 1, moment=SEANCE)              # aucun cours en base
    with pytest.raises(pf.OrdreRefuse, match="inconnue"):
        pf.passer_ordre(engine, "XXX.PA", "achat", 1, moment=SEANCE)


def test_ordre_refuse_n_ecrit_rien(engine):
    with pytest.raises(pf.OrdreRefuse):
        pf.passer_ordre(engine, "AI.PA", "vente", 1, moment=SEANCE)
    assert pf.etat(engine)["ordres"] == []


def test_reinitialiser(engine):
    pf.passer_ordre(engine, "AI.PA", "achat", 1, moment=SEANCE)
    pf.reinitialiser(engine)
    etat = pf.etat(engine)
    assert etat["ordres"] == [] and etat["liquidites"] == pf.CAPITAL_DEPART


# ---------------------------------------------------------------- routes de l'API

def test_routes_portefeuille(monkeypatch):
    import api
    from fastapi.testclient import TestClient
    client = TestClient(api.app)
    client.post("/api/portefeuille/reinitialiser")
    client.post("/api/profil", json={"niveau": "professionnel", "risques_acceptes": True})
    db.enregistrer_cours(api.ENGINE, "AI.PA", [{"date": "2099-01-01", "ouverture": 50, "haut": 50, "bas": 50,
                                                "cloture": 50.0, "volume": 1}])
    monkeypatch.setattr(pf.data, "marche_ouvert", lambda moment=None: True)

    r = client.post("/api/ordres", json={"ticker": "AI.PA", "sens": "achat", "quantite": 2})
    assert r.status_code == 200 and r.json()["ordre"]["prix"] == 50
    assert r.json()["portefeuille"]["positions"][0]["quantite"] == 2

    r = client.post("/api/ordres", json={"ticker": "AI.PA", "sens": "vente", "quantite": 5})
    assert r.status_code == 400 and "ne détenez que 2" in r.json()["detail"]

    r = client.get("/api/portefeuille")
    assert r.headers["cache-control"] == "no-store" and len(r.json()["ordres"]) == 1

    monkeypatch.setattr(pf.data, "marche_ouvert", lambda moment=None: False)
    r = client.post("/api/ordres", json={"ticker": "AI.PA", "sens": "achat", "quantite": 1})
    assert r.status_code == 400 and "Marché fermé" in r.json()["detail"]
    assert client.post("/api/portefeuille/reinitialiser").json()["ordres"] == []


# ---------------------------------------------------------------- niveaux d'investisseur

def etat_vide(capital=500_000):
    return pf.calculer([], {}, capital=capital)


def test_debutant_bloque_au_dela_de_50_000():
    bloque, _ = pf.controler_niveau(etat_vide(), "debutant", "AI.PA", "ACHAT", 1000, 100.0, None)   # 100 000 €
    assert bloque and "ne peut pas dépasser 50 000,00 €" in bloque


def test_debutant_alerte_a_partir_de_10_000():
    bloque, alertes = pf.controler_niveau(etat_vide(), "debutant", "AI.PA", "ACHAT", 150, 100.0, None)  # 15 000 €
    assert bloque is None and any("Ordre important" in a for a in alertes)
    bloque, alertes = pf.controler_niveau(etat_vide(), "debutant", "AI.PA", "ACHAT", 50, 100.0, None)   # 5 000 €
    assert bloque is None and alertes == []


def test_debutant_ne_peut_pas_acheter_contre_le_conseil():
    bloque, _ = pf.controler_niveau(etat_vide(), "debutant", "AI.PA", "ACHAT", 1, 100.0, "VENDRE")
    assert bloque and "VENDRE" in bloque
    bloque, alertes = pf.controler_niveau(etat_vide(), "moyen", "AI.PA", "ACHAT", 1, 100.0, "VENDRE")
    assert bloque is None and any("Contre notre conseil" in a for a in alertes)
    assert pf.controler_niveau(etat_vide(), "professionnel", "AI.PA", "ACHAT", 1, 100.0, "VENDRE") == (None, [])


def test_concentration_par_niveau():
    etat = etat_vide(capital=100_000)
    # 30 000 € sur une seule action = 30 % : interdit en débutant (25 %), alerte en moyen (> 25 %)
    assert pf.controler_niveau(etat, "debutant", "AI.PA", "ACHAT", 300, 100.0, None)[0]
    bloque, alertes = pf.controler_niveau(etat, "moyen", "AI.PA", "ACHAT", 300, 100.0, None)
    assert bloque is None and any("Concentration" in a for a in alertes)


def test_les_ventes_ne_sont_jamais_bloquees_par_le_niveau():
    etat = pf.calculer([o("ACHAT", 2000, 100, id=1)], {"AI.PA": 100})
    bloque, alertes = pf.controler_niveau(etat, "debutant", "AI.PA", "VENTE", 2000, 100.0, None)   # 200 000 €
    assert bloque is None and alertes == []
    bloque, alertes = pf.controler_niveau(etat, "debutant", "AI.PA", "VENTE", 1, 100.0, "ACHETER")
    assert bloque is None and any("ACHETER" in a for a in alertes)


def test_professionnel_sans_limite_de_montant_mais_alerte():
    bloque, alertes = pf.controler_niveau(etat_vide(), "professionnel", "AI.PA", "ACHAT", 2500, 100.0, None)
    assert bloque is None and any("Ordre important" in a for a in alertes)        # 250 000 €


def test_choisir_niveau(engine):
    with pytest.raises(pf.OrdreRefuse, match="risques"):
        pf.choisir_niveau(engine, "professionnel")
    with pytest.raises(pf.OrdreRefuse, match="inconnu"):
        pf.choisir_niveau(engine, "expert")
    pf.choisir_niveau(engine, "debutant")
    assert pf.lire_niveau(engine) == "debutant" and pf.profil(engine)["niveau"] == "debutant"


def test_ordre_refuse_sans_niveau():
    e = db.get_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'n.db')}")
    db.creer_base(e)
    db.enregistrer_cours(e, "AI.PA", [{"date": "2026-11-26", "cloture": 100.0}])
    with pytest.raises(pf.OrdreRefuse, match="niveau"):
        pf.passer_ordre(e, "AI.PA", "achat", 1, moment=SEANCE)


def test_ordre_risque_demande_confirmation(engine):
    pf.choisir_niveau(engine, "debutant")
    with pytest.raises(pf.OrdreAConfirmer) as erreur:
        pf.passer_ordre(engine, "AI.PA", "achat", 150, moment=SEANCE)          # 15 000 €
    assert any("Ordre important" in a for a in erreur.value.alertes)
    assert pf.etat(engine)["ordres"] == []                                       # rien d'exécuté
    ordre = pf.passer_ordre(engine, "AI.PA", "achat", 150, moment=SEANCE, confirme=True)
    assert ordre["quantite"] == 150
    with pytest.raises(pf.OrdreRefuse, match="50 000"):
        pf.passer_ordre(engine, "AI.PA", "achat", 1000, moment=SEANCE, confirme=True)   # même confirmé


def test_routes_niveau_et_confirmation(monkeypatch):
    import api
    from fastapi.testclient import TestClient
    client = TestClient(api.app)
    client.post("/api/portefeuille/reinitialiser")
    db.enregistrer_cours(api.ENGINE, "AI.PA", [{"date": "2099-01-01", "cloture": 50.0}])
    monkeypatch.setattr(pf.data, "marche_ouvert", lambda moment=None: True)

    r = client.post("/api/profil", json={"niveau": "professionnel"})
    assert r.status_code == 400 and "risques" in r.json()["detail"]
    r = client.post("/api/profil", json={"niveau": "debutant"})
    assert r.status_code == 200 and r.json()["niveau"] == "debutant"
    assert client.get("/api/profil").headers["cache-control"] == "no-store"

    ordre = {"ticker": "AI.PA", "sens": "achat", "quantite": 300}                  # 15 000 €
    r = client.post("/api/ordres", json=ordre)
    assert r.status_code == 409 and r.json()["alertes"]
    r = client.post("/api/ordres", json={**ordre, "confirme": True})
    assert r.status_code == 200
    r = client.post("/api/ordres", json={**ordre, "quantite": 2000, "confirme": True})   # 100 000 €
    assert r.status_code == 400 and "50 000" in r.json()["detail"]
    client.post("/api/portefeuille/reinitialiser")
