"""
decision.py — Pondération, seuils et phrase finale du Conseiller Bourse
Responsable : Axel (rôle Financier, risque et décision)

PLACE DANS L'APPLICATION (voir README) :

    module_info.py, module_technique.py, module_financier.py
        └── chaque module donne une note de -1 à +1 par action ──► table « scores »
    CE FICHIER lit les 4 notes de chaque action, les pondère et produit le conseil
        └── ACHETER / VENDRE / NE RIEN FAIRE + la phrase ──► table « conseils »
    app.py (interface Streamlit) affiche le conseil au client.

RÈGLES (README, « Comment fonctionne l'algorithme ») :

    1. Poids des modules, selon qu'il existe une actualité de moins de 7 jours :
           module        avec info récente   sans info récente
           Information        45 %                 0 %
           Technique          30 %                65 %
           Financier          15 %                20 %
           Risque             10 %                15 %
    2. Score final = somme (note du module x poids du module)
    3. Conseil : score > +0,3 -> ACHETER ; score < -0,3 -> VENDRE ; sinon NE RIEN FAIRE
    4. Phrase : « Pour les raisons A, B, C, D, nous vous conseillons d'ACHETER aujourd'hui,
       Monsieur Dupont. »

CHOIX DU GROUPE (non précisé par le README, à valider) :
    - un module indisponible (disponible = False) est écarté et son poids est réparti
      entre les autres modules, au prorata de leur poids ;
    - l'information est « récente » si le module Information est disponible : c'est lui
      qui renvoie disponible = False quand il n'y a pas d'actualité de moins de 7 jours ;
    - on affiche au plus 4 raisons (A, B, C, D), en commençant par les modules qui
      pèsent le plus dans le conseil.

LANCEMENT :
    python decision.py       # calcule les notes des 4 modules puis les conseils des 5 actions
"""

from __future__ import annotations

import json
import os
from datetime import date

import module_financier as mf

# -----------------------------------------------------------------------------
# 0. RÉGLAGES (repris de config.py s'ils y sont définis)
# -----------------------------------------------------------------------------
_reglage = mf._reglage           # même mécanisme que dans module_financier.py

MODULES = ["information", "technique", "financier", "risque"]

POIDS_AVEC_INFO = _reglage("POIDS_AVEC_INFO",
                           {"information": 0.45, "technique": 0.30, "financier": 0.15, "risque": 0.10})
POIDS_SANS_INFO = _reglage("POIDS_SANS_INFO",
                           {"information": 0.00, "technique": 0.65, "financier": 0.20, "risque": 0.15})
SEUIL_ACHAT = _reglage("SEUIL_ACHAT", 0.3)       # score > +0,3 : ACHETER
SEUIL_VENTE = _reglage("SEUIL_VENTE", -0.3)      # score < -0,3 : VENDRE
NB_RAISONS = 4                                   # raisons A, B, C, D

# Nom employé par les autres modules dans la table « scores » -> nom utilisé ici.
# (« info » et « information » désignent le même module.)
ALIAS_MODULES = {"info": "information", "information": "information", "technique": "technique",
                 "financier": "financier", "risque": "risque"}


def nom_client() -> str:
    """Nom du client affiché dans la phrase : NOM_CLIENT (variable d'environnement ou .env)."""
    import db
    db.charger_env()
    return os.getenv("NOM_CLIENT", "Monsieur Dupont")


# -----------------------------------------------------------------------------
# 1. LE CALCUL DU CONSEIL (fonctions sans base de données, faciles à tester)
# -----------------------------------------------------------------------------

def est_disponible(note: dict | None) -> bool:
    """Une note compte si le module l'a produite (disponible = True et score présent)."""
    return bool(note) and bool(note.get("disponible")) and note.get("score") is not None


def poids_utilises(notes: dict) -> dict:
    """Poids effectifs des modules pour cette action.

    1. Info récente (module Information disponible) ? -> POIDS_AVEC_INFO, sinon POIDS_SANS_INFO.
    2. On retire les modules indisponibles ou de poids nul.
    3. On remet les poids restants à 100 % au total (répartition au prorata).
    Exemple sans info et sans module Technique : Financier 20 % et Risque 15 %
    deviennent 57 % et 43 %.
    """
    base = POIDS_AVEC_INFO if est_disponible(notes.get("information")) else POIDS_SANS_INFO
    gardes = {m: p for m, p in base.items() if p > 0 and est_disponible(notes.get(m))}
    total = sum(gardes.values())
    return {m: p / total for m, p in gardes.items()} if total > 0 else {}


