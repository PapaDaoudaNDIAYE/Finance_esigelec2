"""Tests de db.py : création de la base, écriture sans doublon, lectures.

Lancement depuis la racine du projet : pytest tests/
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402


@pytest.fixture
def engine(tmp_path):
    """Base SQLite neuve, dans un dossier temporaire supprimé après le test."""
    return db.creer_base(db.get_engine(f"sqlite:///{tmp_path / 'test.db'}"))


def test_creation_des_tables_et_des_5_actions(engine):
    from sqlalchemy import inspect
    assert set(inspect(engine).get_table_names()) >= {
        "actions", "cours", "actualites", "fondamentaux", "scores", "conseils", "journal"}
    actions = db.lire_actions(engine)
    assert len(actions) == 5 and {"ticker", "nom", "secteur"} <= set(actions[0])
    db.creer_base(engine)                                  # 2e création : sans effet ni doublon
    assert len(db.lire_actions(engine)) == 5


def test_cours_remplaces_sans_doublon_et_dernier_cours(engine):
    db.enregistrer_cours(engine, "AI.PA", [{"date": "2026-11-23", "cloture": 150.0},
                                            {"date": "2026-11-24", "cloture": 151.0}])
    db.enregistrer_cours(engine, "AI.PA", [{"date": "2026-11-24", "cloture": 152.5}])   # correction
    assert db.lire_clotures(engine, "AI.PA") == [150.0, 152.5]
    assert db.lire_dernier_cours(engine, "AI.PA")["date"] == "2026-11-24"
    assert len(db.lire_cours(engine, "AI.PA")) == 2


def test_actualites_recentes_et_sentiment_conserve(engine):
    maintenant = datetime.now()
    recent = (maintenant - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    ancien = (maintenant - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
    articles = [{"titre": "A", "lien": "l1", "date": recent}, {"titre": "B", "lien": "l2", "date": ancien}]
    assert db.enregistrer_actualites(engine, "AI.PA", articles) == 2
    db.enregistrer_sentiment(engine, "AI.PA", "l1", 0.7)
    assert db.enregistrer_actualites(engine, "AI.PA", articles) == 0    # déjà connus : rien d'ajouté
    recentes = db.lire_actualites(engine, "AI.PA", jours=7)
    assert [a["lien"] for a in recentes] == ["l1"] and recentes[0]["score_sentiment"] == 0.7


def test_scores_et_conseil_aller_retour(engine):
    db.enregistrer_score(engine, {"action": "AI.PA", "score": 0.4, "raisons": ["RSI à 42"],
                                  "disponible": True}, "technique")
    assert db.lire_scores(engine, "AI.PA")["technique"]["raisons"] == ["RSI à 42"]
    db.enregistrer_conseil(engine, {"action": "AI.PA", "score_final": 0.4, "signal": "ACHETER",
                                    "phrase": "..."})
    assert db.lire_conseil(engine, "AI.PA")["signal"] == "ACHETER"


def test_compatible_avec_module_financier(engine):
    """Les fonctions de module_financier.py lisent les tables créées par db.py."""
    import module_financier as mf
    db.enregistrer_fondamentaux(engine, "AI.PA", {"per": 30.0, "marge": 0.13})
    assert mf.lire_fondamentaux(engine, "AI.PA")["per"] == 30.0
    mf.enregistrer_score(engine, mf.indisponible("AI.PA", "test"), "risque")
    assert db.lire_scores(engine, "AI.PA")["risque"]["disponible"] is False


def test_lecture_base_vide_ne_plante_pas(tmp_path):
    vide = db.get_engine(f"sqlite:///{tmp_path / 'vide.db'}")      # aucune table
    assert db.lire_dernier_cours(vide, "AI.PA") is None
    assert db.lire_actualites(vide, "AI.PA") == []
    assert db.lire_scores(vide, "AI.PA") == {}
    assert len(db.lire_actions(vide)) == 5                          # l'accueil s'affiche quand même


# ----------------------------------------------------------------------------- PostgreSQL / Vercel

def test_adresses_postgresql_converties_pour_psycopg():
    assert db.normaliser_url("postgres://u:p@h/b") == "postgresql+psycopg://u:p@h/b"
    assert db.normaliser_url("postgresql://u:p@h/b?sslmode=require") == "postgresql+psycopg://u:p@h/b?sslmode=require"
    assert db.normaliser_url("postgresql+psycopg://u:p@h/b") == "postgresql+psycopg://u:p@h/b"
    assert db.normaliser_url("sqlite:///bourse.db") == "sqlite:///bourse.db"


def test_chemin_sqlite_relatif_au_projet(monkeypatch):
    """« sqlite:///bourse.db » désigne le fichier du projet, quel que soit le dossier courant."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///bourse.db")
    monkeypatch.delenv("VERCEL", raising=False)
    assert os.path.samefile(db.url_base()[len("sqlite:///"):], db.BASE_LOCALE) or \
        db.url_base() == f"sqlite:///{db.BASE_LOCALE}"


def test_migration_relancee_sans_doublon(tmp_path):
    import migrer_sqlite_vers_postgres as migration
    source = db.creer_base(db.get_engine(f"sqlite:///{tmp_path / 'source.db'}"))
    db.enregistrer_cours(source, "AI.PA", [{"date": "2026-11-24", "cloture": 150.0},
                                           {"date": "2026-11-25", "cloture": 151.0}])
    db.enregistrer_actualites(source, "AI.PA", [{"lien": "l1", "titre": "t", "date": "2026-11-25 10:00"}])
    cible_url = f"sqlite:///{tmp_path / 'cible.db'}"
    for _ in range(2):                                   # deux fois : aucun doublon
        migration.migrer(f"sqlite:///{tmp_path / 'source.db'}", cible_url)
    cible = db.get_engine(cible_url)
    assert db.lire_clotures(cible, "AI.PA") == [150.0, 151.0]
    assert len(db.lire_actions(cible)) == 5
