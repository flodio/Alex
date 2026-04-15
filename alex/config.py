# Configuration principale — remplir dans ce fichier OU via un fichier .env
# Le fichier .env (s'il existe) est chargé automatiquement et prend la priorité.
# Ne commitez jamais vos clés API dans le dépôt git !
# Copiez .env.example vers .env et remplissez vos valeurs.

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optionnel si valeurs renseignées directement

# Obtenir api_id et api_hash sur https://my.telegram.org
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")     # ex: +33612345678
TELEGRAM_GROUP = os.getenv("TELEGRAM_GROUP", "")     # Nom ou ID du groupe privé

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # Clé API Claude

DB_PATH = os.getenv("DB_PATH", "trades.db")             # Chemin vers la base SQLite

SYMBOL = os.getenv("SYMBOL", "GC=F")                    # XAUUSD sur yfinance (Gold Futures)

# Nombre de messages Telegram à récupérer par défaut
TELEGRAM_MESSAGE_LIMIT = int(os.getenv("TELEGRAM_MESSAGE_LIMIT", "500"))

# Fenêtre de temps pour les données OHLC (jours avant / après le trade)
OHLC_DAYS_BEFORE = int(os.getenv("OHLC_DAYS_BEFORE", "5"))
OHLC_DAYS_AFTER = int(os.getenv("OHLC_DAYS_AFTER", "2"))

# Timeframes analysés pour chaque trade
TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]
