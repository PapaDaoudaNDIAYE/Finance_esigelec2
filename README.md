# Conseiller Bourse : Acheter / Vendre / Ne rien faire
 
Application d'aide à la décision pour un investisseur particulier disposant de 500 000 €.
Pour chacune de ses actions, elle analyse l'information, le graphique, les comptes de l'entreprise et le risque. Elle donne ensuite un conseil clair et explique pourquoi :
 
> « Pour les raisons A, B, C, D, nous vous conseillons d'**ACHETER** aujourd'hui, Monsieur Dupont. »
 
⚠️ **Avertissement** : ce projet est un outil d'aide à la décision réalisé dans un cadre pédagogique. Il ne constitue pas un conseil en investissement. La décision finale revient toujours à l'investisseur.
 
---
 
## Sommaire
1. [Périmètre](#périmètre)
2. [Fonctionnalités](#fonctionnalités)
3. [Comment fonctionne l'algorithme](#comment-fonctionne-lalgorithme)
4. [Architecture](#architecture)
5. [Structure du projet](#structure-du-projet)
6. [Base de données](#base-de-données)
7. [Installation](#installation)
8. [Configuration](#configuration)
9. [Lancement](#lancement)
10. [Déploiement sur Vercel](#déploiement-sur-vercel)
11. [Tests](#tests)
12. [Équipe](#équipe)
13. [Limites et améliorations](#limites-et-améliorations)
---
 
## Périmètre
 
L'application analyse **uniquement** ces 5 actions, toutes cotées sur Euronext Paris :
 
| Société | Ticker | Secteur |
|---|---|---|
| Hermès | `RMS.PA` | Luxe |
| TotalEnergies | `TTE.PA` | Énergie |
| Air Liquide | `AI.PA` | Chimie / gaz industriels |
| Dassault Systèmes | `DSY.PA` | Logiciels |
| Capgemini | `CAP.PA` | Services informatiques |
 
---
 
## Fonctionnalités
 
| # | Cas d'utilisation |
|---|---|
| UC1 | Page d'accueil : « Bonjour Monsieur Dupont » et la liste des 5 actions |
| UC2 | Page détail d'une action : cours, variation du jour, graphique, actualités, chiffres clés |
| UC3 | Conseil **ACHETER / VENDRE / NE RIEN FAIRE**, avec la liste des raisons |
| UC4 | Données rechargées à l'ouverture, et bouton « Actualiser » |
| UC5 | Sans information récente, le modèle s'appuie principalement sur l'analyse technique |
| UC6 | Si une source est indisponible : message clair, l'application ne plante pas |
| UC7 | Si le marché est fermé : affichage du dernier cours connu et de sa date |
 
---
 
## Comment fonctionne l'algorithme
 
### 1. Quatre modules d'analyse
Chaque module rend une note de **-1** (très négatif) à **+1** (très positif) et la liste des raisons qui l'expliquent.
 
| Module | Ce qu'il analyse | Méthode |
|---|---|---|
| **Information** | Actualités, résultats, annonces des 7 derniers jours | LLM : lecture et notation du sentiment |
| **Technique** | Moyennes mobiles (20, 50, 200 jours), bandes de Bollinger, RSI, MACD, supports et résistances | Règles sur les indicateurs |
| **Financier** | PER, croissance, marges, endettement, dividende | Règles sur les ratios |
| **Risque** | Volatilité du cours | Statistiques |
 
### 2. Pondération
L'information est le critère le plus important. Quand il n'y en a pas, l'analyse technique prend le relais.
 
| Module | Info récente disponible | Pas d'info récente |
|---|---|---|
| Information | **45 %** | 0 % |
| Technique | 30 % | **65 %** |
| Financier | 15 % | 20 % |
| Risque | 10 % | 15 % |
 
### 3. Décision
 
```
score final = somme (note du module × poids du module)
```
 
| Score final | Conseil |
|---|---|
| > +0,3 | **ACHETER** |
| < -0,3 | **VENDRE** |
| entre -0,3 et +0,3 | **NE RIEN FAIRE** |
 
Les raisons de chaque module sont rassemblées et affichées sous le conseil.
 
### Format commun des modules
Tous les modules renvoient exactement cette structure :
 
```json
{
  "action": "RMS.PA",
  "score": 0.6,
  "raisons": ["Bons résultats publiés le 20/11", "RSI à 42 : pas de surachat"],
  "disponible": true
}
```
 
`disponible` vaut `false` quand le module n'a pas pu produire de note, par exemple faute d'information récente ou parce qu'une source est en panne.
 
---
 
## Architecture

```
  Sources externes            Traitement (Python)                    Affichage
 ┌──────────────────┐     ┌────────────────────────┐
 │ yfinance (cours, │     │ module_info.py  (LLM)  │
 │ chiffres)        │──┐  │ module_technique.py    │──┐
 │ Google Actualités│  │  │ module_financier.py    │  │
 │ (RSS)            │  │  └────────────────────────┘  │
 └──────────────────┘  ▼            ▲   │            ▼
                  ┌─────────┐       │   │      ┌─────────────┐    ┌──────────┐  JSON  ┌──────────────┐
                  │ data.py │──► bourse.db ◄── │ decision.py │    │  api.py  │──────► │ web/ Next.js │
                  └─────────┘     (SQLite) ──────────────────────► │ FastAPI  │        │ (port 3000)  │
                                                                   └──────────┘        └──────────────┘
```

La base de données est le point central : chaque module lit ses données dans la base et y écrit sa note.
L'API (`api.py`) lit la base et la sert en JSON ; le front-end Next.js (`web/`) n'appelle que l'API.

**Technologies** : Python 3.11+, pandas, numpy, yfinance, SQLAlchemy + SQLite, Ollama (LLM open source local),
FastAPI + Uvicorn, Next.js 15 + React 19 + TypeScript, lightweight-charts (graphiques TradingView), pytest.

---

## Structure du projet

```
Finance_esigelec2/
├── README.md
├── requirements.txt          # dépendances de production (installées par Vercel)
├── requirements-dev.txt      # + uvicorn, pytest : pour travailler en local
├── pyproject.toml            # point d'entrée Vercel : api:app
├── .python-version           # Python 3.12 (Vercel)
├── vercel.json               # durée maximale d'une requête (60 s)
├── .env.example              # modèle du fichier de configuration
├── config.py                 # tickers, poids, seuils
├── db.py                     # schéma et connexion à la base (SQLite ou PostgreSQL)
├── data.py                   # récupération des cours, chiffres et news
├── module_info.py            # module Information (LLM Ollama + lexique de secours)
├── module_technique.py       # module Analyse technique
├── module_financier.py       # modules Financier et Risque
├── decision.py               # pondération, seuils, phrase finale
├── api.py                    # application FastAPI : API /api/... + site (web/out/)
├── migrer_sqlite_vers_postgres.py  # copie bourse.db vers PostgreSQL
├── bourse.db                 # base SQLite locale (mise à jour par mise-a-jour.yml)
├── .github/workflows/
│   ├── mise-a-jour.yml       # met à jour bourse.db 3 fois par jour (dépôt)
│   └── refresh.yml           # appelle /api/refresh du site en ligne toutes les 15 min
├── tests/                    # un fichier de test par module + test_api.py
└── web/                      # front-end Next.js
    ├── app/page.tsx          # accueil (UC1)
    ├── app/action/[ticker]/  # détail d'une action (UC2, UC3)
    ├── components/           # graphique, jauge, cartes, en-tête
    ├── out/                  # site exporté par « npm run build », servi par api.py
    └── lib/                  # appels à l'API, mise en forme
```

---

## Base de données
 
| Table | Colonnes principales |
|---|---|
| `actions` | ticker, nom, secteur |
| `cours` | ticker, date, ouverture, haut, bas, clôture, volume |
| `actualites` | ticker, date, titre, source, lien, score_sentiment |
| `fondamentaux` | ticker, date, per, croissance, marge, dette, dividende |
| `scores` | ticker, date, module, score, raisons, disponible |
| `conseils` | ticker, date, score_final, signal, phrase |
 
SQLite suffit pour le prototype. Grâce à SQLAlchemy, on peut passer à PostgreSQL en changeant seulement `DATABASE_URL` dans le fichier `.env`.
 
---
 
## Installation

Prérequis : Python 3.11 ou plus récent, Node.js 20 ou plus récent, et Git.

```bash
git clone <url-du-depot>
cd Finance_esigelec2

# Python
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements-dev.txt

# Front-end
cd web
npm install
cd ..
```

Facultatif : installer [Ollama](https://ollama.com) puis `ollama pull qwen2.5:7b` pour que les actualités
soient notées par le LLM. Sans Ollama, un lexique de mots-clés prend le relais.

---

## Configuration

Copier le modèle de configuration, puis le remplir :

```bash
cp .env.example .env
```

```env
DATABASE_URL=sqlite:///bourse.db      # en ligne : adresse PostgreSQL (Neon, Supabase)
LLM_API_KEY=                          # vide avec Ollama local ; clé d'un Ollama hébergé sinon
NOM_CLIENT=Monsieur Dupont
REFRESH_SECRET=                       # protège /api/refresh (mise à jour automatique)
LLM_MODELE=qwen2.5:7b
LLM_URL=http://localhost:11434
```

⚠️ Ne jamais publier le fichier `.env` sur GitHub : il est listé dans `.gitignore`.

Les poids et les seuils se règlent dans `config.py`.

---

## Lancement

```bash
# 1. (facultatif) Recharger les données et recalculer les conseils
python data.py
python decision.py

# 2. Construire le site (après chaque modification de web/)
cd web
npm run build          # crée web/out/ (fichiers statiques)
cd ..

# 3. Lancer l'application (API + site)
uvicorn api:app --port 8000
```

Tout s'ouvre à l'adresse `http://localhost:8000` (le site est servi par FastAPI, comme en ligne) ;
la documentation de l'API est sur `http://localhost:8000/docs`.
Le bouton **Actualiser** relance l'étape 1 en arrière-plan sans quitter le site.

Pour modifier le site avec rechargement automatique : garder `uvicorn api:app --port 8000` lancé,
puis `cd web` et `npm run dev`, et ouvrir `http://localhost:3000` (les appels `/api/...` sont
relayés vers le port 8000).

---

## Déploiement sur Vercel

En ligne, une seule application FastAPI (`api.py`) sert l'API **et** le site (`web/out/`).
Les données sont dans une base **PostgreSQL** : le disque de Vercel est en lecture seule et
SQLite n'y conserverait rien.

| Élément | Rôle |
|---|---|
| `pyproject.toml` | indique à Vercel le point d'entrée `api:app` |
| `.python-version` | Python 3.12 |
| `requirements.txt` | dépendances de production (sans uvicorn ni pytest, dans `requirements-dev.txt`) |
| `vercel.json` | durée maximale d'une requête : 60 s |
| `web/out/` | le site exporté par `npm run build` : **à commiter** (Vercel ne construit pas le site) |
| `/api/refresh` | mise à jour complète, protégée par `Authorization: Bearer <REFRESH_SECRET>` |
| `.github/workflows/refresh.yml` | appelle `/api/refresh` toutes les 15 minutes pendant la séance |
| `migrer_sqlite_vers_postgres.py` | copie `bourse.db` vers PostgreSQL, sans doublon |

### Étapes

1. **Créer une base PostgreSQL** gratuite sur [Neon](https://neon.tech) ou [Supabase](https://supabase.com)
   et copier son adresse (`postgresql://...`).
2. **Copier les données** existantes dans cette base :
   ```bash
   # Windows (PowerShell)
   $env:DATABASE_URL="postgresql://..."; python migrer_sqlite_vers_postgres.py
   # macOS / Linux
   DATABASE_URL="postgresql://..." python migrer_sqlite_vers_postgres.py
   ```
3. **Construire le site** (`cd web && npm run build`) et commiter `web/out/` avec le reste.
4. **Importer le dépôt** sur [vercel.com/new](https://vercel.com/new) et ajouter les variables
   d'environnement `DATABASE_URL`, `LLM_API_KEY`, `NOM_CLIENT` et `REFRESH_SECRET`, puis **Deploy**.
5. **Dans GitHub** (Settings → Secrets and variables → Actions), ajouter les secrets `APP_URL`
   (l'adresse en `.vercel.app`, sans `/` final) et `REFRESH_SECRET` (la même valeur que sur Vercel).
6. **Vérifier** : la page d'accueil, une page détail, puis l'onglet Actions → « Rafraîchir le site »
   → Run workflow (doit se terminer en vert).

En ligne, le bouton **Actualiser** recharge l'affichage : la mise à jour des données est faite
toutes les 15 minutes par GitHub Actions (de 9 h à 18 h, heure de Paris, les jours de bourse).
Sans `LLM_API_KEY` (ni Ollama joignable), les actualités sont notées par le lexique de mots-clés.

---

## Tests
 
```bash
pip install -r requirements-dev.txt   # une fois
pytest tests/
```
 
Chaque module a son fichier de test. Exemples de cas vérifiés :
- un RSI à 25 donne une note technique positive ;
- sans news de moins de 7 jours, le poids de l'information passe à 0 % ;
- un score final de +0,45 donne le conseil « ACHETER » ;
- une source indisponible renvoie `disponible: false` sans faire planter l'application.
---
 
## Équipe
 
| Membre | Rôle | Fichiers |
|---|---|---|
| Papa | Données et base de données | `db.py`, `data.py` |
| JP | Module Information | `module_info.py` |
| KONATE Boubacar | Analyse technique + coordination des livrables | `module_technique.py`, `docs/` |
| Axel | Financier, risque et décision | `module_financier.py`, `decision.py` |
| RIVIERE Constance | Front-end | `web/` (Next.js), `api.py` |
 
**Méthode de travail** : une branche Git par module, et une pull request relue par un autre membre avant chaque fusion.
 
---
 
## Limites et améliorations
 
**Limites actuelles**
- Cours avec environ **15 minutes de retard** (source gratuite yfinance).
- News issues de flux RSS : quelques articles hors sujet peuvent passer le filtre.
- Poids et seuils fixés à la main, sans backtest complet.
- Prototype réalisé en 3 jours.
**Pistes d'amélioration**
- Vrai temps réel via l'API d'un courtier ou d'Euronext.
- API de news professionnelle avec sentiment (EODHD, MarketAux).
- Backtest sur plusieurs années pour valider les poids et les seuils.
- Optimisation des poids par machine learning.
- Conseil de montant (combien acheter ou vendre sur les 500 000 €).
- Passage à PostgreSQL et mise à jour plus fréquente (aujourd'hui 3 fois par jour via GitHub Actions).
 