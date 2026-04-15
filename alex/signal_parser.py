"""
Parsing des messages Telegram bruts via Claude API (Anthropic).
Chaque message non structuré est transformé en JSON exploitable.
"""

import json
import logging
from typing import Dict, Optional, List

import anthropic

import config

logger = logging.getLogger(__name__)

# Prompt système envoyé à Claude pour chaque message
SYSTEM_PROMPT = """Tu es un assistant spécialisé dans l'analyse de signaux de trading XAUUSD (Gold).
Tu reçois un message brut extrait d'un groupe Telegram et tu dois en extraire le signal de trading.

Règles strictes :
1. Si le message N'EST PAS un signal de trading (pub, spam, discussion générale), retourne exactement : null
2. Extrais uniquement les données réellement présentes — n'invente rien
3. Pour la direction : si TP > entry c'est BUY, si TP < entry c'est SELL
4. Les prix Gold sont généralement entre 1800 et 5000
5. confidence : score entre 0 et 1 selon la clarté du signal

Retourne UNIQUEMENT un JSON valide (sans texte autour) dans ce format :
{
  "symbol": "XAUUSD",
  "direction": "BUY" ou "SELL",
  "entry_min": <float ou null>,
  "entry_max": <float ou null>,
  "tp1": <float ou null>,
  "tp2": <float ou null>,
  "tp3": <float ou null>,
  "sl": <float ou null>,
  "confidence": <float entre 0 et 1>
}

Ou retourne exactement : null"""


def parser_message(message: Dict) -> Optional[Dict]:
    """
    Envoie un message brut à Claude et retourne le signal structuré.
    Retourne None si Claude identifie le message comme du spam.

    Args:
        message: dict avec les clés 'texte', 'timestamp', 'message_id'

    Returns:
        dict avec les données du signal, ou None si pas un signal valide
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    texte_brut = message.get("texte", "")
    if not texte_brut:
        return None

    try:
        reponse = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Message Telegram à analyser :\n\n{texte_brut}",
                }
            ],
        )

        contenu = reponse.content[0].text.strip()
        logger.debug(f"Réponse Claude pour msg {message.get('message_id')}: {contenu}")

        # Vérification signal invalide / spam
        if contenu.lower() == "null" or contenu == "":
            logger.info(f"Message {message.get('message_id')} ignoré (spam / pas un signal)")
            return None

        donnees = json.loads(contenu)

        # Enrichissement avec les métadonnées Telegram
        donnees["timestamp"] = message.get("timestamp")
        donnees["message_id"] = message.get("message_id")
        donnees["raw_message"] = texte_brut

        return donnees

    except json.JSONDecodeError as e:
        logger.warning(
            f"Impossible de parser la réponse JSON pour le message "
            f"{message.get('message_id')} : {e}"
        )
        return None
    except anthropic.APIError as e:
        logger.error(f"Erreur API Anthropic : {e}")
        raise


def parser_tous_les_messages(messages: List[Dict]) -> List[Dict]:
    """
    Parse une liste de messages bruts et retourne uniquement les signaux valides.

    Args:
        messages: liste de dicts issus de telegram_extractor

    Returns:
        liste des signaux parsés (spam exclu)
    """
    signaux: List[Dict] = []

    for i, message in enumerate(messages, 1):
        logger.info(
            f"Parsing message {i}/{len(messages)} "
            f"(id={message.get('message_id')})"
        )
        signal = parser_message(message)
        if signal is not None:
            signaux.append(signal)

    logger.info(
        f"{len(signaux)} signaux valides extraits sur {len(messages)} messages"
    )
    return signaux
