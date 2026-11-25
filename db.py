"""
db.py — Schéma et connexion à la base bourse.db
Responsable : Papa (rôle Données et base de données)

PLACE DANS L'APPLICATION (voir README) :

    data.py  ──écrit──►  bourse.db  ◄──lit/écrit──  modules + decision.py
                              ▲
                              └──lit──  app.py (Streamlit)

CE FICHIER est le SEUL endroit où l'on décrit les tables. Les autres scripts
n'écrivent pas de SQL : ils appellent les fonctions ci-dessous (lire_..., enregistrer_...).
Si une colonne change, on la change ici et tout le monde en profite.

LES TABLES (document « répartition des tâches ») :

    actions      ticker, nom, secteur                              -> les 5 actions suivies
    cours        ticker, date, ouverture, haut, bas, cloture, volume -> 1 ligne par jour de bourse
    actualites   ticker, date, titre, source, lien, score_sentiment  -> news des derniers jours
    fondamentaux ticker, date, per, croissance, marge, dette, dividende
    scores       ticker, date, module, score, raisons, disponible    -> note de chaque module
    conseils     ticker, date, score_final, signal, phrase           -> conseil final
    journal      date, ticker, source, statut, message               -> AJOUT (à valider) : trace
                 des mises à jour, pour afficher « source indisponible » ou « mis à jour à 17h40 »
                 dans l'application (UC4, UC6).

CONVENTIONS :
    - les dates sont des textes ISO : « 2026-11-24 » (jour) ou « 2026-11-24 14:05 » (actualité) ;
      ce format se trie dans le bon ordre et se lit de la même façon en SQLite et PostgreSQL ;
    - les pourcentages sont des fractions : 12 % s'écrit 0.12 ;
    - « cloture » est écrit sans accent (noms de colonnes sans accent = moins de soucis en SQL).

CONNEXION : DATABASE_URL du fichier .env ; par défaut, le fichier SQLite bourse.db à la racine.
Pour passer à PostgreSQL, il suffit de changer DATABASE_URL (SQLAlchemy fait le reste).

LANCEMENT :
    python db.py      # crée la base (si besoin) et affiche le nombre de lignes par table
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

from sqlalchemy import (Boolean, Column, Float, MetaData, String, Table, Text, and_,
                        create_engine, delete, func, insert, select)

# -----------------------------------------------------------------------------
# 0. LES 5 ACTIONS SUIVIES
# -----------------------------------------------------------------------------
# Repris de config.py s'il existe (TICKERS), sinon valeurs du README.
try:
    import config  # type: ignore
except ImportError:
    config = None

TICKERS = getattr(config, "TICKERS", ["RMS.PA", "TTE.PA", "AI.PA", "DSY.PA", "CAP.PA"])

# Nom complet et secteur, pour l'écran d'accueil (UC1) et la recherche d'actualités.
ACTIONS = getattr(config, "ACTIONS", {
    "RMS.PA": {"nom": "Hermès", "secteur": "Luxe"},
    "TTE.PA": {"nom": "TotalEnergies", "secteur": "Énergie"},
    "AI.PA": {"nom": "Air Liquide", "secteur": "Gaz industriels"},
    "DSY.PA": {"nom": "Dassault Systèmes", "secteur": "Logiciels"},
    "CAP.PA": {"nom": "Capgemini", "secteur": "Services informatiques"},
})

# -----------------------------------------------------------------------------
# 1. DESCRIPTION DES TABLES
# -----------------------------------------------------------------------------
# Les colonnes « primary_key=True » forment la clé : il ne peut exister qu'une ligne
# par clé (par exemple un seul cours par action et par jour).
metadata = MetaData()

actions = Table(
    "actions", metadata,
    Column("ticker", String(12), primary_key=True),   # code Yahoo Finance, ex. « AI.PA »
    Column("nom", String(80)),
    Column("secteur", String(80)),
)

cours = Table(
    "cours", metadata,
    Column("ticker", String(12), primary_key=True),
    Column("date", String(10), primary_key=True),     # jour de bourse « AAAA-MM-JJ »
    Column("ouverture", Float),
    Column("haut", Float),
    Column("bas", Float),
    Column("cloture", Float),
    Column("volume", Float),
)

actualites = Table(
    "actualites", metadata,
    Column("ticker", String(12), primary_key=True),
    Column("lien", String(1000), primary_key=True),   # le lien identifie l'article : pas de doublon
    Column("date", String(16)),                       # « AAAA-MM-JJ HH:MM », heure de Paris
    Column("titre", Text),
    Column("source", String(200)),                    # journal : Les Echos, Boursorama...
    Column("score_sentiment", Float),                 # -1 à +1, rempli par module_info.py
)

fondamentaux = Table(
    "fondamentaux", metadata,
    Column("ticker", String(12), primary_key=True),
    Column("date", String(10), primary_key=True),     # jour où les chiffres ont été relevés
    Column("per", Float),                             # cours / bénéfice par action
    Column("croissance", Float),                      # croissance du chiffre d'affaires (fraction)
    Column("marge", Float),                           # marge nette (fraction)
    Column("dette", Float),                           # dette nette / EBITDA (en années)
    Column("dividende", Float),                       # rendement du dividende (fraction)
)

scores = Table(
    "scores", metadata,
    Column("ticker", String(12), primary_key=True),
    Column("date", String(10), primary_key=True),
    Column("module", String(20), primary_key=True),   # information, technique, financier, risque
    Column("score", Float),                           # -1 à +1, vide si indisponible
    Column("raisons", Text),                          # liste de phrases, stockée en JSON
    Column("disponible", Boolean),
)

conseils = Table(
    "conseils", metadata,
    Column("ticker", String(12), primary_key=True),
    Column("date", String(10), primary_key=True),
    Column("score_final", Float),
    Column("signal", String(20)),                     # ACHETER, VENDRE, NE RIEN FAIRE
    Column("phrase", Text),
)

journal = Table(
    "journal", metadata,
    Column("date", String(16), primary_key=True),     # moment de la mise à jour « AAAA-MM-JJ HH:MM »
    Column("ticker", String(12), primary_key=True),
    Column("source", String(20), primary_key=True),   # cours, fondamentaux, actualites
    Column("statut", String(10)),                     # ok ou erreur
    Column("message", Text),                          # explication lisible par le client
)


# -----------------------------------------------------------------------------
# 2. CONNEXION ET CRÉATION
# -----------------------------------------------------------------------------

def get_engine(url: str | None = None):
    """Connexion à la base.

    url : adresse SQLAlchemy ; si absente, DATABASE_URL du fichier .env,
          sinon « sqlite:///bourse.db » (fichier dans le dossier courant).
    """
    if url is None:
        try:
            from dotenv import load_dotenv
            load_dotenv()                   # lit le fichier .env s'il existe
        except ImportError:
            pass
        url = os.getenv("DATABASE_URL", "sqlite:///bourse.db")
    return create_engine(url)


def creer_base(engine=None):
    """Crée les tables manquantes et remplit la table « actions ». Sans danger si déjà fait :
    les tables existantes et leurs données ne sont pas touchées."""
    engine = engine or get_engine()
    metadata.create_all(engine)
    lignes = [{"ticker": t, **ACTIONS.get(t, {"nom": t, "secteur": None})} for t in TICKERS]
    _remplacer(engine, actions, lignes, ["ticker"])
    return engine


def _remplacer(engine, table, lignes: list[dict], cles: list[str]) -> int:
    """Écrit des lignes en remplaçant celles qui ont la même clé (« upsert » simple).

    Pour chaque ligne : on supprime l'ancienne version (mêmes valeurs dans les colonnes
    « cles »), puis on insère la nouvelle. Tout se fait dans UNE transaction : si une
    erreur survient au milieu, rien n'est modifié (la base reste cohérente).
    """
    if not lignes:
        return 0
    metadata.create_all(engine, tables=[table])   # au cas où la table n'existe pas encore
    colonnes = set(table.c.keys())
    with engine.begin() as cx:
        for ligne in lignes:
            ligne = {k: v for k, v in ligne.items() if k in colonnes}   # ignore les colonnes inconnues
            cx.execute(delete(table).where(and_(*(table.c[k] == ligne[k] for k in cles))))
            cx.execute(insert(table).values(**ligne))
    return len(lignes)


def aujourd_hui() -> str:
    return date.today().isoformat()


def maintenant() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# -----------------------------------------------------------------------------
# 3. ÉCRITURE (utilisée par data.py, les modules et decision.py)
# -----------------------------------------------------------------------------

def enregistrer_cours(engine, ticker: str, lignes: list[dict]) -> int:
    """lignes : [{"date": "2026-11-24", "ouverture": ..., "haut": ..., "bas": ...,
    "cloture": ..., "volume": ...}, ...]. Un jour déjà présent est remplacé."""
    return _remplacer(engine, cours, [{**l, "ticker": ticker} for l in lignes], ["ticker", "date"])


def enregistrer_fondamentaux(engine, ticker: str, chiffres: dict, jour: str | None = None) -> int:
    """chiffres : {"per": 33.9, "croissance": -0.004, ...}. Une ligne par action et par jour."""
    ligne = {**chiffres, "ticker": ticker, "date": jour or aujourd_hui()}
    return _remplacer(engine, fondamentaux, [ligne], ["ticker", "date"])


def enregistrer_actualites(engine, ticker: str, articles: list[dict]) -> int:
    """Ajoute les articles NOUVEAUX (lien pas encore en base).

    Un article déjà présent n'est pas réécrit : on garde ainsi son score_sentiment,
    déjà calculé par module_info.py (on ne paie pas deux fois l'analyse du même titre).
    Renvoie le nombre d'articles ajoutés.
    """
    metadata.create_all(engine, tables=[actualites])
    with engine.begin() as cx:
        deja = set(cx.execute(select(actualites.c.lien).where(actualites.c.ticker == ticker)).scalars())
        nouveaux = [{**a, "ticker": ticker} for a in articles if a.get("lien") and a["lien"] not in deja]
        uniques = list({a["lien"]: a for a in nouveaux}.values())   # le même lien 2 fois dans le flux
        for a in uniques:
            cx.execute(insert(actualites).values(**{k: v for k, v in a.items() if k in actualites.c}))
    return len(uniques)


def enregistrer_sentiment(engine, ticker: str, lien: str, score: float) -> None:
    """Note de sentiment d'un article (-1 à +1), écrite par module_info.py."""
    with engine.begin() as cx:
        cx.execute(actualites.update()
                   .where(and_(actualites.c.ticker == ticker, actualites.c.lien == lien))
                   .values(score_sentiment=score))


def enregistrer_score(engine, note: dict, module: str, jour: str | None = None) -> None:
    """Note d'un module au format commun du README :
    {"action": "RMS.PA", "score": 0.6, "raisons": [...], "disponible": True}."""
    ligne = {"ticker": note["action"], "date": jour or aujourd_hui(), "module": module,
             "score": note.get("score"), "raisons": json.dumps(note.get("raisons") or [], ensure_ascii=False),
             "disponible": bool(note.get("disponible"))}
    _remplacer(engine, scores, [ligne], ["ticker", "date", "module"])


def enregistrer_conseil(engine, conseil: dict, jour: str | None = None) -> None:
    """Conseil final de decision.py (une ligne par action et par jour)."""
    ligne = {"ticker": conseil["action"], "date": jour or aujourd_hui(),
             "score_final": conseil.get("score_final"), "signal": conseil["signal"],
             "phrase": conseil["phrase"]}
    _remplacer(engine, conseils, [ligne], ["ticker", "date"])


def noter_journal(engine, ticker: str, source: str, statut: str, message: str = "") -> None:
    """Trace d'une mise à jour : statut « ok » ou « erreur » + message pour le client."""
    _remplacer(engine, journal, [{"date": maintenant(), "ticker": ticker, "source": source,
                                  "statut": statut, "message": message}],
               ["date", "ticker", "source"])


# -----------------------------------------------------------------------------
# 4. LECTURE (utilisée par les modules, decision.py et app.py)
# -----------------------------------------------------------------------------
# Toutes ces fonctions renvoient une valeur « vide » (liste vide, None) au lieu de planter
# si la table n'existe pas encore : l'application affiche alors « donnée indisponible » (UC6).

def _lire(engine, requete) -> list[dict]:
    try:
        with engine.connect() as cx:
            return [dict(l) for l in cx.execute(requete).mappings().all()]
    except Exception:          # table absente, base introuvable...
        return []


def lire_actions(engine) -> list[dict]:
    """Les 5 actions (ticker, nom, secteur) pour l'écran d'accueil (UC1)."""
    lignes = _lire(engine, select(actions).order_by(actions.c.ticker))
    if lignes:
        return lignes
    # Base encore vide : on renvoie quand même la liste connue, pour que l'accueil s'affiche.
    return [{"ticker": t, **ACTIONS.get(t, {"nom": t, "secteur": None})} for t in TICKERS]


def nom_action(ticker: str) -> str:
    return ACTIONS.get(ticker, {}).get("nom", ticker)


def lire_cours(engine, ticker: str, jours: int | None = None):
    """Historique des cours d'une action, du plus ancien au plus récent (DataFrame pandas,
    pratique pour les calculs du module Technique et les graphiques de app.py).

    jours : si donné, seulement les N derniers jours calendaires.
    """
    import pandas as pd
    requete = select(cours).where(cours.c.ticker == ticker)
    if jours:
        requete = requete.where(cours.c.date >= (date.today() - timedelta(days=jours)).isoformat())
    lignes = _lire(engine, requete.order_by(cours.c.date))
    return pd.DataFrame(lignes, columns=[c.name for c in cours.c])


def lire_clotures(engine, ticker: str) -> list[float]:
    """Cours de clôture, du plus ancien au plus récent (pour le module Risque)."""
    return [l["cloture"] for l in _lire(engine, select(cours.c.cloture)
                                         .where(cours.c.ticker == ticker).order_by(cours.c.date))
            if l["cloture"] is not None]


def lire_dernier_cours(engine, ticker: str) -> dict | None:
    """Dernier cours connu, avec sa date (UC7 : marché fermé -> on affiche le dernier cours)."""
    lignes = _lire(engine, select(cours).where(cours.c.ticker == ticker)
                   .order_by(cours.c.date.desc()).limit(1))
    return lignes[0] if lignes else None


def lire_actualites(engine, ticker: str, jours: int = 7, a_partir_de: datetime | None = None) -> list[dict]:
    """Actualités de moins de « jours » jours, de la plus récente à la plus ancienne."""
    limite = ((a_partir_de or datetime.now()) - timedelta(days=jours)).strftime("%Y-%m-%d %H:%M")
    return _lire(engine, select(actualites)
                 .where(and_(actualites.c.ticker == ticker, actualites.c.date >= limite))
                 .order_by(actualites.c.date.desc()))


def lire_fondamentaux(engine, ticker: str) -> dict | None:
    """Derniers chiffres financiers relevés pour l'action (ou None)."""
    lignes = _lire(engine, select(fondamentaux).where(fondamentaux.c.ticker == ticker)
                   .order_by(fondamentaux.c.date.desc()).limit(1))
    return lignes[0] if lignes else None


def lire_scores(engine, ticker: str, jour: str | None = None) -> dict:
    """Dernière note de chaque module : {"technique": {"action", "score", "raisons", "disponible"}, ...}."""
    requete = select(scores).where(scores.c.ticker == ticker)
    if jour:
        requete = requete.where(scores.c.date == jour)
    notes = {}
    for l in _lire(engine, requete.order_by(scores.c.date)):   # la plus récente écrase les autres
        try:
            raisons = json.loads(l["raisons"]) if l["raisons"] else []
        except ValueError:
            raisons = [l["raisons"]]
        notes[l["module"]] = {"action": ticker, "score": l["score"], "raisons": raisons,
                              "disponible": bool(l["disponible"])}
    return notes


def lire_conseil(engine, ticker: str) -> dict | None:
    """Dernier conseil calculé pour l'action (UC3), ou None."""
    lignes = _lire(engine, select(conseils).where(conseils.c.ticker == ticker)
                   .order_by(conseils.c.date.desc()).limit(1))
    return lignes[0] if lignes else None


def lire_journal(engine, ticker: str | None = None, limite: int = 20) -> list[dict]:
    """Dernières mises à jour (les plus récentes d'abord), pour afficher les erreurs (UC6)."""
    requete = select(journal)
    if ticker:
        requete = requete.where(journal.c.ticker == ticker)
    return _lire(engine, requete.order_by(journal.c.date.desc()).limit(limite))


def derniere_mise_a_jour(engine) -> str | None:
    """Date de la dernière mise à jour réussie, pour le bandeau « mis à jour le ... » (UC4)."""
    lignes = _lire(engine, select(func.max(journal.c.date).label("d")).where(journal.c.statut == "ok"))
    return lignes[0]["d"] if lignes else None


# -----------------------------------------------------------------------------
# 5. LANCEMENT DIRECT
# -----------------------------------------------------------------------------

def main() -> None:
    engine = creer_base()
    print(f"Base : {engine.url}")
    for table in metadata.sorted_tables:
        n = _lire(engine, select(func.count().label("n")).select_from(table))
        print(f"  {table.name:13s} {n[0]['n'] if n else 0:6d} lignes")


if __name__ == "__main__":
    main()
