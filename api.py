"""
api.py — Application web du Conseiller Bourse : API JSON + site (FastAPI)

PLACE DANS L'APPLICATION :

    data.py ─► base (SQLite en local, PostgreSQL en ligne) ◄─ modules + decision.py
                   │
                   └──lit──  CE FICHIER  ──►  /api/...  (JSON)
                                         ──►  /        (site Next.js exporté dans web/out/)

L'API ne fait que LIRE la base, sauf :
    - /api/actualiser : bouton « Actualiser » du site (en local : en arrière-plan ; sur Vercel :
                        pendant la requête, au plus une fois toutes les 2 minutes) ;
    - /api/refresh    : mise à jour complète protégée par REFRESH_SECRET, appelée toutes les
                        15 minutes par GitHub Actions (.github/workflows/refresh.yml) ;
    - /api/ordres et /api/portefeuille/reinitialiser : portefeuille simulé (portefeuille.py).

ROUTES :
    GET       /api/etat               nom du client, marché ouvert/fermé, dernière mise à jour
    GET       /api/actions            les 5 actions : cours, variation, mini-graphique, conseil (UC1)
    GET       /api/actions/{ticker}   tout le détail d'une action (UC2, UC3, UC6, UC7)
    POST      /api/actualiser         relance la mise à jour complète (UC4)
    GET       /api/actualiser         avancement de la mise à jour en cours
    GET/POST  /api/refresh            mise à jour complète (en-tête Authorization: Bearer <secret>)
    GET       /api/portefeuille       portefeuille simulé : liquidités, positions, ordres passés
    POST      /api/ordres             acheter / vendre {"ticker", "sens": "achat"|"vente", "quantite",
                                      "confirme"} ; 409 + avertissements si l'ordre est risqué
    GET/POST  /api/profil             niveau d'investisseur (debutant, moyen, professionnel)
    POST      /api/portefeuille/reinitialiser   efface les ordres (retour au capital de départ)
    /                                 le site (fichiers de web/out/, créés par « npm run build »)

LANCEMENT (local) :
    uvicorn api:app --reload --port 8000     puis http://localhost:8000
    Documentation interactive : http://localhost:8000/docs
    Sur Vercel : pyproject.toml indique « api:app » comme point d'entrée.
"""

from __future__ import annotations

import hmac
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, time as heure

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import data
import db
import decision
import module_technique as mt
import portefeuille

DOSSIER_SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "out")

app = FastAPI(title="Conseiller Bourse", version="1.1")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])



# Règles de cache, lues par les navigateurs ET par le CDN de Vercel (« s-maxage »). Sans elles,
# chaque navigateur décide seul (une ancienne page peut rester affichée après un déploiement)
# et chaque fichier du site repasse par Python. Le CDN de Vercel est vidé à chaque déploiement.
CACHE_FICHIERS_VERSIONNES = "public, max-age=31536000, immutable"     # /_next/static : nom = empreinte
CACHE_PAGES = "public, max-age=0, must-revalidate, s-maxage=86400"     # HTML : toujours revérifié
CACHE_DONNEES = "public, max-age=0, s-maxage=20, stale-while-revalidate=600"
ROUTES_SANS_CACHE = ("/api/actualiser", "/api/refresh", "/api/portefeuille", "/api/ordres", "/api/profil")


@app.middleware("http")
async def regles_de_cache(request: Request, suite):
    reponse = await suite(request)
    chemin = request.url.path
    if request.method != "GET" or reponse.status_code != 200 or chemin.startswith(ROUTES_SANS_CACHE):
        reponse.headers["Cache-Control"] = "no-store"
    elif chemin.startswith("/_next/static/"):
        reponse.headers["Cache-Control"] = CACHE_FICHIERS_VERSIONNES
    elif chemin.startswith("/api/"):
        # Données : servies tout de suite par le CDN (au plus 20 s, puis rafraîchies en
        # arrière-plan). Après « Actualiser », le site redemande avec ?v=... (copie neuve).
        reponse.headers["Cache-Control"] = CACHE_DONNEES
    else:
        reponse.headers["Cache-Control"] = CACHE_PAGES
    return reponse


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


