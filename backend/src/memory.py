import sqlite3
import json
import uuid
from datetime import datetime, timezone

DB_PATH = "memory.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return sqlite3.connect(DB_PATH)


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def init_db():
    conn = get_connection()

    # ----------------------------
    # User memory
    # ----------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            language_preference TEXT,
            facts TEXT,
            last_interaction TEXT
        )
    """)

    # ----------------------------
    # Human escalations
    # ----------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS escalations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            issue TEXT NOT NULL,
            summary TEXT NOT NULL,
            urgency TEXT NOT NULL,
            language TEXT,
            follow_up_method TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # ----------------------------
    # Call analytics - Day 8
    # ----------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# USER MEMORY
# ============================================================

def lookup_user(user_id: str):
    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "user_id": row[0],
        "name": row[1],
        "language_preference": row[2],
        "facts": json.loads(row[3]) if row[3] else {},
        "last_interaction": row[4],
    }


def save_user(
    user_id: str,
    name: str,
    language_preference: str,
    facts: dict,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT OR REPLACE INTO users
        (
            user_id,
            name,
            language_preference,
            facts,
            last_interaction
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            language_preference,
            json.dumps(facts, ensure_ascii=False),
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# HUMAN ESCALATION
# ============================================================

def create_escalation(
    user_id: str,
    issue: str,
    summary: str,
    urgency: str,
    language: str,
    follow_up_method: str,
):
    """
    Create a human-support escalation request.
    """

    escalation_id = (
        f"ESC-{uuid.uuid4().hex[:6].upper()}"
    )

    created_at = datetime.now(
        timezone.utc
    ).isoformat()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO escalations (
            id,
            user_id,
            issue,
            summary,
            urgency,
            language,
            follow_up_method,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            escalation_id,
            user_id,
            issue,
            summary,
            urgency,
            language,
            follow_up_method,
            "open",
            created_at,
        ),
    )

    conn.commit()
    conn.close()

    return escalation_id


# ============================================================
# DAY 8 - CALL ANALYTICS
# ============================================================

def create_calls_table():
    """
    Create the calls table if it does not already exist.
    """

    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calls (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT
        )
        """
    )

    conn.commit()
    conn.close()


def start_call(user_id: str):
    """
    Record the beginning of a call.

    Returns:
        call_id
    """

    call_id = (
        f"CALL-{uuid.uuid4().hex[:8].upper()}"
    )

    started_at = datetime.now(
        timezone.utc
    ).isoformat()

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO calls (
            id,
            user_id,
            started_at,
            ended_at,
            outcome
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            call_id,
            user_id,
            started_at,
            None,
            None,
        ),
    )

    conn.commit()
    conn.close()

    return call_id


def end_call(
    call_id: str,
    outcome: str,
):
    """
    Record the end of a call.

    Valid outcomes:
        success
        failed
    """

    outcome = outcome.lower().strip()

    if outcome not in {
        "success",
        "failed",
    }:
        raise ValueError(
            "Outcome must be 'success' or 'failed'."
        )

    ended_at = datetime.now(
        timezone.utc
    ).isoformat()

    conn = get_connection()

    conn.execute(
        """
        UPDATE calls
        SET
            ended_at = ?,
            outcome = ?
        WHERE id = ?
        """,
        (
            ended_at,
            outcome,
            call_id,
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# CALL ANALYTICS - COUNTS
# ============================================================

def get_total_calls():
    """
    Return total number of recorded calls.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        """
    )

    total = cursor.fetchone()[0]

    conn.close()

    return total


def get_successful_calls():
    """
    Return number of successful calls.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE outcome = 'success'
        """
    )

    successful = cursor.fetchone()[0]

    conn.close()

    return successful


def get_failed_calls():
    """
    Return number of failed calls.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE outcome = 'failed'
        """
    )

    failed = cursor.fetchone()[0]

    conn.close()

    return failed


def get_call_stats():
    """
    Return all three Day 8 dashboard metrics.
    """

    return {
        "total_calls": get_total_calls(),
        "successful_calls": get_successful_calls(),
        "failed_calls": get_failed_calls(),
    }


# ============================================================
# CALL HISTORY
# ============================================================

def get_recent_calls(limit: int = 20):
    """
    Return recent calls for dashboard/history use.

    Does NOT return conversation transcripts
    or sensitive caller information.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        SELECT
            id,
            user_id,
            started_at,
            ended_at,
            outcome
        FROM calls
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()

    conn.close()

    return [
        {
            "id": row[0],
            "user_id": row[1],
            "started_at": row[2],
            "ended_at": row[3],
            "outcome": row[4],
        }
        for row in rows
    ]


# ============================================================
# DEVELOPMENT / TEST
# ============================================================

if __name__ == "__main__":

    init_db()

    print("Database initialized.")

    print(
        "Call statistics:",
        get_call_stats()
    )
def get_call_analytics():
    conn = sqlite3.connect(DB_PATH)

    cursor = conn.execute("""
        SELECT
            COUNT(*) AS total_calls,
            SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successful_calls,
            SUM(CASE WHEN outcome = 'failed' THEN 1 ELSE 0 END) AS failed_calls
        FROM calls
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        "total_calls": row[0] or 0,
        "successful_calls": row[1] or 0,
        "failed_calls": row[2] or 0,
    }
def update_call_outcome(call_id: str, outcome: str):
    conn = sqlite3.connect(DB_PATH)

    conn.execute(
        """
        UPDATE calls
        SET outcome = ?
        WHERE id = ?
        """,
        (outcome, call_id),
    )

    conn.commit()
    conn.close()
