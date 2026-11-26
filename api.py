"""
api.py — API web du Conseiller Bourse (lue par le front-end Next.js du dossier web/)

PLACE DANS L'APPLICATION :

    data.py ─► bourse.db ◄─ modules + decision.py
                   │
                   └──lit──  CE FICHIER (FastAPI, port 8000)  ──JSON──►  web/ (Next.js, port 3000)

L'API ne fait que LIRE la base, sauf la route « actualiser » qui relance tout le calcul
(data.py puis les 4 modules puis decision.py) en arrière-plan (UC4).

ROUTES :
    GET  /api/etat                  nom du client, marché ouvert/fermé, dernière mise à jour
    GET  /api/actions               les 5 actions : cours, variation, mini-graphique, conseil (UC1)
    GET  /api/actions/{ticker}      tout le détail d'une action (UC2, UC3, UC6, UC7)
    POST /api/actualiser            relance la mise à jour complète (UC4)
    GET  /api/actualiser            avancement de la mise à jour en cours

LANCEMENT :
    uvicorn api:app --reload --port 8000
    Documentation interactive : http://localhost:8000/docs
"""

from __future__ import annotations

import math
import threading
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import data
import db
import decision
import module_technique as mt

app = FastAPI(title="Conseiller Bourse", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])

ENGINE = db.creer_base(db.get_engine())
JOURS_SPARKLINE = 30
MAX_ACTUALITES = 15


# -----------------------------------------------------------------------------
# 1. OUTILS
# -----------------------------------------------------------------------------

def propre(x):
    """Remplace NaN / infini par None (le JSON ne connaît pas NaN)."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: propre(v) for k, v in x.items()}
    if isinstance(x, list):
        return [propre(v) for v in x]
    return x


def variation(cours) -> dict:
    """Dernier cours, cours de la veille et variation du jour en %."""
    if len(cours) == 0:
        return {"dernier": None, "veille": None, "variation": None, "date": None}
    dernier = float(cours["cloture"].iloc[-1])
    veille = float(cours["cloture"].iloc[-2]) if len(cours) > 1 else None
    return {"dernier": dernier, "veille": veille, "date": cours["date"].iloc[-1],
            "variation": (dernier / veille - 1) if veille else None}


def conseil_complet(ticker: str) -> dict | None:
    """Conseil recalculé à partir des notes en base : signal, score, raisons, poids, phrase.
    None si aucun module n'a encore noté l'action."""
    notes = decision.lire_notes(ENGINE, ticker)
    if not notes:
        return None
    conseil = decision.decider(ticker, notes)
    enregistre = db.lire_conseil(ENGINE, ticker)
    conseil["date"] = enregistre["date"] if enregistre else None
    return conseil


def etat_sources(ticker: str) -> list[dict]:
    """Dernier statut de chaque source (cours, fondamentaux, actualites) pour l'action (UC6)."""
    vues = {}
    for ligne in db.lire_journal(ENGINE, ticker, limite=30):     # plus récentes d'abord
        vues.setdefault(ligne["source"], ligne)
    return list(vues.values())


# -----------------------------------------------------------------------------
# 2. ROUTES DE LECTURE
# -----------------------------------------------------------------------------

@app.get("/api/etat")
def etat():
    return {
        "client": decision.nom_client(),
        "marche_ouvert": data.marche_ouvert(),
        "derniere_mise_a_jour": db.derniere_mise_a_jour(ENGINE),
        "maintenant": datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M"),
        "seuils": {"achat": decision.SEUIL_ACHAT, "vente": decision.SEUIL_VENTE},
        "mise_a_jour": dict(TACHE),
    }


@app.get("/api/actions")
def liste_actions():
    resultat = []
    for a in db.lire_actions(ENGINE):
        cours = db.lire_cours(ENGINE, a["ticker"])
        conseil = conseil_complet(a["ticker"])
        resultat.append({
            **a,
            **variation(cours),
            "sparkline": [float(x) for x in cours["cloture"].tail(JOURS_SPARKLINE)],
            "signal": conseil["signal"] if conseil else None,
            "score_final": conseil["score_final"] if conseil else None,
        })
    return propre(resultat)


