import logging
from datetime import timedelta

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .discord_utils import verify_signature, interaction_response, pong, register_commands
from .version import __version__
#from .utils import load_alliances, load_json, 
from .utils import load_alliances, load_json, utcnow, parse_iso
#from .legacy import events_path, state_path
from .legacy import events_path, state_path
from .report_common import compute_deltas, load_state_and_baseline, make_table

from .commands.interactions import handle_fullroster, handle_service_record

log = logging.getLogger("scrappystats.interactions")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()

START_TIME = utcnow()

SCRAPPYSTATS_DESCRIPTION = "ScrappyStats helps you command your STFC alliance with fast reports and roster insights."

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
            {"type": 1, "name": "warp-test", "description": "Check if Scrappy is ready for warp ten."},
            {"type": 1, "name": "version", "description": "Show ScrappyStats version."},
            {"type": 1, "name": "uptime", "description": "Show Scrappy's system status and uptime."},
            {"type": 1, "name": "interim", "description": "Interim contribution report since last daily."},
            {"type": 1, "name": "status", "description": "Short system status overview."},
            {"type": 1, "name": "recent-changes", "description": "Recent crew changes in the last 30 days."},
            {"type": 1, "name": "roster", "description": "Display the current crew manifest table."},
            {"type": 1, "name": "manifest", "description": "Alias of roster."},
            {
                "type": 1,
                "name": "top-contributors",
                "description": "Top helpers / RSS / ISO in the last N days.",
                "options": [
                    {
                        "type": 4,
                        "name": "days",
                        "description": "Number of days (default 7)",
                        "required": False,
                    }
                ],
            },
            {"type": 1, "name": "alliance-summary", "description": "Summary of alliance operations."},
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

    if t == 1:  # PING
        return JSONResponse(pong())

    if t == 2:  # APPLICATION_COMMAND
        data = payload.get("data", {})
        name = data.get("name")
        if name != "scrappystats":
            return JSONResponse(
                interaction_response("Scrappy tilts his head. That root command is unfamiliar, Captain.", True)
            )

        options = data.get("options") or []
        sub = options[0] if options else {}
        sub_name = sub.get("name")

        # Simple fun/status commands
        if sub_name == "bark":
            return JSONResponse(interaction_response(
                "Scrappy wags his tail enthusiastically and is waiting for orders, Captain."
            ))
        if sub_name == "warp-test":
            return JSONResponse(interaction_response(
                "Engines are stable and warp coils are charged. Scrappy confirms we are ready for warp ten."
            ))
        if sub_name == "version":
            return JSONResponse(interaction_response(
                f"Scrappy Stats v{__version__} reporting for duty, Captain."
            ))
        if sub_name == "uptime":
            return JSONResponse(interaction_response(uptime_report()))
        if sub_name == "status":
            return JSONResponse(interaction_response(status_report()))
        if sub_name == "interim":
            return JSONResponse(interaction_response(interim_report()))
        if sub_name == "recent-changes":
            return JSONResponse(interaction_response(recent_changes_report()))
        if sub_name in ("roster", "manifest"):
            return JSONResponse(interaction_response(roster_report()))
        if sub_name == "servicerecord":
            opts = {opt["name"]: opt.get("value") for opt in sub.get("options", [])}
            pname = opts.get("name")
            return JSONResponse(interaction_response(handle_service_record("default", pname)))
        if sub_name == "top-contributors":
            opts = {opt["name"]: opt.get("value") for opt in sub.get("options", [])}
            days = int(opts.get("days") or 7)
            return JSONResponse(interaction_response(top_contributors_report(days)))
        if sub_name == "alliance-summary":
            return JSONResponse(interaction_response(alliance_summary_report()))

        # Reports wired to dedicated modules
        if sub_name == "dailyreport":
            from .report_daily import generate_daily_report
            return JSONResponse(interaction_response(generate_daily_report()))
        if sub_name == "weeklyreport":
            from .report_weekly import generate_weekly_report
            return JSONResponse(interaction_response(generate_weekly_report()))

        # Force data pull
        if sub_name == "forcepull":
            from .fetch_and_process import run_all
            result = run_all()
            return JSONResponse(
                interaction_response(f"🖖 Captain, Scrappy has fetched the latest data. Result: {result}")
            )

        # Full roster convenience command
        if sub_name == "fullroster":
            return JSONResponse(interaction_response(handle_fullroster()))

        # Dynamic help listing
        if sub_name == "help":
            help_lines = [
                "Scrappy organizes the LCARS console and presents the current command roster, Captain.",
                "",
            ]
            for opt in COMMANDS[0].get("options", []):
                desc = opt.get("description", "")
                help_lines.append(f"/scrappystats {opt['name']} — {desc}")
            return JSONResponse(interaction_response("\n".join(help_lines)))

        # Unknown subcommand
        return JSONResponse(
            interaction_response("Scrappy tilts his head. That subcommand is not recognized, Captain.", True)
        )

    return JSONResponse({"error": "Unsupported interaction type"}, status_code=400)

