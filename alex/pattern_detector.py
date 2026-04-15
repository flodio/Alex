"""
Détection des patterns et reverse-engineering des confirmations cachées.
Compare les trades gagnants vs perdants pour identifier la vraie stratégie.
"""

import json
import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Confirmations SMC analysées
CONFIRMATIONS_SMC = [
    "choch_present",
    "bos_present",
    "ob_in_zone",
    "fvg_in_zone",
    "liquidity_swept",
]

# Seuil pour les niveaux ronds de Gold (multiples de 50)
NIVEAU_ROND_STEP = 50


def _est_gagnant(trade: Dict, analyse_smc: Dict) -> Optional[bool]:
    """
    Détermine si un trade est gagnant (TP1 atteint) ou perdant (SL touché).
    Retourne None si l'information manque.
    """
    # Vérification basée sur les données du trade si disponibles
    if trade.get("resultat") is not None:
        return bool(trade["resultat"])

    tp1 = trade.get("tp1")
    sl = trade.get("sl")
    entry = trade.get("entry_min") or trade.get("entry_max")
    direction = trade.get("direction", "").upper()

    if not all([tp1, sl, entry, direction]):
        return None

    # Simulation simplifiée basée sur la direction et les prix
    if direction == "BUY":
        return tp1 > entry
    elif direction == "SELL":
        return tp1 < entry
    return None


def _proche_niveau_rond(prix: float, step: float = NIVEAU_ROND_STEP) -> bool:
    """Vérifie si un prix est proche d'un niveau rond."""
    if not prix:
        return False
    reste = prix % step
    tolerance = step * 0.1
    return reste < tolerance or reste > (step - tolerance)


def _calculer_rsi(closes: np.ndarray, periode: int = 14) -> np.ndarray:
    """Calcul du RSI basique."""
    if len(closes) < periode + 1:
        return np.full(len(closes), 50.0)

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    pertes = np.where(deltas < 0, -deltas, 0.0)

    rsi = np.zeros(len(closes))
    avg_gain = np.mean(gains[:periode])
    avg_perte = np.mean(pertes[:periode])

    for i in range(periode, len(closes)):
        avg_gain = (avg_gain * (periode - 1) + gains[i - 1]) / periode
        avg_perte = (avg_perte * (periode - 1) + pertes[i - 1]) / periode
        if avg_perte == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_perte
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def detect_rsi_divergence(ohlc_df: pd.DataFrame) -> bool:
    """
    Détecte une divergence RSI (prix fait un nouveau low/high mais RSI non).
    Confirmation additionnelle potentielle du trader.
    """
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 20:
        return False

    closes = ohlc_df["Close"].values
    lows = ohlc_df["Low"].values
    highs = ohlc_df["High"].values
    rsi = _calculer_rsi(closes)
    n = len(closes)

    # Divergence haussière : prix fait un plus bas, RSI fait un plus haut
    for i in range(5, n):
        if lows[i] < lows[i - 5] and rsi[i] > rsi[i - 5]:
            return True
        # Divergence baissière : prix fait un plus haut, RSI fait un plus bas
        if highs[i] > highs[i - 5] and rsi[i] < rsi[i - 5]:
            return True

    return False


def detect_volume_spike(ohlc_df: pd.DataFrame) -> bool:
    """
    Détecte un pic de volume anormal (> 2x la moyenne sur 20 bougies).
    Potentielle confirmation institutionnelle.
    """
    if ohlc_df is None or ohlc_df.empty or "Volume" not in ohlc_df.columns:
        return False
    if len(ohlc_df) < 5:
        return False

    volumes = ohlc_df["Volume"].values
    if np.mean(volumes) == 0:
        return False

    fenetre = min(20, len(volumes) - 1)
    volume_moyen = np.mean(volumes[-fenetre - 1 : -1])
    dernier_volume = volumes[-1]

    return dernier_volume > volume_moyen * 2.0


