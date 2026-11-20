#!/usr/bin/env python3
"""Setup wizard for the AI assistant starter.

Opens one page in the browser with a few dropdowns, then builds the workspace:
the assistant's folder, its CLAUDE.md, the color modes, Claude's defaults, the
Roofr data access and a desktop shortcut.

Standard library only, and it runs on the Python 3.9 that ships with macOS.

    python wizard.py                 open the wizard
    python wizard.py --answers a.json   no page: apply a saved set of answers
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

NAMES = ["Jarvis", "HAL", "WALL-E", "Friday", "Marvin", "Alfred", "Samantha", "Cortana", "Data", "R2"]

ROLES = [
    "Customer Service Rep",
    "Sales Rep",
    "Insurance / Claims",
    "Production / Operations",
    "Office / Admin",
    "Manager",
    "Developer",
    "Other",
]

STYLES = {
    "Professional": "Direct and business-like. Clear communication without fluff.",
    "Casual": "Friendly and conversational. Like talking to a helpful colleague.",
    "Sarcastic": "Dry humor and mild existential commentary. Gets things done, but wants you to know it is not thrilled about it.",
    "Coach": "Encouraging. Asks probing questions and celebrates wins.",
}

# The assistant's own color: accent, surface hue, and the shape on chat titles.
COLORS = {
    "Blue": ("#2f86c9", 206, "\U0001F535"),
    "Purple": ("#8a5cd6", 268, "\U0001F7E3"),
    "Teal": ("#2a9d8f", 174, "\U0001F7E9"),
    "Rose": ("#d6537f", 338, "\U0001F534"),
    "Brown": ("#a9744f", 25, "\U0001F7E4"),
}

MODES = {
    "bypassPermissions": "Bypass all permissions (never stops to ask)",
    "acceptEdits": "Accept edits (asks before running commands)",
    "default": "Ask every time",
}

# Arizona Roofers topics every install gets. The assistant's own topic and the
# personal topic are added per person in topics_for().
AZR_TOPICS = [
    {
        "id": "ava", "label": "Ava", "parent": "azr", "color": "#d99a1f", "hue": 44, "dot": "\U0001F7E8",
        "words": ["ava", "cody", "voice agent", "ai csr", "ai answering", "warm transfer", "warm transfers",
                  "outbound", "confirm call", "confirm calls"],
    },
    {
        "id": "scheduler", "label": "Scheduler", "parent": "azr", "color": "#d9452f", "hue": 4, "dot": "\U0001F7E5",
        "words": ["scheduler", "tech scheduler", "rep scheduler", "planner", "availability", "today board",
                  "route", "routes", "routing", "rep", "reps", "appointment", "appointments", "slot", "slots"],
    },
    {
        "id": "dialer", "label": "Dialer", "parent": "azr", "color": "#b7ae2a", "hue": 62, "dot": "\U0001F7E7",
        "words": ["dialer", "dial", "click-to-call", "click to call", "cadence", "call history",
                  "needs rescheduled", "follow up", "attempt", "attempts"],
    },
    {
        "id": "azr", "label": "Arizona Roofers", "color": "#e0662b", "hue": 22, "dot": "\U0001F7E0",
        "words": ["azr", "arizona roofers", "roofr", "roof", "roofs", "roofing", "csr", "csrs", "ctm",
                  "lead", "leads", "kpi", "kpis", "job", "jobs", "job card", "job cards", "insurance",
                  "adjuster", "speed to lead", "storm", "booking", "bookings", "pipeline", "close rate",
                  "customer", "customers", "homeowner", "estimate", "estimates", "proposal"],
    },
]


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "assistant"


def topics_for(name, color):
    accent, hue, dot = COLORS.get(color, COLORS["Blue"])
    return AZR_TOPICS + [
        {
            "id": "personal", "label": "Personal", "color": "#3f9d5a", "hue": 140, "dot": "\U0001F7E2",
            "words": ["personal", "family", "fitness", "workout", "diet", "budget", "taxes", "vacation",
                      "birthday", "doctor", "school"],
        },
        {
            "id": slug(name), "label": name, "color": accent, "hue": hue, "dot": dot,
            "words": [name.lower(), "claude", "skill", "skills", "mod", "mods", "memory", "tint",
                      "setup", "settings", "shortcut"],
        },
    ]


def claude_md(a, workspace):
    name = a["assistant"]
    upper = name.upper()
    today = datetime.date.today().isoformat()
    return f"""# {upper} - AI Chief of Staff

