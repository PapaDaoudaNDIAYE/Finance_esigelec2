"""
migrer_sqlite_vers_postgres.py — Copie toutes les tables de bourse.db vers la base de DATABASE_URL

À lancer UNE fois, depuis son ordinateur, après avoir créé la base PostgreSQL (Neon, Supabase) :

    Windows (PowerShell) :  $env:DATABASE_URL="postgresql://..."; python migrer_sqlite_vers_postgres.py
    macOS / Linux        :  DATABASE_URL="postgresql://..." python migrer_sqlite_vers_postgres.py

    (ou mettre DATABASE_URL dans le fichier .env)

Ce que fait le script :
    1. crée les tables manquantes dans la base cible (schéma de db.py, avec ses clés) ;
    2. copie chaque table ligne par ligne, par paquets, avec un « upsert » sur la clé primaire :
       une ligne déjà présente est mise à jour, jamais dupliquée. Le script peut donc être
       relancé sans risque ;
    3. affiche le nombre de lignes de chaque table, avant et après.

La base source est bourse.db, à côté de ce fichier (modifiable avec --source chemin/vers/fichier.db).
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import func, inspect, select

import db

PAQUET = 500       # lignes envoyées en une fois


def compter(engine, table) -> int:
    try:
        with engine.connect() as cx:
            return cx.execute(select(func.count()).select_from(table)).scalar_one()
    except Exception:
        return 0


def migrer(source_url: str, cible_url: str) -> dict:
    """Copie toutes les tables de la source vers la cible. Renvoie {table: lignes copiées}."""
    source = db.get_engine(source_url)
    cible = db.get_engine(cible_url)
    db.metadata.create_all(cible)
    tables_source = set(inspect(source).get_table_names())
    copie = {}
    for table in db.metadata.sorted_tables:
        if table.name not in tables_source:
            print(f"  {table.name:13s} absente de la source : ignorée")
            continue
        cles = [c.name for c in table.primary_key.columns]
        colonnes = [c for c in table.c if c.name in {col["name"] for col in inspect(source).get_columns(table.name)}]
        with source.connect() as cx:
            lignes = [dict(l) for l in cx.execute(select(*colonnes)).mappings()]
        avant = compter(cible, table)
        for i in range(0, len(lignes), PAQUET):
            db._remplacer(cible, table, lignes[i:i + PAQUET], cles)
        if table.name == "ordres" and cible.dialect.name == "postgresql" and lignes:
            # identifiants copiés tels quels : on avance le compteur pour les prochains ordres
            with cible.begin() as cx:
                cx.exec_driver_sql("SELECT setval(pg_get_serial_sequence('ordres', 'id'), "
                                   "(SELECT MAX(id) FROM ordres))")
        copie[table.name] = len(lignes)
        print(f"  {table.name:13s} {len(lignes):6d} lignes lues · cible : {avant} -> {compter(cible, table)}")
    return copie


def main() -> None:
    parser = argparse.ArgumentParser(description="Copie bourse.db vers la base de DATABASE_URL.")
    parser.add_argument("--source", default=db.BASE_LOCALE, help="fichier SQLite source (défaut : bourse.db du projet)")
    args = parser.parse_args()

    db.charger_env()
    cible = os.getenv("DATABASE_URL", "")
    if not cible or cible.startswith("sqlite"):
        sys.exit("DATABASE_URL doit contenir l'adresse de la base PostgreSQL cible (postgresql://...).")
    if not os.path.exists(args.source):
        sys.exit(f"Fichier source introuvable : {args.source}")

    print(f"Source : {args.source}")
    print(f"Cible  : {db.normaliser_url(cible).split('@')[-1]}")     # sans le mot de passe
    migrer(f"sqlite:///{os.path.abspath(args.source)}", cible)
    print("Migration terminée.")


if __name__ == "__main__":
    main()
