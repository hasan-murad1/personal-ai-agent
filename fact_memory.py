import re
import sqlite3

FACTS_DB = "facts.db"

BLOCKED_KEYWORDS = (
    "password", "passcode", "otp", "pin code", "credit card",
    "card number", "secret", "api key", "token",
)


def init_facts_db():
    """Create the facts table if it doesn't already exist."""
    conn = sqlite3.connect(FACTS_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def remember_fact(fact: str, category: str = "general") -> str:
    """Store a fact the user explicitly asked to remember. Rejects sensitive content and duplicates."""
    fact = fact.strip()
    if not fact:
        return "Error: nothing to remember."

    lowered = fact.lower()
    for keyword in BLOCKED_KEYWORDS:
        if keyword in lowered:
            return "Error: this looks like sensitive information, so it was not saved."

    conn = sqlite3.connect(FACTS_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM facts WHERE LOWER(fact) = ?", (lowered,))
    if cursor.fetchone():
        conn.close()
        return f"Already remembered: '{fact}'"

    cursor.execute(
        "INSERT INTO facts (fact, category) VALUES (?, ?)",
        (fact, category.strip().lower() or "general")
    )
    conn.commit()
    conn.close()
    return f"Remembered: '{fact}' (category: {category})"


def get_all_facts():
    """Return all stored facts as a list of (id, fact, category) tuples."""
    conn = sqlite3.connect(FACTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact, category FROM facts ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def recall_facts() -> str:
    """Return every stored fact as readable text."""
    rows = get_all_facts()
    if not rows:
        return "No facts are stored yet."
    return "\n".join(f"- [{category}] {fact}" for _, fact, category in rows)


def format_facts_for_prompt() -> str:
    """Format stored facts for injection into the system prompt at session start."""
    rows = get_all_facts()
    if not rows:
        return ""
    lines = "\n".join(f"- {fact}" for _, fact, _ in rows)
    return f"Known facts about the user (saved at their request):\n{lines}"


def forget_fact(keyword: str) -> str:
    """Delete a stored fact whose text contains every meaningful word of the keyword. Refuses if more than one fact matches."""
    words = [w for w in re.findall(r"\w+", keyword.lower()) if len(w) > 2]
    if not words:
        return "Error: please specify which fact to forget."

    conn = sqlite3.connect(FACTS_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fact FROM facts")
    all_facts = cursor.fetchall()

    matches = [
        (fact_id, fact_text) for fact_id, fact_text in all_facts
        if all(word in fact_text.lower() for word in words)
    ]

    if not matches:
        conn.close()
        return f"No stored fact matches '{keyword}'."

    if len(matches) > 1:
        conn.close()
        listed = [fact for _, fact in matches]
        return f"Multiple facts match: {listed}. Please be more specific."

    fact_id, fact_text = matches[0]
    cursor.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    conn.close()
    return f"Forgot: '{fact_text}'"