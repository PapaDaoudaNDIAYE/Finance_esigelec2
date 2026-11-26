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

CONNEXION : DATABASE_URL (variable d'environnement ou fichier .env) ; par défaut, le fichier
SQLite bourse.db à côté de ce fichier. Pour passer à PostgreSQL (Neon, Supabase...), il suffit
de mettre son adresse dans DATABASE_URL : « postgres://... » est converti pour le pilote psycopg.
Toutes les écritures passent par SQLAlchemy et marchent à l'identique sur SQLite et PostgreSQL.

LANCEMENT :
    python db.py      # crée la base (si besoin) et affiche le nombre de lignes par table
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import (Boolean, Column, Float, Integer, MetaData, String, Table, Text, and_,
                        create_engine, delete, event, func, insert, select)

# Chemins calculés depuis l'emplacement de ce fichier : ils ne dépendent pas du dossier courant.
DOSSIER = os.path.dirname(os.path.abspath(__file__))
BASE_LOCALE = os.path.join(DOSSIER, "bourse.db")
FICHIER_ENV = os.path.join(DOSSIER, ".env")
SUR_VERCEL = bool(os.getenv("VERCEL"))


def charger_env() -> None:
    """Lit le fichier .env du projet s'il existe (les variables déjà définies sont gardées)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(FICHIER_ENV)
    except ImportError:
        pass

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
    Column("lien", Text, primary_key=True),           # le lien identifie l'article : pas de doublon
    Column("date", String(16)),                       # « AAAA-MM-JJ HH:MM », heure de Paris
    Column("titre", Text),
    Column("source", Text),                           # journal : Les Echos, Boursorama...
    # (Text et non String(n) : PostgreSQL refuse un texte trop long, SQLite non ;
    #  les liens Google Actualités dépassent parfois 700 caractères.)
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

ordres = Table(
    "ordres", metadata,                               # portefeuille simulé (portefeuille.py)
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String(19)),                       # « AAAA-MM-JJ HH:MM:SS », heure de Paris
    Column("ticker", String(12)),
    Column("sens", String(6)),                        # ACHAT ou VENTE
    Column("quantite", Integer),
    Column("prix", Float),                            # cours d'exécution (dernier cours connu)
    Column("frais", Float),                           # frais de courtage en euros
    Column("signal", String(20)),                     # conseil du moment (ACHETER, VENDRE...)
)

reglages = Table(
    "reglages", metadata,                             # choix du client, ex. niveau = « debutant »
    Column("cle", String(40), primary_key=True),
    Column("valeur", Text),
)


# -----------------------------------------------------------------------------
# 2. CONNEXION ET CRÉATION
# -----------------------------------------------------------------------------

def normaliser_url(url: str) -> str:
    """Adresse PostgreSQL -> pilote psycopg (version 3), installé par requirements.txt.
    Neon et Supabase donnent « postgres://... » ou « postgresql://... »."""
    for prefixe in ("postgres://", "postgresql://"):
        if url.startswith(prefixe):
            return "postgresql+psycopg://" + url[len(prefixe):]
    return url


def url_base() -> str:
    """DATABASE_URL (variable d'environnement ou .env), sinon le fichier bourse.db du projet.

    Sur Vercel sans PostgreSQL : les fichiers du déploiement ne sont pas modifiables, on
    travaille donc sur une copie de bourse.db dans /tmp (temporaire : mode démonstration).
    """
    charger_env()
    url = normaliser_url(os.getenv("DATABASE_URL") or f"sqlite:///{BASE_LOCALE}")
    # « sqlite:///bourse.db » (chemin relatif) : relatif au projet, pas au dossier courant.
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        chemin = url[len("sqlite:///"):]
        if not os.path.isabs(chemin) and not chemin.startswith("/"):
            url = f"sqlite:///{os.path.join(DOSSIER, chemin)}"
    if SUR_VERCEL and url.startswith("sqlite:///") and not url.startswith("sqlite:////tmp/"):
        source = url[len("sqlite:///"):]
        copie = "/tmp/bourse.db"
        if not os.path.exists(copie) and os.path.exists(source):
            shutil.copyfile(source, copie)
        url = f"sqlite:///{copie}"
    return url


def get_engine(url: str | None = None):
    """Connexion à la base.

    url : adresse SQLAlchemy ; si absente, voir url_base().
    PostgreSQL en serverless (Vercel) : chaque fonction garde au plus 1 connexion ouverte
    (+2 en renfort), vérifiée avant usage (la base a pu la fermer entre deux appels).
    """
    url = normaliser_url(url) if url else url_base()
    if url.startswith("postgresql"):
        engine = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=2,
                               connect_args={"connect_timeout": 10})
        event.listen(engine, "connect", _limites_postgresql)
        return engine
    return create_engine(url)


def _limites_postgresql(connexion, _record) -> None:
    """Garde-fous PostgreSQL, posés à chaque nouvelle connexion. Sur Vercel, une fonction
    coupée à 60 s peut laisser une transaction ouverte qui verrouille des lignes : sans ces
    limites, toutes les requêtes suivantes attendraient ce verrou indéfiniment.
        lock_timeout       : abandonner après 10 s d'attente d'un verrou ;
        statement_timeout  : aucune requête de plus de 30 s ;
        idle_in_transaction_session_timeout : la base ferme d'elle-même une transaction
                             abandonnée depuis 30 s (et libère ses verrous)."""
    try:
        with connexion.cursor() as cur:
            cur.execute("SET lock_timeout = '10s'")
            cur.execute("SET statement_timeout = '30s'")
            cur.execute("SET idle_in_transaction_session_timeout = '30s'")
        connexion.commit()
    except Exception:            # réglage refusé (droits, proxy...) : on continue sans
        try:
            connexion.rollback()
        except Exception:
            pass