def uptime_report() -> str:
    now = utcnow()
    delta = now - START_TIME
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    mins, _ = divmod(rem, 60)
    lines = []
    lines.append("Scrappy reports all systems operational, Captain.")
    lines.append("")
    lines.append(f"Uptime: {days}d {hours}h {mins}m")
    lines.append(f"Version: v{__version__}")
    lines.append(f"Started at: {START_TIME.isoformat()}")
    return "\n".join(lines)

def status_report() -> str:
    cfg = load_alliances()
    alliances = cfg.get("alliances", [])
    lines = []
    lines.append("Scrappy provides a brief status summary, Captain.")
    lines.append("")
    lines.append(f"Tracked Alliances: {len(alliances)}")
    for a in alliances:
        lines.append(f"- {a.get('name', a['id'])} (ID {a['id']})")
    return "\n".join(lines)

def interim_report() -> str:
    cfg = load_alliances()
    lines = []
    lines.append("Scrappy taps the console and compiles interim contribution scans, Captain.")
    for alliance in cfg.get("alliances", []):
        aid = alliance["id"]
        name = alliance.get("name", aid)
        state, prev = load_state_and_baseline(aid, "daily")
        deltas = compute_deltas(state, prev)
        helpers = sorted(deltas.items(), key=lambda kv: kv[1].get("helps", 0), reverse=True)
        lines.append("")
        lines.append(f"📊 **Interim — {name}**")
        count = 0
        for player, d in helpers:
            if d.get("helps", 0) <= 0:
                continue
            lines.append(f"- {player}: {d['helps']} helps since last daily")
            count += 1
            if count >= 10:
                break
        if count == 0:
            lines.append("_No positive contribution deltas since last daily._")
    return "\n".join(lines)

def recent_changes_report(days: int = 30) -> str:
    cfg = load_alliances()
    cutoff = utcnow() - timedelta(days=days)
    lines = []
    lines.append("Scrappy accesses the crew manifest logs and compiles recent changes for your review, Captain.")
    for alliance in cfg.get("alliances", []):
        aid = alliance["id"]
        name = alliance.get("name", aid)
        events = load_json(events_path(aid), [])
        recent = []
        for ev in events:
            ts = ev.get("timestamp")
            if not ts:
                continue
            try:
                dt = parse_iso(ts)
            except Exception:
                continue
            if dt >= cutoff:
                recent.append(ev)

        lines.append("")
        lines.append(f"🧑‍🚀 **{name}** — {len(recent)} changes in the last {days} days")

        if not recent:
            lines.append("_No manifest changes in this window._")
            continue

        rows = []
        for ev in sorted(recent, key=lambda e: e.get("timestamp", ""), reverse=True)[:20]:
            etype = ev.get("type")
            player = ev.get("player") or "Unknown"
            ts = ev.get("timestamp") or ""
            if etype == "join":
                desc = "Joined the alliance"
            elif etype == "rejoin":
                desc = "Rejoined the alliance"
            elif etype == "leave":
                desc = "Left the alliance"
            elif etype == "level_up":
                desc = f"Level up {ev.get('from_level')} → {ev.get('to_level')}"
            elif etype == "promotion":
                desc = f"Promotion {ev.get('from_rank')} → {ev.get('to_rank')}"
            else:
                desc = f"Event [{etype}]"
            rows.append([ts, player, desc])

        table = make_table(rows, headers=["Timestamp", "Officer", "Change"])
        lines.append(table)

    return "\n".join(lines)

def roster_report() -> str:
    cfg = load_alliances()
    if not cfg.get("alliances"):
        return "Scrappy whines softly — no alliances are configured yet, Captain."
    alliance = cfg["alliances"][0]
    aid = alliance["id"]
    name = alliance.get("name", aid)
    state = load_json(state_path(aid), {})
    if not state:
        return f"Scrappy reports an empty crew manifest for {name}, Captain."

    # Build table rows for make_table
    rows = []
    for pdata in state.values():
        rows.append([
            pdata.get("name", ""),
            str(pdata.get("level", "")),
            str(pdata.get("role", "")),
            pdata.get("join_date_original", "") or "",
            pdata.get("join_date_recent", "") or "",
        ])

    table = make_table(
        rows,
        headers=["Name", "Level", "Rank", "Original Join", "Recent Join"],
    )
    lines = []
    lines.append(f"📋 Crew Manifest — {name}")
    lines.append("Scrappy taps the LCARS interface and displays the active roster, Captain.")
    lines.append("")
    lines.append(table)
    return "\n".join(lines)

