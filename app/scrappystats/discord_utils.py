import os
import json
import logging
from typing import List, Dict, Any

import requests
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

from .version import __version__

log = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY", "")
APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")

def verify_signature(signature: str, timestamp: str, body: bytes) -> bool:
    if not PUBLIC_KEY:
        log.error("DISCORD_PUBLIC_KEY not set")
        return False
    try:
        vk = VerifyKey(bytes.fromhex(PUBLIC_KEY))
        vk.verify(f"{timestamp}".encode() + body, bytes.fromhex(signature))
        return True
    except BadSignatureError:
        log.warning("Invalid Discord signature")
        return False

def discord_headers():
    return {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }

def register_commands(commands: List[Dict[str, Any]]):
    if not (BOT_TOKEN and APPLICATION_ID and GUILD_ID):
        log.warning(
            "BOT_TOKEN, APPLICATION_ID, or DISCORD_GUILD_ID not set; skipping command registration"
        )
        return

    url = (
        f"{DISCORD_API_BASE}/applications/"
        f"{APPLICATION_ID}/guilds/{GUILD_ID}/commands"
    )

    resp = requests.put(
        url,
        headers=discord_headers(),
        data=json.dumps(commands),
    )

    if resp.status_code not in (200, 201):
        log.error(
            "Failed to register GUILD commands: %s %s",
            resp.status_code,
            resp.text,
        )
    else:
        log.info(
            "Registered %d GUILD commands with Discord (instant update)",
            len(commands),
        )
        

#def register_commands(commands: List[Dict[str, Any]]):
#    if not (BOT_TOKEN and APPLICATION_ID):
#        log.warning("BOT_TOKEN or APPLICATION_ID not set; skipping command registration")
#        return
#    url = f"{DISCORD_API_BASE}/applications/{APPLICATION_ID}/commands"
#    resp = requests.put(url, headers=discord_headers(), data=json.dumps(commands))
#    if resp.status_code not in (200, 201):
#        log.error("Failed to register commands: %s %s", resp.status_code, resp.text)
#    else:
#        log.info("Registered %d commands with Discord", len(commands))

def interaction_response(content: str, ephemeral: bool = True) -> dict:
    data = {"content": content}
    if ephemeral:
        data["flags"] = 64
    return {"type": 4, "data": data}

def pong():
    return {"type": 1}
