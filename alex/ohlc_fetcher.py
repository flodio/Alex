"""
Récupération des données OHLC pour XAUUSD (Gold Futures) via yfinance.
Les données sont mises en cache localement pour éviter les requêtes répétées.
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

import config

logger = logging.getLogger(__name__)

# Dossier de cache local
CACHE_DIR = "ohlc_cache"

# Intervalles nativement supportés par yfinance
YFINANCE_INTERVALS: Dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "1d":  "1d",
}

# Le timeframe 4h est obtenu par rééchantillonnage depuis 1h
RESAMPLE_DEPUIS: Dict[str, str] = {
    "4h": "1h",
}

# yfinance limite la profondeur historique selon l'intervalle
MAX_DAYS_PAR_INTERVALLE: Dict[str, int] = {
    "1m":  7,
    "5m":  60,
    "15m": 60,
    "1h":  730,
    "4h":  730,
    "1d":  3650,
}


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


def _telecharger_ohlc(
    symbol: str,
    intervalle: str,
    debut: datetime,
    fin: datetime,
) -> pd.DataFrame:
    """
    Télécharge les données OHLC depuis yfinance avec gestion du cache.
    Respecte les limites d'historique par intervalle.
    Les timeframes nécessitant un rééchantillonnage (ex: 4h) sont construits
    à partir de leur source (ex: 1h).
    """
    # Gestion des timeframes obtenus par rééchantillonnage
    if intervalle in RESAMPLE_DEPUIS:
        source_tf = RESAMPLE_DEPUIS[intervalle]
        df_source = _telecharger_ohlc(symbol, source_tf, debut, fin)
        if intervalle == "4h":
            return _resample_4h(df_source)
        return df_source

    # Ajustement de la date de début selon les limites yfinance
    max_jours = MAX_DAYS_PAR_INTERVALLE.get(intervalle, 60)
    limite_debut = datetime.now() - timedelta(days=max_jours)
    if debut < limite_debut:
        logger.debug(
            f"Intervalle {intervalle} : début ajusté de {debut} à {limite_debut}"
        )
        debut = limite_debut

    debut_str = debut.strftime("%Y-%m-%d")
    fin_str = fin.strftime("%Y-%m-%d")
    interval_yf = YFINANCE_INTERVALS.get(intervalle, intervalle)

    chemin = _chemin_cache(symbol, intervalle, debut_str, fin_str)
    df_cache = _charger_cache(chemin)
    if df_cache is not None:
        return df_cache

    logger.info(f"Téléchargement OHLC : {symbol} {intervalle} {debut_str} → {fin_str}")
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=debut_str, end=fin_str, interval=interval_yf)

    if df.empty:
        logger.warning(f"Aucune donnée retournée pour {symbol} {intervalle}")
        return df

    _sauvegarder_cache(chemin, df)
    return df


def get_ohlc(
    timestamp: str,
    symbol: str = None,
    timeframes: list = None,
) -> Dict[str, pd.DataFrame]:
    """
    Récupère les données OHLC autour du timestamp d'un trade.

    Args:
        timestamp : ISO 8601, ex "2024-01-15T14:30:00+00:00"
        symbol    : symbole yfinance, défaut = config.SYMBOL
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