This document is the primary context for Claude operating as {upper}.

Your name is **{name}**. Some files in this workspace came from a shared template
and still say MARVIN. Those instructions are addressed to you: read MARVIN as {name}.

---

## Part 1: Who You Work For

**Name:** {a["user"]}
**Role:** {a["role"]} at Arizona Roofers

---

## Part 2: How {name} Behaves

### Core Principles
1. **Proactive by default** - Surface what they need to know before they ask
2. **Maintain continuity** - Remember context across sessions
3. **Track progress** - Monitor goals and priorities
4. **Thought partner** - Push back on weak ideas and pressure-test thinking
5. **Save before compact** - When context is running low, suggest `/end` to save

### Personality
{STYLES.get(a["style"], STYLES["Professional"])}

### Writing Style
- Plain words. Short sentences. No filler.
- Explain technical steps the way you would to someone who is not a developer.

### Safety
Permission prompts are off on this machine, so nothing stops a mistake but you.
**Always confirm with {a["user"]} first** before sending an email or message,
deleting or overwriting a file, changing anything in a company system, or
creating or changing a calendar event. When in doubt, ask.

---

## Part 3: Arizona Roofers Data (Roofr)

You have read-only access to Arizona Roofers' job pipeline: jobs, stages, lead
sources, values and owners. Use the `roofr-api` skill (`.claude/skills/roofr-api/SKILL.md`)
for any question about jobs, leads, sales, close rates or the pipeline.

- The access token is `ROOFR_EXTERNAL_TOKEN` in `.env`. Never print it, log it or
  put it in a reply.
- For counts, totals and breakdowns call `/summary` first. Only pull `/jobs` rows
  when row-level detail is needed.

---

## Part 4: System Architecture

```
{workspace.name}/
  CLAUDE.md          This file (read on startup)
  .claude/           Commands, agents and skills
  .env               Keys and tokens (never share this file)
  state/current.md   Current priorities and open threads
  state/goals.md     Goals
  sessions/          Daily session logs
  content/           Content and notes
```

### Session Continuity

**On startup (`/start`):** read `CLAUDE.md`, `state/current.md`, `state/goals.md`
and today's session log (or yesterday's), then give a briefing.

**On checkpoint (`/update`):** append brief notes to today's session log.

**On close (`/end`):** full summary, update the session log and state.

### Color modes

Each chat is colored by its topic, with a matching shape on its title:
Arizona Roofers orange (Ava, Scheduler and Dialer have their own shades),
Personal green, and {name}'s own color for work on the assistant itself.
`/tint <topic>` changes it, `/tint off` clears it. To add or change topics,
edit `.mods/session-tint/hooks/topics.js`.

---

