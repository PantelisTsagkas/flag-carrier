"""Flag Carrier: daily European flag quiz for the stand-up.

Everyone gets the same 10 flags per day (seeded by the Europe/London date).
First submitted score per name per day stands. Scores live in SQLite.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
LONDON = ZoneInfo("Europe/London")

ROUNDS_PER_DAY = 10
OPTIONS_PER_ROUND = 4
ROUND_SECONDS = 10
MAX_SCORE = 200 * ROUNDS_PER_DAY

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

COUNTRIES: dict[str, str] = {
    "al": "Albania",
    "ad": "Andorra",
    "at": "Austria",
    "by": "Belarus",
    "be": "Belgium",
    "ba": "Bosnia & Herzegovina",
    "bg": "Bulgaria",
    "hr": "Croatia",
    "cy": "Cyprus",
    "cz": "Czechia",
    "dk": "Denmark",
    "ee": "Estonia",
    "fi": "Finland",
    "fr": "France",
    "de": "Germany",
    "gr": "Greece",
    "hu": "Hungary",
    "is": "Iceland",
    "ie": "Ireland",
    "it": "Italy",
    "xk": "Kosovo",
    "lv": "Latvia",
    "li": "Liechtenstein",
    "lt": "Lithuania",
    "lu": "Luxembourg",
    "mt": "Malta",
    "md": "Moldova",
    "mc": "Monaco",
    "me": "Montenegro",
    "nl": "Netherlands",
    "mk": "North Macedonia",
    "no": "Norway",
    "pl": "Poland",
    "pt": "Portugal",
    "ro": "Romania",
    "ru": "Russia",
    "sm": "San Marino",
    "rs": "Serbia",
    "sk": "Slovakia",
    "si": "Slovenia",
    "es": "Spain",
    "se": "Sweden",
    "ch": "Switzerland",
    "tr": "Turkey",
    "ua": "Ukraine",
    "gb": "United Kingdom",
}

# Distractors are drawn from the same look-alike family first, so the daily
# run reliably serves up the Monaco/Poland and Slovakia/Slovenia traps.
SIMILARITY_GROUPS: list[set[str]] = [
    {"dk", "no", "se", "fi", "is"},
    {"nl", "lu", "ru", "sk", "si", "hr", "rs", "cz"},
    {"fr", "it", "ie", "be", "ro", "md"},
    {"pl", "mc", "at", "lv"},
    {"lt", "ee", "hu", "bg"},
    {"al", "xk", "mk", "me", "ba"},
    {"sm", "li", "ad"},
]


def _seed(date_str: str) -> int:
    digest = hashlib.sha256(f"flag-carrier:{date_str}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _rounds_from_rng(rng: random.Random) -> list[dict]:
    codes = sorted(COUNTRIES)
    answers = rng.sample(codes, ROUNDS_PER_DAY)
    rounds: list[dict] = []
    for code in answers:
        group = next((g for g in SIMILARITY_GROUPS if code in g), None)
        same_pool = sorted(group - {code}) if group else []
        wrongs = rng.sample(same_pool, min(2, len(same_pool)))
        rest = sorted(set(codes) - {code} - set(wrongs))
        wrongs += rng.sample(rest, OPTIONS_PER_ROUND - 1 - len(wrongs))
        options = wrongs + [code]
        rng.shuffle(options)
        rounds.append(
            {
                "answer": code,
                "name": COUNTRIES[code],
                "options": [{"code": c, "name": COUNTRIES[c]} for c in options],
            }
        )
    return rounds


def daily_rounds(date_str: str) -> list[dict]:
    return _rounds_from_rng(random.Random(_seed(date_str)))


def today_london() -> str:
    return datetime.now(LONDON).strftime("%Y-%m-%d")


def _validate_date(date_str: str) -> str:
    if not DATE_RE.match(date_str):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="not a real date")
    return date_str


def _db() -> sqlite3.Connection:
    path = Path(os.environ.get("FC_DB_PATH", str(BASE_DIR / "data" / "scores.db")))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name_key TEXT NOT NULL,
            name TEXT NOT NULL,
            score INTEGER NOT NULL,
            dep_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (date, name_key)
        )
        """
    )
    return conn


def _position(conn: sqlite3.Connection, date: str, score: int, row_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM scores WHERE date = ? AND (score > ? OR (score = ? AND id < ?))",
        (date, score, score, row_id),
    ).fetchone()
    return row["n"] + 1


class ScoreIn(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    score: int = Field(ge=0, le=MAX_SCORE)
    date: str | None = None


app = FastAPI(title="Flag Carrier")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/daily")
def daily(date: str | None = None) -> dict:
    d = _validate_date(date) if date else today_london()
    return {"date": d, "round_seconds": ROUND_SECONDS, "rounds": daily_rounds(d)}


@app.get("/api/practice")
def practice() -> dict:
    rng = random.Random(random.SystemRandom().randrange(2**63))
    return {"date": None, "round_seconds": ROUND_SECONDS, "rounds": _rounds_from_rng(rng)}


@app.post("/api/scores")
def submit_score(payload: ScoreIn) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is empty")
    d = _validate_date(payload.date) if payload.date else today_london()
    name_key = name.casefold()
    now = datetime.now(LONDON)
    with _db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO scores (date, name_key, name, score, dep_time, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    d,
                    name_key,
                    name,
                    payload.score,
                    now.strftime("%H:%M"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            pos = _position(conn, d, payload.score, cur.lastrowid)
            return {
                "logged": True,
                "date": d,
                "name": name,
                "standing_score": payload.score,
                "position": pos,
            }
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id, score FROM scores WHERE date = ? AND name_key = ?",
                (d, name_key),
            ).fetchone()
            pos = _position(conn, d, row["score"], row["id"])
            return {
                "logged": False,
                "date": d,
                "name": name,
                "standing_score": row["score"],
                "position": pos,
            }


@app.get("/api/leaderboard")
def leaderboard(date: str | None = None) -> dict:
    d = _validate_date(date) if date else today_london()
    with _db() as conn:
        rows = conn.execute(
            "SELECT name, score, dep_time FROM scores WHERE date = ? ORDER BY score DESC, id ASC",
            (d,),
        ).fetchall()
    return {
        "date": d,
        "entries": [
            {"pos": i + 1, "name": r["name"], "score": r["score"], "time": r["dep_time"]}
            for i, r in enumerate(rows)
        ],
    }


@app.get("/api/alltime")
def alltime() -> dict:
    with _db() as conn:
        rows = conn.execute(
            "SELECT MAX(name) AS name, SUM(score) AS total, COUNT(*) AS days "
            "FROM scores GROUP BY name_key ORDER BY total DESC LIMIT 100"
        ).fetchall()
    return {
        "entries": [
            {"pos": i + 1, "name": r["name"], "total": r["total"], "days": r["days"]}
            for i, r in enumerate(rows)
        ]
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/flags", StaticFiles(directory=STATIC_DIR / "flags"), name="flags")
