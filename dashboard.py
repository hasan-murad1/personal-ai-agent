"""Read-only live dashboard for the voice agent.

It runs a tiny web server on this computer only (127.0.0.1) in a background thread and shows,
in plain language, what the agent is doing: what you said, which tool runs, when it is waiting
for your typed approval, and what it answered.

Design rules:
- Read-only: the page has no buttons and cannot control the agent. Approvals stay typed in the terminal.
- Never block the voice loop: add_event() only appends to an in-memory list under a lock.
- Never crash the agent: if the server cannot start, the agent keeps working without it.
- Untrusted text (web results, model replies) is shown with textContent in the browser, never as HTML.
"""

import collections
import itertools
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"          # this computer only; other devices on the network cannot open it
DEFAULT_PORT = 8765
PORT_ATTEMPTS = 5           # try 8765..8769 if a port is busy
MAX_EVENTS = 300            # older events are dropped, so memory stays bounded
MAX_TEXT_CHARS = 2000       # long texts are cut before they are stored

STATUS_LABELS = {
    "idle": "Idle - press Enter in the terminal",
    "calibrating": "Measuring room noise",
    "listening": "Listening",
    "thinking": "Thinking",
    "approval": "Waiting for your typed approval",
    "speaking": "Speaking",
}

_lock = threading.Lock()
_events = collections.deque(maxlen=MAX_EVENTS)
_ids = itertools.count(1)
_state = {
    "status": "idle",
    "turn": 0,
    "stats": {"tools_used": 0, "approved": 0, "blocked": 0, "web_searches": 0, "web_search_limit": 0},
}
_server = None
_url = None


def _clip(value):
    """Turn a value into text and cut it to a safe length."""
    text = str(value) if value is not None else ""
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "..."
    return text


def add_event(kind, **fields):
    """Record one event for the page. Fast and safe to call from the voice loop.

    Kinds used by the page: session, user, tool, approval, approval_result, agent, info.
    """
    try:
        with _lock:
            if kind == "user":
                _state["turn"] += 1
            event = {"id": next(_ids), "kind": kind, "turn": _state["turn"], "time": time.strftime("%H:%M:%S")}
            for key, value in fields.items():
                event[key] = value if isinstance(value, (bool, int, float)) or value is None else _clip(value)
            _events.append(event)
    except Exception:
        pass  # the dashboard must never break the agent


def set_status(status):
    """Set the current status shown in the header (see STATUS_LABELS)."""
    with _lock:
        _state["status"] = status if status in STATUS_LABELS else "idle"


def update_stats(**changes):
    """Update session numbers, e.g. update_stats(tools_used=3, web_search_limit=15)."""
    with _lock:
        for key, value in changes.items():
            if key in _state["stats"]:
                _state["stats"][key] = value


def increment_stat(name, amount=1):
    """Add to one of the session numbers."""
    with _lock:
        if name in _state["stats"]:
            _state["stats"][name] += amount


def _snapshot(after_id):
    """Return events newer than after_id plus the current state, as plain data."""
    with _lock:
        events = [e for e in _events if e["id"] > after_id]
        status = _state["status"]
        return {
            "events": events,
            "status": status,
            "status_label": STATUS_LABELS.get(status, status),
            "turn": _state["turn"],
            "stats": dict(_state["stats"]),
            "oldest_id": _events[0]["id"] if _events else 0,
        }