@app.get("/api/actions/{ticker}")
def detail_action(ticker: str):
    ticker = ticker.upper()
    action = next((a for a in db.lire_actions(ENGINE) if a["ticker"] == ticker), None)
    if action is None:
        raise HTTPException(404, f"Action inconnue : {ticker}")

    cours = db.lire_cours(ENGINE, ticker)
    if len(cours):
        tableau = mt.indicateurs(cours)
        colonnes = ["date", "ouverture", "haut", "bas", "cloture", "volume", "mm20", "mm50", "mm200",
                    "boll_haut", "boll_bas", "rsi", "macd", "macd_signal", "macd_histo"]
        historique = tableau[colonnes].astype(object).where(tableau[colonnes].notna(), None).to_dict("records")
        dernier = tableau.iloc[-1]
        niveaux = {"support": dernier["support"], "resistance": dernier["resistance"],
                   "rsi": dernier["rsi"], "macd": dernier["macd"], "macd_signal": dernier["macd_signal"]}
        familles = mt.detail_familles(cours)
    else:
        historique, niveaux, familles = [], {}, {}

    return propre({
        **action,
        **variation(cours),
        "etat_marche": data.etat_marche(ENGINE, ticker),
        "marche_ouvert": data.marche_ouvert(),
        "historique": historique,
        "indicateurs": {k: (float(v) if v is not None else None) for k, v in niveaux.items()},
        "familles_techniques": familles,
        "fondamentaux": db.lire_fondamentaux(ENGINE, ticker),
        "actualites": db.lire_actualites(ENGINE, ticker, jours=7)[:MAX_ACTUALITES],
        "scores": db.lire_scores(ENGINE, ticker),
        "conseil": conseil_complet(ticker),
        "sources": etat_sources(ticker),
    })


# -----------------------------------------------------------------------------
# 3. MISE À JOUR EN ARRIÈRE-PLAN (bouton « Actualiser », UC4)
# -----------------------------------------------------------------------------
# La mise à jour prend de 30 s à quelques minutes (internet + LLM). Elle tourne dans un
# fil séparé ; le front-end interroge GET /api/actualiser toutes les 2 secondes.

TACHE = {"en_cours": False, "etape": None, "debut": None, "fin": None, "erreur": None}
_verrou = threading.Lock()


def _mettre_a_jour():
    try:
        TACHE["etape"] = "Récupération des cours, chiffres et actualités"
        data.mettre_a_jour(ENGINE)
        client = decision.nom_client()
        for i, ticker in enumerate(db.TICKERS, start=1):
            TACHE["etape"] = f"Analyse de {db.nom_action(ticker)} ({i}/{len(db.TICKERS)})"
            decision.calculer_notes(ENGINE, ticker)
            decision.enregistrer_conseil(ENGINE, decision.decider(ticker, decision.lire_notes(ENGINE, ticker), client))
        TACHE["etape"] = "Terminé"
    except Exception as e:                       # la tâche ne doit jamais faire tomber l'API
        TACHE["erreur"] = f"La mise à jour a échoué ({type(e).__name__}) : {e}"
    finally:
        TACHE["en_cours"] = False
        TACHE["fin"] = datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S")
        _verrou.release()


@app.post("/api/actualiser")
def lancer_actualisation():
    if not _verrou.acquire(blocking=False):
        return {"lance": False, **TACHE}         # une mise à jour tourne déjà
    TACHE.update(en_cours=True, etape="Démarrage", erreur=None, fin=None,
                 debut=datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S"))
    threading.Thread(target=_mettre_a_jour, daemon=True).start()
    return {"lance": True, **TACHE}


@app.get("/api/actualiser")
def suivi_actualisation():
    return dict(TACHE)