def score_final(notes: dict, poids: dict) -> float | None:
    """Score final = somme (note x poids). Entre -1 et +1. None si aucun module n'a noté."""
    if not poids:
        return None
    return sum(notes[m]["score"] * p for m, p in poids.items())


def signal(score: float | None) -> str:
    """Traduit le score final en conseil (seuils du README)."""
    if score is None:
        return "NE RIEN FAIRE"          # aucune donnée : on ne prend pas de risque
    if score > SEUIL_ACHAT:
        return "ACHETER"
    if score < SEUIL_VENTE:
        return "VENDRE"
    return "NE RIEN FAIRE"


def choisir_raisons(notes: dict, poids: dict, conseil: str) -> list[str]:
    """Choisit au plus 4 raisons à afficher sous le conseil.

    - ACHETER : on ne cite que les modules à note positive (ceux qui justifient l'achat) ;
      VENDRE : seulement les modules à note négative ; NE RIEN FAIRE : tous, car le
      conseil vient justement de l'équilibre entre arguments pour et contre.
    - Les modules sont classés par poids réel dans la décision (|note x poids|).
    - On prend la 1re raison de chaque module, puis la 2e, etc.
    """
    def apport(m):
        return notes[m]["score"] * poids[m]

    if conseil == "ACHETER":
        modules = [m for m in poids if apport(m) > 0]
    elif conseil == "VENDRE":
        modules = [m for m in poids if apport(m) < 0]
    else:
        modules = list(poids)
    modules = sorted(modules or list(poids), key=lambda m: -abs(apport(m)))
    raisons, rang = [], 0
    while len(raisons) < NB_RAISONS and any(rang < len(notes[m]["raisons"]) for m in modules):
        for m in modules:
            if rang < len(notes[m]["raisons"]) and len(raisons) < NB_RAISONS:
                raisons.append(notes[m]["raisons"][rang])
        rang += 1
    return raisons


def rediger_phrase(conseil: str, raisons: list[str], client: str) -> str:
    """Phrase finale, sur le modèle du README.

    « Pour les raisons suivantes : A ; B ; C ; D, nous vous conseillons d'ACHETER
    aujourd'hui, Monsieur Dupont. »
    """
    verbe = {"ACHETER": "d'ACHETER", "VENDRE": "de VENDRE", "NE RIEN FAIRE": "de NE RIEN FAIRE"}[conseil]
    if not raisons:
        return f"Faute de données suffisantes, nous vous conseillons {verbe} aujourd'hui, {client}."
    return (f"Pour les raisons suivantes : {' ; '.join(raisons)}, "
            f"nous vous conseillons {verbe} aujourd'hui, {client}.")


def decider(ticker: str, notes: dict, client: str | None = None) -> dict:
    """Conseil complet pour une action.

    notes : {"information": {...}, "technique": {...}, "financier": {...}, "risque": {...}}
            chaque valeur au format commun du README (score, raisons, disponible).
    Renvoie : action, score_final, signal, raisons, phrase, poids (pour l'affichage détaillé).
    """
    poids = poids_utilises(notes)
    score = score_final(notes, poids)
    conseil = signal(score)
    raisons = choisir_raisons(notes, poids, conseil) if poids else []
    return {
        "action": ticker,
        "score_final": None if score is None else round(score, 3),
        "signal": conseil,
        "raisons": raisons,
        "phrase": rediger_phrase(conseil, raisons, client or nom_client()),
        "poids": {m: round(p, 3) for m, p in poids.items()},
    }


# -----------------------------------------------------------------------------
# 2. LIEN AVEC LA BASE ET AVEC LES AUTRES MODULES
# -----------------------------------------------------------------------------