class _Server(ThreadingHTTPServer):
    """On Windows, SO_REUSEADDR would let us share a port another program already uses, so turn it off there."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    """Serves the page and the event feed. Only GET, only two paths."""

    def _host_allowed(self):
        # Blocks DNS-rebinding tricks: a foreign website cannot read the feed through another host name.
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code, body, content_type):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_allowed():
            self._send(403, "Forbidden", "text/plain; charset=utf-8")
            return
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE_HTML, "text/html; charset=utf-8")
        elif parsed.path == "/events":
            try:
                after_id = int(parse_qs(parsed.query).get("after", ["0"])[0])
            except ValueError:
                after_id = 0
            self._send(200, json.dumps(_snapshot(after_id)), "application/json; charset=utf-8")
        else:
            self._send(404, "Not found", "text/plain; charset=utf-8")

    def log_message(self, format, *args):
        pass  # keep the terminal clean; the page polls twice a second


def start(port=DEFAULT_PORT, open_browser=True):
    """Start the dashboard in a background thread. Returns its URL, or None if it could not start."""
    global _server, _url
    if _server is not None:
        return _url
    for candidate in range(port, port + PORT_ATTEMPTS):
        try:
            server = _Server((HOST, candidate), _Handler)
            break
        except OSError:
            continue
    else:
        print(f"[Dashboard not started: ports {port}-{port + PORT_ATTEMPTS - 1} are busy. The agent still works.]")
        return None

    thread = threading.Thread(target=server.serve_forever, name="dashboard-server", daemon=True)
    thread.start()
    _server = server
    _url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"[Dashboard running at {_url}]")
    if open_browser:
        try:
            webbrowser.open(_url)
        except Exception:
            pass
    return _url


def stop():
    """Stop the dashboard server (used by tests; the agent can simply exit)."""
    global _server, _url
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
        _url = None


PAGE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Personal AI Agent</title>
<style>
  :root {
    --accent: #0f766e; --accent-tint: #e6f4f2; --accent-border: #b9e0da;
    --bg: #f6f7fb; --panel: #ffffff; --line: #e6e8ef; --text: #1d2330; --muted: #6b7486;
    --ok: #137a3d; --ok-tint: #e8f7ee; --warn: #8a5a00; --warn-tint: #fff7e6; --warn-border: #f0b429;
    --bad: #9b1c1c; --bad-tint: #fdecec;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body { background: var(--bg); color: var(--text); font-family: "Segoe UI", Inter, Arial, sans-serif; }
  .app { display: flex; flex-direction: column; height: 100vh; }
  header { display: flex; align-items: center; justify-content: space-between; gap: 16px;
           padding: 16px 24px; background: var(--panel); border-bottom: 1px solid var(--line); }
  header h1 { font-size: 20px; font-weight: 650; }
  .pill { display: flex; align-items: center; gap: 9px; padding: 7px 14px; border-radius: 999px;
          font-weight: 600; font-size: 14px; background: #eef0f3; color: var(--muted); white-space: nowrap; }
  .pill .dot { width: 10px; height: 10px; border-radius: 50%; background: currentColor; }
  .pill.st-listening { background: var(--ok-tint); color: var(--ok); }
  .pill.st-listening .dot { box-shadow: 0 0 0 5px rgba(19,122,61,.15); animation: pulse 1.4s infinite; }
  .pill.st-thinking, .pill.st-speaking, .pill.st-calibrating { background: var(--accent-tint); color: var(--accent); }
  .pill.st-approval { background: var(--warn-tint); color: var(--warn); }
  @keyframes pulse { 50% { box-shadow: 0 0 0 9px rgba(19,122,61,.05); } }
  main { display: flex; flex: 1; min-height: 0; }
  #chat { flex: 1; overflow-y: auto; padding: 22px 26px; display: flex; flex-direction: column; gap: 12px; }
  .empty { margin: auto; color: var(--muted); text-align: center; font-size: 15px; line-height: 1.6; }
  .msg { max-width: 78%; padding: 12px 16px; border-radius: 16px; font-size: 16px; line-height: 1.45;
         white-space: pre-wrap; word-wrap: break-word; }
  .who { font-size: 12.5px; font-weight: 650; opacity: .75; margin-bottom: 4px; white-space: normal; }
  .you { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 5px; }
  .agent { align-self: flex-start; background: var(--panel); border: 1px solid var(--line); border-bottom-left-radius: 5px; }
  .card { align-self: flex-start; max-width: 82%; display: flex; gap: 12px; align-items: flex-start;
          padding: 11px 14px; border-radius: 12px; font-size: 14.5px; }
  .card .ic { font-size: 19px; line-height: 1.2; }
  .card b { display: block; }
  .card .sub { color: var(--muted); font-size: 13.5px; margin-top: 2px; word-break: break-word; }
  .card.tool { background: var(--accent-tint); border: 1px solid var(--accent-border); }
  .card.info { background: #eef0f3; border: 1px solid var(--line); color: var(--muted); }
  .session { align-self: center; color: var(--muted); font-size: 13px; padding: 4px 12px;
             border: 1px dashed var(--line); border-radius: 999px; }
  .card.approval { align-self: stretch; max-width: none; flex-direction: column; gap: 6px;
              background: var(--warn-tint); border: 2px solid var(--warn-border); border-radius: 14px; padding: 14px 18px; }
  .card.approval .h { font-weight: 700; color: var(--warn); font-size: 15.5px; }
  .card.approval .k { color: #5b4a26; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .card.approval .hint { align-self: flex-start; background: var(--text); color: #fff; padding: 5px 10px;
                    border-radius: 8px; font-family: Consolas, monospace; font-size: 13px; }
  .card.approval.allowed { background: var(--ok-tint); border-color: #9fd8b5; }
  .card.approval.allowed .h { color: var(--ok); }
  .card.approval.blocked { background: var(--bad-tint); border-color: #f2b8b8; }
  .card.approval.blocked .h { color: var(--bad); }
  aside { width: 300px; background: var(--panel); border-left: 1px solid var(--line); padding: 20px;
          display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
  aside h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .6px; color: var(--muted); margin-top: 6px; }
  .step { display: flex; gap: 9px; align-items: flex-start; font-size: 14px; padding: 8px 11px;
          border-radius: 10px; background: var(--bg); line-height: 1.35; word-break: break-word; }
  .step.done { color: var(--ok); }
  .step.now { background: var(--warn-tint); color: var(--warn); font-weight: 650; }
  .stat { display: flex; justify-content: space-between; font-size: 14px; color: #4a5468; padding: 3px 2px; }
  .stat b { color: var(--text); }
  footer { padding: 8px 24px; font-size: 12.5px; color: var(--muted); background: var(--panel); border-top: 1px solid var(--line); }
  @media (max-width: 820px) { aside { display: none; } .msg, .card { max-width: 95%; } }
</style>
</head>
<body>
<div class="app">
  <header>
    <h1>Personal AI Agent</h1>
    <div id="pill" class="pill"><span class="dot"></span><span id="pill-text">Connecting...</span></div>
  </header>
  <main>
    <section id="chat"><div class="empty" id="empty">Nothing yet.<br>Press Enter in the terminal and start talking.</div></section>
    <aside>
      <h2>What is happening</h2>
      <div id="steps"><div class="step">Waiting for you to speak</div></div>
      <h2>This session</h2>
      <div class="stat">Tools used <b id="s-tools">0</b></div>
      <div class="stat">Risky actions approved <b id="s-approved">0</b></div>
      <div class="stat">Risky actions blocked <b id="s-blocked">0</b></div>
      <div class="stat">Web searches <b id="s-web">0</b></div>
    </aside>
  </main>
  <footer>Read-only view. It only shows what the agent is doing. Approvals are typed in the terminal.</footer>
</div>
<script>
"use strict";
// Every piece of text from the agent is inserted with textContent, never innerHTML,
// because web results and model replies are untrusted.
let lastId = 0;
let currentTurn = 0;
const chat = document.getElementById("chat");
const approvalCards = {};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Shows **bold** and "* item" bullets without ever parsing HTML: text goes in as text nodes only.
function appendRich(parent, text) {
  const lines = String(text).split("\n");
  lines.forEach((line, i) => {
    if (i > 0) parent.appendChild(document.createTextNode("\n"));
    line = line.replace(/^(\s*)[*-]\s+/, "$1• ").replace(/^#{1,6}\s*/, "");
    const parts = line.split(/\*\*(.+?)\*\*/g);
    parts.forEach((part, j) => {
      if (!part) return;
      if (j % 2 === 1) parent.appendChild(el("b", "", part));
      else parent.appendChild(document.createTextNode(part.replace(/\*\*/g, "")));
    });
  });
}

function nearBottom() { return chat.scrollHeight - chat.scrollTop - chat.clientHeight < 120; }

function card(cls, icon, title, sub) {
  const c = el("div", "card " + cls);
  c.appendChild(el("div", "ic", icon));
  const body = el("div");
  body.appendChild(el("b", "", title));
  if (sub) body.appendChild(el("div", "sub", sub));
  c.appendChild(body);
  return c;
}

function render(e) {
  const empty = document.getElementById("empty");
  if (empty) empty.remove();
  let node = null;
  if (e.kind === "user") {
    node = el("div", "msg you");
    node.appendChild(el("div", "who", "You (voice)"));
    node.appendChild(document.createTextNode(e.text || ""));
  } else if (e.kind === "agent") {
    node = el("div", "msg agent");
    node.appendChild(el("div", "who", "Agent"));
    appendRich(node, e.text || "");
  } else if (e.kind === "tool") {
    node = card("tool", e.icon || "🛠️", e.title || "Using a tool", e.detail || "");
  } else if (e.kind === "approval") {
    node = el("div", "card approval");
    node.appendChild(el("div", "h", "⚠️ Waiting for your approval"));
    node.appendChild(el("div", "k", e.detail || ""));
    node.appendChild(el("div", "hint", "Type yes in the terminal to allow · anything else cancels"));
    approvalCards[e.approval_id] = node;
  } else if (e.kind === "approval_result") {
    const target = approvalCards[e.approval_id];
    if (target) {
      target.classList.add(e.allowed ? "allowed" : "blocked");
      target.querySelector(".h").textContent = e.allowed ? "✓ Allowed by you" : "✕ Cancelled by you";
      const hint = target.querySelector(".hint");
      if (hint) hint.remove();
    }
    return;
  } else if (e.kind === "session") {
    node = el("div", "session", e.text || "");
  } else {
    node = card("info", e.icon || "ℹ️", e.text || "");
  }
  const stick = nearBottom();
  chat.appendChild(node);
  if (stick) chat.scrollTop = chat.scrollHeight;
}

const STEP_TEXT = {
  user: e => "Heard you",
  tool: e => e.title || "Used a tool",
  approval: e => "Asked for your approval",
  approval_result: e => e.allowed ? "You allowed it" : "You cancelled it",
  agent: e => "Answered",
  info: e => e.step || null,
};
let stepsForTurn = [];

function renderSteps(status) {
  const box = document.getElementById("steps");
  box.textContent = "";
  if (!stepsForTurn.length) {
    box.appendChild(el("div", "step", "Waiting for you to speak"));
    return;
  }
  stepsForTurn.forEach(text => box.appendChild(el("div", "step done", "✓ " + text)));
  const nowText = {
    thinking: "⏳ Thinking", approval: "⏳ Waiting for typed approval",
    speaking: "🔊 Speaking the answer", listening: "🎙 Listening for your next question",
    calibrating: "⏳ Measuring room noise",
  }[status];
  if (nowText) box.appendChild(el("div", "step now", nowText));
}

function update(data) {
  if (data.oldest_id > lastId + 1 && lastId !== 0) {
    // Events were dropped while the page was away; start fresh to stay consistent.
    location.reload();
    return;
  }
  for (const e of data.events) {
    if (e.turn !== currentTurn && e.kind === "user") { currentTurn = e.turn; stepsForTurn = []; }
    render(e);
    const fn = STEP_TEXT[e.kind];
    if (fn && e.turn === currentTurn) { const t = fn(e); if (t) stepsForTurn.push(t); }
    lastId = e.id;
  }
  const pill = document.getElementById("pill");
  pill.className = "pill st-" + data.status;
  document.getElementById("pill-text").textContent = data.status_label;
  renderSteps(data.status);
  const s = data.stats;
  document.getElementById("s-tools").textContent = s.tools_used;
  document.getElementById("s-approved").textContent = s.approved;
  document.getElementById("s-blocked").textContent = s.blocked;
  document.getElementById("s-web").textContent =
    s.web_search_limit ? (s.web_searches + " / " + s.web_search_limit) : s.web_searches;
}

async function poll() {
  try {
    const r = await fetch("/events?after=" + lastId, { cache: "no-store" });
    if (r.ok) update(await r.json());
  } catch (err) {
    const pill = document.getElementById("pill");
    pill.className = "pill";
    document.getElementById("pill-text").textContent = "Agent not running";
  }
  setTimeout(poll, 500);
}
poll();
</script>
</body>
</html>
"""


