# Task Compass

A local tool that turns a vague task into a precise task card, helps you
estimate it honestly, times the work, and learns from the gap between your
estimate and reality. Hebrew, right-to-left interface; runs only on
`localhost`.

The flow: **definition (Grill Me interview) → time estimate → execution →
checkpoint (if time runs out) → retrospective.**

## Setup (Windows, PowerShell)

Requirements: Python 3.11+, Docker Desktop.

```powershell
cd C:\projects\task_helper
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

copy .env.example .env      # then fill in ANTHROPIC_API_KEY and POSTGRES_PASSWORD
docker compose up -d        # PostgreSQL on localhost:5433 (project name: task_compass)
alembic upgrade head        # create the tables
pytest                      # all tests should pass
flask --app task_compass.web run
```

Open http://localhost:5000.

The database also gets a separate `<POSTGRES_DB>_test` database for pytest,
created automatically the first time the Docker volume is created.

## Everyday commands

| What | Command |
|---|---|
| Start the database | `docker compose up -d` |
| Run the app | `flask --app task_compass.web run` |
| Interview in the terminal | `python -m task_compass.cli "לסדר את המחסן"` |
| Back up the database | `python -m scripts.backup` (writes `backups/*.sql`) |
| Restore a backup (stop the app first) | `python -m scripts.backup --restore backups\<file>.sql` |
| Fast tests (scripted model, free) | `pytest` |
| Real-model behavior run (costs money) | `python -m scripts.run_behavior_live` |

## How the code is organized

```
task_compass/
  config.py        settings from .env, model names, prices, thresholds
  texts_he.py      every Hebrew string in the interface, in one place
  models.py        database tables (the single source of truth)
  domain/          pure rules, no model and no database (unit-tested):
                   field tests, readiness, calibration, estimates, execution, retro
  llm/             model access: gateway (cost cap, logging, one repair),
                   anthropic_client (real), fake (tests), schemas, prompts/*.md
  interview/       the Grill Me interview: graph.py (LangGraph step), service.py
  services/        estimate, execution, retro, reports (history, spend)
  wiring.py        builds the services once
  web/             Flask routes, Jinja templates, HTMX, static files (vendored)
  cli.py           interview in the terminal
migrations/        Alembic
scripts/           backup/restore, live behavior run
tests/unit         layer 1: rules
tests/behavior     layer 2: interview behavior (scripted) + scenarios for the live run
tests/integration  database and full web flow
docs/acceptance.md layer 3: manual acceptance checklist
```

Where to start when adding a feature:
- A new rule → `domain/` with a unit test.
- A new step in a stage → a method in the stage's service, a route in
  `web/routes.py`, a form in `web/templates/partials/<stage>.html`, strings in
  `texts_he.py`.
- A prompt change → `llm/prompts/*.md`, then run `python -m scripts.run_behavior_live`.

## Key behaviors

- The interview asks one question at a time, on the first field that has not
  passed. A card is ready only when every field passes; the code decides, the
  model only judges. "Enough" never bypasses the tests. After 12 answered
  rounds without a ready card: split off a smaller piece or open an
  investigation; no partial card.
- Your input is saved before every model call. If a call fails you get a
  Hebrew message and a retry button; nothing is lost.
- The blind estimate is locked before the model's proposal is requested and is
  never overwritten. A 2x gap forces one clarification round.
- The timer's start time is stored on the server; a refresh does not reset it.
  One extension per task.
- Model calls are logged with tokens and cost (`llm_calls`). A local monthly
  cap (`MONTHLY_COST_CAP_USD`) stops calls once reached; the spend screen warns
  at 70%.
- No external requests from the browser: htmx, Pico.css and the Heebo font
  are served from `web/static/vendor`.
