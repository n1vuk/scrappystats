import logging
import asyncio
from datetime import timedelta

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .discord_utils import (
    verify_signature,
    interaction_response,
    pong,
    register_commands,
)
from .version import __version__
from .utils import utcnow

log = logging.getLogger("scrappystats.interactions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
START_TIME = utcnow()

SCRAPPYSTATS_DESCRIPTION = (
    "ScrappyStats helps you command your STFC alliance with fast reports and roster insights."
)

COMMANDS = [
    {
        "name": "scrappystats",
        "description": SCRAPPYSTATS_DESCRIPTION,
        "options": [
            {"type": 1, "name": "dailyreport", "description": "Show the daily alliance report."},
            {"type": 1, "name": "weeklyreport", "description": "Show the weekly alliance report."},
            {"type": 1, "name": "forcepull", "description": "Force Scrappy to fetch new data."},
            {"type": 1, "name": "fullroster", "description": "Show full roster with join dates."},
            {"type": 1, "name": "help", "description": "Show help for all ScrappyStats commands."},
            {"type": 1, "name": "bark", "description": "Scrappy says hello."},
            {"type": 1, "name": "version", "description": "Show ScrappyStats version."},
        ],
    }
]


# ─────────────────────────────────────────────────────────────
# Startup: register commands WITHOUT blocking interaction ACKs
# ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    async def _register():
        try:
            register_commands(COMMANDS)
            log.info("Commands registered successfully")
        except Exception:
            log.exception("Command registration failed")

    asyncio.create_task(_register())
    log.info("Interaction server started, version %s", __version__)


# ─────────────────────────────────────────────────────────────
# Interaction handler
# ─────────────────────────────────────────────────────────────
@app.post("/discord/interactions")
async def interactions(request: Request):
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    body = await request.body()

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature")

    if not verify_signature(signature, timestamp, body):
        raise HTTPException(status_code=401, detail="Invalid request signature")

    payload = await request.json()
    t = payload.get("type")

    # Discord PING
    if t == 1:
        return JSONResponse(pong())

    # Slash command → ACK IMMEDIATELY
    if t == 2:
        asyncio.create_task(handle_command(payload))
        return JSONResponse({"type": 5})  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE

    return JSONResponse({"error": "Unsupported interaction type"}, status_code=400)


# ─────────────────────────────────────────────────────────────
# Command logic (runs AFTER ACK)
# ─────────────────────────────────────────────────────────────
async def handle_command(payload: dict):
    try:
        data = payload.get("data", {})
        name = data.get("name")

        if name != "scrappystats":
            await send_followup(
                payload,
                "Scrappy tilts his head. That root command is unfamiliar, Captain.",
                ephemeral=True,
            )
            return

        options = data.get("options") or []
        sub = options[0] if options else {}
        sub_name = sub.get("name")

        if sub_name == "bark":
            await send_followup(
                payload,
                "Scrappy wags his tail enthusiastically and is waiting for orders, Captain."
            )
            return

        if sub_name == "version":
            await send_followup(
                payload,
                f"ScrappyStats v{__version__} reporting for duty, Captain."
            )
            return

        if sub_name == "help":
            lines = ["Available commands:"]
            for opt in COMMANDS[0]["options"]:
                lines.append(f"/scrappystats {opt['name']} — {opt['description']}")
            await send_followup(payload, "\n".join(lines))
            return

        await send_followup(
            payload,
            "Scrappy tilts his head. That subcommand is not recognized, Captain.",
            ephemeral=True,
        )

    except Exception:
        log.exception("Error handling interaction")
        await send_followup(
            payload,
            "⚠️ Scrappy tripped while fetching your command. Please try again.",
            ephemeral=True,
        )


# ─────────────────────────────────────────────────────────────
# Follow-up helper
# ─────────────────────────────────────────────────────────────
async def send_followup(payload: dict, content: str, ephemeral: bool = False):
    """
    Uses the interaction webhook to send the real response
    """
    import httpx

    application_id = payload["application_id"]
    token = payload["token"]

    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}"

    data = {
        "content": content,
        "flags": 64 if ephemeral else 0,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=data)

