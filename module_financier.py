"""
module_financier.py — Modules « Financier » et « Risque » du Conseiller Bourse
Responsable : Axel (rôle Financier, risque et décision)

PLACE DANS L'APPLICATION (voir README) :

    data.py remplit bourse.db  ──►  CE FICHIER lit la base et note chaque action
                               ──►  les notes vont dans la table « scores »
                               ──►  decision.py les combine en conseil

DEUX MODULES DANS CE FICHIER :

    Module Financier : est-ce une entreprise saine et bien valorisée ?
        PER, croissance, marge, endettement, dividende (table « fondamentaux »).
    Module Risque    : le cours bouge-t-il beaucoup ?
        volatilité sur 1 an (table « cours ») et simulation de Monte Carlo de la
        perte possible en une semaine (piste d'amélioration du README).

FORMAT DE SORTIE (identique pour tous les modules du projet, voir README) :

    {"action": "RMS.PA",                  # le ticker
     "score": 0.6,                        # de -1 (très négatif) à +1 (très positif)
     "raisons": ["...", "..."],           # phrases courtes, lisibles par le client
     "disponible": True}                  # False si le module n'a pas pu noter

LANCEMENT :
    python module_financier.py            # note les 5 actions et enregistre les notes

Les réglages (seuils, nombre de simulations...) sont regroupés en haut du fichier.
S'ils existent dans config.py (fichier commun du groupe), ce sont eux qui sont utilisés.
"""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np

# -----------------------------------------------------------------------------
# 0. RÉGLAGES
# -----------------------------------------------------------------------------
# On essaie de lire config.py (fichier commun). S'il n'existe pas encore, ou s'il
# ne définit pas un réglage, on prend la valeur par défaut écrite ici.
try:
    import config  # type: ignore
except ImportError:  # config.py pas encore écrit : on garde les valeurs par défaut
    config = None


def _reglage(nom: str, defaut):
    """Valeur de config.py si elle existe, sinon la valeur par défaut."""
    return getattr(config, nom, defaut) if config is not None else defaut


# Les 5 actions du projet (README, section « Périmètre »)
TICKERS = _reglage("TICKERS", ["RMS.PA", "TTE.PA", "AI.PA", "DSY.PA", "CAP.PA"])

# --- Module Financier : règles de notation des ratios -------------------------
# Pour chaque ratio : la valeur jugée « bonne » vaut +1, la valeur « mauvaise » -1,
# et entre les deux la note varie en ligne droite (au-delà, elle reste à +1 ou -1).
# Exemple PER : 12 -> +1 ; 21 -> 0 ; 30 -> -1 ; 40 -> -1.
# Les ratios en % sont écrits en fraction : 0.10 = 10 %.
REGLES_RATIOS = _reglage("REGLES_RATIOS", {
    "per":        {"bon": 12.0, "mauvais": 30.0},   # cours / bénéfice par action
    "croissance": {"bon": 0.10, "mauvais": -0.05},  # croissance du chiffre d'affaires
    "marge":      {"bon": 0.20, "mauvais": 0.05},   # résultat net / chiffre d'affaires
    "dette":      {"bon": 0.5,  "mauvais": 3.5},    # dette nette / EBITDA, en années
    "dividende":  {"bon": 0.04, "mauvais": 0.005},  # rendement du dividende
})
NB_RAISONS_FINANCIER = 3          # on garde les 3 ratios les plus marquants

# --- Module Risque -------------------------------------------------------------
VOL_BASSE = _reglage("VOL_BASSE", 0.20)    # volatilité annuelle <= 20 % : note +1
VOL_HAUTE = _reglage("VOL_HAUTE", 0.40)    # volatilité annuelle >= 40 % : note -1 (30 % -> 0)
MIN_COURS = 60                             # il faut au moins 60 séances pour estimer le risque
JOURS_HISTORIQUE = 252                     # on utilise la dernière année de bourse

# Monte Carlo : probabilité de perdre au moins 10 % en une semaine sur l'action
SEUIL_PERTE = _reglage("SEUIL_PERTE", 0.10)            # 10 % : limite de perte du projet
HORIZON_JOURS = _reglage("HORIZON_JOURS", 5)           # 1 semaine = 5 séances
NB_SIMULATIONS = _reglage("NB_SIMULATIONS", 10_000)
GRAINE = 42                                            # même graine -> mêmes résultats
SEUIL_ALERTE = _reglage("SEUIL_ALERTE", 0.05)          # au-delà de 5 % de risque : alerte