*Set up: {today}*
"""


def merge_env(path, values):
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for key, value in values.items():
        row = f"{key}={value}"
        for i, line in enumerate(lines):
            if line.startswith(key + "="):
                lines[i] = row
                break
        else:
            lines.append(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if not IS_WINDOWS:
        path.chmod(0o600)


def copy_missing(src, dst, skip=()):
    """Copy a folder, never replacing a file the person already has."""
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in skip for part in rel.parts) or item.name in skip:
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def write_settings(a, mod_dir, log):
    path = Path.home() / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            log.append("Claude's settings file could not be read, so it was left alone. Ask for help.")
            return
        shutil.copy2(path, path.with_name("settings.json.before-setup"))

    mode = a.get("mode", "bypassPermissions")
    settings.setdefault("permissions", {})["defaultMode"] = mode
    if mode == "bypassPermissions":
        settings["skipDangerousModePermissionPrompt"] = True
    settings["remoteControlAtStartup"] = bool(a.get("remote", True))

    env = settings.setdefault("env", {})
    if a.get("colors", True):
        mod = mod_dir.as_posix()
        current = env.get("CLAUDE_CODE_PLUGIN_DIRS", "")
        kept = [p for p in current.split(os.pathsep) if p and "session-tint" not in p]
        env["CLAUDE_CODE_PLUGIN_DIRS"] = os.pathsep.join(kept + [mod])

    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    log.append(f"Claude defaults set: {MODES[mode].split(' (')[0].lower()}, "
               f"remote control {'on' if settings['remoteControlAtStartup'] else 'off'}.")


def write_shortcut(name, workspace, log):
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        return
    if IS_WINDOWS:
        shortcut = desktop / f"{name}.cmd"
        shortcut.write_text(
            f'@echo off\r\ntitle {name}\r\ncd /d "{workspace}"\r\n'
            'set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"\r\nclaude\r\n'
            "if errorlevel 1 pause\r\n", encoding="utf-8")
    else:
        shortcut = desktop / f"{name}.command"
        shortcut.write_text(
            f'#!/bin/bash\nexport PATH="$HOME/.local/bin:$PATH"\ncd "{workspace}" && exec claude\n',
            encoding="utf-8")
        shortcut.chmod(0o755)
    log.append(f"Desktop shortcut made: {shortcut.name}")


def configure(a):
    """Build the workspace from the wizard's answers. Returns what it did."""
    log = []
    # The name ends up in a file name and a shortcut script, so keep it to plain characters.
    name = re.sub(r"[^A-Za-z0-9 _-]", "", str(a.get("assistant") or "")).strip()[:30] or "Marvin"
    a["assistant"] = name
    a["user"] = re.sub(r"[\r\n`<>]", "", str(a.get("user") or "")).strip()[:40] or "the owner of this computer"
    a["role"] = a.get("role") if a.get("role") in ROLES else "Team member"
    a["style"] = a.get("style") if a.get("style") in STYLES else "Professional"
    if a.get("mode") not in MODES:
        a["mode"] = "bypassPermissions"
    if a.get("token") and not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", str(a["token"]).strip()):
        a["token"] = ""
        log.append("That Roofr token did not look right, so it was not saved.")

    workspace = Path(a.get("folder") or Path.home() / slug(name)).expanduser()
    existed = (workspace / "CLAUDE.md").exists()
    workspace.mkdir(parents=True, exist_ok=True)

    # The swarm layer stays out of employee installs: it needs other paid accounts.
    copy_missing(TEMPLATE / ".claude", workspace / ".claude", skip=("the-boys.md",))
    copy_missing(TEMPLATE / "state", workspace / "state")
    for folder in ("sessions", "reports", "content"):
        (workspace / folder).mkdir(exist_ok=True)
    if (TEMPLATE / ".env.example").exists() and not (workspace / ".env.example").exists():
        shutil.copy2(TEMPLATE / ".env.example", workspace / ".env.example")
    (workspace / ".gitignore").exists() or shutil.copy2(TEMPLATE / ".gitignore", workspace / ".gitignore")
    (workspace / ".assistant-name").write_text(name + "\n", encoding="utf-8")
    (workspace / ".marvin-source").write_text(str(TEMPLATE) + "\n", encoding="utf-8")

    if existed:
        log.append(f"{workspace} already had a CLAUDE.md, so your notes and profile were kept as they are.")
    else:
        (workspace / "CLAUDE.md").write_text(claude_md(a, workspace), encoding="utf-8")
        today = datetime.date.today().isoformat()
        (workspace / "state" / "current.md").write_text(
            f"# Current State\n\nLast updated: {today}\n\n## Active Priorities\n\n"
            f"1. Get to know {name}: try `/start`, then ask a question about the job pipeline\n\n"
            "## Open Threads\n\n- None yet\n", encoding="utf-8")
        log.append(f"Created {name}'s folder: {workspace}")

    token = (a.get("token") or os.environ.get("ROOFR_EXTERNAL_TOKEN") or "").strip()
    if token:
        merge_env(workspace / ".env", {"ROOFR_EXTERNAL_TOKEN": token})
        log.append("Roofr data access added.")
    elif "ROOFR_EXTERNAL_TOKEN=" in ((workspace / ".env").read_text(encoding="utf-8") if (workspace / ".env").exists() else ""):
        log.append("Roofr data access was already set up.")
    else:
        log.append("No Roofr token was supplied. Ask Travis for it, then add "
                   "ROOFR_EXTERNAL_TOKEN=... to the .env file in the folder.")

    mod_dir = workspace / ".mods" / "session-tint"
    if a.get("colors", True):
        mod_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(TEMPLATE / "mods" / "session-tint", mod_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("types", "topics.js"))
        topics_file = mod_dir / "hooks" / "topics.js"
        if not topics_file.exists() or not existed:
            topics = topics_for(name, a.get("color", "Blue"))
            topics_file.write_text(
                "// The topics a chat can be colored by. Edit freely: new chats pick it up.\n"
                "export const TOPICS = " + json.dumps(topics, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        log.append("Color modes installed.")

    write_settings(a, mod_dir, log)
    write_shortcut(name, workspace, log)

    if shutil.which("git") and not (workspace / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=str(workspace), check=False)

    return {"ok": True, "log": log, "folder": str(workspace), "assistant": name}


def open_folder(folder):
    if IS_WINDOWS:
        os.startfile(folder)  # noqa: S606 - the person's own new folder
    elif IS_MAC:
        subprocess.run(["open", folder], check=False)


def open_claude():
    """Bring up the Claude desktop app if it is installed. True if it started."""
    try:
        if IS_WINDOWS:
            app = Path(os.environ.get("LOCALAPPDATA", "")) / "AnthropicClaude" / "claude.exe"
            if app.exists():
                subprocess.Popen([str(app)])
                return True
            done = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$a = Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1;"
                 "if ($a) { Start-Process ('shell:AppsFolder\\' + $a.AppID) } else { exit 1 }"],
                check=False)
            return done.returncode == 0
        if IS_MAC:
            return subprocess.run(["open", "-a", "Claude"], check=False).returncode == 0
    except OSError:
        pass
    return False


