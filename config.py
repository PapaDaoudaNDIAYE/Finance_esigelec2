"""
config.py — Réglages communs du Conseiller Bourse

Tous les modules lisent ce fichier s'il existe (sinon ils gardent leurs valeurs par défaut,
qui sont les mêmes que ci-dessous). Pour changer un poids ou un seuil, on le change ICI.
Les secrets (clé, adresse de la base, nom du client) restent dans le fichier .env.
"""

# -----------------------------------------------------------------------------
# Les 5 actions suivies (README, « Périmètre »)
# -----------------------------------------------------------------------------
TICKERS = ["RMS.PA", "TTE.PA", "AI.PA", "DSY.PA", "CAP.PA"]

ACTIONS = {
    "RMS.PA": {"nom": "Hermès", "secteur": "Luxe"},
    "TTE.PA": {"nom": "TotalEnergies", "secteur": "Énergie"},
    "AI.PA": {"nom": "Air Liquide", "secteur": "Gaz industriels"},
    "DSY.PA": {"nom": "Dassault Systèmes", "secteur": "Logiciels"},
    "CAP.PA": {"nom": "Capgemini", "secteur": "Services informatiques"},
}

# -----------------------------------------------------------------------------
# Décision (decision.py)
# -----------------------------------------------------------------------------
POIDS_AVEC_INFO = {"information": 0.45, "technique": 0.30, "financier": 0.15, "risque": 0.10}
POIDS_SANS_INFO = {"information": 0.00, "technique": 0.65, "financier": 0.20, "risque": 0.15}
SEUIL_ACHAT = 0.3      # score final > +0,3 : ACHETER
SEUIL_VENTE = -0.3     # score final < -0,3 : VENDRE

# -----------------------------------------------------------------------------
# Module Technique (module_technique.py)
# -----------------------------------------------------------------------------
# Part de chaque famille d'indicateurs dans la note technique (total = 1).
POIDS_TECHNIQUE = {
    "tendance": 0.35,    # moyennes mobiles 20, 50 et 200 jours
    "rsi": 0.20,         # RSI 14 jours
    "macd": 0.20,        # MACD 12/26/9
    "bollinger": 0.15,   # bandes de Bollinger 20 jours, 2 écarts-types
    "niveaux": 0.10,     # supports et résistances sur 60 séances
}

# -----------------------------------------------------------------------------
# Portefeuille simulé (portefeuille.py) : argent virtuel, aucun ordre réel
# -----------------------------------------------------------------------------
CAPITAL_DEPART = 500_000   # euros disponibles au départ
FRAIS_ORDRE = 0.001        # frais de courtage : 0,1 % du montant de chaque ordre
