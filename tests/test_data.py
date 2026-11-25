"""Tests de data.py, SANS internet : les réponses de Yahoo et de Google sont simulées.

Lancement depuis la racine du projet : pytest tests/
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data  # noqa: E402
import db  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    return db.creer_base(db.get_engine(f"sqlite:///{tmp_path / 'test.db'}"))


# ----------------------------------------------------------------------------- marché (UC7)

def test_horaires_et_jours_feries_euronext():
    assert data.paques(2026).isoformat() == "2026-04-05"
    mardi = datetime(2026, 11, 24, 10, 0, tzinfo=data.PARIS)
    assert data.marche_ouvert(mardi)
    assert not data.marche_ouvert(mardi.replace(hour=18))              # après 17 h 30
    assert not data.marche_ouvert(datetime(2026, 11, 28, 10, tzinfo=data.PARIS))   # samedi
    assert not data.marche_ouvert(datetime(2026, 12, 25, 10, tzinfo=data.PARIS))   # Noël
    assert not data.marche_ouvert(datetime(2026, 4, 3, 10, tzinfo=data.PARIS))     # Vendredi saint


def test_message_marche_ferme_avec_dernier_cours(engine):
    db.enregistrer_cours(engine, "AI.PA", [{"date": "2026-11-27", "cloture": 1523.4}])
    msg = data.etat_marche(engine, "AI.PA", datetime(2026, 11, 28, 10, tzinfo=data.PARIS))
    assert msg == "Marché fermé : dernier cours connu 1 523,40 € (clôture du 27/11/2026)."
    assert data.etat_marche(engine, "RMS.PA").startswith("Cours indisponible")


# ----------------------------------------------------------------------------- cours et ratios

def test_conversion_des_cours_yfinance():
    historique = pd.DataFrame({"Open": [1, 2], "High": [1, 2], "Low": [1, 2], "Close": [1.5, float("nan")],
                               "Volume": [10, 20]}, index=pd.to_datetime(["2026-11-23", "2026-11-24"]))
    lignes = data.lignes_cours(historique)
    assert lignes == [{"date": "2026-11-23", "ouverture": 1.0, "haut": 1.0, "bas": 1.0,
                       "cloture": 1.5, "volume": 10.0}]                 # le jour sans clôture est ignoré


def test_calcul_des_ratios():
    info = {"trailingPE": 30.0, "totalDebt": 120.0, "totalCash": 20.0, "ebitda": 50.0, "dividendYield": 1.8}
    compte = pd.DataFrame({"2025": [110.0, 11.0], "2024": [100.0, 9.0]}, index=["Total Revenue", "Net Income"])
    r = data.calculer_fondamentaux(info, compte)
    assert r["per"] == 30.0 and r["dette"] == 2.0
    assert r["croissance"] == pytest.approx(0.10) and r["marge"] == pytest.approx(0.10)
    assert r["dividende"] == pytest.approx(0.018)                       # 1,8 % -> 0,018


def test_per_negatif_si_perte_et_valeurs_absentes():
    r = data.calculer_fondamentaux({"currentPrice": 50.0, "trailingEps": -5.0})
    assert r["per"] == -10.0
    assert r["dette"] is None and r["croissance"] is None


# ----------------------------------------------------------------------------- actualités

def flux(*articles):
    """Fabrique un flux RSS au format de Google Actualités."""
    items = "".join(f"<item><title>{t} - {s}</title><link>{l}</link><source>{s}</source>"
                    f"<pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>"
                    for t, l, s, d in articles)
    return f"<rss><channel>{items}</channel></rss>".encode()


def test_lecture_et_filtrage_des_actualites():
    maintenant = datetime.now(data.PARIS)
    contenu = flux(("Air Liquide relève ses objectifs", "l1", "Les Echos", maintenant - timedelta(hours=3)),
                   ("Air Liquide relève ses objectifs", "l2", "Zonebourse", maintenant - timedelta(hours=4)),
                   ("Le CAC 40 termine en hausse", "l3", "Boursorama", maintenant - timedelta(hours=5)),
                   ("Air Liquide : vieux contrat", "l4", "Les Echos", maintenant - timedelta(days=12)))
    articles = data.filtrer_articles(data.lire_flux_rss(contenu), "AI.PA")
    assert [a["lien"] for a in articles] == ["l1"]        # doublon, hors-sujet et trop vieux retirés
    assert articles[0]["titre"] == "Air Liquide relève ses objectifs"   # « - Les Echos » retiré
    assert articles[0]["source"] == "Les Echos"


def test_flux_illisible():
    with pytest.raises(data.SourceIndisponible):
        data.lire_flux_rss(b"<html>erreur</html")


# ----------------------------------------------------------------------------- mise à jour (UC6)

def test_une_source_en_panne_ne_bloque_pas_les_autres(engine, monkeypatch):
    def yahoo_en_panne(ticker):
        raise data.SourceIndisponible("aucun cours reçu de Yahoo Finance")
    monkeypatch.setattr(data, "charger_cours", yahoo_en_panne)
    monkeypatch.setattr(data, "charger_fondamentaux", lambda t: {"per": 20.0})
    monkeypatch.setattr(data, "charger_actualites", lambda t: [])
    rapport = data.mettre_a_jour(engine, ["AI.PA"])
    assert rapport["AI.PA"]["cours"] == "aucun cours reçu de Yahoo Finance"
    assert rapport["AI.PA"]["fondamentaux"] == "ok"
    assert db.lire_fondamentaux(engine, "AI.PA")["per"] == 20.0
    statuts = {l["source"]: l["statut"] for l in db.lire_journal(engine, "AI.PA")}
    assert statuts == {"cours": "erreur", "fondamentaux": "ok", "actualites": "ok"}
