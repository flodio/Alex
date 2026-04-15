"""
Script de première connexion Telegram — à lancer UNE SEULE FOIS avant main.py.

Ce script permet de faire l'authentification OTP (code envoyé sur votre téléphone
ou dans l'application Telegram) de façon interactive dans le terminal.

Une fois la session créée (fichier session_alex.session), vous n'avez plus besoin
de relancer ce script : main.py utilisera la session existante automatiquement.

Lancement :
    python alex/setup_telegram.py
"""

import asyncio
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

import config


async def setup_session() -> None:
    """Crée et sauvegarde la session Telegram de façon interactive."""
    print("=== Configuration de la session Telegram ===")
    print("Ce script est à lancer UNE SEULE FOIS pour autoriser l'accès à votre compte.")
    print()

    # Vérification des paramètres de configuration
    if not config.TELEGRAM_API_ID or not config.TELEGRAM_API_HASH or not config.TELEGRAM_PHONE:
        print(
            "ERREUR : TELEGRAM_API_ID, TELEGRAM_API_HASH et TELEGRAM_PHONE "
            "doivent être renseignés dans config.py ou dans votre fichier .env"
        )
        sys.exit(1)

    # Connexion avec Telethon — la session est sauvegardée dans session_alex.session
    client = TelegramClient(
        "session_alex",
        int(config.TELEGRAM_API_ID),
        config.TELEGRAM_API_HASH,
    )

    await client.connect()

    if await client.is_user_authorized():
        print("✅ Vous êtes déjà connecté. La session session_alex.session est valide.")
        await client.disconnect()
        return

    # Envoi du code OTP sur le numéro de téléphone configuré
    print(f"Envoi du code de vérification sur {config.TELEGRAM_PHONE} ...")
    await client.send_code_request(config.TELEGRAM_PHONE)

    code = input("Entrez le code de vérification reçu sur Telegram : ").strip()

    try:
        await client.sign_in(config.TELEGRAM_PHONE, code)
    except SessionPasswordNeededError:
        # Authentification à deux facteurs activée sur le compte
        mot_de_passe = input(
            "Votre compte a la vérification en deux étapes activée.\n"
            "Entrez votre mot de passe 2FA : "
        ).strip()
        await client.sign_in(password=mot_de_passe)

    if await client.is_user_authorized():
        print()
        print("✅ Connexion réussie ! La session est sauvegardée dans session_alex.session")
        print("   Vous pouvez maintenant lancer le pipeline principal avec : python alex/main.py")
    else:
        print("❌ Échec de l'authentification. Vérifiez vos identifiants et réessayez.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup_session())
