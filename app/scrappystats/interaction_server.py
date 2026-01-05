import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .discord_utils import verify_signature, interaction_response, pong, register_commands
from .log import configure_logging
from .version import __version__
from .utils import utcnow
#from .commands.reports import handle_report
from .commands.slash_service import handle_report_slash
from .commands.interactions import (
    handle_fullroster,
    handle_forcepull,
    handle_service_record_slash,
    handle_name_changes_slash,
)
from scrappystats.config import load_config

log = logging.getLogger("scrappystats.interactions")
configure_logging()

app = FastAPI()
START_TIME = utcnow()

## Check for valid config file and fail if one is not found
load_config(fatal=True)


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
            {"type": 1, "name": "interimreport", "description": "Show the interim alliance report."},
            {"type": 1, "name": "forcepull", "description": "Force Scrappy to fetch new data."},
            {"type": 1, "name": "fullroster", "description": "Show full roster with join dates."},
            {
                "type": 1,
                "name": "servicerecord",
                "description": "Show a member's service record.",
                "options": [
                    {
                        "type": 3,
                        "name": "player",
                        "description": "Exact player name to look up.",
                        "required": True,
                    }
                ],
            },
            {
                "type": 1,
                "name": "namechanges",
                "description": "Show recorded name changes.",
                "options": [
                    {
                        "type": 3,
                        "name": "player",
                        "description": "Exact player name to filter.",
                        "required": False,
                    }
                ],
            },
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
        "dailyreport": lambda p: handle_report_slash(p, period="daily"),
        "weeklyreport": lambda p: handle_report_slash(p, period="weekly"),
        "interimreport": lambda p: handle_report_slash(p, period="interim"),
        "servicerecord": handle_service_record_slash,
        "namechanges": handle_name_changes_slash,

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