def analyser_patterns(
    trades: List[Dict],
    analyses_smc: List[Dict],
    ohlc_data_list: Optional[List[Dict]] = None,
) -> Dict:
    """
    Compare les trades gagnants vs perdants pour identifier les patterns cachés.

    Args:
        trades       : liste des trades parsés
        analyses_smc : liste des analyses SMC correspondantes (même ordre)
        ohlc_data_list: liste des données OHLC par trade (optionnel)

    Returns:
        dict rapport complet des patterns détectés
    """
    if not trades or not analyses_smc:
        logger.warning("Aucune donnée disponible pour l'analyse des patterns")
        return {}

    gagnants: List[Tuple[Dict, Dict]] = []
    perdants: List[Tuple[Dict, Dict]] = []

    for i, (trade, analyse) in enumerate(zip(trades, analyses_smc)):
        resultat = _est_gagnant(trade, analyse)
        if resultat is True:
            gagnants.append((trade, analyse))
        elif resultat is False:
            perdants.append((trade, analyse))

    total = len(trades)
    n_gagnants = len(gagnants)
    n_perdants = len(perdants)
    win_rate = n_gagnants / total if total > 0 else 0.0

    logger.info(
        f"Analyse patterns : {total} trades, {n_gagnants} gagnants "
        f"({win_rate:.1%}), {n_perdants} perdants"
    )

    # ----- Confirmations toujours présentes dans les trades gagnants -----
    toujours_presents = []
    souvent_presents = []

    if gagnants:
        for conf in CONFIRMATIONS_SMC:
            nb_present = sum(
                1 for _, analyse in gagnants if analyse.get(conf, False)
            )
            taux = nb_present / len(gagnants)
            if taux == 1.0:
                toujours_presents.append(conf)
            elif taux >= 0.6:
                souvent_presents.append(conf)

    # ----- Session préférée -----
    sessions_gagnants = Counter(
        analyse.get("session", "unknown")
        for _, analyse in gagnants
    )
    session_preferee = (
        sessions_gagnants.most_common(1)[0][0] if sessions_gagnants else "unknown"
    )

    # ----- Niveau Fibonacci préféré -----
    niveaux_fibo = [
        analyse.get("fibonacci_level")
        for _, analyse in gagnants
        if analyse.get("fibonacci_level") is not None
    ]
    fibo_prefere = None
    if niveaux_fibo:
        counter_fibo = Counter(niveaux_fibo)
        fibo_prefere = counter_fibo.most_common(1)[0][0]

    # ----- Zone premium/discount -----
    zones = Counter(
        analyse.get("premium_discount", "equilibrium")
        for _, analyse in gagnants
    )
    zone_preferee = zones.most_common(1)[0][0] if zones else "equilibrium"

    # ----- Direction associée à la zone -----
    directions_g = Counter(
        trade.get("direction", "UNKNOWN").upper()
        for trade, _ in gagnants
    )
    direction_principale = (
        directions_g.most_common(1)[0][0] if directions_g else "UNKNOWN"
    )
    if direction_principale == "BUY":
        pref_premium_discount = "discount_pour_buy"
    elif direction_principale == "SELL":
        pref_premium_discount = "premium_pour_sell"
    else:
        pref_premium_discount = zone_preferee

    # ----- Analyse des confirmations cachées potentielles -----
    confirmations_cachees = _analyser_confirmations_cachees(
        gagnants, perdants, ohlc_data_list
    )

    # ----- Analyse des niveaux ronds -----
    nb_niveaux_ronds_gagnants = sum(
        1
        for trade, _ in gagnants
        if _proche_niveau_rond(trade.get("entry_min") or 0)
        or _proche_niveau_rond(trade.get("entry_max") or 0)
    )
    taux_niveaux_ronds = (
        nb_niveaux_ronds_gagnants / len(gagnants) if gagnants else 0.0
    )

    rapport = {
        "total_trades": total,
        "winning_trades": n_gagnants,
        "losing_trades": n_perdants,
        "win_rate": round(win_rate, 4),
        "confirmed_strategy": {
            "always_present_in_wins": toujours_presents,
            "often_present_in_wins": souvent_presents,
            "time_preference": session_preferee,
            "fibonacci_preference": fibo_prefere,
            "premium_discount_preference": pref_premium_discount,
        },
        "hidden_confirmations": confirmations_cachees,
        "confluence_niveaux_ronds": {
            "taux": round(taux_niveaux_ronds, 4),
            "significatif": taux_niveaux_ronds > 0.5,
        },
    }

    return rapport


def _analyser_confirmations_cachees(
    gagnants: List[Tuple],
    perdants: List[Tuple],
    ohlc_data_list: Optional[List[Dict]],
) -> List[Dict]:
    """
    Analyse les confirmations cachées potentielles en comparant gagnants/perdants.
    """
    cachees: List[Dict] = []

    # Confirmation 1 : Nombre total de confirmations SMC
    if gagnants:
        avg_conf_g = np.mean(
            [a.get("confirmations_count", 0) for _, a in gagnants]
        )
        avg_conf_p = (
            np.mean([a.get("confirmations_count", 0) for _, a in perdants])
            if perdants
            else 0.0
        )
        if avg_conf_g > avg_conf_p + 0.5:
            cachees.append({
                "nom": "confirmations_multiples",
                "description": "Les trades gagnants ont en moyenne plus de confirmations SMC",
                "moyenne_gagnants": round(float(avg_conf_g), 2),
                "moyenne_perdants": round(float(avg_conf_p), 2),
                "confiance": min(1.0, (avg_conf_g - avg_conf_p) / 3),
            })

    # Confirmation 2 : Fibonacci à 0.66
    nb_fibo_66_g = sum(
        1 for _, a in gagnants if a.get("fibonacci_level") == 0.66
    )
    nb_fibo_66_p = sum(
        1 for _, a in perdants if a.get("fibonacci_level") == 0.66
    )
    if gagnants and nb_fibo_66_g / len(gagnants) > 0.4:
        cachees.append({
            "nom": "fibonacci_0.66",
            "description": "Entrée préférentielle au retracement 0.66 de Fibonacci",
            "taux_gagnants": round(nb_fibo_66_g / len(gagnants), 4),
            "taux_perdants": round(nb_fibo_66_p / len(perdants), 4) if len(perdants) > 0 else 0,
            "confiance": 0.75,
        })

    # Confirmation 3 : Session London/NY
    sessions_g = Counter(a.get("session") for _, a in gagnants)
    for session in ["london", "new_york"]:
        taux = sessions_g.get(session, 0) / len(gagnants) if gagnants else 0
        if taux > 0.4:
            cachees.append({
                "nom": f"session_{session}",
                "description": f"Préférence marquée pour la session {session}",
                "taux_gagnants": round(taux, 4),
                "confiance": min(0.9, taux + 0.1),
            })

    return cachees


def generer_rapport(
    trades: List[Dict],
    analyses_smc: List[Dict],
    ohlc_data_list: Optional[List[Dict]] = None,
    chemin_sortie: str = "pattern_report.json",
) -> Dict:
    """
    Génère et sauvegarde le rapport complet des patterns détectés.

    Returns:
        Le rapport sous forme de dict
    """
    rapport = analyser_patterns(trades, analyses_smc, ohlc_data_list)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)

    logger.info(f"Rapport patterns sauvegardé : {chemin_sortie}")
    return rapport
