"""
Gestion de la base de données SQLite.
Stockage des trades, analyses SMC et rapports de patterns.
"""

import csv
import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connexion et initialisation
# ---------------------------------------------------------------------------

def _get_connexion() -> sqlite3.Connection:
    """Retourne une connexion SQLite configurée."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # accès par nom de colonne
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def initialiser_base() -> None:
    """Crée les tables si elles n'existent pas encore."""
    conn = _get_connexion()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      INTEGER UNIQUE,
                timestamp       TEXT,
                symbol          TEXT DEFAULT 'XAUUSD',
                direction       TEXT,
                entry_min       REAL,
                entry_max       REAL,
                tp1             REAL,
                tp2             REAL,
                tp3             REAL,
                sl              REAL,
                confidence      REAL,
                raw_message     TEXT,
                resultat        INTEGER,  -- 1=gagnant, 0=perdant, NULL=inconnu
                cree_le         TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS smc_analysis (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id            INTEGER NOT NULL REFERENCES trades(id),
                choch_present       INTEGER,
                bos_present         INTEGER,
                ob_in_zone          INTEGER,
                fvg_in_zone         INTEGER,
                liquidity_swept     INTEGER,
                fibonacci_level     REAL,
                premium_discount    TEXT,
                session             TEXT,
                confirmations_count INTEGER,
                cree_le             TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pattern_report (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rapport_json    TEXT,
                cree_le         TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        logger.info("Base de données initialisée")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD Trades
# ---------------------------------------------------------------------------

def inserer_trade(trade: Dict) -> int:
    """
    Insère un trade et retourne son id.
    Si le message_id existe déjà, retourne l'id existant.
    """
    conn = _get_connexion()
    try:
        # Vérification doublon
        if trade.get("message_id"):
            cur = conn.execute(
                "SELECT id FROM trades WHERE message_id = ?",
                (trade["message_id"],),
            )
            row = cur.fetchone()
            if row:
                logger.debug(f"Trade déjà existant pour message_id={trade['message_id']}")
                return row["id"]

        cur = conn.execute(
            """
            INSERT INTO trades
                (message_id, timestamp, symbol, direction,
                 entry_min, entry_max, tp1, tp2, tp3, sl,
                 confidence, raw_message, resultat)
            VALUES
                (:message_id, :timestamp, :symbol, :direction,
                 :entry_min, :entry_max, :tp1, :tp2, :tp3, :sl,
                 :confidence, :raw_message, :resultat)
            """,
            {
                "message_id": trade.get("message_id"),
                "timestamp": trade.get("timestamp"),
                "symbol": trade.get("symbol", "XAUUSD"),
                "direction": trade.get("direction"),
                "entry_min": trade.get("entry_min"),
                "entry_max": trade.get("entry_max"),
                "tp1": trade.get("tp1"),
                "tp2": trade.get("tp2"),
                "tp3": trade.get("tp3"),
                "sl": trade.get("sl"),
                "confidence": trade.get("confidence"),
                "raw_message": trade.get("raw_message"),
                "resultat": trade.get("resultat"),
            },
        )
        conn.commit()
        logger.debug(f"Trade inséré avec id={cur.lastrowid}")
        return cur.lastrowid
    finally:
        conn.close()


def lire_tous_trades() -> List[Dict]:
    """Retourne tous les trades de la base."""
    conn = _get_connexion()
    try:
        cur = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def lire_trade(trade_id: int) -> Optional[Dict]:
    """Retourne un trade par son id."""
    conn = _get_connexion()
    try:
        cur = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def mettre_a_jour_resultat(trade_id: int, gagnant: bool) -> None:
    """Met à jour le résultat d'un trade (1=gagnant, 0=perdant)."""
    conn = _get_connexion()
    try:
        conn.execute(
            "UPDATE trades SET resultat = ? WHERE id = ?",
            (1 if gagnant else 0, trade_id),
        )
        conn.commit()
    finally:
        conn.close()


def supprimer_trade(trade_id: int) -> None:
    """Supprime un trade et son analyse SMC associée."""
    conn = _get_connexion()
    try:
        conn.execute("DELETE FROM smc_analysis WHERE trade_id = ?", (trade_id,))
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD Analyses SMC
# ---------------------------------------------------------------------------

def inserer_analyse_smc(trade_id: int, analyse: Dict) -> int:
    """Insère une analyse SMC et retourne son id."""
    conn = _get_connexion()
    try:
        cur = conn.execute(
            """
            INSERT INTO smc_analysis
                (trade_id, choch_present, bos_present, ob_in_zone,
                 fvg_in_zone, liquidity_swept, fibonacci_level,
                 premium_discount, session, confirmations_count)
            VALUES
                (:trade_id, :choch_present, :bos_present, :ob_in_zone,
                 :fvg_in_zone, :liquidity_swept, :fibonacci_level,
                 :premium_discount, :session, :confirmations_count)
            """,
            {
                "trade_id": trade_id,
                "choch_present": int(analyse.get("choch_present", False)),
                "bos_present": int(analyse.get("bos_present", False)),
                "ob_in_zone": int(analyse.get("ob_in_zone", False)),
                "fvg_in_zone": int(analyse.get("fvg_in_zone", False)),
                "liquidity_swept": int(analyse.get("liquidity_swept", False)),
                "fibonacci_level": analyse.get("fibonacci_level"),
                "premium_discount": analyse.get("premium_discount"),
                "session": analyse.get("session"),
                "confirmations_count": analyse.get("confirmations_count", 0),
            },
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def lire_analyses_smc() -> List[Dict]:
    """Retourne toutes les analyses SMC avec les informations du trade associé."""
    conn = _get_connexion()
    try:
        cur = conn.execute(
            """
            SELECT s.*, t.direction, t.entry_min, t.entry_max,
                   t.tp1, t.sl, t.timestamp, t.resultat
            FROM smc_analysis s
            JOIN trades t ON s.trade_id = t.id
            ORDER BY t.timestamp DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CRUD Rapports
# ---------------------------------------------------------------------------

def inserer_rapport(rapport: Dict) -> int:
    """Insère un rapport de patterns et retourne son id."""
    conn = _get_connexion()
    try:
        cur = conn.execute(
            "INSERT INTO pattern_report (rapport_json) VALUES (?)",
            (json.dumps(rapport, ensure_ascii=False),),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def lire_dernier_rapport() -> Optional[Dict]:
    """Retourne le dernier rapport de patterns."""
    conn = _get_connexion()
    try:
        cur = conn.execute(
            "SELECT rapport_json FROM pattern_report ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            return json.loads(row["rapport_json"])
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def export_to_csv(chemin: str = "trades_export.csv") -> str:
    """
    Exporte tous les trades avec leurs analyses SMC en CSV.

    Returns:
        Chemin du fichier généré
    """
    analyses = lire_analyses_smc()
    if not analyses:
        logger.warning("Aucune donnée à exporter")
        return chemin

    colonnes = list(analyses[0].keys())
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes)
        writer.writeheader()
        writer.writerows(analyses)

    logger.info(f"Export CSV : {len(analyses)} lignes → {chemin}")
    return chemin