# -----------------------------------------------------------------------------
# 1. OUTILS
# -----------------------------------------------------------------------------

def resultat(ticker: str, score, raisons: list[str], disponible: bool) -> dict:
    """Construit la réponse au format commun du README (4 clés, rien d'autre)."""
    if score is not None:
        score = round(max(-1.0, min(1.0, float(score))), 3)   # toujours entre -1 et +1
    return {"action": ticker, "score": score, "raisons": raisons, "disponible": disponible}


def indisponible(ticker: str, raison: str) -> dict:
    """Réponse quand le module ne peut pas noter : pas de note, disponible = False."""
    return resultat(ticker, None, [raison], False)


def note_lineaire(valeur: float, bon: float, mauvais: float) -> float:
    """Note de -1 à +1 : +1 si la valeur atteint « bon », -1 si elle atteint « mauvais ».

    Marche dans les deux sens : pour le PER, « bon » (12) est plus petit que
    « mauvais » (30) ; pour la marge, « bon » (20 %) est plus grand que « mauvais » (5 %).
    """
    position = (valeur - mauvais) / (bon - mauvais)   # 0 sur « mauvais », 1 sur « bon »
    return max(-1.0, min(1.0, 2 * position - 1))


def fr(x: float, decimales: int = 1) -> str:
    """Nombre au format français : 13.06 -> « 13,1 »."""
    return f"{x:.{decimales}f}".replace(".", ",")


def est_absent(x) -> bool:
    """Vrai si la valeur manque (None ou NaN)."""
    return x is None or (isinstance(x, float) and math.isnan(x))


# -----------------------------------------------------------------------------
# 2. MODULE FINANCIER
# -----------------------------------------------------------------------------

def en_fraction(valeur):
    """Accepte 10 ou 0.10 pour « 10 % » et renvoie toujours 0.10.

    Convention avec data.py : les % sont stockés en fraction. Ce garde-fou évite
    une erreur si une valeur arrive en pourcentage (une marge de 15 % ne s'écrit
    jamais 0,15 % : au-delà de 1, c'est forcément un pourcentage).
    """
    if est_absent(valeur):
        return None
    valeur = float(valeur)
    return valeur / 100 if abs(valeur) > 1 else valeur


def raison_ratio(nom: str, v: float, note: float) -> str:
    """Phrase compréhensible par le client pour un ratio et sa note."""
    bien, mal = note > 0.3, note < -0.3            # au-delà de ±0,3 : on qualifie
    if nom == "per":
        if v <= 0:
            return "l'entreprise est en perte (PER négatif)"
        etat = "action peu chère" if bien else "action chère" if mal else "prix raisonnable"
        return f"PER de {fr(v)} : {etat}"
    if nom == "croissance":
        sens = "hausse" if v >= 0 else "baisse"
        return f"chiffre d'affaires en {sens} de {fr(abs(v) * 100)} %"
    if nom == "marge":
        etat = "très rentable" if bien else "peu rentable" if mal else "rentabilité correcte"
        return f"marge de {fr(v * 100)} % : {etat}"
    if nom == "dette":
        if v < 0:
            return "aucune dette nette : l'entreprise a plus de trésorerie que de dettes"
        etat = "dette faible" if bien else "dette élevée" if mal else "dette raisonnable"
        return f"dette égale à {fr(v)} années de résultat : {etat}"
    if nom == "dividende":
        etat = "dividende généreux" if bien else "dividende faible" if mal else "dividende moyen"
        return f"{etat} ({fr(v * 100)} % par an)"
    return f"{nom} : {fr(v)}"


