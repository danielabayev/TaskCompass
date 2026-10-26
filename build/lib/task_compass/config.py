"""Settings read from the environment (.env). Nothing secret is hard-coded here."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# The tool has a single user for now. Every table carries this id so more
# users can be added later without a data migration.
USER_ID = 1

# Model choice (see decisions doc, section 2): a stronger model for the
# interview questions and the estimate proposal, a small one for judging.
STRONG_MODEL = "claude-opus-5-5"
SMALL_MODEL = "claude-haiku-5-5"

# USD per million tokens: (input, output). Used for the local spend screen
# and the local monthly cap. Update when Anthropic prices change.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

# Interview rules.
MAX_INTERVIEW_ROUNDS = 12

# Calibration: median over the most recent N finished tasks, and the minimum
# number of samples before a factor is trusted.
CALIBRATION_WINDOW = 10
CALIBRATION_MIN_SAMPLES = 3

# Retrospective: actual/binding within this range counts as "on estimate".
ON_ESTIMATE_LOW = 0.8
ON_ESTIMATE_HIGH = 1.2


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def database_url(test: bool = False) -> str:
    """Build the SQLAlchemy URL from the POSTGRES_* variables (or DATABASE_URL)."""
    if not test and _env("DATABASE_URL"):
        return _env("DATABASE_URL")
    if test and _env("TEST_DATABASE_URL"):
        return _env("TEST_DATABASE_URL")
    db = _env("POSTGRES_DB", "task_compass") + ("_test" if test else "")
    return (
        f"postgresql+psycopg://{_env('POSTGRES_USER', 'task_compass')}:"
        f"{_env('POSTGRES_PASSWORD')}@{_env('POSTGRES_HOST', 'localhost')}:"
        f"{_env('POSTGRES_PORT', '5433')}/{db}"
    )


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    monthly_cost_cap_usd: float = field(
        default_factory=lambda: float(_env("MONTHLY_COST_CAP_USD", "10"))
    )
    # Seconds per model call before it is treated as a network failure.
    llm_timeout_s: float = 90.0
    # Automatic retries (with growing waits) on overload, rate limit, network.
    llm_max_retries: int = 3
