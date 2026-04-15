"""
Extraction des signaux de trading depuis un groupe Telegram privé.
Utilise Telethon pour se connecter avec un compte personnel (pas un bot).
"""

import logging
import re
from datetime import datetime
from typing import List, Dict, Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

import config

logger = logging.getLogger(__name__)

# Mots-clés présents dans les signaux de trading Gold/XAUUSD
SIGNAL_KEYWORDS = [
    "gold", "xauusd", "buy", "sell", "tp", "sl", "entry",
    "long", "short", "target", "stop"
]


def _ressemble_a_un_signal(texte: str) -> bool:
    """
    Filtre pré-analyse rapide : retourne True si le message contient
    au moins un mot-clé de trading (insensible à la casse).
    """
    texte_min = texte.lower()
    return any(mot in texte_min for mot in SIGNAL_KEYWORDS)


async def _extraire_messages_async(
    limit: int = None,
) -> List[Dict]:
    """
    Connexion async au groupe Telegram et récupération des messages.
    Retourne une liste de dicts {message_id, timestamp, texte}.
    """
    if limit is None:
        limit = config.TELEGRAM_MESSAGE_LIMIT

    client = TelegramClient(
        "session_alex",
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH,
    )

    messages_filtres: List[Dict] = []

    try:
        await client.start(phone=config.TELEGRAM_PHONE)
        logger.info("Connecté à Telegram avec succès")

        # Résolution de l'entité groupe (nom ou ID)
        groupe = await client.get_entity(config.TELEGRAM_GROUP)
        logger.info(f"Groupe trouvé : {groupe.title if hasattr(groupe, 'title') else groupe.id}")

        total_recuperes = 0
        async for message in client.iter_messages(groupe, limit=limit):
            if message.text:
                total_recuperes += 1
                if _ressemble_a_un_signal(message.text):
                    messages_filtres.append({
                        "message_id": message.id,
                        "timestamp": message.date.isoformat(),
                        "texte": message.text,
                    })

        logger.info(
            f"{total_recuperes} messages récupérés, "
            f"{len(messages_filtres)} ressemblent à des signaux"
        )

    except SessionPasswordNeededError:
        logger.error(
            "Authentification à deux facteurs requise — "
            "entrez votre mot de passe Telegram dans le terminal."
        )
        raise
    finally:
        await client.disconnect()

    return messages_filtres


def extraire_signaux(limit: Optional[int] = None) -> List[Dict]:
    """
    Point d'entrée synchrone.
    Lance la boucle asyncio, retourne la liste des messages pré-filtrés.
    """
    import asyncio

    if limit is None:
        limit = config.TELEGRAM_MESSAGE_LIMIT

    logger.info(f"Démarrage extraction — {limit} messages max")
    messages = asyncio.run(_extraire_messages_async(limit=limit))
    logger.info(f"{len(messages)} messages pré-filtrés retournés")
    return messages