def player_report(name_query: str) -> str:
    cfg = load_alliances()
    if not name_query:
        return "Scrappy scratches behind his ear — I need a name to search for, Captain."
    alliance = cfg["alliances"][0] if cfg.get("alliances") else None
    if not alliance:
        return "Scrappy whines softly — no alliances are configured yet, Captain."
    aid = alliance["id"]
    aname = alliance.get("name", aid)
    state = load_json(state_path(aid), {})
    candidates = [p for p in state.values() if name_query.lower() in (p.get("name", "").lower())]
    if not candidates:
        return f"Scrappy cannot find any active officer matching '{name_query}', Captain."
    if len(candidates) > 1:
        names = ", ".join(sorted(p.get("name", "") for p in candidates))
        return f"Scrappy found multiple matches: {names}\nPlease provide a more specific name, Captain."
    p = candidates[0]
    lines = []
    lines.append(f"Scrappy retrieves the personnel file for **{p.get('name','')}**, Captain.")
    lines.append("")
    lines.append("```")
    lines.append(f"Name            : {p.get('name','')}")
    lines.append(f"Level           : {p.get('level','')}")
    lines.append(f"Rank            : {p.get('role','')}")
    lines.append(f"Original Join   : {p.get('join_date_original','')}")
    lines.append(f"Recent Join     : {p.get('join_date_recent','')}")
    lines.append(f"Total Joins     : {len(p.get('join_dates',[]))}")
    lines.append(f"Total Leaves    : {len(p.get('left_dates',[]))}")
    lines.append("```")
    return "\n".join(lines)

def top_contributors_report(days: int) -> str:
    cfg = load_alliances()
    cutoff = utcnow() - timedelta(days=days)
    lines = []
    lines.append(f"Scrappy has compiled the top performers for the last {days} days, Captain.")
    for alliance in cfg.get("alliances", []):
        aid = alliance["id"]
        name = alliance.get("name", aid)
        events = load_json(events_path(aid), [])
        contrib = {}
        for ev in events:
            ts = ev.get("timestamp")
            if not ts:
                continue
            try:
                dt = parse_iso(ts)
            except Exception:
                continue
            if dt < cutoff:
                continue
            player = ev.get("player")
            if not player:
                continue
            entry = contrib.setdefault(player, {"level_ups": 0, "promotions": 0})
            if ev.get("type") == "level_up":
                entry["level_ups"] += 1
            elif ev.get("type") == "promotion":
                entry["promotions"] += 1
        lines.append("")
        lines.append(f"🧑‍🚀 **{name}**")
        if not contrib:
            lines.append("_No qualifying events in this window._")
            continue
        sorted_players = sorted(
            contrib.items(),
            key=lambda kv: (kv[1]["level_ups"], kv[1]["promotions"]),
            reverse=True,
        )
        lines.append("```")
        lines.append("Name                 | Level-ups | Promotions")
        lines.append("---------------------+-----------+-----------")
        for player, c in sorted_players[:10]:
            lines.append(f"{player.ljust(20)} | {str(c['level_ups']).rjust(9)} | {str(c['promotions']).rjust(9)}")
        lines.append("```")
    return "\n".join(lines)

def alliance_summary_report() -> str:
    cfg = load_alliances()
    if not cfg.get("alliances"):
        return "Scrappy whines softly — no alliances are configured yet, Captain."
    alliance = cfg["alliances"][0]
    aid = alliance["id"]
    name = alliance.get("name", aid)
    state = load_json(state_path(aid), {})
    if not state:
        return f"Scrappy reports no active crew for {name}, Captain."
    levels = [p.get("level", 0) for p in state.values()]
    ranks = {}
    for p in state.values():
        role = p.get("role", "Unknown")
        ranks[role] = ranks.get(role, 0) + 1
    avg_level = sum(levels) / len(levels) if levels else 0
    lines = []
    lines.append("Scrappy provides a summary of alliance operations, Captain.")
    lines.append("")
    lines.append("======== Alliance Operational Summary ========")
    lines.append(f"Alliance: {name}")
    lines.append("")
    lines.append(f"Roster Size   : {len(state)} active officers")
    lines.append(f"Average Level : {avg_level:.1f}")
    lines.append("")
    lines.append("Rank Distribution:")
    for role, count in sorted(ranks.items(), key=lambda kv: kv[0]):
        lines.append(f"  • {role}: {count}")
    return "\n".join(lines)
    
## moved to supervisord v2.1.25
## if __name__ == "__main__":
##    uvicorn.run(
##        "scrappystats.interaction_server:app",
##        host="0.0.0.0",
##        port=8000,
##        reload=False,
##    )
