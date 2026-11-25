"""Tests de la décision (decision.py) : pondération, seuils, raisons, phrase finale.

Lancement depuis la racine du projet : pytest tests/
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decision as d  # noqa: E402


def note(score, raisons=None, disponible=True):
    """Note au format commun du README."""
    return {"action": "X", "score": score, "raisons": raisons or [f"raison {score}"],
            "disponible": disponible}


def indispo():
    return {"action": "X", "score": None, "raisons": ["indisponible"], "disponible": False}


# ----------------------------------------------------------------------------- exemples du README

def test_score_de_plus_045_donne_acheter():
    assert d.signal(0.45) == "ACHETER"
    assert d.signal(-0.45) == "VENDRE"
    assert d.signal(0.3) == "NE RIEN FAIRE"          # seuil strict : il faut dépasser +0,3
    assert d.signal(None) == "NE RIEN FAIRE"


def test_sans_info_recente_le_poids_de_l_information_passe_a_zero():
    notes = {"information": indispo(), "technique": note(0.5), "financier": note(0.5), "risque": note(0.5)}
    poids = d.poids_utilises(notes)
    assert "information" not in poids
    assert poids["technique"] == pytest.approx(0.65)


def test_avec_info_recente_poids_du_readme():
    notes = {m: note(0.1) for m in d.MODULES}
    assert d.poids_utilises(notes) == pytest.approx(
        {"information": 0.45, "technique": 0.30, "financier": 0.15, "risque": 0.10})


def test_module_indisponible_poids_reparti_au_prorata():
    notes = {"information": indispo(), "technique": indispo(), "financier": note(1), "risque": note(-1)}
    poids = d.poids_utilises(notes)
    assert poids["financier"] == pytest.approx(0.20 / 0.35)
    assert sum(poids.values()) == pytest.approx(1)


def test_score_final_somme_ponderee():
    notes = {"information": note(1), "technique": note(0), "financier": note(-1), "risque": note(0.5)}
    # 0,45 x 1 + 0,30 x 0 + 0,15 x (-1) + 0,10 x 0,5 = 0,35
    assert d.score_final(notes, d.poids_utilises(notes)) == pytest.approx(0.35)


# ----------------------------------------------------------------------------- raisons et phrase

def test_conseil_complet_et_phrase():
    notes = {"information": note(1, ["bons résultats publiés"]), "technique": note(0.5, ["RSI à 42"]),
             "financier": note(-0.5, ["action chère"]), "risque": note(0.2, ["volatilité faible"])}
    c = d.decider("AI.PA", notes, "Monsieur Dupont")
    assert c["signal"] == "ACHETER"
    assert c["raisons"][0] == "bons résultats publiés"             # le module qui pèse le plus
    assert len(c["raisons"]) <= 4
    assert c["phrase"].endswith("nous vous conseillons d'ACHETER aujourd'hui, Monsieur Dupont.")


def test_aucune_note_disponible_ne_plante_pas():
    c = d.decider("X", {m: indispo() for m in d.MODULES}, "Monsieur Dupont")
    assert c["signal"] == "NE RIEN FAIRE" and c["score_final"] is None
    assert c["phrase"].startswith("Faute de données suffisantes")


# ----------------------------------------------------------------------------- base de données

def test_aller_retour_base(tmp_path):
    from sqlalchemy import create_engine, text
    import module_financier as mf
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    mf.enregistrer_score(engine, note(0.8, ["actualité positive"]), "info")   # alias « info »
    mf.enregistrer_score(engine, note(0.4), "technique")
    notes = d.lire_notes(engine, "X")
    assert notes["information"]["raisons"] == ["actualité positive"]
    c = d.decider("X", notes, "Monsieur Dupont")
    d.enregistrer_conseil(engine, c)
    with engine.connect() as cx:
        ligne = cx.execute(text("SELECT * FROM conseils")).mappings().first()
    assert ligne["signal"] == c["signal"]
