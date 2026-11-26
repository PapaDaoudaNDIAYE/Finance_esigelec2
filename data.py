"""
data.py — Récupération des cours, des chiffres financiers et des actualités
Responsable : Papa (rôle Données et base de données)

PLACE DANS L'APPLICATION (voir README) :

    Yahoo Finance (yfinance) ──► cours, fondamentaux ─┐
    Google Actualités (RSS)  ──► actualites ──────────┼──► bourse.db (via db.py)
                                                      └──► journal (ce qui a marché ou non)

    Ensuite : python decision.py (calcul des notes et des conseils), puis app.py affiche.

CE QUE FAIT CE FICHIER :
    1. charger_cours        : 1 an de cours journaliers (ouverture, haut, bas, clôture, volume) ;
    2. charger_fondamentaux : les 5 ratios du module Financier (PER, croissance, marge, dette, dividende) ;
    3. charger_actualites   : les titres de presse des 7 derniers jours qui parlent de l'entreprise ;
    4. mettre_a_jour        : fait les 3 pour les 5 actions et écrit tout en base, SANS JAMAIS
                              PLANTER : si une source ne répond pas, l'erreur est notée dans le
                              journal et les autres données sont quand même mises à jour (UC6) ;
    5. etat_marche          : marché ouvert ou fermé (horaires Euronext Paris), pour afficher
                              « marché fermé, dernier cours du ... » (UC7).

LANCEMENT :
    python data.py        # met à jour bourse.db (environ 30 secondes, il faut internet)
"""

from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, time as heure, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import os

import db

PARIS = ZoneInfo("Europe/Paris")

# -----------------------------------------------------------------------------
# 0. RÉGLAGES
# -----------------------------------------------------------------------------
PERIODE_COURS = "1y"          # 1 an d'historique : assez pour la MM200 et la volatilité
JOURS_ACTUALITES = 7          # le README parle d'actualités « de moins de 7 jours »
DELAI_RESEAU = 15             # secondes d'attente maximum par requête internet
ESSAIS = 3                    # nombre d'essais si une source répond mal (ex. erreur 429)

# Horaires de la bourse de Paris (Euronext), heure de Paris.
OUVERTURE = heure(9, 0)
FERMETURE = heure(17, 30)

# Mots qui doivent apparaître dans le titre pour garder un article (en minuscules).
# Le nom seul ne suffit pas toujours : « Total » ou « Hermès » sont aussi des mots courants.
MOTS_CLES = {
    "RMS.PA": ["hermès", "hermes"],
    "TTE.PA": ["totalenergies", "total energies"],
    "AI.PA": ["air liquide"],
    "DSY.PA": ["dassault systèmes", "dassault systemes", "3ds"],
    "CAP.PA": ["capgemini"],
}


class SourceIndisponible(Exception):
    """Une source (Yahoo, Google Actualités) n'a pas répondu ou n'a rien renvoyé."""


def _yfinance():
    """Importe yfinance. Sur Vercel, seul /tmp est modifiable : son cache (fuseaux horaires,
    cookies) y est donc rangé, sinon il essaierait d'écrire dans le dossier de l'utilisateur."""
    import yfinance
    if os.getenv("VERCEL"):
        yfinance.set_tz_cache_location("/tmp/yf-cache")
    return yfinance


# -----------------------------------------------------------------------------
# 1. COURS (yfinance)
# -----------------------------------------------------------------------------

def charger_cours(ticker: str, periode: str = PERIODE_COURS) -> list[dict]:
    """Cours journaliers de l'action sur la période (« 1y » = 1 an).

    Renvoie une liste de lignes prêtes pour la table « cours ».
    Lève SourceIndisponible si Yahoo ne renvoie rien (coupure, ticker inconnu...).
    """
    yf = _yfinance()
    historique = yf.Ticker(ticker).history(period=periode, auto_adjust=False)
    if historique is None or historique.empty:
        raise SourceIndisponible(f"aucun cours reçu de Yahoo Finance pour {ticker}")
    return lignes_cours(historique)


