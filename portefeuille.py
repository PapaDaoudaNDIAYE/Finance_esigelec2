"""
portefeuille.py — Portefeuille simulé : acheter et vendre les 5 actions avec de l'argent virtuel

PLACE DANS L'APPLICATION :

    base (cours, conseils) ──► CE FICHIER ──► table « ordres » ──► api.py (/api/portefeuille, /api/ordres)

AUCUN ORDRE RÉEL n'est passé : c'est un entraînement. Le client part de CAPITAL_DEPART euros
(config.py) et peut acheter ou vendre les 5 actions suivies.

RÈGLES (« en fonction du marché ») :
    - un ordre n'est accepté que pendant la séance d'Euronext Paris (9 h - 17 h 30, jours ouvrés) ;
    - il est exécuté au dernier cours connu (environ 15 minutes de retard, comme l'affichage) ;
    - frais de courtage : FRAIS_ORDRE (0,1 %) du montant ;
    - on ne peut pas acheter au-delà de ses liquidités, ni vendre plus d'actions qu'on n'en a ;
    - le conseil du moment (ACHETER, VENDRE, NE RIEN FAIRE) est noté avec l'ordre, pour comparer
      après coup les décisions du client et celles du conseiller.

Seuls les ordres sont enregistrés. Liquidités, positions, prix de revient et plus-values sont
recalculés à partir d'eux (calculer() : une fonction sans base de données, facile à tester).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, insert, select, text

import data
import db

try:
    import config  # type: ignore
except ImportError:
    config = None

CAPITAL_DEPART = float(getattr(config, "CAPITAL_DEPART", 500_000))
FRAIS_ORDRE = float(getattr(config, "FRAIS_ORDRE", 0.001))
QUANTITE_MAX = 1_000_000        # garde-fou contre une faute de frappe
HISTORIQUE = 100                # ordres renvoyés au site (les plus récents)


class OrdreRefuse(Exception):
    """Ordre impossible : le message est affiché tel quel au client."""


def _euros(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def frais(montant: float) -> float:
    return round(montant * FRAIS_ORDRE, 2)


# -----------------------------------------------------------------------------
# 1. LE CALCUL (sans base de données)
# -----------------------------------------------------------------------------

def calculer(ordres: list[dict], cours: dict[str, float | None], capital: float = CAPITAL_DEPART) -> dict:
    """Rejoue les ordres dans l'ordre chronologique.

    Prix de revient unitaire (PRU) : coût moyen d'achat, frais compris. Une vente ne change pas
    le PRU des actions restantes ; elle dégage une plus-value réalisée = (prix - PRU) x quantité - frais.
    cours : dernier cours de chaque action (sinon le prix du dernier ordre sert d'estimation).
    """
    liquidites, realise, frais_payes = capital, 0.0, 0.0
    lignes: dict[str, dict] = {}
    for o in sorted(ordres, key=lambda o: (o["date"], o.get("id") or 0)):
        p = lignes.setdefault(o["ticker"], {"quantite": 0, "cout": 0.0, "dernier_prix": o["prix"]})
        montant = o["quantite"] * o["prix"]
        frais_payes += o["frais"]
        p["dernier_prix"] = o["prix"]
        if o["sens"] == "ACHAT":
            liquidites -= montant + o["frais"]
            p["quantite"] += o["quantite"]
            p["cout"] += montant + o["frais"]
        else:
            pru = p["cout"] / p["quantite"] if p["quantite"] else 0.0
            liquidites += montant - o["frais"]
            realise += montant - o["frais"] - pru * o["quantite"]
            p["cout"] -= pru * o["quantite"]
            p["quantite"] -= o["quantite"]

    positions = []
    for ticker, p in lignes.items():
        if p["quantite"] <= 0:
            continue
        prix = cours.get(ticker) or p["dernier_prix"]
        valeur = p["quantite"] * prix
        positions.append({"ticker": ticker, "quantite": p["quantite"], "pru": p["cout"] / p["quantite"],
                          "cours": prix, "valeur": valeur, "plus_value": valeur - p["cout"],
                          "plus_value_pct": valeur / p["cout"] - 1 if p["cout"] else None})
    valeur_titres = sum(p["valeur"] for p in positions)
    total = liquidites + valeur_titres
    for p in positions:
        p["poids"] = p["valeur"] / total if total else None
    positions.sort(key=lambda p: -p["valeur"])
    return {
        "capital_depart": capital,
        "liquidites": liquidites,
        "valeur_titres": valeur_titres,
        "valeur_totale": total,
        "gain": total - capital,
        "performance": total / capital - 1 if capital else None,
        "plus_value_latente": sum(p["plus_value"] for p in positions),
        "plus_value_realisee": realise,
        "frais_payes": frais_payes,
        "positions": positions,
    }


def verifier(etat: dict, ticker: str, sens: str, quantite: int, prix: float) -> float:
    """Lève OrdreRefuse si l'ordre est impossible ; sinon renvoie ses frais."""
    if sens not in ("ACHAT", "VENTE"):
        raise OrdreRefuse("Sens inconnu : choisissez « achat » ou « vente ».")
    if not isinstance(quantite, int) or isinstance(quantite, bool) or quantite < 1:
        raise OrdreRefuse("La quantité doit être un nombre entier d'actions, au moins 1.")
    if quantite > QUANTITE_MAX:
        raise OrdreRefuse(f"Quantité trop grande (maximum {QUANTITE_MAX:,} actions par ordre).".replace(",", " "))
    montant = quantite * prix
    f = frais(montant)
    nom = db.nom_action(ticker)
    if sens == "ACHAT" and montant + f > etat["liquidites"] + 1e-6:
        raise OrdreRefuse(f"Liquidités insuffisantes : cet achat coûte {_euros(montant + f)} (frais compris), "
                          f"vous disposez de {_euros(etat['liquidites'])}.")
    if sens == "VENTE":
        detenues = next((p["quantite"] for p in etat["positions"] if p["ticker"] == ticker), 0)
        if detenues == 0:
            raise OrdreRefuse(f"Vous ne détenez aucune action {nom} : rien à vendre.")
        if quantite > detenues:
            raise OrdreRefuse(f"Vous ne détenez que {detenues} action{'s' if detenues > 1 else ''} {nom} : "
                              f"impossible d'en vendre {quantite}.")
    return f


# -----------------------------------------------------------------------------
# 2. LECTURE ET ÉCRITURE DANS LA BASE
# -----------------------------------------------------------------------------

def lire_ordres(connexion) -> list[dict]:
    return [dict(l) for l in connexion.execute(select(db.ordres).order_by(db.ordres.c.id)).mappings()]


def derniers_cours(engine) -> dict[str, dict]:
    """{ticker: {"prix", "date"}} : dernier cours connu de chaque action."""
    resultat = {}
    for ticker in db.TICKERS:
        dernier = db.lire_dernier_cours(engine, ticker)
        resultat[ticker] = {"prix": dernier["cloture"] if dernier else None,
                            "date": dernier["date"] if dernier else None}
    return resultat


def etat(engine) -> dict:
    """Tout ce qu'affiche la page « Portefeuille » : synthèse, positions, actions, historique."""
    db.creer_base(engine)
    with engine.connect() as cx:
        ordres = lire_ordres(cx)
    cours = derniers_cours(engine)
    signaux = {t: (db.lire_conseil(engine, t) or {}).get("signal") for t in db.TICKERS}
    resultat = calculer(ordres, {t: c["prix"] for t, c in cours.items()})
    detenues = {p["ticker"]: p["quantite"] for p in resultat["positions"]}
    for p in resultat["positions"]:
        p.update(nom=db.nom_action(p["ticker"]), signal=signaux.get(p["ticker"]))
    resultat["actions"] = [{"ticker": t, "nom": db.nom_action(t), "prix": cours[t]["prix"],
                            "date": cours[t]["date"], "signal": signaux[t], "detenues": detenues.get(t, 0)}
                           for t in db.TICKERS]
    resultat["ordres"] = [{**o, "nom": db.nom_action(o["ticker"]), "montant": o["quantite"] * o["prix"]}
                          for o in reversed(ordres[-HISTORIQUE:])]
    resultat["frais_ordre"] = FRAIS_ORDRE
    resultat["marche_ouvert"] = data.marche_ouvert()
    return resultat


def passer_ordre(engine, ticker: str, sens: str, quantite: int, moment: datetime | None = None) -> dict:
    """Exécute un ordre au dernier cours connu. Lève OrdreRefuse s'il est impossible.

    La vérification des liquidités et l'écriture se font dans UNE transaction, verrouillée sur
    PostgreSQL : deux ordres envoyés en même temps ne peuvent pas dépenser deux fois le même argent.
    """
    ticker, sens = str(ticker).upper(), str(sens).upper()
    sens = {"ACHETER": "ACHAT", "VENDRE": "VENTE"}.get(sens, sens)
    if ticker not in db.TICKERS:
        raise OrdreRefuse(f"Action inconnue : {ticker}.")
    if not data.marche_ouvert(moment):
        raise OrdreRefuse("Marché fermé : les ordres sont acceptés pendant la séance d'Euronext Paris, "
                          "de 9 h à 17 h 30, du lundi au vendredi.")
    dernier = db.lire_dernier_cours(engine, ticker)
    if not dernier or not dernier.get("cloture"):
        raise OrdreRefuse(f"Cours de {db.nom_action(ticker)} indisponible pour le moment : réessayez plus tard.")
    prix = round(float(dernier["cloture"]), 2)          # exécution au centime près
    signal = (db.lire_conseil(engine, ticker) or {}).get("signal")

    db.creer_base(engine)
    with engine.begin() as cx:
        if engine.dialect.name == "postgresql":
            cx.execute(text("SELECT pg_advisory_xact_lock(7340001)"))   # un ordre à la fois
        etat_actuel = calculer(lire_ordres(cx), {})
        f = verifier(etat_actuel, ticker, sens, quantite, prix)
        ordre = {"date": (moment or datetime.now(data.PARIS)).astimezone(data.PARIS).strftime("%Y-%m-%d %H:%M:%S"),
                 "ticker": ticker, "sens": sens, "quantite": quantite, "prix": prix, "frais": f, "signal": signal}
        ordre["id"] = cx.execute(insert(db.ordres).values(**ordre).returning(db.ordres.c.id)).scalar_one()
    return {**ordre, "nom": db.nom_action(ticker), "montant": quantite * prix}


def reinitialiser(engine) -> None:
    """Efface tous les ordres : on repart du capital de départ."""
    db.creer_base(engine)
    with engine.begin() as cx:
        cx.execute(delete(db.ordres))
