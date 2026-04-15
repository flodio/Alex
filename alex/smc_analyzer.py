"""
Analyse SMC/ICT complète pour chaque trade.
Détecte : Order Blocks, Fair Value Gaps, CHOCH, BOS, liquidités,
zones premium/discount et niveaux Fibonacci.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _session_depuis_heure(heure_utc: int) -> str:
    """Retourne la session de trading selon l'heure UTC."""
    if 0 <= heure_utc < 8:
        return "asia"
    elif 8 <= heure_utc < 13:
        return "london"
    elif 13 <= heure_utc < 18:
        return "new_york"
    else:
        return "after_hours"


# ---------------------------------------------------------------------------
# Détection Order Blocks (OB)
# ---------------------------------------------------------------------------

def detect_order_blocks(ohlc_df: pd.DataFrame, timeframe: str) -> List[Dict]:
    """
    Détecte les Order Blocks dans un DataFrame OHLC.

    Un OB haussier = dernière bougie baissière avant un mouvement impulsif haussier.
    Un OB baissier = dernière bougie haussière avant un mouvement impulsif baissier.

    Returns:
        Liste de dicts {type, prix_haut, prix_bas, index, timeframe}
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 5:
        return []

    obs: List[Dict] = []
    df = ohlc_df.copy()

    for i in range(2, len(df) - 2):
        bougie = df.iloc[i]
        suivante = df.iloc[i + 1]
        apres = df.iloc[i + 2]

        corps_actuel = abs(bougie["Close"] - bougie["Open"])
        if corps_actuel < 1e-6:
            continue

        # OB haussier : bougie baissière suivie d'un fort mouvement haussier
        if (
            bougie["Close"] < bougie["Open"]  # bougie baissière
            and suivante["Close"] > suivante["Open"]  # bougie haussière
            and (suivante["Close"] - suivante["Open"]) > corps_actuel * 1.5
        ):
            obs.append({
                "type": "bullish_ob",
                "prix_haut": float(bougie["High"]),
                "prix_bas": float(bougie["Low"]),
                "index": i,
                "timeframe": timeframe,
            })

        # OB baissier : bougie haussière suivie d'un fort mouvement baissier
        elif (
            bougie["Close"] > bougie["Open"]  # bougie haussière
            and suivante["Close"] < suivante["Open"]  # bougie baissière
            and (suivante["Open"] - suivante["Close"]) > corps_actuel * 1.5
        ):
            obs.append({
                "type": "bearish_ob",
                "prix_haut": float(bougie["High"]),
                "prix_bas": float(bougie["Low"]),
                "index": i,
                "timeframe": timeframe,
            })

    logger.debug(f"OB détectés ({timeframe}) : {len(obs)}")
    return obs


# ---------------------------------------------------------------------------
# Détection Fair Value Gaps (FVG)
# ---------------------------------------------------------------------------

def detect_fvg(ohlc_df: pd.DataFrame, timeframe: str) -> List[Dict]:
    """
    Détecte les Fair Value Gaps (FVG / imbalances).

    Un FVG haussier existe quand : Low[i+1] > High[i-1]  (gap entre 3 bougies)
    Un FVG baissier existe quand : High[i+1] < Low[i-1]

    Returns:
        Liste de dicts {type, prix_haut, prix_bas, index, timeframe}
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 3:
        return []

    fvgs: List[Dict] = []
    df = ohlc_df.copy()

    for i in range(1, len(df) - 1):
        prev_high = df.iloc[i - 1]["High"]
        prev_low = df.iloc[i - 1]["Low"]
        next_high = df.iloc[i + 1]["High"]
        next_low = df.iloc[i + 1]["Low"]

        # FVG haussier
        if next_low > prev_high:
            fvgs.append({
                "type": "bullish_fvg",
                "prix_haut": float(next_low),
                "prix_bas": float(prev_high),
                "index": i,
                "timeframe": timeframe,
            })
        # FVG baissier
        elif next_high < prev_low:
            fvgs.append({
                "type": "bearish_fvg",
                "prix_haut": float(prev_low),
                "prix_bas": float(next_high),
                "index": i,
                "timeframe": timeframe,
            })

    logger.debug(f"FVG détectés ({timeframe}) : {len(fvgs)}")
    return fvgs


# ---------------------------------------------------------------------------
# Détection CHOCH (Change of Character)
# ---------------------------------------------------------------------------

