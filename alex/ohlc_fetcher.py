"""
Récupération des données OHLC pour XAUUSD via MetaTrader5 (source principale).
Si MT5 n'est pas installé ou pas connecté, fallback automatique sur yfinance (GC=F).
Les données sont mises en cache localement pour éviter les requêtes répétées.
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from types import ModuleType
from typing import Dict, Optional

import numpy as np
import pandas as pd
import yfinance as yf

import config

logger = logging.getLogger(__name__)

# Dossier de cache local
CACHE_DIR = "ohlc_cache"

# ----- Détection de MetaTrader5 -----
try:
    import MetaTrader5 as mt5
    _MT5_DISPONIBLE = mt5.initialize()
    if not _MT5_DISPONIBLE:
        logger.warning(
            "MetaTrader5 installé mais impossible de se connecter à MT5. "
            "Vérifiez que MT5 est ouvert et connecté à un broker. "
            "Fallback sur yfinance (GC=F) — les prix peuvent différer des prix spot."
        )
except ImportError:
    mt5: Optional[ModuleType] = None
    _MT5_DISPONIBLE = False
    logger.warning(
        "Package MetaTrader5 non installé. "
        "Fallback sur yfinance (GC=F) — les prix peuvent différer des prix spot. "
        "Pour utiliser MT5 : pip install MetaTrader5 (Windows uniquement)."
    )

# Correspondance timeframe → constante MT5
_MT5_TIMEFRAMES: Dict[str, int] = {}
if mt5 is not None:
    _MT5_TIMEFRAMES = {
        "1m":  mt5.TIMEFRAME_M1,
        "5m":  mt5.TIMEFRAME_M5,
        "15m": mt5.TIMEFRAME_M15,
        "1h":  mt5.TIMEFRAME_H1,
        "4h":  mt5.TIMEFRAME_H4,
        "1d":  mt5.TIMEFRAME_D1,
    }

# ----- Configuration yfinance (fallback) -----
# Symbole Gold Futures utilisé en fallback si MT5 non disponible
_YFINANCE_SYMBOLE_FALLBACK = "GC=F"

# Intervalles nativement supportés par yfinance
_YFINANCE_INTERVALS: Dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
}

# Le timeframe 4h est obtenu par rééchantillonnage depuis 1h (yfinance uniquement)
_RESAMPLE_DEPUIS: Dict[str, str] = {
    "4h": "1h",
}

# Limites d'historique yfinance selon l'intervalle
_MAX_DAYS_PAR_INTERVALLE: Dict[str, int] = {
    "1m":  7,
    "5m":  60,
    "15m": 60,
    "1h":  730,
    "4h":  730,
    "1d":  3650,
}


# ---------------------------------------------------------------------------
# Helpers cache
# ---------------------------------------------------------------------------

def _chemin_cache(symbol: str, intervalle: str, debut: str, fin: str) -> str:
    """Construit le chemin du fichier de cache pour une requête donnée."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    nom = f"{symbol}_{intervalle}_{debut}_{fin}.pkl".replace(":", "-")
    return os.path.join(CACHE_DIR, nom)


def _charger_cache(chemin: str) -> Optional[pd.DataFrame]:
    """Charge un DataFrame depuis le cache si disponible."""
    if os.path.exists(chemin):
        with open(chemin, "rb") as f:
            logger.debug(f"Cache chargé : {chemin}")
            return pickle.load(f)
    return None


def _sauvegarder_cache(chemin: str, df: pd.DataFrame) -> None:
    """Sauvegarde un DataFrame dans le cache."""
    with open(chemin, "wb") as f:
        pickle.dump(df, f)
    logger.debug(f"Cache sauvegardé : {chemin}")


# ---------------------------------------------------------------------------
# Source MT5
# ---------------------------------------------------------------------------

def _telecharger_ohlc_mt5(
    symbol: str,
    intervalle: str,
    debut: datetime,
    fin: datetime,
) -> pd.DataFrame:
    """
    Télécharge les données OHLC depuis MetaTrader5.

    Args:
        symbol    : symbole MT5, ex "XAUUSD"
        intervalle: timeframe, ex "1h"
        debut     : datetime de début (naive UTC)
        fin       : datetime de fin (naive UTC)

    Returns:
        DataFrame pandas avec colonnes Open, High, Low, Close, Volume
        ou DataFrame vide si aucune donnée.
    """
    if mt5 is None or not _MT5_DISPONIBLE:
        return pd.DataFrame()

    tf_mt5 = _MT5_TIMEFRAMES.get(intervalle)
    if tf_mt5 is None:
        logger.warning(f"Timeframe MT5 inconnu : {intervalle}")
        return pd.DataFrame()

    debut_str = debut.strftime("%Y-%m-%d")
    fin_str = fin.strftime("%Y-%m-%d")
    chemin = _chemin_cache(symbol, intervalle, debut_str, fin_str)
    df_cache = _charger_cache(chemin)
    if df_cache is not None:
        return df_cache

    logger.info(f"[MT5] Téléchargement OHLC : {symbol} {intervalle} {debut_str} → {fin_str}")
    rates = mt5.copy_rates_range(symbol, tf_mt5, debut, fin)

    if rates is None or len(rates) == 0:
        logger.warning(f"[MT5] Aucune donnée retournée pour {symbol} {intervalle}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    # La colonne 'time' MT5 est un timestamp POSIX (secondes)
    df.index = pd.to_datetime(df["time"], unit="s")
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "tick_volume": "Volume",
    })
    df = df[["Open", "High", "Low", "Close", "Volume"]]

    _sauvegarder_cache(chemin, df)
    return df