DELAI_MINIMAL_MIN = 2    # en ligne : pas de nouvelle mise à jour moins de 2 min après la précédente


def minutes_depuis_derniere_maj(maintenant: datetime | None = None) -> float | None:
    """Minutes écoulées depuis la dernière mise à jour réussie (lue dans la base, donc commune
    à toutes les instances Vercel). None si aucune mise à jour n'a encore été faite."""
    derniere = db.derniere_mise_a_jour(ENGINE)
    if not derniere:
        return None
    try:
        quand = datetime.strptime(derniere[:16], "%Y-%m-%d %H:%M").replace(tzinfo=data.PARIS)
    except ValueError:
        return None
    return ((maintenant or datetime.now(data.PARIS)) - quand).total_seconds() / 60


def actualiser_directement() -> dict:
    """Bouton « Actualiser » sur Vercel : la mise à jour est faite PENDANT la requête (environ
    5 s pour les 5 actions, sous la limite de 60 s), car une tâche en arrière-plan y serait
    coupée dès la réponse envoyée. Pas de secret (il serait visible dans le site) : à la place,
    on refuse de relancer moins de DELAI_MINIMAL_MIN minutes après la dernière mise à jour."""
    vide = {"lance": False, "en_cours": False, "debut": None, "fin": None, "erreur": None}
    ecart = minutes_depuis_derniere_maj()
    if ecart is not None and ecart < DELAI_MINIMAL_MIN:
        return {**vide, "etape": (f"Les données viennent d'être mises à jour (il y a moins de "
                                  f"{DELAI_MINIMAL_MIN} minutes). Affichage rechargé.")}
    if not _verrou.acquire(blocking=False):
        return {**vide, "etape": "Une mise à jour est déjà en cours. Affichage rechargé."}
    debut = datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S")
    try:
        resultat = rafraichir(delai_max=delai_max())
    finally:
        _verrou.release()
    fin = datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S")
    if not resultat["maj"]:
        return {**vide, "lance": True, "debut": debut, "fin": fin, "etape": None,
                "erreur": "La mise à jour a échoué pour toutes les actions. Réessayez plus tard."}
    n = len(resultat["erreurs"])
    etape = "Terminé" if not n else f"Conseils recalculés ({n} source(s) indisponible(s) pour l'instant)."
    return {**vide, "lance": True, "debut": debut, "fin": fin, "etape": etape}


@app.post("/api/actualiser")
def lancer_actualisation():
    # Sur Vercel, une fonction s'arrête dès qu'elle a répondu : pas de fil en arrière-plan,
    # la mise à jour est faite tout de suite (voir actualiser_directement).
    if db.SUR_VERCEL:
        return actualiser_directement()
    if not _verrou.acquire(blocking=False):
        return {"lance": False, **TACHE}         # une mise à jour tourne déjà
    TACHE.update(en_cours=True, etape="Démarrage", erreur=None, fin=None,
                 debut=datetime.now(data.PARIS).strftime("%Y-%m-%d %H:%M:%S"))
    threading.Thread(target=_mettre_a_jour, daemon=True).start()
    return {"lance": True, **TACHE}


@app.get("/api/actualiser")
def suivi_actualisation():
    return dict(TACHE)


# -----------------------------------------------------------------------------
# 4. MISE À JOUR AUTOMATIQUE : /api/refresh (appelée par GitHub Actions)
# -----------------------------------------------------------------------------

FIN_RELEVE = heure(18, 0)    # après la clôture (17 h 30), encore 30 min pour relever le cours de clôture


