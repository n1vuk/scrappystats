## 2.0.5
- Fix missing load_alliances causing startup failure
- Ensure __version__ export exists
- Restore full Docker-based release layout

## 2.1.10 - 2025-12-12
- Fixed `scrappystats.storage` packaging and added `save_raw_html()` export used by startup fetch.
- Stabilized `fetch_and_process.py` entrypoint to call `scrappystats.services.sync` rather than re-exporting removed symbols.
- Installed and configured cron inside the container to eliminate supervisord cron spawn errors.

## 2.1.8 - 2025-12-12
- Fix: restore `save_raw_html` export in `scrappystats.storage` to prevent startup ImportError.
- Fix: use correct cron binary path (`/usr/sbin/cron -f`) in supervisord.

## 2.1.7 - 2025-12-12
### Fixed
- Install and run system cron correctly (supervisor now uses /usr/sbin/cron; Docker image installs cron).
- Restore legacy compatibility helpers so startup init no longer fails on missing imports (save_raw_html, state_path, events_path, history_* paths).


## v2.0.9 — Application Restore & Deployment Fixes

### 🧩 Application Restore
- Restored full application code from v2.0.5 (last complete release)
- Reinstates startup_init, health_server, interaction_server, and all services

### 🐳 Container & Deployment Fixes
- Dockerfile now copies `app/` to `/app/` so scrappystats is importable
- docker-compose.yml is authoritative and defines build context
- Supervisor uses correct cron path and runs as root

### 🧾 No Functional Logic Changes
- Application logic unchanged from v2.0.5
- This release strictly restores functionality and preserves infra fixes

## v2.1.0 — Python Import Path Fix

### 🐍 Container Import Resolution
- Explicitly sets `PYTHONPATH=/app` in Dockerfile
- Ensures `scrappystats.*` modules are discoverable by Python
- Fixes `No module named scrappystats.startup_init` at runtime

### 🧾 No Application Logic Changes
- Pure container/runtime configuration fix

## v2.1.1 — Compatibility Shim Release

### 🩹 Backward Compatibility Fixes
- Restored legacy symbols expected by startup and report modules
- Added compatibility alias for `fetch_alliance_page`
- Added compatibility shims for history path helpers in utils

### 🧾 No Behavioral Changes
- Logic unchanged; this release only restores internal API compatibility

## v2.1.2 — Defensive Internal API Shims

- Added defensive runtime shims for legacy imports
- Guarantees fetch_and_process and reports import correctly
- No behavior changes beyond compatibility

## v2.1.3 — Deterministic Docker Builds

### 🐳 Docker Build Fix
- Docker Compose no longer builds from a symlinked context
- Build context is now the real project directory
- Prevents Docker from reusing stale images across updates

### 🔁 Deployment Reliability
- Ensures updated ZIP contents always result in a new container image
- Eliminates "ghost code" caused by Docker layer caching

### 🧾 No Application Logic Changes
- Application code unchanged from v2.1.2


## 2.1.4
- Added legacy compatibility module to stabilize refactored imports
- Restored missing internal symbols via legacy layer
- Fixed cron executable path for supervisor


## 2.1.5
- Wired legacy compatibility layer into runtime imports
- Eliminated ImportError restart loops
- Stabilized init, reporting, and interaction server startup


## 2.1.6
- Force-rewired legacy imports to eliminate multiline import misses
- Removed remaining direct imports of removed internal symbols
- Guaranteed legacy layer usage at runtime

## 2.1.13 - 2025-12-12
- Restore full build/deploy packaging (Dockerfile, supervisord, compose, cron).
- Install and run cron under supervisord; ensure root crontab is installed.
- Add cron job execution markers and Docker HEALTHCHECK.
- Add cron health check script and improve startup init marker writes.


## 2.1.14 – Stability & Runtime Fixes

### Fixed
- Rebuilt from complete 2.1.10 baseline and merged 2.1.11–2.1.13 deltas
- Installed system cron inside Docker image (fixes supervisor spawn errors)
- Restored legacy `save_raw_html` import compatibility
- Ensured crontab is installed and executed correctly at runtime

### Improved
- Version reporting consistency during deployment
- Startup reliability under supervisor

### Notes
- This release repairs missing-package and partial-zip regressions

## v2.1.16 & v2.1.17

### Fixed
- Fixed release packaging so VERSION inside build artifacts always matches the Git tag.
- Hardened release build script to reliably produce zip artifacts from tagged commits.

## v2.1.18
- Fix deployment when running Docker Compose from symlinked `current`
- Pin Docker Compose project name to prevent container name conflicts
- No application code changes

## v2.1.19
- tweak to deploy script
- fixed discord services not starting

## v2.1.20
- fixed deploy script not being executable

## v2.1.24
- fixed missing report table function

## v2.1.25 
- Fix: remove embedded uvicorn startup from interaction_server

## through 3.0.0 stabalizing refactor
