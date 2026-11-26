"""
serveur.py — API web du Conseiller Bourse (lue par le front-end Next.js)

PLACE DANS L'APPLICATION :

    data.py ─► bourse.db ◄─ modules + decision.py
                   │
                   └──lit──  CE FICHIER (FastAPI)  ──JSON──►  site Next.js (app/, components/)

DEUX FAÇONS DE LE FAIRE TOURNER :

    En local    : uvicorn serveur:app --reload --port 8000
                  Le site (npm run dev) relaie /api/py/... vers http://127.0.0.1:8000.
                  Documentation interactive : http://localhost:8000/api/py/docs
    Sur Vercel  : api/index.py importe « app » d'ici ; Vercel en fait une fonction Python.
                  Le fichier bourse.db du dépôt est copié dans /tmp (seul dossier modifiable).

ROUTES :
    GET  /api/py/etat               nom du client, marché ouvert/fermé, dernière mise à jour
    GET  /api/py/actions            les 5 actions : cours, variation, mini-graphique, conseil (UC1)
    GET  /api/py/actions/{ticker}   tout le détail d'une action (UC2, UC3, UC6, UC7)
    POST /api/py/actualiser         relance la mise à jour complète (UC4)
    GET  /api/py/actualiser         avancement de la mise à jour

BOUTON « ACTUALISER » (UC4) :
    En local : la mise à jour tourne dans un fil séparé de ce serveur.
    Sur Vercel : une fonction s'arrête dès qu'elle a répondu, elle ne peut donc pas faire tourner
    une mise à jour de plusieurs minutes. Le bouton déclenche alors la tâche GitHub Actions
    « Mise à jour des données » (.github/workflows/mise-a-jour.yml), qui recalcule tout avec le
    LLM et publie bourse.db ; Vercel redéploie ensuite le site avec les nouvelles données.
    Il faut pour cela les variables GITHUB_TOKEN et GITHUB_REPO (voir README).
"""

from __future__ import annotations

import math
import os
import shutil
import threading
from datetime import datetime, timezone

# Sur Vercel, les fichiers du déploiement ne sont pas modifiables : on travaille sur une copie
# de bourse.db dans /tmp. À faire AVANT d'ouvrir la base (db.get_engine lit DATABASE_URL).
SUR_VERCEL = bool(os.getenv("VERCEL"))
if SUR_VERCEL:
    _source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bourse.db")
    _copie = "/tmp/bourse.db"
    if not os.path.exists(_copie) and os.path.exists(_source):
        shutil.copyfile(_source, _copie)
    os.environ["DATABASE_URL"] = f"sqlite:///{_copie}"

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import data  # noqa: E402
import db  # noqa: E402
import decision  # noqa: E402
import module_technique as mt  # noqa: E402

app = FastAPI(title="Conseiller Bourse", version="1.1",
              docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])

ENGINE = db.creer_base(db.get_engine())
JOURS_SPARKLINE = 30
MAX_ACTUALITES = 15
WORKFLOW = "mise-a-jour.yml"


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

@app.get("/api/py/etat")
def etat():
    return {
        "client": decision.nom_client(),
        "marche_ouvert": data.marche_ouvert(),
        "derniere_mise_a_jour": db.derniere_mise_a_jour(ENGINE),
        "maintenant": datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M"),
        "seuils": {"achat": decision.SEUIL_ACHAT, "vente": decision.SEUIL_VENTE},
        "mise_a_jour": dict(TACHE),
        "mode_actualisation": "github" if SUR_VERCEL else "local",
    }


@app.get("/api/py/actions")
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


@app.get("/api/py/actions/{ticker}")
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
# 3. BOUTON « ACTUALISER » EN LOCAL : mise à jour dans un fil séparé
# -----------------------------------------------------------------------------
# La mise à jour prend de 30 s à quelques minutes (internet + LLM). Le front-end
# interroge GET /api/py/actualiser toutes les 2 secondes.

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


