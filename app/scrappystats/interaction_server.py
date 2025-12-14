import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .discord_utils import verify_signature, interaction_response, pong, register_commands
from .version import __version__
from .utils import utcnow

# ---- command handlers (moved out during refactor) ----
from .commands.interactions import (
    handle_fullroster,
    handle_service_record,
    handle_forcepull,
)

log = logging.getLogger("scrappystats.interactions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
START_TIME = utcnow()

SCRAPPYSTATS_DESCRIPTION = (
    "ScrappyStats helps you command your STFC alliance with fast reports and roster insights."
)

# ---- Discord command schema ----
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


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    register_commands(COMMANDS)
    log.info("Interaction server started, version %s", __version__)
    log.info(
        "Registered commands: %s",
        [opt["name"] for opt in COMMANDS[0]["options"]],
    )


# ─────────────────────────────────────────────
# Dispatcher table
# ─────────────────────────────────────────────
def dispatch_command(sub_name: str, payload: dict):
    """
    Central dispatcher for all /scrappystats subcommands.
    """

    COMMAND_HANDLERS = {
        # ---- lightweight inline commands ----
        "bark": lambda _: interaction_response(
            "Scrappy wags his tail enthusiastically and awaits orders, Captain."
        ),

        "version": lambda _: interaction_response(
            f"ScrappyStats v{__version__} reporting for duty, Captain."
        ),

        "help": lambda _: interaction_response(
            "\n".join(
                ["Available commands:"]
                + [
                    f"/scrappystats {opt['name']} — {opt['description']}"
                    for opt in COMMANDS[0]["options"]
                ]
            )
        ),

        # ---- real commands (moved out of this file) ----
        "fullroster": handle_fullroster,
        "dailyreport": lambda p: handle_service_record(p, mode="daily"),
        "weeklyreport": lambda p: handle_service_record(p, mode="weekly"),
        "forcepull": handle_forcepull,
    }

    handler = COMMAND_HANDLERS.get(sub_name)

    if not handler:
        log.error("No handler registered for command: %s", sub_name)
        return interaction_response(
            f"⚠️ `{sub_name}` is registered but not wired up yet.",
            True,
        )

    return handler(payload)


# ─────────────────────────────────────────────
# Interaction endpoint
# ─────────────────────────────────────────────
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

    # ---- Discord ping ----
    if t == 1:
        return JSONResponse(pong())

    # ---- Slash command ----
    if t == 2:
        data = payload.get("data", {})
        name = data.get("name")

        if name != "scrappystats":
            return JSONResponse(
                interaction_response(
                    "Scrappy tilts his head. That root command is unfamiliar, Captain.",
                    True,
                )
            )

        options = data.get("options") or []
        sub = options[0] if options else {}
        sub_name = sub.get("name")

        log.info("Received command: /scrappystats %s", sub_name)

        try:
            result = dispatch_command(sub_name, payload)
            return JSONResponse(result)

        except Exception:
            log.exception("Command execution failed: %s", sub_name)
            return JSONResponse(
                interaction_response(
                    "⚠️ Scrappy encountered an error while executing that command.",
                    True,
                )
            )

    return JSONResponse({"error": "Unsupported interaction type"}, status_code=400)
