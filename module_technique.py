"""
module_technique.py — Module « Analyse technique » du Conseiller Bourse
Responsable : KONATE Boubacar (rôle Analyse technique)

PLACE DANS L'APPLICATION (voir README) :

    data.py a rangé 1 an de cours dans la table « cours ».
    CE FICHIER calcule les indicateurs techniques et donne UNE note par action
    au format commun ──► table « scores » (module « technique »)
    decision.py utilise cette note avec un poids de 30 % (65 % sans actualité récente).

LES 5 FAMILLES D'INDICATEURS (chacune notée de -1 à +1) :

    tendance   moyennes mobiles 20, 50, 200 jours : cours au-dessus = tendance haussière ;
               MM50 au-dessus de la MM200 = « croisement doré » (signal positif de fond).
    rsi        RSI 14 jours : sous 30 l'action est « survendue » (rebond probable, note +1),
               au-dessus de 70 « surachetée » (note -1). Note = (50 - RSI) / 20.
    macd       MACD 12/26/9 : MACD au-dessus de sa ligne de signal = élan haussier.
    bollinger  bandes 20 jours ± 2 écarts-types : sous la bande basse = excès de baisse (+1),
               au-dessus de la bande haute = excès de hausse (-1).
    niveaux    support (plus bas) et résistance (plus haut) des 60 séances précédentes :
               près du support = zone d'achat, près de la résistance = zone de vente ;
               cassure de la résistance = signal haussier, cassure du support = baissier.

    Note technique = moyenne pondérée des familles (POIDS_TECHNIQUE, modifiable dans config.py).

FORMAT DE SORTIE (identique pour tous les modules) :
    {"action": "RMS.PA", "score": 0.42, "raisons": [...], "disponible": True}

LANCEMENT :
    python module_technique.py      # note les 5 actions et enregistre les notes
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

import db

# -----------------------------------------------------------------------------
# 0. RÉGLAGES (repris de config.py s'ils y sont définis)
# -----------------------------------------------------------------------------
try:
    import config  # type: ignore
except ImportError:
    config = None

POIDS_TECHNIQUE = getattr(config, "POIDS_TECHNIQUE", {
    "tendance": 0.35, "rsi": 0.20, "macd": 0.20, "bollinger": 0.15, "niveaux": 0.10,
})

MIN_SEANCES = 60           # en dessous, pas assez d'historique : module indisponible
PERIODE_RSI = 14
MACD_RAPIDE, MACD_LENTE, MACD_SIGNAL = 12, 26, 9
BOLLINGER_JOURS, BOLLINGER_ECARTS = 20, 2
JOURS_NIVEAUX = 60         # fenêtre des supports et résistances
ZONE_NIVEAU = 0.15         # à moins de 15 % de l'écart support-résistance : « proche »
JOURS_CROISEMENT = 5       # un croisement MACD de moins de 5 séances est signalé
NB_RAISONS_TECHNIQUE = 3


# -----------------------------------------------------------------------------
# 1. OUTILS
# -----------------------------------------------------------------------------

def resultat(ticker: str, score, raisons: list[str], disponible: bool) -> dict:
    """Format commun du README (4 clés). La note est bornée entre -1 et +1."""
    if score is not None:
        score = round(max(-1.0, min(1.0, float(score))), 3)
    return {"action": ticker, "score": score, "raisons": list(raisons), "disponible": disponible}


def indisponible(ticker: str, raison: str) -> dict:
    return resultat(ticker, None, [raison], False)


def borner(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))


def fr(x: float, decimales: int = 1) -> str:
    """Nombre au format français : 1234.5 -> « 1 234,5 »."""
    return f"{x:,.{decimales}f}".replace(",", " ").replace(".", ",")


def euros(x: float) -> str:
    return f"{fr(x, 2)} €"


# -----------------------------------------------------------------------------
# 2. CALCUL DES INDICATEURS
# -----------------------------------------------------------------------------

def rsi(cloture: pd.Series, periode: int = PERIODE_RSI) -> pd.Series:
    """RSI de Wilder : 100 - 100 / (1 + moyenne des hausses / moyenne des baisses)."""
    ecart = cloture.diff()
    hausses = ecart.clip(lower=0).ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()
    baisses = (-ecart.clip(upper=0)).ewm(alpha=1 / periode, adjust=False, min_periods=periode).mean()
    valeur = 100 - 100 / (1 + hausses / baisses)
    # Aucune baisse sur la période : RSI = 100 (division par zéro évitée)
    return valeur.where(baisses != 0, 100.0).where(hausses.notna())


def indicateurs(cours: pd.DataFrame) -> pd.DataFrame:
    """Ajoute toutes les colonnes d'indicateurs au tableau des cours.

    cours : colonnes date, ouverture, haut, bas, cloture (du plus ancien au plus récent).
    Colonnes ajoutées : mm20, mm50, mm200, boll_haut, boll_bas, rsi, macd, macd_signal,
    macd_histo, support, resistance. Utilisé aussi par api.py pour le graphique.
    """
    df = cours.copy().reset_index(drop=True)
    c = df["cloture"].astype(float)
    haut = df["haut"].astype(float).fillna(c) if "haut" in df else c
    bas = df["bas"].astype(float).fillna(c) if "bas" in df else c

    for n in (20, 50, 200):
        df[f"mm{n}"] = c.rolling(n).mean()

    ecart_type = c.rolling(BOLLINGER_JOURS).std(ddof=0)
    milieu = c.rolling(BOLLINGER_JOURS).mean()
    df["boll_haut"] = milieu + BOLLINGER_ECARTS * ecart_type
    df["boll_bas"] = milieu - BOLLINGER_ECARTS * ecart_type

    df["rsi"] = rsi(c)

    ema_rapide = c.ewm(span=MACD_RAPIDE, adjust=False).mean()
    ema_lente = c.ewm(span=MACD_LENTE, adjust=False).mean()
    df["macd"] = ema_rapide - ema_lente
    df["macd_signal"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_histo"] = df["macd"] - df["macd_signal"]
    df.loc[: MACD_LENTE - 2, ["macd", "macd_signal", "macd_histo"]] = np.nan   # pas assez de recul

    # Support / résistance : plus bas / plus haut des 60 séances PRÉCÉDENTES (sans le jour même),
    # pour pouvoir détecter une cassure le jour où elle se produit.
    df["support"] = bas.rolling(JOURS_NIVEAUX).min().shift(1)
    df["resistance"] = haut.rolling(JOURS_NIVEAUX).max().shift(1)
    return df


# -----------------------------------------------------------------------------
# 3. NOTATION DE CHAQUE FAMILLE
# -----------------------------------------------------------------------------
# Chaque fonction reçoit le tableau d'indicateurs et renvoie (note, raison) ou None
# si l'indicateur n'est pas calculable (historique trop court).

def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def noter_tendance(df: pd.DataFrame):
    d = df.iloc[-1]
    prix = d["cloture"]
    moyennes = [n for n in (20, 50, 200) if _ok(d[f"mm{n}"])]
    if not moyennes:
        return None
    dessus = [n for n in moyennes if prix > d[f"mm{n}"]]
    votes = [1 if prix > d[f"mm{n}"] else -1 for n in moyennes]

    croisement = None
    if _ok(d["mm50"]) and _ok(d["mm200"]):
        votes.append(1 if d["mm50"] > d["mm200"] else -1)
        croisement = "MM50 au-dessus de la MM200" if d["mm50"] > d["mm200"] else "MM50 sous la MM200"

    note = sum(votes) / len(votes)
    noms = ", ".join(str(n) for n in moyennes)
    if len(dessus) == len(moyennes):
        texte = f"cours au-dessus des moyennes mobiles {noms} jours : tendance haussière"
    elif not dessus:
        texte = f"cours sous les moyennes mobiles {noms} jours : tendance baissière"
    else:
        texte = (f"cours au-dessus de la MM{'/'.join(str(n) for n in dessus)} mais sous la "
                 f"MM{'/'.join(str(n) for n in moyennes if n not in dessus)} : tendance hésitante")
    if croisement:
        texte += f" ({croisement})"
    return note, texte


def noter_rsi(df: pd.DataFrame):
    valeur = df["rsi"].iloc[-1]
    if not _ok(valeur):
        return None
    note = borner((50 - valeur) / 20)
    if valeur < 30:
        texte = f"RSI à {fr(valeur, 0)} : action survendue, rebond possible"
    elif valeur > 70:
        texte = f"RSI à {fr(valeur, 0)} : action surachetée, risque de repli"
    elif valeur <= 50:
        texte = f"RSI à {fr(valeur, 0)} : pas de surachat"
    else:
        texte = f"RSI à {fr(valeur, 0)} : se rapproche de la zone de surachat (70)"
    return note, texte


def noter_macd(df: pd.DataFrame):
    m, s = df["macd"].iloc[-1], df["macd_signal"].iloc[-1]
    if not (_ok(m) and _ok(s)):
        return None
    au_dessus = m > s
    note = 0.6 * (1 if au_dessus else -1) + 0.4 * (1 if m > 0 else -1)

    # Croisement récent ? On cherche le dernier changement de signe de l'histogramme.
    histo = df["macd_histo"].dropna()
    signes = np.sign(histo.to_numpy())
    depuis = None
    for i in range(1, min(JOURS_CROISEMENT, len(signes) - 1) + 1):
        if signes[-i] != signes[-i - 1]:
            depuis = i - 1
            break
    if depuis is not None:
        sens = "haussier" if au_dessus else "baissier"
        quand = "aujourd'hui" if depuis == 0 else f"il y a {depuis} séance{'s' if depuis > 1 else ''}"
        texte = f"croisement {sens} du MACD {quand}"
        note = borner(note * 1.2)
    else:
        texte = ("MACD au-dessus de sa ligne de signal : élan haussier" if au_dessus
                 else "MACD sous sa ligne de signal : élan baissier")
    return note, texte


def noter_bollinger(df: pd.DataFrame):
    d = df.iloc[-1]
    if not (_ok(d["boll_haut"]) and _ok(d["boll_bas"])) or d["boll_haut"] == d["boll_bas"]:
        return None
    position = (d["cloture"] - d["boll_bas"]) / (d["boll_haut"] - d["boll_bas"])   # 0 = bande basse
    note = borner(1 - 2 * position)
    if position < 0:
        texte = "cours sous la bande basse de Bollinger : excès de baisse"
    elif position > 1:
        texte = "cours au-dessus de la bande haute de Bollinger : excès de hausse"
    elif position < 0.2:
        texte = "cours proche de la bande basse de Bollinger"
    elif position > 0.8:
        texte = "cours proche de la bande haute de Bollinger"
    else:
        texte = "cours au milieu des bandes de Bollinger : pas d'excès"
    return note, texte


def noter_niveaux(df: pd.DataFrame):
    d = df.iloc[-1]
    sup, res, prix = d["support"], d["resistance"], d["cloture"]
    if not (_ok(sup) and _ok(res)) or res <= sup:
        return None
    if prix > res:
        return 0.6, f"cassure de la résistance à {euros(res)} : signal haussier"
    if prix < sup:
        return -0.6, f"cassure du support à {euros(sup)} : signal baissier"
    position = (prix - sup) / (res - sup)
    if position < ZONE_NIVEAU:
        return 0.6, f"cours proche du support à {euros(sup)} : zone d'achat"
    if position > 1 - ZONE_NIVEAU:
        return -0.6, f"cours proche de la résistance à {euros(res)} : zone de vente"
    return 0.0, f"cours entre le support ({euros(sup)}) et la résistance ({euros(res)})"


FAMILLES = {
    "tendance": noter_tendance,
    "rsi": noter_rsi,
    "macd": noter_macd,
    "bollinger": noter_bollinger,
    "niveaux": noter_niveaux,
}


# -----------------------------------------------------------------------------
# 4. NOTE TECHNIQUE D'UNE ACTION
# -----------------------------------------------------------------------------

def detail_familles(cours: pd.DataFrame) -> dict:
    """Note et raison de chaque famille : {"rsi": {"note": 0.4, "raison": "..."}, ...}.
    Les familles non calculables sont absentes. Utilisé par noter_technique et api.py."""
    df = indicateurs(cours)
    detail = {}
    for nom, fonction in FAMILLES.items():
        res = fonction(df)
        if res is not None:
            detail[nom] = {"note": round(float(res[0]), 3), "raison": res[1]}
    return detail


def noter_technique(ticker: str, cours: pd.DataFrame | None) -> dict:
    """MODULE TECHNIQUE — note une action à partir de son historique de cours.

    Étapes :
      1. au moins MIN_SEANCES séances, sinon disponible = False ;
      2. calcul des indicateurs et note de chaque famille ;
      3. note = moyenne pondérée (poids remis à 100 % si une famille manque) ;
      4. raisons = d'abord les familles qui vont dans le sens de la note, les plus fortes en tête.
    """
    if cours is None or len(cours) == 0:
        return indisponible(ticker, "cours indisponibles pour l'analyse technique")
    cours = cours.dropna(subset=["cloture"])
    if len(cours) < MIN_SEANCES:
        return indisponible(ticker, "historique de cours insuffisant pour l'analyse technique")

    detail = detail_familles(cours)
    poids = {nom: POIDS_TECHNIQUE.get(nom, 0) for nom in detail}
    total = sum(poids.values())
    if total <= 0:
        return indisponible(ticker, "indicateurs techniques non calculables")

    score = sum(detail[n]["note"] * p for n, p in poids.items()) / total
    apports = sorted(detail, key=lambda n: (detail[n]["note"] * score < 0,
                                            -abs(detail[n]["note"] * poids[n])))
    raisons = [detail[n]["raison"] for n in apports[:NB_RAISONS_TECHNIQUE]]
    return resultat(ticker, score, raisons, True)


def analyser(ticker: str, engine=None) -> dict:
    """Point d'entrée appelé par decision.py : lecture des cours en base puis notation."""
    engine = engine or db.get_engine()
    return noter_technique(ticker, db.lire_cours(engine, ticker))


def main() -> None:
    engine = db.get_engine()
    for ticker in db.TICKERS:
        res = analyser(ticker, engine)
        db.enregistrer_score(engine, res, "technique")
        note = "indisponible" if res["score"] is None else f"{res['score']:+.2f}"
        print(f"{ticker:7s} technique {note:>12s}  {' | '.join(res['raisons'])}")


if __name__ == "__main__":
    main()
