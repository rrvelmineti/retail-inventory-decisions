"""Plain-English questions to SQL with Gemini, run safely, and checked against verified answers."""
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request

from .db import SCHEMA

MAX_ROWS = 1_000
MAX_SECONDS = 5


class AIError(ValueError):
    """Gemini was unavailable or its answer could not be used."""


def gemini_settings():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "").strip().removeprefix("models/")
    if not key or not model:
        raise AIError("Set GEMINI_API_KEY and GEMINI_MODEL in your environment to use Gemini.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise AIError("GEMINI_MODEL must be an API model ID such as the one shown in AI Studio's Get code.")
    return key, model


def call_gemini(prompt, *, json_output, opener=None):
    key, model = gemini_settings()
    config = {"temperature": 0}
    if json_output:
        config["responseMimeType"] = "application/json"
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with (opener or urllib.request.urlopen)(request, timeout=60) as response:
            raw = response.read(200_001)
        if len(raw) > 200_000:
            raise ValueError("Response too large")
        candidate = json.loads(raw)["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ValueError("Incomplete response")
        text = "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
        return json.loads(text) if json_output else text
    except urllib.error.HTTPError as exc:
        raise AIError(f"Gemini returned HTTP {exc.code}. Check the model ID, key and quota.") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise AIError("Gemini was unavailable or returned an answer that could not be read.") from None


def sql_prompt(question):
    return ("You write SQLite queries for a retail analyst. Use only the tables and columns below. "
            "Write one read-only SELECT (a WITH clause is fine). Round money to 2 decimals. "
            "If the question is ambiguous, choose the most reasonable reading and say so in assumptions. "
            "Return only JSON: {\"sql\": <query>, \"assumptions\": <one short sentence>}.\n\n"
            f"{SCHEMA}\nQuestion: {question}")


def draft_sql(question, opener=None):
    """Ask Gemini to write SQL. Only the schema description and the question are sent, never data rows."""
    answer = call_gemini(sql_prompt(question), json_output=True, opener=opener)
    if not isinstance(answer, dict) or not isinstance(answer.get("sql"), str):
        raise AIError("Gemini did not return a SQL query.")
    assumptions = answer.get("assumptions")
    return answer["sql"].strip(), assumptions if isinstance(assumptions, str) else ""


def check_read_only(sql):
    """Allow a single SELECT or WITH statement only."""
    text = sql.strip().rstrip(";").strip()
    if not text:
        raise ValueError("Empty query.")
    stripped = re.sub(r"'(?:[^']|'')*'", "''", text)       # ignore semicolons inside string literals
    if ";" in stripped:
        raise ValueError("Only one statement is allowed.")
    if not re.match(r"(?is)^\s*(select|with)\b", stripped):
        raise ValueError("Only SELECT queries are allowed.")
    return text


def run_query(conn, sql):
    """Run a checked query on a read-only connection with a time and row limit."""
    text = check_read_only(sql)
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

    def authorizer(action, *args):
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
    deadline = time.monotonic() + MAX_SECONDS
    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cursor = conn.execute(text)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(MAX_ROWS + 1)
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
    if len(rows) > MAX_ROWS:
        raise ValueError(f"The query returned more than {MAX_ROWS} rows; ask a narrower question.")
    return columns, rows


def _normal(value):
    if isinstance(value, float):
        return round(value, 2)
    return value


def same_answer(expected, actual, ordered):
    """True if the AI's result holds the verified answer.

    Same number of rows, and every verified column appears among the AI's columns with the same values
    (rounded to 2 decimals). Extra columns, column names and column order are ignored. For questions
    where order matters (top N, rankings) values must be in the same order; otherwise order is ignored.
    """
    if len(expected) != len(actual):
        return False
    if not expected:
        return True
    def columns(rows):
        cols = [[_normal(row[j]) for row in rows] for j in range(len(rows[0]))]
        return cols if ordered else [sorted(c, key=repr) for c in cols]
    have = columns(actual)
    return all(col in have for col in columns(expected))