def lire_notes(engine, ticker: str) -> dict:
    """Dernière note de chaque module pour cette action, lue dans la table « scores »."""
    from sqlalchemy import text
    try:
        with engine.connect() as cx:
            lignes = cx.execute(text("SELECT * FROM scores WHERE ticker = :t ORDER BY date"),
                                {"t": ticker}).mappings().all()
    except Exception:                 # table absente : aucune note
        return {}
    notes = {}
    for ligne in lignes:             # triées par date : la plus récente écrase les autres
        module = ALIAS_MODULES.get(str(ligne["module"]).lower())
        if module is None:
            continue
        raisons = ligne["raisons"]
        if isinstance(raisons, str):
            try:
                raisons = json.loads(raisons)
            except ValueError:
                raisons = [raisons]
        notes[module] = {"action": ticker, "score": ligne["score"], "raisons": list(raisons or []),
                         "disponible": bool(ligne["disponible"])}
    return notes


def enregistrer_conseil(engine, conseil: dict) -> None:
    """Écrit le conseil dans la table « conseils » (une ligne par action et par jour)."""
    from sqlalchemy import text
    jour = date.today().isoformat()
    with engine.begin() as cx:
        cx.execute(text("CREATE TABLE IF NOT EXISTS conseils (ticker TEXT, date TEXT, "
                        "score_final REAL, signal TEXT, phrase TEXT)"))
        cx.execute(text("DELETE FROM conseils WHERE ticker = :t AND date = :d"),
                   {"t": conseil["action"], "d": jour})
        cx.execute(text("INSERT INTO conseils (ticker, date, score_final, signal, phrase) "
                        "VALUES (:t, :d, :s, :sig, :p)"),
                   {"t": conseil["action"], "d": jour, "s": conseil["score_final"],
                    "sig": conseil["signal"], "p": conseil["phrase"]})


def calculer_notes(engine, ticker: str) -> None:
    """Fait tourner les 4 modules pour une action et enregistre leurs notes.

    Convention à valider avec JP et KONATE Boubacar : module_info.py et
    module_technique.py exposent une fonction analyser(ticker) ou
    analyser(ticker, engine) qui renvoie le format commun. Tant qu'un module
    n'existe pas, sa note est « indisponible » et l'application continue de
    fonctionner (UC6).
    """
    import inspect
    for module, nom_fichier in (("information", "module_info"), ("technique", "module_technique")):
        try:
            analyser = __import__(nom_fichier).analyser
            # On passe la connexion à la base si le module l'accepte (même base pour tous).
            accepte_engine = len(inspect.signature(analyser).parameters) >= 2
            res = analyser(ticker, engine) if accepte_engine else analyser(ticker)
        except Exception:            # module pas encore écrit, ou erreur : il ne bloque pas les autres
            res = mf.indisponible(ticker, f"module {module} indisponible")
        mf.enregistrer_score(engine, res, module)
    mf.enregistrer_score(engine, mf.analyser_financier(ticker, engine), "financier")
    mf.enregistrer_score(engine, mf.analyser_risque(ticker, engine), "risque")


def calculer_conseil(engine, ticker: str, client: str | None = None) -> dict:
    """Notes des 4 modules puis conseil d'UNE action, enregistrés en base. Renvoie le conseil."""
    calculer_notes(engine, ticker)
    conseil = decider(ticker, lire_notes(engine, ticker), client or nom_client())
    enregistrer_conseil(engine, conseil)
    return conseil


def calculer_conseils(engine=None, tickers: list[str] | None = None) -> list[dict]:
    """Notes des modules puis conseils des actions (par défaut les 5). Utilisé par main()
    et par la route /api/refresh de api.py."""
    engine = engine or mf.moteur()
    client = nom_client()
    return [calculer_conseil(engine, ticker, client) for ticker in (tickers or mf.TICKERS)]


def main() -> None:
    """Étape 2 du lancement (README) : notes des modules puis conseils des 5 actions."""
    for conseil in calculer_conseils():
        ticker = conseil["action"]
        score = "—" if conseil["score_final"] is None else f"{conseil['score_final']:+.2f}"
        print(f"{ticker:7s} {conseil['signal']:14s} score {score}\n        {conseil['phrase']}")


if __name__ == "__main__":
    main()