def lignes_cours(historique) -> list[dict]:
    """Transforme le tableau renvoyé par yfinance (colonnes Open, High, Low, Close, Volume)
    en lignes de la table « cours ». Les jours sans clôture sont ignorés."""
    lignes = []
    for jour, l in historique.iterrows():
        if l.get("Close") is None or l["Close"] != l["Close"]:     # NaN : x != x
            continue
        lignes.append({"date": jour.strftime("%Y-%m-%d"), "ouverture": _nombre(l.get("Open")),
                       "haut": _nombre(l.get("High")), "bas": _nombre(l.get("Low")),
                       "cloture": _nombre(l["Close"]), "volume": _nombre(l.get("Volume"))})
    return lignes


def _nombre(x):
    """Convertit en float ; None si absent ou NaN."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


# -----------------------------------------------------------------------------
# 2. CHIFFRES FINANCIERS (yfinance)
# -----------------------------------------------------------------------------

def charger_fondamentaux(ticker: str) -> dict:
    """Les 5 ratios du module Financier, pour la table « fondamentaux ».

    Une valeur introuvable vaut None : module_financier.py l'ignore simplement.
    """
    yf = _yfinance()
    action = yf.Ticker(ticker)
    info = action.info or {}
    try:
        compte = action.income_stmt          # comptes de résultat annuels (colonnes = années)
    except Exception:
        compte = None
    chiffres = calculer_fondamentaux(info, compte)
    if all(v is None for v in chiffres.values()):
        raise SourceIndisponible(f"aucun chiffre financier reçu de Yahoo Finance pour {ticker}")
    return chiffres


def calculer_fondamentaux(info: dict, compte=None) -> dict:
    """Calcule les ratios à partir des données Yahoo.

    info   : dictionnaire « info » de yfinance (cours, BPA, dette, trésorerie...) ;
    compte : compte de résultat annuel (lignes « Total Revenue », « Net Income »,
             colonnes = années, la plus récente en premier). Peut être absent.

    Définitions (cours ABC Bourse, rappelées dans module_financier.py) :
        PER        = cours / bénéfice par action (négatif si l'entreprise perd de l'argent)
        croissance = chiffre d'affaires de l'année / celui de l'année précédente - 1
        marge      = résultat net / chiffre d'affaires
        dette      = (dette totale - trésorerie) / EBITDA : années de résultat pour rembourser
        dividende  = dividende annuel / cours
    """
    # PER : Yahoo ne donne pas trailingPE quand le bénéfice est négatif ; on le recalcule
    # alors avec cours / BPA pour garder l'information « l'entreprise perd de l'argent ».
    per = _nombre(info.get("trailingPE"))
    cours_actuel = _nombre(info.get("currentPrice") or info.get("regularMarketPrice"))
    bpa = _nombre(info.get("trailingEps"))
    if per is None and cours_actuel and bpa:
        per = cours_actuel / bpa

    # Croissance et marge : d'abord le compte de résultat annuel, sinon les champs de « info ».
    ca = _ligne_compte(compte, "Total Revenue")
    resultat = _ligne_compte(compte, "Net Income")
    croissance = ca[0] / ca[1] - 1 if len(ca) >= 2 and ca[1] else _nombre(info.get("revenueGrowth"))
    marge = resultat[0] / ca[0] if resultat and ca and ca[0] else _nombre(info.get("profitMargins"))

    # Dette nette / EBITDA. Négatif = l'entreprise a plus de trésorerie que de dettes.
    dette_totale, tresorerie = _nombre(info.get("totalDebt")), _nombre(info.get("totalCash"))
    ebitda = _nombre(info.get("ebitda"))
    dette = (dette_totale - (tresorerie or 0)) / ebitda if dette_totale is not None and ebitda else None

    # Rendement du dividende. Attention : dans les versions récentes de yfinance,
    # « dividendYield » est en POURCENT (1,8 pour 1,8 %), « trailingAnnualDividendYield » en fraction.
    rendement = _nombre(info.get("dividendYield"))
    dividende = rendement / 100 if rendement is not None else _nombre(info.get("trailingAnnualDividendYield"))

    return {"per": per, "croissance": croissance, "marge": marge, "dette": dette, "dividende": dividende}


def _ligne_compte(compte, nom: str) -> list[float]:
    """Valeurs d'une ligne du compte de résultat (année la plus récente d'abord), sans les vides."""
    if compte is None or getattr(compte, "empty", True) or nom not in compte.index:
        return []
    return [v for v in (_nombre(x) for x in compte.loc[nom].tolist()) if v is not None]


# -----------------------------------------------------------------------------
# 3. ACTUALITÉS (flux RSS de Google Actualités)
# -----------------------------------------------------------------------------
# Google Actualités regroupe la presse française (Les Echos, Boursorama, Zonebourse...).
# Son flux RSS est gratuit, sans clé ni compte. « when:7d » limite aux 7 derniers jours.

def adresse_flux(nom: str, jours: int = JOURS_ACTUALITES) -> str:
    requete = quote(f'"{nom}" when:{jours}d')
    return f"https://news.google.com/rss/search?q={requete}&hl=fr&gl=FR&ceid=FR:fr"


def telecharger(url: str) -> bytes:
    """Télécharge une page, avec quelques essais espacés si le site répond mal
    (erreur 429 « trop de requêtes », coupure réseau...)."""
    import requests
    derniere_erreur = None
    for essai in range(ESSAIS):
        try:
            reponse = requests.get(url, timeout=DELAI_RESEAU,
                                   headers={"User-Agent": "Mozilla/5.0 (conseiller-bourse, projet etudiant)"})
            if reponse.status_code == 200:
                return reponse.content
            derniere_erreur = f"code HTTP {reponse.status_code}"
        except requests.RequestException as e:
            derniere_erreur = type(e).__name__
        time.sleep(2 * (essai + 1))           # 2 s, puis 4 s, puis 6 s
    raise SourceIndisponible(f"Google Actualités ne répond pas ({derniere_erreur})")


def lire_flux_rss(contenu: bytes) -> list[dict]:
    """Extrait les articles d'un flux RSS : titre, lien, source, date (heure de Paris)."""
    articles = []
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as e:
        raise SourceIndisponible("flux d'actualités illisible") from e
    for item in racine.iter("item"):
        titre = html.unescape((item.findtext("title") or "").strip())
        source = (item.findtext("source") or "").strip()
        # Google ajoute « - Nom du journal » à la fin du titre : on le retire.
        if source and titre.endswith(f" - {source}"):
            titre = titre[: -len(source) - 3].strip()
        try:
            publie = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(PARIS)
        except (TypeError, ValueError):
            continue                           # article sans date : on ne peut pas savoir s'il est récent
        articles.append({"titre": titre, "lien": (item.findtext("link") or "").strip(),
                         "source": source or None, "date": publie.strftime("%Y-%m-%d %H:%M")})
    return articles