def noter_financier(ticker: str, fondamentaux: dict | None) -> dict:
    """MODULE FINANCIER — note une action à partir de ses ratios.

    fondamentaux : la dernière ligne de la table « fondamentaux » pour cette action,
                   ex. {"per": 33.9, "croissance": -0.004, "marge": 0.131,
                        "dette": 2.0, "dividende": 0.018}
    Étapes :
      1. noter chaque ratio présent de -1 à +1 (règles de REGLES_RATIOS) ;
      2. note Financier = moyenne des notes ;
      3. raisons = les ratios les plus marquants (note la plus forte, en + ou en -).
    """
    if not fondamentaux:
        return indisponible(ticker, "données financières indisponibles")

    notes, raisons = [], []
    for nom, regle in REGLES_RATIOS.items():
        v = fondamentaux.get(nom)
        if est_absent(v):
            continue                                   # ratio absent : on l'ignore
        v = en_fraction(v) if nom in ("croissance", "marge", "dividende") else float(v)
        if nom == "per" and v <= 0:
            note = -1.0                                # PER négatif = entreprise en perte
        else:
            note = note_lineaire(v, regle["bon"], regle["mauvais"])
        notes.append(note)
        raisons.append((nom, note, raison_ratio(nom, v, note)))

    if not notes:                                      # aucun ratio exploitable
        return indisponible(ticker, "données financières indisponibles")

    score = sum(notes) / len(notes)
    # Ordre des raisons : d'abord celles qui vont dans le sens de la note globale
    # (ex. note positive -> d'abord les points forts), puis les plus marquantes.
    raisons.sort(key=lambda r: (r[1] * score < 0, -abs(r[1])))
    return resultat(ticker, score, [texte for _, _, texte in raisons[:NB_RAISONS_FINANCIER]], True)


# -----------------------------------------------------------------------------
# 3. MODULE RISQUE
# -----------------------------------------------------------------------------

def rendements_log(clotures) -> np.ndarray:
    """Rendements logarithmiques quotidiens : ln(cours du jour / cours de la veille)."""
    c = np.asarray(clotures, dtype=float)
    c = c[~np.isnan(c)]
    return np.diff(np.log(c))


def volatilite_annuelle(clotures) -> float:
    """Volatilité annualisée = écart-type des rendements quotidiens x racine(252).

    Exemple : 1 % de variation typique par jour -> environ 16 % par an.
    """
    return float(np.std(rendements_log(clotures), ddof=1) * math.sqrt(252))


def simulation_monte_carlo(clotures, horizon: int = HORIZON_JOURS, n: int = NB_SIMULATIONS,
                           graine: int = GRAINE) -> dict:
    """Simule n semaines possibles du cours (mouvement brownien géométrique).

    Principe :
      - on mesure m (rendement moyen) et s (écart-type) des rendements quotidiens ;
      - après h jours : cours final = cours actuel x exp(h x m + s x racine(h) x Z),
        Z étant un tirage au hasard d'une loi normale (cloche) ;
      - on répète 10 000 fois et on compte les cas où la perte dépasse 10 %.
    Renvoie la probabilité de perdre au moins SEUIL_PERTE et la VaR à 95 %
    (perte qui n'est dépassée que dans 5 % des cas).
    """
    r = rendements_log(clotures)
    m, s = r.mean(), r.std(ddof=1)
    z = np.random.default_rng(graine).standard_normal(n)
    variation = np.exp(horizon * m + s * math.sqrt(horizon) * z) - 1   # ex. -0.04 = -4 %
    return {
        "proba_perte": float((variation <= -SEUIL_PERTE).mean()),
        "var_95": float(-np.quantile(variation, 0.05)),
    }


def noter_risque(ticker: str, clotures) -> dict:
    """MODULE RISQUE — note une action selon l'ampleur de ses variations.

    clotures : cours de clôture quotidiens, du plus ancien au plus récent.
    Étapes :
      1. au moins MIN_COURS séances, sinon disponible = False ;
      2. volatilité sur 1 an -> note : 20 % ou moins = +1 ; 30 % = 0 ; 40 % ou plus = -1 ;
      3. Monte Carlo : si le risque de perdre 10 % en une semaine dépasse 5 %,
         la note est plafonnée à -0,5 (alerte liée à la limite de perte du projet).
    Une note positive veut dire « action peu risquée ».
    """
    c = [x for x in (clotures or []) if not est_absent(x)]
    if len(c) < MIN_COURS:
        return indisponible(ticker, "historique de cours insuffisant pour mesurer le risque")
    c = c[-(JOURS_HISTORIQUE + 1):]                    # dernière année seulement

    vol = volatilite_annuelle(c)
    score = note_lineaire(vol, VOL_BASSE, VOL_HAUTE)
    niveau = "faible" if score > 0.3 else "élevé" if score < -0.3 else "moyen"
    raisons = [f"volatilité de {fr(vol * 100, 0)} % par an : risque {niveau}"]

    mc = simulation_monte_carlo(c)
    raisons.append(f"sur une semaine, {fr(mc['proba_perte'] * 100)} % de risque de perdre "
                   f"{fr(SEUIL_PERTE * 100, 0)} % ou plus (simulation de Monte Carlo)")
    if mc["proba_perte"] > SEUIL_ALERTE:
        score = min(score, -0.5)                       # alerte : risque de toucher la limite
        raisons.insert(0, f"alerte : risque de perte de {fr(SEUIL_PERTE * 100, 0)} % trop élevé")
    else:
        raisons.append(f"dans 95 % des cas, la perte sur une semaine reste sous "
                       f"{fr(mc['var_95'] * 100)} %")
    return resultat(ticker, score, raisons, True)