# ---------------------------------------------------------------------------
# Source yfinance (fallback)
# ---------------------------------------------------------------------------

def _resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Rééchantillonne un DataFrame 1h en 4h."""
    if df_1h.empty:
        return df_1h
    return df_1h.resample("4h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()


def _telecharger_ohlc_yfinance(
    symbol: str,
    intervalle: str,
    debut: datetime,
    fin: datetime,
) -> pd.DataFrame:
    """
    Télécharge les données OHLC depuis yfinance (fallback uniquement).
    Utilise GC=F (Gold Futures) indépendamment du symbole passé en paramètre.
    """
    # Gestion des timeframes obtenus par rééchantillonnage (ex: 4h depuis 1h)
    if intervalle in _RESAMPLE_DEPUIS:
        source_tf = _RESAMPLE_DEPUIS[intervalle]
        df_source = _telecharger_ohlc_yfinance(symbol, source_tf, debut, fin)
        if intervalle == "4h":
            return _resample_4h(df_source)
        return df_source

    # Ajustement de la date de début selon les limites yfinance
    max_jours = _MAX_DAYS_PAR_INTERVALLE.get(intervalle, 60)
    limite_debut = datetime.now() - timedelta(days=max_jours)
    if debut < limite_debut:
        logger.debug(
            f"[yfinance] Intervalle {intervalle} : début ajusté de {debut} à {limite_debut}"
        )
        debut = limite_debut

    # Toujours utiliser le symbole Gold Futures en fallback
    symbole_yf = _YFINANCE_SYMBOLE_FALLBACK
    debut_str = debut.strftime("%Y-%m-%d")
    fin_str = fin.strftime("%Y-%m-%d")
    interval_yf = _YFINANCE_INTERVALS.get(intervalle, intervalle)

    chemin = _chemin_cache(symbole_yf, intervalle, debut_str, fin_str)
    df_cache = _charger_cache(chemin)
    if df_cache is not None:
        return df_cache

    logger.info(f"[yfinance] Téléchargement OHLC : {symbole_yf} {intervalle} {debut_str} → {fin_str}")
    ticker = yf.Ticker(symbole_yf)
    df = ticker.history(start=debut_str, end=fin_str, interval=interval_yf)

    if df.empty:
        logger.warning(f"[yfinance] Aucune donnée retournée pour {symbole_yf} {intervalle}")
        return df

    _sauvegarder_cache(chemin, df)
    return df


# ---------------------------------------------------------------------------
# Interface publique
# ---------------------------------------------------------------------------

def _telecharger_ohlc(
    symbol: str,
    intervalle: str,
    debut: datetime,
    fin: datetime,
) -> pd.DataFrame:
    """
    Télécharge les données OHLC en utilisant MT5 en priorité.
    Si MT5 n'est pas disponible ou ne retourne pas de données, fallback sur yfinance.
    """
    if _MT5_DISPONIBLE:
        df = _telecharger_ohlc_mt5(symbol, intervalle, debut, fin)
        if not df.empty:
            return df
        logger.warning(
            f"[MT5] Pas de données pour {symbol} {intervalle} — tentative fallback yfinance."
        )

    return _telecharger_ohlc_yfinance(symbol, intervalle, debut, fin)


def get_ohlc(
    timestamp: str,
    symbol: str = None,
    timeframes: list = None,
) -> Dict[str, pd.DataFrame]:
    """
    Récupère les données OHLC autour du timestamp d'un trade.

    Utilise MetaTrader5 en source principale (symbole spot XAUUSD).
    Si MT5 n'est pas disponible, fallback automatique sur yfinance (GC=F).

    Args:
        timestamp : ISO 8601, ex "2024-01-15T14:30:00+00:00"
        symbol    : symbole MT5, défaut = config.SYMBOL (XAUUSD)
        timeframes: liste de timeframes, défaut = config.TIMEFRAMES

    Returns:
        dict {timeframe: DataFrame OHLC}
    """
    if symbol is None:
        symbol = config.SYMBOL
    if timeframes is None:
        timeframes = config.TIMEFRAMES

    # Conversion du timestamp en datetime
    ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    ts_naive = ts.replace(tzinfo=None)

    debut = ts_naive - timedelta(days=config.OHLC_DAYS_BEFORE)
    fin = ts_naive + timedelta(days=config.OHLC_DAYS_AFTER)

    resultats: Dict[str, pd.DataFrame] = {}
    for tf in timeframes:
        df = _telecharger_ohlc(symbol, tf, debut, fin)
        resultats[tf] = df

    return resultats
