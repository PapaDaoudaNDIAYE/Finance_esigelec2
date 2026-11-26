"""
api/index.py — Point d'entrée de l'API pour Vercel.

Vercel transforme chaque fichier Python du dossier api/ en fonction serverless.
Celui-ci importe simplement l'application FastAPI de serveur.py (à la racine du projet),
qui contient toutes les routes /api/py/... En local, on lance serveur.py avec uvicorn.
"""

import os
import sys

# Les modules du projet (serveur.py, db.py, data.py...) sont à la racine, un dossier au-dessus.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from serveur import app  # noqa: E402,F401