def _lancer_local() -> dict:
    if not _verrou.acquire(blocking=False):
        return {"lance": False, **TACHE}         # une mise à jour tourne déjà
    TACHE.update(en_cours=True, etape="Démarrage", erreur=None, fin=None,
                 debut=datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S"))
    threading.Thread(target=_mettre_a_jour, daemon=True).start()
    return {"lance": True, **TACHE}


# -----------------------------------------------------------------------------
# 4. BOUTON « ACTUALISER » SUR VERCEL : déclenche GitHub Actions
# -----------------------------------------------------------------------------

def _github(methode: str, chemin: str, **kwargs):
    """Appel à l'API GitHub avec le jeton GITHUB_TOKEN, sur le dépôt GITHUB_REPO."""
    import requests
    jeton, depot = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPO")
    if not jeton or not depot:
        raise RuntimeError("Actualisation non configurée : ajoutez GITHUB_TOKEN et GITHUB_REPO "
                           "dans les variables d'environnement Vercel.")
    return requests.request(methode, f"https://api.github.com/repos/{depot}{chemin}", timeout=15,
                            headers={"Authorization": f"Bearer {jeton}",
                                     "Accept": "application/vnd.github+json",
                                     "User-Agent": "conseiller-bourse"}, **kwargs)


def _tache_erreur(message: str) -> dict:
    return {"en_cours": False, "etape": None, "debut": None, "fin": None, "erreur": message}


def _lancer_github() -> dict:
    debut = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        r = _github("POST", f"/actions/workflows/{WORKFLOW}/dispatches",
                    json={"ref": os.getenv("GITHUB_BRANCHE", "main")})
    except Exception as e:
        return {"lance": False, **_tache_erreur(str(e))}
    if r.status_code != 204:
        return {"lance": False, **_tache_erreur(f"GitHub a refusé la mise à jour (code {r.status_code}).")}
    return {"lance": True, "en_cours": True, "etape": "Mise à jour demandée à GitHub Actions…",
            "debut": debut, "fin": None, "erreur": None}


ETAPES_GITHUB = {"queued": "En attente d'un serveur GitHub…", "waiting": "En attente d'un serveur GitHub…",
                 "requested": "En attente d'un serveur GitHub…", "pending": "En attente d'un serveur GitHub…",
                 "in_progress": "Calcul en cours sur GitHub (cours, actualités, LLM, conseils)…"}


def _suivi_github(depuis: str | None) -> dict:
    """Avancement de la dernière exécution lancée par le bouton (depuis = heure du clic, UTC)."""
    try:
        r = _github("GET", f"/actions/workflows/{WORKFLOW}/runs",
                    params={"event": "workflow_dispatch", "per_page": 5})
        executions = r.json().get("workflow_runs", []) if r.status_code == 200 else None
    except Exception as e:
        return _tache_erreur(str(e))
    if executions is None:
        return _tache_erreur(f"Suivi impossible (code GitHub {r.status_code}).")
    if depuis:
        executions = [x for x in executions if x["created_at"] >= depuis]
    if not executions:                           # GitHub n'a pas encore créé l'exécution
        return {"en_cours": True, "etape": "Démarrage sur GitHub…", "debut": depuis, "fin": None, "erreur": None}
    x = executions[0]
    if x["status"] != "completed":
        return {"en_cours": True, "etape": ETAPES_GITHUB.get(x["status"], "Calcul en cours sur GitHub…"),
                "debut": x["created_at"], "fin": None, "erreur": None}
    if x["conclusion"] != "success":
        return _tache_erreur(f"La mise à jour GitHub a échoué ({x['conclusion']}). Détail : {x['html_url']}")
    return {"en_cours": False, "debut": x["created_at"], "fin": x["updated_at"], "erreur": None,
            "etape": "Données publiées : le site se met à jour dans 1 à 2 minutes, puis rechargez la page."}


@app.post("/api/py/actualiser")
def lancer_actualisation():
    return _lancer_github() if SUR_VERCEL else _lancer_local()


@app.get("/api/py/actualiser")
def suivi_actualisation(depuis: str | None = None):
    return _suivi_github(depuis) if SUR_VERCEL else dict(TACHE)