def seance_ou_cloture(moment: datetime | None = None) -> bool:
    """Vrai pendant la séance d'Euronext Paris ET jusqu'à 18 h : les cours ont 15 minutes de
    retard, il faut donc un dernier passage après 17 h 30 pour enregistrer la clôture."""
    moment = (moment or datetime.now(data.PARIS)).astimezone(data.PARIS)
    if data.marche_ouvert(moment):
        return True
    return (moment.weekday() < 5 and moment.date() not in data.jours_feries(moment.year)
            and data.FERMETURE <= moment.time() < FIN_RELEVE)


def secret_valide(request: Request) -> bool:
    """En-tête « Authorization: Bearer <REFRESH_SECRET> ». Sans secret configuré : toujours refusé."""
    db.charger_env()
    secret = os.getenv("REFRESH_SECRET") or ""
    entete = request.headers.get("authorization", "")
    attendu = f"Bearer {secret}"
    return bool(secret) and hmac.compare_digest(entete.encode(), attendu.encode())


DELAI_MAX_VERCEL = 40    # s : une requête Vercel est coupée à 60 s ; on répond avant, quoi qu'il arrive
FILS_VERCEL = 3          # actions traitées en parallèle sur Vercel (= connexions du pool PostgreSQL)


def rafraichir_action(ticker: str, client: str) -> tuple[dict | None, list[dict]]:
    """Met à jour une action (data.py) puis calcule son conseil (decision.py).
    Renvoie (résumé du conseil ou None, erreurs). Ne lève jamais d'exception."""
    erreurs = []
    try:
        rapport = data.mettre_a_jour(ENGINE, [ticker]).get(ticker, {})
        for source, message in rapport.items():         # data.py ne plante jamais : il rend
            if not str(message).startswith("ok"):        # « ok ... » ou un message d'erreur
                erreurs.append({"action": ticker, "etape": source, "message": message})
        conseil = decision.calculer_conseil(ENGINE, ticker, client)
        return {"action": ticker, "signal": conseil["signal"], "score_final": conseil["score_final"]}, erreurs
    except Exception as e:
        erreurs.append({"action": ticker, "etape": "conseil", "message": f"{type(e).__name__} : {e}"})
        return None, erreurs


def rafraichir(tickers: list[str] | None = None, delai_max: float | None = None) -> dict:
    """Met à jour les données puis calcule les conseils, action par action. Une erreur sur une
    action ou une source n'empêche pas de traiter les autres.

    delai_max (Vercel) : les actions sont traitées en parallèle et la fonction rend la main au
    bout de delai_max secondes au plus ; les actions pas encore finies sont signalées dans
    « erreurs » (elles seront reprises au passage suivant). Sans delai_max : une par une."""
    tickers = list(tickers or db.TICKERS)
    client = decision.nom_client()
    resultats = {}
    if delai_max is None:
        for ticker in tickers:
            resultats[ticker] = rafraichir_action(ticker, client)
    else:
        pool = ThreadPoolExecutor(max_workers=FILS_VERCEL)
        taches = {pool.submit(rafraichir_action, t, client): t for t in tickers}
        finies, _ = wait(taches, timeout=delai_max)
        pool.shutdown(wait=False, cancel_futures=True)   # on n'attend pas les retardataires
        for tache in finies:
            resultats[taches[tache]] = tache.result()
    maj, erreurs = [], []
    for ticker in tickers:
        if ticker not in resultats:
            erreurs.append({"action": ticker, "etape": "délai",
                            "message": f"pas terminée en {delai_max:.0f} s, reprise au prochain passage"})
            continue
        resume, err = resultats[ticker]
        erreurs.extend(err)
        if resume:
            maj.append(resume)
    return {"maj": maj, "erreurs": erreurs}


def delai_max() -> float | None:
    return DELAI_MAX_VERCEL if db.SUR_VERCEL else None