def filtrer_articles(articles: list[dict], ticker: str, jours: int = JOURS_ACTUALITES,
                     a_partir_de: datetime | None = None) -> list[dict]:
    """Garde les articles récents qui citent vraiment l'entreprise dans leur titre,
    sans doublon (même titre repris par plusieurs sites)."""
    mots = MOTS_CLES.get(ticker, [db.nom_action(ticker).lower()])
    limite = ((a_partir_de or datetime.now(PARIS)) - timedelta(days=jours)).strftime("%Y-%m-%d %H:%M")
    gardes, titres_vus = [], set()
    for a in sorted(articles, key=lambda a: a["date"], reverse=True):     # plus récents d'abord
        titre_simple = re.sub(r"\W+", " ", a["titre"].lower()).strip()
        if (a["date"] >= limite and a["lien"] and titre_simple not in titres_vus
                and any(m in a["titre"].lower() for m in mots)):
            titres_vus.add(titre_simple)
            gardes.append(a)
    return gardes


def charger_actualites(ticker: str) -> list[dict]:
    """Titres de presse des 7 derniers jours sur l'entreprise. Liste vide = aucune actualité
    (ce n'est pas une erreur : module_info.py passera alors en « pas d'info récente », UC5)."""
    contenu = telecharger(adresse_flux(db.nom_action(ticker)))
    return filtrer_articles(lire_flux_rss(contenu), ticker)