def _demo():
    """Play a scripted conversation so the page can be checked without the agent."""
    url = start()
    if not url:
        return
    print("Demo running. Watch the browser. Press Ctrl+C to stop.")
    update_stats(web_search_limit=15)
    steps = [
        (1.5, lambda: (set_status("calibrating"), add_event("session", text="Session started"))),
        (1.5, lambda: set_status("listening")),
        (2.0, lambda: (add_event("user", text="Who is the prime minister of Bangladesh?"), set_status("thinking"))),
        (1.5, lambda: (add_event("tool", icon="🔎", title="Searching the live web",
                                 detail='"prime minister of Bangladesh" · results treated as untrusted'),
                       increment_stat("tools_used"), increment_stat("web_searches"))),
        (2.0, lambda: (add_event("agent", text="The prime minister of Bangladesh is Tarique Rahman, sworn in in February 2026. (BBC, Al Jazeera)"),
                       set_status("speaking"))),
        (3.0, lambda: set_status("listening")),
        (2.0, lambda: (add_event("user", text="Send an email saying the demo is working."), set_status("thinking"))),
        (1.5, lambda: (add_event("approval", approval_id=1,
                                 detail="Send an email to the pre-approved address\nSubject: The demo is working"),
                       set_status("approval"))),
        (4.0, lambda: (add_event("approval_result", approval_id=1, allowed=True), increment_stat("approved"),
                       set_status("thinking"))),
        (1.0, lambda: (add_event("tool", icon="✉️", title="Sending the email", detail="to the pre-approved address"),
                       increment_stat("tools_used"))),
        (1.5, lambda: (add_event("agent", text="Done. The email was sent."), set_status("speaking"))),
        (2.0, lambda: (add_event("user", text="Create a folder called demo in the sandbox."), set_status("thinking"))),
        (1.5, lambda: (add_event("approval", approval_id=2, detail="Create the folder \"demo\" in the sandbox"),
                       set_status("approval"))),
        (3.0, lambda: (add_event("approval_result", approval_id=2, allowed=False), increment_stat("blocked"),
                       add_event("agent", text="Okay, I did not create the folder."), set_status("speaking"))),
        (2.0, lambda: set_status("listening")),
        (3.0, lambda: (add_event("session", text="Session ended"), set_status("idle"))),
    ]
    try:
        for delay, action in steps:
            time.sleep(delay)
            action()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDemo stopped.")
    finally:
        stop()


if __name__ == "__main__":
    _demo()