def creer_base(engine=None):
    """Crée les tables manquantes et remplit la table « actions ». Sans danger si déjà fait :
    les tables existantes et leurs données ne sont pas touchées."""
    engine = engine or get_engine()
    if "*" in _verifiees(engine):    # déjà fait par ce processus : rien à refaire
        return engine
    metadata.create_all(engine)
    lignes = [{"ticker": t, **ACTIONS.get(t, {"nom": t, "secteur": None})} for t in TICKERS]
    # On n'écrit que si la table « actions » n'est pas déjà à jour : une écriture à chaque
    # démarrage attendrait (sur PostgreSQL) les verrous d'une autre mise à jour en cours.
    presentes = {l["ticker"]: l for l in _lire(engine, select(actions))}
    if any({k: presentes.get(l["ticker"], {}).get(k) for k in l} != l for l in lignes):
        _remplacer(engine, actions, lignes, ["ticker"])
    _verifiees(engine).add("*")
    return engine


def _verifiees(engine) -> set:
    """Tables dont l'existence a déjà été vérifiée sur ce moteur (« * » : toutes)."""
    if not hasattr(engine, "_tables_verifiees"):
        engine._tables_verifiees = set()
    return engine._tables_verifiees


def _remplacer(engine, table, lignes: list[dict], cles: list[str]) -> int:
    """Écrit des lignes en remplaçant celles qui ont la même clé (« upsert »).

    Résultat identique sur SQLite et PostgreSQL : une seule ligne par clé, la plus récente.
    1. Méthode rapide : « INSERT ... ON CONFLICT (clé) DO UPDATE » du dialecte (SQLite ou
       PostgreSQL), toutes les lignes en un seul envoi. Utile pour une base distante.
    2. Si elle échoue (table créée sans clé primaire, autre base...) : pour chaque ligne,
       suppression de l'ancienne version puis insertion de la nouvelle.
    Chaque méthode tourne dans UNE transaction : en cas d'erreur, rien n'est modifié.
    """
    if not lignes:
        return 0
    if not _verifiees(engine) & {"*", table.name}:        # au cas où la table n'existe pas encore
        metadata.create_all(engine, tables=[table])       # (vérifié une fois par moteur :
        _verifiees(engine).add(table.name)                #  chaque vérification = un aller-retour)
    colonnes = set(table.c.keys())
    lignes = [{k: v for k, v in l.items() if k in colonnes} for l in lignes]   # ignore les colonnes inconnues
    # Toutes les lignes doivent avoir les mêmes colonnes pour un envoi groupé ; une colonne
    # absente vaut NULL, exactement comme avec une insertion simple.
    utilisees = sorted({k for l in lignes for k in l})
    lignes = [{k: l.get(k) for k in utilisees} for l in lignes]
    # Dernière version de chaque clé (une clé en double dans un même envoi ferait échouer l'upsert).
    lignes = list({tuple(l[k] for k in cles): l for l in lignes}.values())

    dialecte = engine.dialect.name
    if dialecte in ("sqlite", "postgresql"):
        if dialecte == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as insert_dialecte
        else:
            from sqlalchemy.dialects.postgresql import insert as insert_dialecte
        requete = insert_dialecte(table)
        autres = [c for c in utilisees if c not in cles]
        requete = (requete.on_conflict_do_update(index_elements=cles,
                                                 set_={c: requete.excluded[c] for c in autres})
                   if autres else requete.on_conflict_do_nothing(index_elements=cles))
        try:
            with engine.begin() as cx:
                cx.execute(requete, lignes)
            return len(lignes)
        except Exception:
            pass                                   # on passe à la méthode simple ci-dessous

    with engine.begin() as cx:
        for ligne in lignes:
            cx.execute(delete(table).where(and_(*(table.c[k] == ligne[k] for k in cles))))
            cx.execute(insert(table).values(**ligne))
    return len(lignes)


def aujourd_hui() -> str:
    return date.today().isoformat()


def heure_paris() -> datetime:
    """Heure de Paris, sans fuseau (les dates de la base sont en heure de Paris). Nécessaire
    sur Vercel, dont les serveurs sont à l'heure UTC."""
    return datetime.now(ZoneInfo("Europe/Paris")).replace(tzinfo=None)


def maintenant() -> str:
    return heure_paris().strftime("%Y-%m-%d %H:%M")


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


def lire_reglage(engine, cle: str) -> str | None:
    lignes = _lire(engine, select(reglages.c.valeur).where(reglages.c.cle == cle))
    return lignes[0]["valeur"] if lignes else None


def ecrire_reglage(engine, cle: str, valeur: str) -> None:
    _remplacer(engine, reglages, [{"cle": cle, "valeur": valeur}], ["cle"])


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
    limite = ((a_partir_de or heure_paris()) - timedelta(days=jours)).strftime("%Y-%m-%d %H:%M")
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