# -----------------------------------------------------------------------------
# 4. LIEN AVEC LA BASE DE DONNÉES (bourse.db)
# -----------------------------------------------------------------------------
# Les tables sont créées et remplies par db.py / data.py (Papa). Ici on ne fait que
# LIRE « fondamentaux » et « cours », et ÉCRIRE dans « scores ».

def moteur():
    """Connexion à la base, la même que pour tout le projet (db.get_engine) :
    DATABASE_URL (SQLite ou PostgreSQL), sinon le fichier bourse.db du projet."""
    import db
    return db.get_engine()


def lire_fondamentaux(engine, ticker: str) -> dict | None:
    """Dernière ligne de la table « fondamentaux » pour cette action (None si absente)."""
    from sqlalchemy import text
    try:
        with engine.connect() as cx:
            ligne = cx.execute(text("SELECT * FROM fondamentaux WHERE ticker = :t "
                                    "ORDER BY date DESC LIMIT 1"), {"t": ticker}).mappings().first()
        return dict(ligne) if ligne else None
    except Exception:            # table absente ou base injoignable : le module sera indisponible
        return None


def lire_clotures(engine, ticker: str) -> list[float]:
    """Cours de clôture de la table « cours », du plus ancien au plus récent."""
    from sqlalchemy import text
    try:
        with engine.connect() as cx:
            lignes = cx.execute(text("SELECT * FROM cours WHERE ticker = :t ORDER BY date"),
                                {"t": ticker}).mappings().all()
    except Exception:
        return []
    # Le nom de la colonne peut être écrit avec ou sans accent
    for colonne in ("cloture", "clôture", "close"):
        if lignes and colonne in lignes[0]:
            return [l[colonne] for l in lignes]
    return []


def enregistrer_score(engine, res: dict, module: str) -> None:
    """Écrit une note dans la table « scores » (une ligne par action, module et jour).

    La table est créée si db.py ne l'a pas encore fait. Une note du même jour
    pour la même action et le même module est remplacée (pas de doublon).
    """
    from sqlalchemy import text
    jour = date.today().isoformat()
    with engine.begin() as cx:
        cx.execute(text("CREATE TABLE IF NOT EXISTS scores (ticker TEXT, date TEXT, module TEXT, "
                        "score REAL, raisons TEXT, disponible BOOLEAN)"))
        cx.execute(text("DELETE FROM scores WHERE ticker = :t AND date = :d AND module = :m"),
                   {"t": res["action"], "d": jour, "m": module})
        cx.execute(text("INSERT INTO scores (ticker, date, module, score, raisons, disponible) "
                        "VALUES (:t, :d, :m, :s, :r, :disp)"),
                   {"t": res["action"], "d": jour, "m": module, "s": res["score"],
                    "r": json.dumps(res["raisons"], ensure_ascii=False), "disp": res["disponible"]})


def analyser_financier(ticker: str, engine=None) -> dict:
    """Module Financier complet pour une action : lecture en base puis notation."""
    return noter_financier(ticker, lire_fondamentaux(engine or moteur(), ticker))


def analyser_risque(ticker: str, engine=None) -> dict:
    """Module Risque complet pour une action : lecture en base puis notation."""
    return noter_risque(ticker, lire_clotures(engine or moteur(), ticker))


def main() -> None:
    """Note les 5 actions avec les deux modules et enregistre les notes en base."""
    engine = moteur()
    for ticker in TICKERS:
        for module, fonction in (("financier", analyser_financier), ("risque", analyser_risque)):
            res = fonction(ticker, engine)
            enregistrer_score(engine, res, module)
            note = "indisponible" if res["score"] is None else f"{res['score']:+.2f}"
            print(f"{ticker:7s} {module:10s} {note:>12s}  {' | '.join(res['raisons'])}")


if __name__ == "__main__":
    main()
