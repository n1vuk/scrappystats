
import os
import json
import requests

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_APPLICATION_ID = os.getenv("DISCORD_APPLICATION_ID")

if not DISCORD_BOT_TOKEN or not DISCORD_APPLICATION_ID:
    raise SystemExit("Missing DISCORD_BOT_TOKEN or DISCORD_APPLICATION_ID in environment.")

from scrappystats.interaction_server import COMMANDS

def register_commands():
    url = f"https://discord.com/api/v10/applications/{DISCORD_APPLICATION_ID}/commands"

    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    print("📡 Registering commands with Discord…")
    response = requests.put(url, headers=headers, data=json.dumps(COMMANDS))

    print(f"➡ Status: {response.status_code}")
    print(f"➡ Response: {response.text}")

    return response.status_code, response.text
