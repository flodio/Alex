# Alex — SMC/ICT Trading Analyzer

Outil complet pour extraire, analyser et reverse-engineer les signaux de trading XAUUSD (Gold) d'un groupe Telegram privé.

## Fonctionnalités

- **Extraction automatique** des signaux depuis un groupe Telegram privé (via compte personnel Telethon)
- **Parsing intelligent** avec Claude API (Anthropic) — gère le texte libre, les emojis, le spam
- **Données OHLC** XAUUSD récupérées via yfinance (Gold Futures `GC=F`)
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
├── ohlc_fetcher.py            # Données XAUUSD via yfinance
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

### 2. Cloner le projet et installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Obtenir les clés API Telegram

1. Rendez-vous sur [https://my.telegram.org](https://my.telegram.org)
2. Connectez-vous avec votre numéro de téléphone
3. Cliquez sur **"API development tools"**
4. Créez une application et notez `api_id` et `api_hash`

### 4. Obtenir une clé API Claude (Anthropic)

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

### Lancer l'analyse complète

```bash
cd alex
python main.py
```

Lors de la première connexion, Telethon vous demandera votre code de vérification Telegram (envoyé par SMS ou dans l'app).

Le pipeline exécute automatiquement :
1. Extraction des messages Telegram (500 messages par défaut)
2. Filtrage et parsing Claude → signaux structurés JSON
3. Récupération OHLC via yfinance
4. Analyse SMC/ICT complète par trade
5. Détection des patterns et confirmations cachées
6. Sauvegarde dans `trades.db` (SQLite)
7. Export `trades_export.csv` et `pattern_report.json`

### Lancer le dashboard

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