def detect_choch(ohlc_df: pd.DataFrame, timeframe: str) -> bool:
    """
    Détecte un Change of Character (CHOCH).

    Principe : le marché casse un Higher Low (en tendance haussière)
    ou un Lower High (en tendance baissière) avant de reprendre.

    Returns:
        True si un CHOCH est détecté dans la fenêtre de données
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 10:
        return False

    closes = ohlc_df["Close"].values
    highs = ohlc_df["High"].values
    lows = ohlc_df["Low"].values

    n = len(closes)
    # Identification des swing highs/lows sur une fenêtre glissante
    for i in range(2, n - 2):
        # Swing high : plus haut des 2 bougies précédentes et suivantes
        est_swing_high = highs[i] == max(highs[i - 2 : i + 3])
        # Swing low : plus bas
        est_swing_low = lows[i] == min(lows[i - 2 : i + 3])

        if i >= 6:
            # Tendance haussière : HH + HL → CHOCH si HL cassé
            if est_swing_low:
                hl_precedent = None
                for j in range(i - 1, max(0, i - 6), -1):
                    if lows[j] == min(lows[max(0, j - 2) : j + 3]):
                        hl_precedent = lows[j]
                        break
                if hl_precedent is not None and lows[i] < hl_precedent:
                    logger.debug(f"CHOCH détecté ({timeframe}) à l'index {i}")
                    return True

    return False


# ---------------------------------------------------------------------------
# Détection BOS (Break of Structure)
# ---------------------------------------------------------------------------

def detect_bos(ohlc_df: pd.DataFrame, timeframe: str) -> bool:
    """
    Détecte un Break of Structure (BOS).

    Un BOS haussier = close au-dessus d'un swing high précédent.
    Un BOS baissier = close en-dessous d'un swing low précédent.

    Returns:
        True si un BOS est détecté
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 6:
        return False

    closes = ohlc_df["Close"].values
    highs = ohlc_df["High"].values
    lows = ohlc_df["Low"].values
    n = len(closes)

    for i in range(4, n):
        # Recherche du dernier swing high dans les 10 bougies précédentes
        fenetre = min(10, i)
        swing_high = max(highs[i - fenetre : i])
        swing_low = min(lows[i - fenetre : i])

        if closes[i] > swing_high:
            logger.debug(f"BOS haussier ({timeframe}) à l'index {i}")
            return True
        if closes[i] < swing_low:
            logger.debug(f"BOS baissier ({timeframe}) à l'index {i}")
            return True

    return False


# ---------------------------------------------------------------------------
# Détection des balayages de liquidité (Liquidity Sweeps)
# ---------------------------------------------------------------------------

