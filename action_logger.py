import sqlite3
import datetime

LOG_DB = "action_log.db"


def init_log_db():
    """Create the action_log table if it doesn't already exist."""
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            arguments TEXT,
            result TEXT,
            was_risky INTEGER,
            was_confirmed INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def log_action(tool_name, arguments, result, was_risky, was_confirmed):
    """Record a single tool execution to the action log."""
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO action_log (tool_name, arguments, result, was_risky, was_confirmed) VALUES (?, ?, ?, ?, ?)",
        (tool_name, str(arguments), str(result), int(was_risky), int(was_confirmed))
    )
    conn.commit()
    conn.close()


def get_recent_actions(limit=10) -> str:
    """Return a readable summary of the most recent logged actions."""
    conn = sqlite3.connect(LOG_DB)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT tool_name, arguments, result, was_risky, timestamp FROM action_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "No actions have been logged yet."

    output = []
    for tool_name, arguments, result, was_risky, timestamp in rows:
        risk_tag = "⚠️ RISKY" if was_risky else "safe"
        output.append(f"[{timestamp}] {tool_name} ({risk_tag})\n  args: {arguments}\n  result: {result}")

    return "\n\n".join(output)