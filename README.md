# Alex — SMC/ICT Trading Analyzer

Outil complet pour extraire, analyser et reverse-engineer les signaux de trading XAUUSD (Gold) d'un groupe Telegram privé.

## Fonctionnalités

- **Extraction automatique** des signaux depuis un groupe Telegram privé (via compte personnel Telethon)
- **Parsing intelligent** avec Claude API (Anthropic) — gère le texte libre, les emojis, le spam
- **Données OHLC** XAUUSD récupérées via MetaTrader5 (fallback yfinance `GC=F`)
- **Analyse SMC/ICT** complète : Order Blocks, FVG, CHOCH, BOS, liquidités, Fibonacci, premium/discount
- **Reverse-engineering** des confirmations cachées par comparaison gagnants vs perdants
- **Dashboard Streamlit** interactif avec visualisations Plotly

---

## Structure du projet

```
alex/
├── config.py                  # Clés API + configuration
├── telegram_extractor.py      # Extraction signaux via Telethon
├── signal_parser.py           # Parsing avec Claude API
├── ohlc_fetcher.py            # Données XAUUSD via MetaTrader5 (fallback yfinance)
├── smc_analyzer.py            # Détection OB, FVG, CHOCH, BOS, liquidités
├── pattern_detector.py        # Reverse-engineering confirmations cachées
├── database.py                # SQLite — stockage trades + analyses
├── dashboard.py               # Streamlit dashboard
├── main.py                    # Point d'entrée principal
requirements.txt
README.md
```

---

## Installation

### 1. Prérequis

- Python 3.10+ installé sur votre serveur Windows
- Compte Telegram personnel (pas un bot)
- MetaTrader5 installé et connecté à un broker (voir section **Configuration MT5** ci-dessous)

### 2. Cloner le projet et installer les dépendances

```bash
pip install -r requirements.txt
```

> **Note :** Le package `MetaTrader5` est Windows uniquement. Sur d'autres systèmes,
> les données OHLC seront récupérées automatiquement via yfinance (`GC=F`) en fallback.

### 3. Configuration MT5

1. Téléchargez et installez MetaTrader 5 depuis [metatrader5.com](https://www.metatrader5.com/fr/download)
2. Ouvrez un compte démo gratuit chez un broker supportant XAUUSD spot (ex : ICMarkets, Pepperstone, XM)
3. Dans MT5, vérifiez que le symbole `XAUUSD` est disponible dans l'onglet *Observation du marché*
4. Laissez MT5 ouvert et connecté en arrière-plan pendant l'exécution du pipeline

### 4. Obtenir les clés API Telegram

1. Rendez-vous sur [https://my.telegram.org](https://my.telegram.org)
2. Connectez-vous avec votre numéro de téléphone
3. Cliquez sur **"API development tools"**
4. Créez une application et notez `api_id` et `api_hash`

### 5. Obtenir une clé API Claude (Anthropic)

1. Rendez-vous sur [https://console.anthropic.com](https://console.anthropic.com)
2. Créez un compte et générez une clé API

---

## Configuration

Ouvrez `alex/config.py` et remplissez vos informations :

```python
TELEGRAM_API_ID = "123456"          # Votre api_id de my.telegram.org
TELEGRAM_API_HASH = "abcdef..."     # Votre api_hash
TELEGRAM_PHONE = "+33612345678"     # Votre numéro Telegram
TELEGRAM_GROUP = "nom_du_groupe"    # Nom ou ID du groupe privé
ANTHROPIC_API_KEY = "sk-ant-..."    # Votre clé API Claude
```

---

## Utilisation

### Étape 1 — Première connexion Telegram (une seule fois)

Avant de lancer le pipeline, authentifiez votre compte Telegram de façon interactive :

```bash
python alex/setup_telegram.py
```

Ce script vous demandera le code OTP reçu sur votre téléphone (et le mot de passe 2FA si activé).
La session est sauvegardée dans `session_alex.session` — vous n'aurez plus à le relancer ensuite.

### Étape 2 — Lancer l'analyse complète

```bash
python alex/main.py
```

Le pipeline exécute automatiquement :
1. Extraction des messages Telegram (500 messages par défaut)
2. Filtrage et parsing Claude → signaux structurés JSON
3. Récupération OHLC via MetaTrader5 (fallback yfinance si MT5 indisponible)
4. Analyse SMC/ICT complète par trade
5. Détection des patterns et confirmations cachées
6. Sauvegarde dans `trades.db` (SQLite)
7. Export `trades_export.csv` et `pattern_report.json`

### Étape 3 — Lancer le dashboard

```bash
streamlit run alex/dashboard.py
```

Ouvrez votre navigateur sur [http://localhost:8501](http://localhost:8501).

---

## Formats de signaux gérés

Le parser Claude gère automatiquement ces formats (et beaucoup d'autres) :

**Signal complet avec direction explicite :**
```
sell gold 4829.84 - 4832
TP 4813
TP 4796
SL 4839
```

**Signal sans direction (direction déduite du TP > entry) :**
```
4911 - 4906.73
TP 4932
TP 4959
SL : 4899
```

**Spam ignoré automatiquement :**
```
Rejoignez notre VIP ici 👉 t.me/xxx
🔥🔥🔥 100% winrate garanti
Bonjour tout le monde !
```

---

## Outputs générés

| Fichier | Description |
|---------|-------------|
| `trades.db` | Base SQLite avec tous les trades et analyses |
| `trades_export.csv` | Export CSV de tous les trades |
| `pattern_report.json` | Rapport JSON des patterns détectés |
| `alex.log` | Logs d'exécution |
| `ohlc_cache/` | Cache des données OHLC (évite les re-téléchargements) |

---

## Dashboard — Pages disponibles

| Page | Contenu |
|------|---------|
| 📋 Trades | Tableau complet avec filtres direction/résultat/confiance |
| 🔍 Analyse SMC | Détail des confirmations par trade (CHOCH, BOS, OB, FVG, liquidité) |
| 📈 Patterns | Win rate, préférences session/Fibonacci/zone, comparaison gagnants/perdants |
| 🔐 Confirmations Cachées | Confirmations probables non documentées avec niveau de confiance |

---

## Analyse SMC/ICT expliquée

L'outil détecte automatiquement :

- **Order Blocks (OB)** : dernière bougie opposée avant un mouvement impulsif
- **Fair Value Gaps (FVG)** : déséquilibres entre 3 bougies consécutives
- **CHOCH** (Change of Character) : cassure de la structure de tendance
- **BOS** (Break of Structure) : cassure d'un swing high/low précédent
- **Liquidités** : sweeps des highs/lows précédents
- **Premium/Discount** : position du prix dans le range (50% d'équilibre)
- **Fibonacci** : niveaux 0.618, 0.66, 0.786 les plus proches de l'entrée
- **Session** : Asia (0-8h UTC), London (8-13h UTC), New York (13-18h UTC)