# -----------------------------------------------------------------------------
# 4. MARCHÉ OUVERT OU FERMÉ (UC7)
# -----------------------------------------------------------------------------

def paques(annee: int) -> date:
    """Date de Pâques (algorithme de Meeus/Jones/Butcher, calendrier grégorien)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return date(annee, mois, jour)


def jours_feries(annee: int) -> set[date]:
    """Jours de fermeture d'Euronext Paris : 1er janvier, Vendredi saint, lundi de Pâques,
    1er mai, 25 et 26 décembre."""
    p = paques(annee)
    return {date(annee, 1, 1), p - timedelta(days=2), p + timedelta(days=1),
            date(annee, 5, 1), date(annee, 12, 25), date(annee, 12, 26)}


def marche_ouvert(moment: datetime | None = None) -> bool:
    """True si la bourse de Paris est ouverte à ce moment (par défaut : maintenant)."""
    moment = (moment or datetime.now(PARIS)).astimezone(PARIS)
    return (moment.weekday() < 5                                # lundi (0) à vendredi (4)
            and moment.date() not in jours_feries(moment.year)
            and OUVERTURE <= moment.time() < FERMETURE)


def etat_marche(engine, ticker: str, moment: datetime | None = None) -> str:
    """Phrase à afficher sous le cours (UC7), par exemple :
    « Marché fermé : dernier cours connu 152,30 € (clôture du 24/11/2026). »"""
    dernier = db.lire_dernier_cours(engine, ticker)
    if dernier is None:
        return "Cours indisponible pour le moment."
    prix = f"{dernier['cloture']:,.2f} €".replace(",", " ").replace(".", ",")
    jour = datetime.strptime(dernier["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
    if marche_ouvert(moment):
        return f"Marché ouvert : dernier cours {prix} (mis à jour le {jour})."
    return f"Marché fermé : dernier cours connu {prix} (clôture du {jour})."


# -----------------------------------------------------------------------------
# 5. MISE À JOUR COMPLÈTE (UC4 : bouton « Actualiser » de app.py)
# -----------------------------------------------------------------------------

def mettre_a_jour(engine=None, tickers: list[str] | None = None) -> dict:
    """Met à jour les cours, les chiffres et les actualités des actions.

    Ne plante jamais : chaque source de chaque action est essayée séparément.
    Renvoie un rapport {ticker: {"cours": "ok" | message d'erreur, ...}} et écrit
    la même chose dans la table « journal » (affichable par app.py, UC6).
    """
    engine = db.creer_base(engine)
    etapes = {
        "cours": lambda t: f"{db.enregistrer_cours(engine, t, charger_cours(t))} jours",
        "fondamentaux": lambda t: (db.enregistrer_fondamentaux(engine, t, charger_fondamentaux(t)), "ok")[1],
        "actualites": lambda t: f"{db.enregistrer_actualites(engine, t, charger_actualites(t))} nouvelles",
    }
    rapport = {}
    for ticker in tickers or db.TICKERS:
        rapport[ticker] = {}
        for source, etape in etapes.items():
            try:
                detail = etape(ticker)
                db.noter_journal(engine, ticker, source, "ok", detail)
                rapport[ticker][source] = "ok" if detail == "ok" else f"ok ({detail})"
            except Exception as e:                 # n'importe quelle erreur : on continue
                message = str(e) if isinstance(e, SourceIndisponible) else \
                    f"{source} indisponible pour le moment ({type(e).__name__})"
                db.noter_journal(engine, ticker, source, "erreur", message)
                rapport[ticker][source] = message
    return rapport


def main() -> None:
    engine = db.get_engine()
    print("Mise à jour des données...")
    for ticker, etat in mettre_a_jour(engine).items():
        print(f"  {ticker:7s} " + " | ".join(f"{s} : {m}" for s, m in etat.items()))
    print("Marché ouvert." if marche_ouvert() else "Marché fermé : les derniers cours connus sont utilisés.")


if __name__ == "__main__":
    main()