@app.api_route("/api/refresh", methods=["GET", "POST"])
def refresh(request: Request, force: bool = False):
    """Mise à jour complète, protégée par REFRESH_SECRET.

    Hors séance (et après 18 h), ne fait rien, sauf avec ?force=1 (lancement manuel).
    Réponse : {"ok": true, "maj": [...], "erreurs": [...], "duree_s": ...}.
    """
    if not secret_valide(request):
        return JSONResponse({"ok": False, "erreur": "non autorisé"}, status_code=401)
    debut = time.monotonic()
    if not force and not seance_ou_cloture():
        return {"ok": True, "maj": [], "erreurs": [], "duree_s": 0.0,
                "message": "marché fermé : aucune mise à jour"}
    if not _verrou.acquire(blocking=False):
        return {"ok": True, "maj": [], "erreurs": [], "duree_s": 0.0,
                "message": "une mise à jour est déjà en cours"}
    try:
        resultat = rafraichir(delai_max=delai_max())
    finally:
        _verrou.release()
    return {"ok": True, **resultat, "duree_s": round(time.monotonic() - debut, 1)}


# -----------------------------------------------------------------------------
# 5. PORTEFEUILLE SIMULÉ (argent virtuel, voir portefeuille.py)
# -----------------------------------------------------------------------------

class DemandeOrdre(BaseModel):
    ticker: str
    sens: str            # « achat » ou « vente »
    quantite: int
    confirme: bool = False   # le client a lu et accepté les avertissements de son niveau


class DemandeNiveau(BaseModel):
    niveau: str              # debutant, moyen ou professionnel
    risques_acceptes: bool = False


@app.get("/api/profil")
def lire_profil():
    """Niveau d'investisseur choisi (None : pas encore choisi) et règles de chaque niveau."""
    return portefeuille.profil(ENGINE)


@app.post("/api/profil")
def changer_niveau(demande: DemandeNiveau):
    try:
        portefeuille.choisir_niveau(ENGINE, demande.niveau, demande.risques_acceptes)
    except portefeuille.OrdreRefuse as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return portefeuille.profil(ENGINE)


@app.get("/api/portefeuille")
def lire_portefeuille():
    return propre(portefeuille.etat(ENGINE))


@app.post("/api/ordres")
def passer_ordre(demande: DemandeOrdre):
    try:
        ordre = portefeuille.passer_ordre(ENGINE, demande.ticker, demande.sens, demande.quantite,
                                          confirme=demande.confirme)
    except portefeuille.OrdreRefuse as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except portefeuille.OrdreAConfirmer as e:
        # 409 : rien n'est exécuté ; le site affiche les avertissements et renvoie l'ordre
        # avec "confirme": true si le client accepte.
        return JSONResponse({"detail": "confirmation requise", "alertes": e.alertes}, status_code=409)
    return propre({"ordre": ordre, "portefeuille": portefeuille.etat(ENGINE)})


@app.post("/api/portefeuille/reinitialiser")
def reinitialiser_portefeuille():
    portefeuille.reinitialiser(ENGINE)
    return propre(portefeuille.etat(ENGINE))


# -----------------------------------------------------------------------------
# 6. LE SITE (déclaré APRÈS toutes les routes /api/ pour ne pas les masquer)
# -----------------------------------------------------------------------------
# web/out/ contient le site Next.js exporté (« npm run build » dans web/).
# html=True : « /action/AI.PA/ » sert web/out/action/AI.PA/index.html.

@app.get("/action/{ticker}.txt", include_in_schema=False)
def donnees_page_action(ticker: str):
    """Next.js prend « .PA » de « AI.PA » pour une extension de fichier : pour préparer la page
    d'une action, il demande /action/AI.PA.txt au lieu de /action/AI.PA/index.txt (fichier
    réellement exporté). Sans cette route : erreur 404, puis « Application error » au clic."""
    fichier = os.path.join(DOSSIER_SITE, "action", ticker, "index.txt")
    if ticker not in db.TICKERS or not os.path.isfile(fichier):
        raise HTTPException(404, "page inconnue")
    return FileResponse(fichier, media_type="text/x-component")


if os.path.isdir(DOSSIER_SITE):
    app.mount("/", StaticFiles(directory=DOSSIER_SITE, html=True), name="web")
