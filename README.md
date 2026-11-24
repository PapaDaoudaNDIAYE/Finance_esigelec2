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
10. [Tests](#tests)
11. [Équipe](#équipe)
12. [Limites et améliorations](#limites-et-améliorations)
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
  Sources externes                Traitement                     Affichage
 ┌──────────────────┐        ┌──────────────────────┐
 │ yfinance (cours, │        │  module_info.py      │
 │ chiffres)        │──┐     │  module_technique.py │──┐
 │ News RSS         │  │     │  module_financier.py │  │
 └──────────────────┘  │     └──────────────────────┘  │
                       ▼               ▲   │           ▼
                  ┌─────────┐          │   │     ┌─────────────┐     ┌──────────┐
                  │ data.py │──► bourse.db ◄───── │ decision.py │───► │  app.py  │
                  └─────────┘     (SQLite)        └─────────────┘     │ Streamlit│
                                                                      └──────────┘
```
 
La base de données est le point central : chaque module lit ses données dans la base et y écrit sa note. Le front-end lit uniquement la base.
 
**Technologies** : Python 3.11+, pandas, pandas-ta, yfinance, feedparser, SQLAlchemy + SQLite, API LLM, Streamlit, pytest.
 
---
 
## Structure du projet
 
```
conseiller-bourse/
├── README.md
├── requirements.txt
├── .env.example            # modèle du fichier de configuration
├── config.py               # tickers, poids, seuils
├── db.py                   # schéma et connexion à la base
├── data.py                 # récupération des cours, chiffres et news
├── module_info.py          # module Information
├── module_technique.py     # module Analyse technique
├── module_financier.py     # modules Financier et Risque
├── decision.py             # pondération, seuils, phrase finale
├── app.py                  # interface Streamlit
├── bourse.db               # base SQLite (générée, non versionnée)
├── tests/
│   ├── test_data.py
│   ├── test_module_info.py
│   ├── test_module_technique.py
│   ├── test_module_financier.py
│   └── test_decision.py
└── docs/
    ├── documentation_technique.md
    ├── rapport_limites.md
    └── presentation.pdf
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
 
Prérequis : Python 3.11 ou plus récent, et Git.
 
```bash
git clone <url-du-depot>
cd conseiller-bourse
 
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
 
pip install -r requirements.txt
```
 
---
 
## Configuration
 
Copier le modèle de configuration, puis le remplir :
 
```bash
cp .env.example .env
```
 
```env
LLM_API_KEY=votre_cle_api
DATABASE_URL=sqlite:///bourse.db
NOM_CLIENT=Monsieur Dupont
```
 
⚠️ Ne jamais publier le fichier `.env` sur GitHub : il est listé dans `.gitignore`.
 
Les poids et les seuils se règlent dans `config.py`.
 
---
 
## Lancement
 
```bash
# 1. Créer la base et charger les données
python data.py
 
# 2. Calculer les notes et les conseils
python decision.py
 
# 3. Lancer l'interface
streamlit run app.py
```
 
L'application s'ouvre dans le navigateur à l'adresse `http://localhost:8501`.
Le bouton **Actualiser** relance les étapes 1 et 2 sans quitter l'interface.
 
---
 
## Tests
 
```bash
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
| RIVIERE Constance | Front-end | `app.py` |
 
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
- Simulation Monte-Carlo pour le module Risque.
- Conseil de montant (combien acheter ou vendre sur les 500 000 €).
- Passage à PostgreSQL et mise à jour automatique toutes les 15 minutes.
 