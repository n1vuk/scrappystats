import logging
from datetime import timedelta

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .discord_utils import verify_signature, interaction_response, pong, register_commands
from .version import __version__
from .utils import load_alliances, load_json, utcnow, parse_iso
from .legacy import events_path, state_path
from .report_common import compute_deltas, load_state_and_baseline, make_table
from .commands.interactions import handle_fullroster, handle_service_record

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

@app.on_event("startup")
async def on_startup():
    register_commands(COMMANDS)
    log.info("Interaction server started, version %s", __version__)

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

    if t == 1:
        return JSONResponse(pong())

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

        if sub_name == "bark":
            return JSONResponse(
                interaction_response(
                    "Scrappy wags his tail enthusiastically and is waiting for orders, Captain."
                )
            )

        if sub_name == "version":
            return JSONResponse(
                interaction_response(f"ScrappyStats v{__version__} reporting for duty, Captain.")
            )

        if sub_name == "help":
            lines = ["Available commands:"]
            for opt in COMMANDS[0]["options"]:
                lines.append(f"/scrappystats {opt['name']} — {opt['description']}")
            return JSONResponse(interaction_response("\n".join(lines)))

        return JSONResponse(
            interaction_response(
                "Scrappy tilts his head. That subcommand is not recognized, Captain.",
                True,
            )
        )

    return JSONResponse({"error": "Unsupported interaction type"}, status_code=400)