def detect_liquidity_sweeps(ohlc_df: pd.DataFrame, timeframe: str) -> Dict:
    """
    Détecte les prises de liquidité (sweep des highs/lows précédents).

    Returns:
        dict {
            "swept": bool,
            "type": "buy_side" | "sell_side" | None,
            "niveau": float | None
        }
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 10:
        return {"swept": False, "type": None, "niveau": None}

    highs = ohlc_df["High"].values
    lows = ohlc_df["Low"].values
    closes = ohlc_df["Close"].values
    n = len(closes)

    for i in range(5, n):
        # Référence : high et low des 5 dernières bougies
        ref_high = max(highs[i - 5 : i])
        ref_low = min(lows[i - 5 : i])

        # Sweep du buy-side liquidity (égaux highs / range highs)
        if highs[i] > ref_high and closes[i] < ref_high:
            return {
                "swept": True,
                "type": "buy_side",
                "niveau": float(ref_high),
            }

        # Sweep du sell-side liquidity
        if lows[i] < ref_low and closes[i] > ref_low:
            return {
                "swept": True,
                "type": "sell_side",
                "niveau": float(ref_low),
            }

    return {"swept": False, "type": None, "niveau": None}


# ---------------------------------------------------------------------------
# Zones Premium / Discount
# ---------------------------------------------------------------------------

def detect_premium_discount(ohlc_df: pd.DataFrame, entry_price: float) -> str:
    """
    Identifie si le prix d'entrée se situe en zone premium, discount ou équilibre.

    Utilise l'équilibre (50%) d'un swing récent.

    Returns:
        "premium" | "discount" | "equilibrium"
    """
    if ohlc_df is None or ohlc_df.empty:
        return "equilibrium"

    swing_high = float(ohlc_df["High"].max())
    swing_low = float(ohlc_df["Low"].min())

    if swing_high == swing_low:
        return "equilibrium"

    equilibre = (swing_high + swing_low) / 2
    ratio = (entry_price - swing_low) / (swing_high - swing_low)

    if ratio > 0.55:
        return "premium"
    elif ratio < 0.45:
        return "discount"
    else:
        return "equilibrium"


# ---------------------------------------------------------------------------
# Niveaux Fibonacci
# ---------------------------------------------------------------------------

def detect_fibonacci_zone(ohlc_df: pd.DataFrame, entry_price: float) -> Optional[float]:
    """
    Identifie le niveau Fibonacci (0.618, 0.66, 0.786) le plus proche de l'entrée.

    Returns:
        float (ex: 0.66) ou None si hors range
    """
    if ohlc_df is None or ohlc_df.empty:
        return None

    swing_high = float(ohlc_df["High"].max())
    swing_low = float(ohlc_df["Low"].min())

    if swing_high == swing_low:
        return None

    ratio = (swing_high - entry_price) / (swing_high - swing_low)

    niveaux_fibonacci = [0.236, 0.382, 0.5, 0.618, 0.66, 0.786, 0.886]
    tolerance = 0.04  # ±4%

    meilleur = None
    meilleur_distance = float("inf")
    for niveau in niveaux_fibonacci:
        dist = abs(ratio - niveau)
        if dist < tolerance and dist < meilleur_distance:
            meilleur = niveau
            meilleur_distance = dist

    return meilleur


# ---------------------------------------------------------------------------
# Analyse SMC complète d'un trade
# ---------------------------------------------------------------------------

def analyze_trade_smc(trade: Dict, ohlc_data: Dict) -> Dict:
    """
    Lance toutes les analyses SMC/ICT sur un trade et retourne un rapport complet.

    Args:
        trade     : dict avec au minimum 'entry_min', 'entry_max', 'timestamp'
        ohlc_data : dict {timeframe: DataFrame} retourné par ohlc_fetcher.get_ohlc

    Returns:
        dict avec les résultats de l'analyse SMC
    """
    entry_price = None
    if trade.get("entry_min") and trade.get("entry_max"):
        entry_price = (trade["entry_min"] + trade["entry_max"]) / 2
    elif trade.get("entry_min"):
        entry_price = trade["entry_min"]

    # Timeframe principal pour l'analyse = H1
    tf_principal = "1h"
    df_principal = ohlc_data.get(tf_principal, pd.DataFrame())

    # Timeframe secondaire = 15m (confirmation)
    df_15m = ohlc_data.get("15m", pd.DataFrame())

    # ----- Détection des signaux -----
    choch_present = detect_choch(df_15m, "15m") or detect_choch(df_principal, "1h")
    bos_present = detect_bos(df_15m, "15m") or detect_bos(df_principal, "1h")

    # Order Block dans la zone d'entrée
    ob_in_zone = False
    if entry_price is not None:
        obs = detect_order_blocks(df_principal, tf_principal)
        for ob in obs:
            if ob["prix_bas"] <= entry_price <= ob["prix_haut"]:
                ob_in_zone = True
                break

    # FVG dans la zone d'entrée
    fvg_in_zone = False
    if entry_price is not None:
        fvgs = detect_fvg(df_principal, tf_principal)
        for fvg in fvgs:
            if fvg["prix_bas"] <= entry_price <= fvg["prix_haut"]:
                fvg_in_zone = True
                break

    # Liquidités
    liquidity_info = detect_liquidity_sweeps(df_15m, "15m")
    liquidity_swept = liquidity_info.get("swept", False)

    # Premium / Discount
    premium_discount = "equilibrium"
    fibonacci_level = None
    if entry_price is not None:
        premium_discount = detect_premium_discount(df_principal, entry_price)
        fibonacci_level = detect_fibonacci_zone(df_principal, entry_price)

    # Session de trading
    session = "unknown"
    if trade.get("timestamp"):
        try:
            ts = datetime.fromisoformat(
                trade["timestamp"].replace("Z", "+00:00")
            )
            session = _session_depuis_heure(ts.hour)
        except Exception:
            pass

    # Comptage des confirmations
    confirmations = sum([
        choch_present,
        bos_present,
        ob_in_zone,
        fvg_in_zone,
        liquidity_swept,
    ])

    return {
        "choch_present": choch_present,
        "bos_present": bos_present,
        "ob_in_zone": ob_in_zone,
        "fvg_in_zone": fvg_in_zone,
        "liquidity_swept": liquidity_swept,
        "fibonacci_level": fibonacci_level,
        "premium_discount": premium_discount,
        "session": session,
        "confirmations_count": confirmations,
    }