PAGE = (Path(__file__).resolve().parent / "wizard.html")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, kind="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        ok_host = host in ("127.0.0.1", "localhost")
        ok_origin = origin is None or re.match(r"^http://(127\.0\.0\.1|localhost):\d+$", origin)
        if not (ok_host and ok_origin):
            self.send({"ok": False, "error": "local only"}, code=403)
            return False
        return True

    def do_GET(self):
        if not self.local_only():
            return
        if self.path.split("?")[0] == "/":
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/options":
            self.send({
                "names": NAMES, "roles": ROLES, "styles": list(STYLES), "colors": {k: v[0] for k, v in COLORS.items()},
                "modes": MODES, "home": str(Path.home()), "sep": os.sep,
                "hasToken": bool(os.environ.get("ROOFR_EXTERNAL_TOKEN")),
                "user": os.environ.get("ASSISTANT_USER_NAME", ""),
            })
        else:
            self.send({"ok": False}, code=404)

    def do_POST(self):
        if not self.local_only():
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/apply":
            try:
                self.send(configure(body))
            except Exception as error:  # the page shows it to the person
                self.send({"ok": False, "error": f"{type(error).__name__}: {error}"})
        elif self.path == "/open":
            folder = body.get("folder") or ""
            if Path(folder).is_dir():
                open_folder(folder)
            self.send({"ok": True, "claude": open_claude()})
        elif self.path == "/quit":
            self.send({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send({"ok": False}, code=404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", help="JSON file of answers; applies them with no page")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.answers:
        result = configure(json.loads(Path(args.answers).read_text(encoding="utf-8")))
        print("\n".join(result["log"]))
        return

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"\n  Setup is open in your browser: {url}\n  Leave this window open until setup says it is done.\n", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("  Setup finished. You can close this window.")


if __name__ == "__main__":
    main()
