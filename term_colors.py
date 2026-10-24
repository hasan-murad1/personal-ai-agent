"""Small helpers that colour terminal output, so each kind of line is easy to spot.

Colours are only used when output goes to a real terminal and the NO_COLOR environment variable
is not set; otherwise the text is returned unchanged. No extra package is needed.
"""

import os
import sys

ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

if ENABLED and os.name == "nt":
    # Turns on ANSI colour codes in the classic Windows console (PowerShell, cmd). VS Code's terminal supports them already.
    os.system("")


def _style(code):
    """Return a function that wraps text in one ANSI style and resets it afterwards."""
    def apply(text):
        if not ENABLED:
            return str(text)
        return f"\033[{code}m{text}\033[0m"
    return apply


dim = _style("90")      # background details: listening, timings, debug lines
info = _style("94")     # safety rules and tool calls
warn = _style("93")     # risky actions waiting for approval, warnings
ok = _style("92")       # approved actions, session started
bad = _style("91")      # cancelled actions, errors
bold = _style("1")      # labels such as "You said:" and "Agent:"