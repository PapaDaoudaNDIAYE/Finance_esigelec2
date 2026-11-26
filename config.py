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

# Niveaux d'investisseur, choisis à l'entrée de l'application (portefeuille.py).
#   montant_max     : achat le plus gros autorisé, en euros (None : pas de limite)
#   montant_alerte  : à partir de ce montant, l'achat demande une confirmation
#   part_max        : part maximale d'une action dans le portefeuille après un achat (None : libre)
#   part_alerte     : au-delà de cette part, l'achat demande une confirmation
#   achat_contre_conseil / vente_contre_conseil : « interdit », « alerte » ou « libre »
#       (acheter une action que nous conseillons de VENDRE, vendre une action notée ACHETER)
NIVEAUX = {
    "debutant": {"nom": "Débutant", "montant_max": 50_000, "montant_alerte": 10_000,
                 "part_max": 0.25, "part_alerte": 0.15,
                 "achat_contre_conseil": "interdit", "vente_contre_conseil": "alerte"},
    "moyen": {"nom": "Moyen", "montant_max": 150_000, "montant_alerte": 50_000,
              "part_max": 0.40, "part_alerte": 0.25,
              "achat_contre_conseil": "alerte", "vente_contre_conseil": "alerte"},
    "professionnel": {"nom": "Professionnel", "montant_max": None, "montant_alerte": 200_000,
                      "part_max": None, "part_alerte": 0.50,
                      "achat_contre_conseil": "libre", "vente_contre_conseil": "libre"},
}
