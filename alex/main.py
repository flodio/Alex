"""
Point d'entrée principal du pipeline Alex.
Exécute l'ensemble du workflow : extraction → parsing → OHLC → SMC → patterns → DB.
"""

import logging
import sys
import os

# Ajout du dossier alex au path pour les imports
sys.path.insert(0, os.path.dirname(__file__))

import config
import database as db
import ohlc_fetcher
import pattern_detector
import signal_parser
import smc_analyzer
import telegram_extractor

# ---------------------------------------------------------------------------
# Configuration du logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("alex.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def verifier_configuration() -> bool:
    """Vérifie que les clés API obligatoires sont renseignées."""
    manquants = []
    if not config.TELEGRAM_API_ID:
        manquants.append("TELEGRAM_API_ID")
    if not config.TELEGRAM_API_HASH:
        manquants.append("TELEGRAM_API_HASH")
    if not config.TELEGRAM_PHONE:
        manquants.append("TELEGRAM_PHONE")
    if not config.TELEGRAM_GROUP:
        manquants.append("TELEGRAM_GROUP")
    if not config.ANTHROPIC_API_KEY:
        manquants.append("ANTHROPIC_API_KEY")

    if manquants:
        logger.error(
            f"Configuration incomplète — champs manquants dans config.py : "
            f"{', '.join(manquants)}"
        )
        return False
    return True


def main() -> None:
    """Pipeline complet d'analyse."""
    logger.info("═" * 60)
    logger.info("  Alex — SMC/ICT Trading Analyzer")
    logger.info("═" * 60)

    # ----- Étape 0 : Vérification config -----
    if not verifier_configuration():
        logger.error("Arrêt : remplissez config.py avant de continuer.")
        sys.exit(1)

    # ----- Étape 1 : Initialisation base de données -----
    logger.info("Étape 1/7 — Initialisation base de données")
    db.initialiser_base()

    # ----- Étape 2 : Extraction Telegram -----
    logger.info("Étape 2/7 — Extraction signaux Telegram")
    try:
        messages_bruts = telegram_extractor.extraire_signaux(
            limit=config.TELEGRAM_MESSAGE_LIMIT
        )
        logger.info(f"{len(messages_bruts)} messages pré-filtrés récupérés")
    except Exception as e:
        logger.error(f"Erreur extraction Telegram : {e}")
        sys.exit(1)

    if not messages_bruts:
        logger.warning("Aucun message récupéré. Vérifiez la configuration Telegram.")
        return

    # ----- Étape 3 : Parsing Claude API -----
    logger.info("Étape 3/7 — Parsing des signaux avec Claude API")
    try:
        signaux = signal_parser.parser_tous_les_messages(messages_bruts)
        logger.info(f"{len(signaux)} signaux valides parsés")
    except Exception as e:
        logger.error(f"Erreur parsing Claude : {e}")
        sys.exit(1)

    if not signaux:
        logger.warning("Aucun signal valide extrait après parsing.")
        return

    # ----- Étape 4 : Récupération OHLC + Analyse SMC -----
    logger.info("Étape 4/7 — Récupération données OHLC (yfinance) + analyse SMC par trade")

    trades_sauvegardes: list = []
    analyses_sauvegardes: list = []
    ohlc_data_list: list = []

    for i, signal in enumerate(signaux, 1):
        logger.info(f"  Trade {i}/{len(signaux)} : {signal.get('direction')} @ {signal.get('entry_min')}-{signal.get('entry_max')}")

        # Sauvegarde du trade
        trade_id = db.inserer_trade(signal)
        signal["id"] = trade_id
        trades_sauvegardes.append(signal)

        # Récupération OHLC
        ohlc = {}
        if signal.get("timestamp"):
            try:
                ohlc = ohlc_fetcher.get_ohlc(
                    timestamp=signal["timestamp"],
                    symbol=config.SYMBOL,
                    timeframes=config.TIMEFRAMES,
                )
            except Exception as e:
                logger.warning(f"Impossible de récupérer OHLC pour le trade {trade_id} : {e}")

        ohlc_data_list.append(ohlc)

        # Analyse SMC
        try:
            analyse = smc_analyzer.analyze_trade_smc(signal, ohlc)
            db.inserer_analyse_smc(trade_id, analyse)
            analyses_sauvegardes.append(analyse)
            logger.info(
                f"    SMC : CHOCH={analyse['choch_present']}, "
                f"BOS={analyse['bos_present']}, "
                f"OB={analyse['ob_in_zone']}, "
                f"FVG={analyse['fvg_in_zone']}, "
                f"Liquidité={analyse['liquidity_swept']}, "
                f"Confirmations={analyse['confirmations_count']}"
            )
        except Exception as e:
            logger.warning(f"Erreur analyse SMC pour trade {trade_id} : {e}")
            analyses_sauvegardes.append({})

    # ----- Étape 5 : Détection des patterns -----
    logger.info("Étape 5/7 — Détection des patterns et confirmations cachées")
    try:
        rapport = pattern_detector.generer_rapport(
            trades=trades_sauvegardes,
            analyses_smc=analyses_sauvegardes,
            ohlc_data_list=ohlc_data_list,
            chemin_sortie="pattern_report.json",
        )
        db.inserer_rapport(rapport)

        logger.info(
            f"Rapport patterns : {rapport.get('total_trades', 0)} trades, "
            f"win rate = {rapport.get('win_rate', 0):.1%}"
        )
        confirmations_cachees = rapport.get("hidden_confirmations", [])
        if confirmations_cachees:
            logger.info(f"Confirmations cachées identifiées :")
            for cc in confirmations_cachees:
                logger.info(
                    f"  - {cc.get('nom')} (confiance : {cc.get('confiance', 0):.1%})"
                )

    except Exception as e:
        logger.warning(f"Erreur détection patterns : {e}")

    # ----- Étape 6 : Export CSV -----
    logger.info("Étape 6/7 — Export CSV")
    try:
        chemin_csv = db.export_to_csv("trades_export.csv")
        logger.info(f"Export CSV : {chemin_csv}")
    except Exception as e:
        logger.warning(f"Erreur export CSV : {e}")

    # ----- Résumé final -----
    logger.info("Étape 7/7 — Résumé final")
    logger.info("═" * 60)
    logger.info("Pipeline terminé avec succès !")
    logger.info(f"  • Trades analysés   : {len(trades_sauvegardes)}")
    logger.info(f"  • Base de données   : {config.DB_PATH}")
    logger.info(f"  • Rapport patterns  : pattern_report.json")
    logger.info(f"  • Export CSV        : trades_export.csv")
    logger.info("  • Dashboard         : streamlit run alex/dashboard.py")
    logger.info("═" * 60)


if __name__ == "__main__":
    main()
