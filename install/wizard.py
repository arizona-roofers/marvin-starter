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
import base64
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

# Taken out of the environment so the apps this wizard opens do not inherit it.
INSTALLER_TOKEN = os.environ.pop("ROOFR_EXTERNAL_TOKEN", "")


def install_file():
    """The install file this setup came from, if it can be found.

    When Windows or macOS refuses to run the file, people start setup by pasting a
    line instead. The file is still sitting in Downloads, and it can be read even
    though it cannot be run, so the token and the knowledge pack still come along.
    """
    named = os.environ.get("ASSISTANT_INSTALL_FILE", "")
    if named and Path(named).is_file():
        return Path(named)
    found = []
    for folder in (Path.home() / "Downloads", Path.home() / "Desktop"):
        if folder.is_dir():
            found += [f for f in folder.glob("Install Assistant*") if f.suffix.lower() in (".cmd", ".command") and f.is_file()]
            found += [f for f in folder.glob("Install Assistant*/Install Assistant*.command") if f.is_file()]
    return max(found, key=lambda f: f.stat().st_mtime) if found else None


def _token_from_install_file():
    source = install_file()
    if source is None:
        return ""
    try:
        head = source.read_text(encoding="utf-8", errors="ignore")[:4000]
    except OSError:
        return ""
    match = re.search(r"ROOFR_EXTERNAL_TOKEN=['\"]?([A-Za-z0-9_\-]{20,200})", head)
    return match.group(1) if match else ""


if not INSTALLER_TOKEN:
    INSTALLER_TOKEN = _token_from_install_file()


def _install_setting(name, allowed):
    """A setting the install file carries: from the environment, or read out of the file on a later run."""
    named = os.environ.get(name, "")
    if not named:
        source = install_file()
        try:
            head = source.read_text(encoding="utf-8", errors="ignore")[:4000] if source else ""
        except OSError:
            head = ""
        match = re.search(name + r"=['\"]?([" + allowed + r"]{1,60})", head)
        named = match.group(1) if match else ""
    return re.sub(r"[^" + allowed + r"]", "", named).strip()[:60]


def _contact():
    """Who to ask for help. The install file names them; nobody is named in this repository."""
    return _install_setting("ASSISTANT_HELP_CONTACT", "A-Za-z0-9 .@-") or "your manager"


CONTACT = _contact()

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

# What each role gets: what the assistant focuses on, which SOPs it reads first,
# the example prompts in START-HERE.md, and the model Claude starts on.
KITS = {
    "Customer Service Rep": {
        "focus": "Answering and booking calls. Speed to lead comes first: answer fast, book the appointment.",
        "sops": ["booking", "intake-calls", "cancellations", "escalations"],
        "model": "sonnet",
        "try": [
            "Should I book this? Tile roof, about 12 years old, leak over the garage, in Mesa.",
            "A homeowner wants to cancel tomorrow's appointment. What do I say?",
            "When did this number last call, and what did they want? (give the number)",
            "How many jobs came in this week, by lead source?",
        ],
    },
    "Sales Rep": {
        "focus": "Running appointments and closing jobs, and keeping their own pipeline moving.",
        "sops": ["booking", "insurance-pipeline"],
        "model": "sonnet",
        "try": [
            "Show me my open jobs and what stage each one is in.",
            "Which of my jobs have sat in the same stage the longest?",
            "What is my close rate this month compared to last month?",
            "Draft a follow-up text for a homeowner who said they want to think about it.",
        ],
    },
    "Insurance / Claims": {
        "focus": "Moving insurance jobs from signed contract to close-out without anything stalling.",
        "sops": ["insurance-pipeline", "escalations"],
        "model": "sonnet",
        "try": [
            "Which insurance jobs have gone longest without a stage change?",
            "What is the next step once the adjuster has approved a claim?",
            "Draft an update for a homeowner on where their claim stands. (paste the details)",
            "How many insurance jobs did we win this quarter?",
        ],
    },
    "Production / Operations": {
        "focus": "Getting sold jobs built: scheduling, routing and keeping jobs from sitting.",
        "sops": ["scheduler", "insurance-pipeline"],
        "model": "sonnet",
        "try": [
            "How many jobs are in progress right now, by workflow?",
            "Which in-progress jobs have gone longest without a stage change?",
            "How does the scheduler decide which rep gets an appointment?",
            "Summarize this week's won jobs.",
        ],
    },
    "Office / Admin": {
        "focus": "Keeping the office running: customers, paperwork and follow-ups.",
        "sops": ["escalations", "cancellations"],
        "model": "sonnet",
        "try": [
            "An existing customer is upset about a delay. How should I handle the call?",
            "Help me write a reply to this customer. (paste the message)",
            "Export this month's won jobs to a spreadsheet.",
            "Remind me what each tool is for.",
        ],
    },
    "Manager": {
        "focus": "Running a team by the numbers: what is working, what is stuck, who needs help.",
        "sops": ["booking", "escalations", "insurance-pipeline", "scheduler"],
        "model": "sonnet",
        "try": [
            "Close rate by lead source this quarter.",
            "Compare this month to last month: jobs won, total value and close rate.",
            "Which owner has the most jobs in progress, and which are oldest?",
            "What does the Booking SOP say about one-leggers?",
        ],
    },
    "Developer": {
        "focus": "Building and maintaining the company's tools.",
        "sops": ["scheduler"],
        "model": "opus",
        "try": [
            "Walk me through the Roofr External API schema.",
            "Pull last week's jobs as CSV and check the columns.",
            "/new-project to scaffold a tool.",
            "How does the scheduler decide which rep gets an appointment?",
        ],
    },
}
DEFAULT_KIT = {
    "focus": "Helping with day-to-day work at Arizona Roofers.",
    "sops": ["booking", "escalations"],
    "model": "sonnet",
    "try": [
        "How many jobs did we win last month?",
        "What is our close rate by lead source this year?",
        "Help me write a reply to this customer. (paste the message)",
        "Remind me what each tool is for.",
    ],
}

SOP_TITLES = {
    "booking": "who to book and when to dispatch",
    "intake-calls": "the CSR call script",
    "cancellations": "when a homeowner calls to cancel",
    "escalations": "an existing customer with a problem",
    "insurance-pipeline": "insurance jobs, signed contract to close-out",
    "scheduler": "how appointments get assigned and routed",
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


TAKEN_IDS = {t["id"] for t in AZR_TOPICS} | {"personal", "default", "auto", "off"}


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
            "id": slug(name) if slug(name) not in TAKEN_IDS else "assistant-" + slug(name), "label": name, "color": accent, "hue": hue, "dot": dot,
            "words": [name.lower(), "claude", "skill", "skills", "mod", "mods", "memory", "tint",
                      "setup", "settings", "shortcut"],
        },
    ]


def company_section(a, workspace):
    """The part of CLAUDE.md that points at the knowledge pack, if setup brought one."""
    pack = workspace / "company"
    if not (pack / "README.md").exists():
        return ""
    kit = KITS.get(a["role"], DEFAULT_KIT)
    first = [f"- `company/sops/{sop}.md`: {SOP_TITLES[sop]}" for sop in kit["sops"]
             if (pack / "sops" / f"{sop}.md").exists()]
    lines = [
        "## Arizona Roofers Knowledge",
        "",
        "The `company/` folder holds the company facts and the SOPs. **Read",
        "`company/README.md` before answering any question about how Arizona Roofers",
        "works**, and follow its rules: quote the SOP, never invent a price or a policy.",
        "",
    ]
    if first:
        lines += [f"For a {a['role']}, these come up most:", ""] + first + [""]
    if (workspace / ".claude" / "skills" / "roofr-changes" / "SKILL.md").exists():
        lines += [
            "### Changing things in Roofr",
            "",
            "Use the `roofr-changes` skill. Changes are made in the person's own Chrome, signed",
            "in as them, so Roofr's own permissions decide what is allowed. Say what you are",
            "about to change and wait for a yes, every time. The data API above is read-only.",
            "",
        ]
    if (workspace / ".claude" / "skills" / "call-lookup" / "SKILL.md").exists():
        lines += [
            "### Phone calls",
            "",
            "Use the `call-lookup` skill for who called, when, who took it, and what was said.",
            "It is read-only and uses the same token as the Roofr data.",
            "",
        ]
    if (pack / "travis.md").exists():
        # The opening paragraph of the bio goes here, so it is in mind in every chat.
        bio = (pack / "travis.md").read_text(encoding="utf-8")
        opening = next((part.strip() for part in bio.split("\n\n")
                        if part.strip() and not part.lstrip().startswith("#")), "")
        lines += ["### Who set this up", "", opening, "",
                  "Send people to him when the assistant is broken or confusing, when an SOP looks",
                  "out of date, or when they need access to something. More in `company/travis.md`.", ""]
    return "\n".join(lines) + "\n---\n\n"


def claude_md(a, workspace):
    name = a["assistant"]
    upper = name.upper()
    today = datetime.date.today().isoformat()
    kit = KITS.get(a["role"], DEFAULT_KIT)
    roofr = (f"\n**Name in Roofr:** {a['roofr']}. Jobs owned by this name are \"my jobs\": use it as\n"
             f"the `owner` filter when {a['user']} asks about their own jobs, pipeline or numbers.\n"
             if a.get("roofr") else "")
    return f"""# {upper} - AI Chief of Staff

This document is the primary context for Claude operating as {upper}.

Your name is **{name}**. Some files in this workspace came from a shared template
and still say MARVIN. Those instructions are addressed to you: read MARVIN as {name}.

---

## Part 1: Who You Work For

**Name:** {a["user"]}
**Role:** {a["role"]} at Arizona Roofers
**Their work:** {kit["focus"]}
{roofr}
---

{company_section(a, workspace)}
## Part 2: How {name} Behaves

### Core Principles
1. **Proactive by default** - Surface what they need to know before they ask
2. **Maintain continuity** - Remember context across sessions
3. **Track progress** - Monitor goals and priorities
4. **Thought partner** - Push back on weak ideas and pressure-test thinking
5. **Save before compact** - When context is running low, suggest `/save` to save

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

**On close (`/save`):** full summary, update the session log and state.

### Slash commands

| Command | What it does |
|---------|--------------|
| `/start` | Start the day: reads the notes and gives a briefing |
| `/save` | Save everything when done, so the next chat picks up from here |
| `/compact` | Built in: shrinks a long chat to a summary and carries on |
| `/clear` | Built in: wipes the current chat. Suggest `/save` first |
| `/update` | Quick checkpoint in the middle of work |
| `/help` | List every command and connected tool |
| `/report` | Weekly summary of the work done |
| `/status` | Check that everything is connected and healthy |
| `/tint <topic>` | Change this chat's color |

If {a["user"]} seems unsure what to type, point them to `START-HERE.md`.

### Color modes

Each chat is colored by its topic, with a matching shape on its title:
Arizona Roofers orange (Ava, Scheduler and Dialer have their own shades),
Personal green, and {name}'s own color for work on the assistant itself.
`/tint <topic>` changes it, `/tint off` clears it. To add or change topics,
edit `.mods/session-tint/hooks/topics.js`.

### Other assistants

If you chose them in setup, Gemini (Antigravity), Codex or Grok run in a terminal on
this same folder: double-click the matching `Open ...` file in this folder. Each reads
the same notes through `AGENTS.md` (Gemini through `GEMINI.md`) and asks you to sign in
with its own account the first time.

### Usage bar

Above the message box, three meters show how full this chat is (Context) and
how much of the Session and Week limits is used, with when each resets. They
turn amber at 60% and red at 85%. When Context is high, `/compact` or `/save`
and start a new chat.

---

*Set up: {today}*
"""


def start_here(name, role=""):
    examples = "\n".join(f'- "{line}"' for line in KITS.get(role, DEFAULT_KIT)["try"])
    return f"""# Start here

{name} is your AI assistant. You talk to it in plain English. The commands below
are shortcuts: type one in the chat box and press Enter.

## The four commands

| Type this | When | What happens |
|-----------|------|--------------|
| `/start` | First thing, in a new chat | {name} reads its notes and tells you where things stand |
| `/save` | When you are done | {name} writes a summary and saves it, so tomorrow's chat picks up from here |
| `/compact` | When a chat has got long | Shrinks the chat to a summary, so {name} stays quick and keeps going |
| `/clear` | When you want a fresh start | Wipes the current chat. Run `/save` first if you want it remembered |

Think of `/start` and `/save` as bookends. Everything in between is just conversation.

## Handy extras

| Type this | What happens |
|-----------|--------------|
| `/update` | A quick checkpoint in the middle of work, so nothing is lost |
| `/help` | Lists every command and what {name} is connected to |
| `/report` | A summary of your week |
| `/status` | Checks that everything is connected and working |
| `/tint azr` | Colors this chat. Try `azr`, `personal`, `ava`, `scheduler`, `dialer`, or `off` |

## Things to try

{examples}
- "Move the Lopez job to Needs Rescheduled." ({name} tells you what it will change and waits for your yes)
- "Remember that I work Tuesday to Saturday."

## Good to know

- **It remembers.** Tell it something once and it writes it down.
- **It asks before it sends.** {name} will check with you before sending a message,
  deleting anything, or changing a company system.
- **Colors mean topics.** Orange is Arizona Roofers, green is personal. The shape on
  a chat's title in the sidebar matches.
- **Your phone works too.** Open the Claude app on your phone to pick up any chat.
- **Stuck?** Type "I'm stuck" and say what you were trying to do, or send {CONTACT} a screenshot.
"""


def pack_bytes():
    """The company knowledge pack as zip bytes, or None. It rides inside the install file."""
    source = install_file()
    if source is None:
        return None
    chunks = []
    try:
        with open(source, encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = re.match(r"^(?:::|#)PACK:([A-Za-z0-9+/=]+)\s*$", line)
                if match:
                    chunks.append(match.group(1))
        return base64.b64decode("".join(chunks)) if chunks else None
    except (OSError, ValueError):
        return None


def load_pack(workspace, log):
    """Put the company knowledge pack in <workspace>/company, replacing the last copy."""
    target = workspace / "company"
    folder = os.environ.get("ASSISTANT_PACK_DIR", "")
    files = {}
    if folder and Path(folder).is_dir():
        for item in Path(folder).rglob("*.md"):
            files[item.relative_to(folder).as_posix()] = item.read_bytes()
    else:
        data = pack_bytes()
        if data is None:
            return
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as pack:
                for info in pack.infolist():
                    files[info.filename] = pack.read(info)
        except (zipfile.BadZipFile, OSError):
            log.append("The company knowledge pack in the install file could not be read, so it was skipped.")
            return
    written = 0
    for name, content in files.items():
        # Only plain notes. skills/<name>/SKILL.md becomes a skill; the rest goes in company/.
        skill = re.fullmatch(r"skills/([A-Za-z0-9_-]+)/SKILL\.md", name)
        if skill:
            dest = workspace / ".claude" / "skills" / skill.group(1) / "SKILL.md"
        elif re.fullmatch(r"(?:[A-Za-z0-9_-]+/)?[A-Za-z0-9_-]+\.md", name) and not name.startswith("skills/"):
            dest = target / name
        else:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        written += 1
    if written:
        log.append(f"Company knowledge added: {written} files of facts and SOPs.")


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
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError:
            settings = None
        if not isinstance(settings, dict):
            log.append("Claude's settings file could not be read, so it was left alone. Ask for help.")
            return
        backup = path.with_name("settings.json.before-setup")
        if not backup.exists():  # keep the true original across re-runs
            shutil.copy2(path, backup)
    if not isinstance(settings.get("permissions", {}), dict) or not isinstance(settings.get("env", {}), dict):
        log.append("Claude's settings file has an unexpected shape, so it was left alone. Ask for help.")
        return

    mode = a.get("mode", "bypassPermissions")
    settings.setdefault("permissions", {})["defaultMode"] = mode
    if mode == "bypassPermissions":
        settings["skipDangerousModePermissionPrompt"] = True
    settings["remoteControlAtStartup"] = bool(a.get("remote", True))
    if settings["remoteControlAtStartup"]:
        settings.setdefault("agentPushNotifEnabled", True)  # phone alert when a task finishes
    settings.setdefault("cleanupPeriodDays", 3650)  # keep old chats; the default deletes them after 30 days
    settings.setdefault("voiceEnabled", True)
    settings.setdefault("model", KITS.get(a.get("role"), DEFAULT_KIT)["model"])

    env = settings.setdefault("env", {})
    if a.get("colors", True):
        mod = mod_dir.as_posix()
        current = env.get("CLAUDE_CODE_PLUGIN_DIRS", "")
        kept = [p for p in current.split(os.pathsep) if p and "session-tint" not in p]
        env["CLAUDE_CODE_PLUGIN_DIRS"] = os.pathsep.join(kept + [mod])

    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    log.append(f"Claude defaults set: {MODES[mode].split(' (')[0].lower()}, "
               f"remote control {'on' if settings['remoteControlAtStartup'] else 'off'}.")


def desktop_folder():
    """The person's Desktop. On a work PC, OneDrive often moves it."""
    candidates = [Path.home() / "Desktop"]
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            candidates.insert(0, Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0])))
        except OSError:
            pass
        candidates += sorted(Path.home().glob("OneDrive*/Desktop"))
    for folder in candidates:
        if folder.is_dir():
            return folder
    return None


def write_shortcut(name, workspace, log):
    desktop = desktop_folder()
    if desktop is None:
        log.append("No Desktop folder was found, so no shortcut was made. Open the folder from the Claude app instead.")
        return
    if IS_WINDOWS:
        shortcut = desktop / f"{name}.cmd"
        lines = ["@echo off", "chcp 65001 >nul", f"title {name}", f'cd /d "{workspace}"',
                 'set "PATH=%USERPROFILE%\\.local\\bin;%PATH%"', "claude --desktop || claude",
                 "if errorlevel 1 pause", ""]
        shortcut.write_bytes("\r\n".join(lines).encode("utf-8"))
    else:
        shortcut = desktop / f"{name}.command"
        shortcut.write_text(
            f'#!/bin/bash\nexport PATH="$HOME/.local/bin:$PATH"\ncd "{workspace}" && (claude --desktop || exec claude)\n',
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
    a["roofr"] = re.sub(r"[^A-Za-z0-9 .'-]", "", str(a.get("roofr") or "")).strip()[:60]
    a["style"] = a.get("style") if a.get("style") in STYLES else "Professional"
    if a.get("mode") not in MODES:
        a["mode"] = "bypassPermissions"
    if a.get("token") and not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", str(a["token"]).strip()):
        a["token"] = ""
        log.append("That Roofr token did not look right, so it was not saved.")

    # The folder is always ~/<name>: a path from outside would end up inside the shortcut script.
    folder_name = slug(name)
    if re.fullmatch(r"con|prn|aux|nul|com\d|lpt\d", folder_name):
        folder_name += "-assistant"
    workspace = Path.home() / folder_name
    if workspace.exists() and any(workspace.iterdir()) and not (workspace / ".assistant-name").exists():
        raise ValueError(f"You already have a folder called {workspace.name}. Pick a different name.")
    existed = (workspace / "CLAUDE.md").exists()
    workspace.mkdir(parents=True, exist_ok=True)

    # The swarm layer stays out of employee installs: it needs other paid accounts.
    skip = () if a["role"] == "Developer" else ("the-boys.md",)
    copy_missing(TEMPLATE / ".claude", workspace / ".claude", skip=skip)
    copy_missing(TEMPLATE / "state", workspace / "state")
    for folder in ("sessions", "reports", "content"):
        (workspace / folder).mkdir(exist_ok=True)
    if (TEMPLATE / ".env.example").exists() and not (workspace / ".env.example").exists():
        shutil.copy2(TEMPLATE / ".env.example", workspace / ".env.example")
    (workspace / ".gitignore").exists() or shutil.copy2(TEMPLATE / ".gitignore", workspace / ".gitignore")
    (workspace / ".assistant-name").write_text(name + "\n", encoding="utf-8")
    (workspace / ".marvin-source").write_text(str(TEMPLATE) + "\n", encoding="utf-8")

    load_pack(workspace, log)

    if not (workspace / "START-HERE.md").exists():
        (workspace / "START-HERE.md").write_text(start_here(name, a["role"]), encoding="utf-8")

    if existed:
        log.append(f"{workspace} already had a CLAUDE.md, so your notes and profile were kept as they are.")
        section = company_section(a, workspace)
        current = (workspace / "CLAUDE.md").read_text(encoding="utf-8")
        if section and "company/README.md" not in current:  # add the pointer, change nothing else
            (workspace / "CLAUDE.md").write_text(current.rstrip("\n") + "\n\n---\n\n" + section, encoding="utf-8")
    else:
        (workspace / "CLAUDE.md").write_text(claude_md(a, workspace), encoding="utf-8")
        today = datetime.date.today().isoformat()
        (workspace / "state" / "current.md").write_text(
            f"# Current State\n\nLast updated: {today}\n\n## Active Priorities\n\n"
            f"1. Get to know {name}: try `/start`, then ask a question about the job pipeline\n\n"
            "## Open Threads\n\n- None yet\n", encoding="utf-8")
        log.append(f"Created {name}'s folder: {workspace}")

    # A token from the install file wins on a re-run: that is how a new token reaches people.
    token = (a.get("token") or INSTALLER_TOKEN or "").strip()
    if token:
        merge_env(workspace / ".env", {"ROOFR_EXTERNAL_TOKEN": token})
        log.append("Roofr data access added.")
    elif "ROOFR_EXTERNAL_TOKEN=" in ((workspace / ".env").read_text(encoding="utf-8") if (workspace / ".env").exists() else ""):
        log.append("Roofr data access was already set up.")
    else:
        log.append(f"No Roofr token was supplied. Ask {CONTACT} for it, then add "
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
    extras = chosen_extras(a)
    write_extras(a, workspace, name, extras, log)
    if not os.environ.get("ASSISTANT_SKIP_INSTALLS"):
        for tool in extras:
            install_extra(tool)
    try:
        write_shortcut(name, workspace, log)
    except OSError:
        log.append("The desktop shortcut could not be made. Open the folder from the Claude app instead.")

    if a.get("chrome", True) and not os.environ.get("ASSISTANT_SKIP_CHROME"):
        offer_extension(log)

    missing = missing_apps()
    if missing:
        log.append("Still to install: " + "; ".join(missing) + ".")

    if shutil.which("git") and not (workspace / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=str(workspace), check=False)

    return {"ok": True, "log": log, "folder": str(workspace), "assistant": name,
            "tools": [{"id": t, "label": EXTRAS[t]["label"], "account": EXTRAS[t]["account"]} for t in extras],
            "user": a["user"] if a["user"] != "the owner of this computer" else "",
            "try": KITS.get(a["role"], DEFAULT_KIT)["try"][:3]}


def missing_apps():
    """Apps the install step could not put on this machine, with where to get them."""
    if IS_WINDOWS:
        has_chrome = any((Path(os.environ.get(v, "")) / "Google" / "Chrome" / "Application" / "chrome.exe").exists()
                         for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
    elif IS_MAC:
        has_chrome = Path("/Applications/Google Chrome.app").exists()
    else:
        return []
    has_claude = claude_app_installed()
    missing = []
    if not has_claude:
        missing.append("the Claude app (claude.ai/download)")
    if not has_chrome:
        missing.append("Google Chrome (google.com/chrome)")
    return missing


# Anthropic's Claude in Chrome extension, as listed on the Chrome Web Store.
CLAUDE_EXTENSION = "fcoeoabgfenejglbffodgkkbkcdhcgfn"
WEB_STORE_UPDATES = "https://clients2.google.com/service/update2/crx"

# The only pages the setup page may ask Chrome to open.
CHROME_PAGES = {
    "google": "https://accounts.google.com/",
    "extension": "https://chromewebstore.google.com/detail/claude/" + CLAUDE_EXTENSION,
    "claude": "https://claude.ai/login",
    "github-device": "https://github.com/login/device",
    "github-signup": "https://github.com/signup",
    "claude-download": "https://claude.ai/download",
    "connectors": "https://claude.ai/settings/connectors",
}


def offer_extension(log):
    """Ask Chrome to offer Claude in Chrome the next time it starts.

    This is Chrome's own "external extension" route. Chrome shows the person a
    box to turn the extension on; nothing is installed behind their back.
    """
    try:
        if IS_WINDOWS:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\Extensions" + "\\" + CLAUDE_EXTENSION)
            winreg.SetValueEx(key, "update_url", 0, winreg.REG_SZ, WEB_STORE_UPDATES)
            winreg.CloseKey(key)
        elif IS_MAC:
            folder = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "External Extensions"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (CLAUDE_EXTENSION + ".json")).write_text(
                json.dumps({"external_update_url": WEB_STORE_UPDATES}) + "\n", encoding="utf-8")
        else:
            return
        log.append("Chrome will offer the Claude extension the next time it opens.")
    except OSError:
        pass  # the setup page's own button covers it


def chrome_path():
    if IS_WINDOWS:
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            exe = Path(os.environ.get(var, "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if exe.exists():
                return str(exe)
    return None


def open_in_chrome(page):
    """Open one of CHROME_PAGES in Chrome (the default browser if Chrome is missing)."""
    url = CHROME_PAGES.get(page)
    if url is None:
        return False
    try:
        if IS_WINDOWS and chrome_path():
            subprocess.Popen([chrome_path(), url])
            return True
        if IS_MAC and subprocess.run(["open", "-a", "Google Chrome", url], check=False).returncode == 0:
            return True
    except OSError:
        pass
    webbrowser.open(url)
    return False


# --- GitHub (optional): sign in and keep a private backup of the workspace ---------

GITHUB = {"state": "none", "code": "", "user": "", "error": ""}


GH_TOOL = {"tried": False}


def gh_path():
    local = Path.home() / ".local" / "bin" / ("gh.exe" if IS_WINDOWS else "gh")
    return shutil.which("gh") or (str(local) if local.exists() else None)


def ensure_gh():
    """Put GitHub's own command-line tool in ~/.local/bin if this computer has none."""
    if gh_path() or GH_TOOL["tried"]:
        return
    GH_TOOL["tried"] = True
    import platform
    import tempfile
    import urllib.request
    arm = platform.machine().lower() in ("arm64", "aarch64")
    want = ("macos_arm64.zip" if arm else "macos_amd64.zip") if IS_MAC else (
        "windows_arm64.zip" if arm else "windows_amd64.zip") if IS_WINDOWS else None
    if want is None:
        return
    work = Path(tempfile.mkdtemp(prefix="gh-tool-"))
    try:
        request = urllib.request.Request("https://api.github.com/repos/cli/cli/releases/latest",
                                         headers={"User-Agent": "assistant-setup", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=30) as reply:
            assets = json.loads(reply.read()).get("assets", [])
        url = next((a["browser_download_url"] for a in assets if a.get("name", "").lower().endswith(want)), None)
        if not url or not url.startswith("https://github.com/cli/cli/releases/download/"):
            return
        _download(url, work / "gh.zip")
        with zipfile.ZipFile(work / "gh.zip") as archive:
            name = next(n for n in archive.namelist() if n.endswith("bin/gh.exe" if IS_WINDOWS else "bin/gh"))
            target = Path.home() / ".local" / "bin" / Path(name).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
            if not IS_WINDOWS:
                target.chmod(0o755)
    except Exception:  # the page tells the person this step has to wait
        pass
    finally:
        shutil.rmtree(work, ignore_errors=True)


def gh(*args, cwd=None, timeout=60):
    """Run the GitHub tool. Returns (worked, output)."""
    exe = gh_path()
    if exe is None:
        return False, "GitHub tool not installed"
    try:
        done = subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                              stdin=subprocess.DEVNULL)
        return done.returncode == 0, (done.stdout + done.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)


def github_user():
    worked, out = gh("api", "user", "--jq", ".login + \" \" + (.id|tostring)")
    return out.split() if worked and len(out.split()) == 2 else None


def github_refresh():
    """Notice a sign-in that has finished, and point git at it."""
    if GITHUB["state"] == "connected":
        return
    found = github_user()
    if found is None:
        return
    login, user_id = found
    GITHUB.update(state="connected", user=login, code="", error="")
    gh("auth", "setup-git")
    git = shutil.which("git")
    if git:
        for key, value in (("user.name", login), ("user.email", f"{user_id}+{login}@users.noreply.github.com")):
            has = subprocess.run([git, "config", "--global", key], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if not has.stdout.strip():
                subprocess.run([git, "config", "--global", key, value], check=False)


def github_connect():
    """Start GitHub's sign-in: it gives a short code to type on a GitHub page."""
    github_refresh()
    if GITHUB["state"] in ("connected", "waiting"):
        return
    exe = gh_path()
    if exe is None:
        GITHUB.update(state="none", error="The GitHub tool is not installed on this computer.")
        return
    try:
        proc = subprocess.Popen(
            [exe, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web",
             "--scopes", "repo"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace")
    except OSError as error:
        GITHUB.update(state="none", error=str(error))
        return
    GITHUB.update(state="waiting", code="", error="")

    def watch():
        for line in proc.stdout:
            match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", line)
            if match and not GITHUB["code"]:
                GITHUB["code"] = match.group(1)
                open_in_chrome("github-device")
        proc.wait()
        if proc.returncode == 0:
            GITHUB["state"] = "none"
            github_refresh()
        if GITHUB["state"] != "connected":
            GITHUB.update(state="none", code="", error="GitHub sign-in did not finish. Click Connect to try again.")

    threading.Thread(target=watch, daemon=True).start()


def github_backup(folder):
    """Put the workspace in a private repository on the person's own GitHub."""
    workspace = Path(folder)
    if not (workspace / ".assistant-name").exists() or workspace.parent != Path.home():
        return {"ok": False, "error": "That is not an assistant folder."}
    github_refresh()
    git = shutil.which("git")
    if GITHUB["state"] != "connected":
        return {"ok": False, "error": "Connect GitHub first."}
    if git is None or not _has_git():
        return {"ok": False, "error": "Git is still installing. Try again when it shows as done."}
    ignore = (workspace / ".gitignore").read_text(encoding="utf-8") if (workspace / ".gitignore").exists() else ""
    if ".env" not in ignore.split():
        (workspace / ".gitignore").write_text(ignore.rstrip("\n") + "\n.env\n", encoding="utf-8")

    def run(*args):
        return subprocess.run([git, *args], cwd=str(workspace), capture_output=True, text=True, encoding="utf-8", errors="replace")

    if not (workspace / ".git").exists():
        run("init", "-q")
    run("add", "-A")
    if run("ls-files", ".env").stdout.strip():  # never send the token file
        run("rm", "--cached", "-q", ".env")
    run("commit", "-q", "-m", "First backup")
    repo = workspace.name + "-assistant"
    if not run("remote", "get-url", "origin").stdout.strip():
        worked, out = gh("repo", "create", repo, "--private", "--source", str(workspace), "--remote", "origin",
                         cwd=str(workspace))
        if not worked and "already exists" not in out:
            return {"ok": False, "error": out.splitlines()[-1] if out else "GitHub would not create the backup."}
        if not worked:
            run("remote", "add", "origin", f"https://github.com/{GITHUB['user']}/{repo}.git")
    branch = run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
    pushed = run("push", "-u", "origin", branch)
    if pushed.returncode != 0:
        return {"ok": False, "error": (pushed.stderr.strip().splitlines() or ["The backup could not be sent."])[-1]}
    return {"ok": True, "url": f"https://github.com/{GITHUB['user']}/{repo}"}


def open_folder(folder):
    if IS_WINDOWS:
        os.startfile(folder)  # noqa: S606 - the person's own new folder
    elif IS_MAC:
        subprocess.run(["open", folder], check=False)


def open_claude(folder=""):
    """Bring up the Claude desktop app, on the assistant's folder when one is given.

    `claude --desktop` opens the app on the folder it is run from. It only works from
    a real terminal window, so one is opened for a moment to run it.
    """
    workspace = Path(folder) if folder else None
    cli = claude_cli()
    if workspace and cli and workspace.parent == Path.home() and (workspace / ".assistant-name").exists():
        try:
            if IS_WINDOWS:
                subprocess.Popen(["cmd", "/c", "start", "", "/min", "cmd", "/c", cli, "--desktop"],
                                 cwd=str(workspace))
                return True
            if IS_MAC:
                quoted = str(workspace).replace("\\", "\\\\").replace('"', '\\"')
                tool = cli.replace("\\", "\\\\").replace('"', '\\"')
                script = f'tell application "Terminal" to do script "cd \\"{quoted}\\" && \\"{tool}\\" --desktop; exit"'
                if subprocess.run(["osascript", "-e", script], capture_output=True).returncode == 0:
                    return True
        except OSError:
            pass
    try:
        if IS_WINDOWS:
            where = claude_app_path()
            if where and where.startswith("shell:"):
                subprocess.Popen(["explorer", where])
                return True
            if where:
                subprocess.Popen([where])
                return True
        if IS_MAC:
            where = claude_app_path()
            return subprocess.run(["open", where] if where else ["open", "-a", "Claude"], check=False).returncode == 0
    except OSError:
        pass
    return False


# --- The Claude desktop app: is it here, and get it if not -------------------------

# Anthropic's own "latest" links; each answers with a redirect to the current installer.
CLAUDE_APP_URL = {
    # The app's own update feed. It is open to plain downloaders; claude.ai's link is not.
    "mac": "https://downloads.claude.ai/releases/darwin/universal/RELEASES.json",
    "win": "https://claude.ai/api/desktop/win32/x64/setup/latest/redirect",
    "win-arm": "https://claude.ai/api/desktop/win32/arm64/setup/latest/redirect",
}
CLAUDE_APP = {"state": "unknown", "error": ""}


def claude_app_path():
    """Where the Claude desktop app is on this computer, wherever it was put. None if absent."""
    if IS_MAC:
        for base in (Path("/Applications"), Path.home() / "Applications"):
            if (base / "Claude.app").exists():
                return str(base / "Claude.app")
        try:  # Spotlight finds it in Downloads, on the Desktop, or anywhere else
            found = subprocess.run(
                ["mdfind", "kMDItemCFBundleIdentifier == 'com.anthropic.claudefordesktop' || "
                           "(kMDItemContentType == 'com.apple.application-bundle' && kMDItemFSName == 'Claude.app')"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
            for line in found.stdout.splitlines():
                if line.endswith(".app") and "/Volumes/" not in line and Path(line).exists():
                    return line
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None
    if IS_WINDOWS:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        exe = local / "AnthropicClaude" / "claude.exe"
        if exe.exists():
            return str(exe)
        store = list((local / "Microsoft" / "WindowsApps").glob("Claude*"))
        if store:
            return str(store[0])
        try:  # anything the Start menu knows as "Claude"
            found = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-StartApps | Where-Object { $_.Name -eq 'Claude' } | Select-Object -First 1).AppID"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            if found.stdout.strip():
                return "shell:AppsFolder\\" + found.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


def claude_app_installed():
    return claude_app_path() is not None


BROWSER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def _download(url, dest, least=1_000_000):
    """Fetch a file. claude.ai turns away clients that do not look like a browser."""
    curl = shutil.which("curl")
    if curl:  # the system's own downloader: uses the system's certificates, follows redirects
        done = subprocess.run([curl, "-fL", "--retry", "2", "-sS", "-A", BROWSER_AGENT, "-o", str(dest), url],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        if done.returncode == 0 and Path(dest).exists() and Path(dest).stat().st_size > least:
            return
        problem = (done.stderr or "").strip().splitlines()[-1:] or ["download failed"]
        raise OSError("curl: " + problem[0])
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as reply, open(dest, "wb") as out:
        shutil.copyfileobj(reply, out)


def _install_claude_app():
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="claude-app-"))
    try:
        if IS_MAC:
            feed = work / "releases.json"
            _download(CLAUDE_APP_URL["mac"], feed, least=20)
            releases = json.loads(feed.read_text(encoding="utf-8"))
            current = releases["currentRelease"]
            url = next(r["updateTo"]["url"] for r in releases["releases"] if r["version"] == current)
            if not url.startswith("https://downloads.claude.ai/") or not url.endswith(".zip"):
                raise OSError("unexpected download address")
            archive = work / "Claude.zip"
            _download(url, archive)
            target = Path("/Applications")
            if not os.access(str(target), os.W_OK):
                target = Path.home() / "Applications"
                target.mkdir(exist_ok=True)
            subprocess.run(["ditto", "-x", "-k", str(archive), str(target)], check=True)
        elif IS_WINDOWS:
            import platform
            setup = work / "Claude-Setup.exe"
            _download(CLAUDE_APP_URL["win-arm" if "ARM" in platform.machine().upper() else "win"], setup)
            subprocess.run([str(setup)], check=False, timeout=900)
        else:
            raise OSError("no desktop app for this system")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ensure_claude_app():
    """Start getting the Claude app in the background if this computer lacks it."""
    if claude_app_installed():
        CLAUDE_APP.update(state="installed", error="")
        return
    if CLAUDE_APP["state"] == "installing":
        return
    CLAUDE_APP.update(state="installing", error="")

    def work():
        try:
            _install_claude_app()
        except Exception as error:  # shown on the page with a manual way out
            CLAUDE_APP["error"] = f"{type(error).__name__}: {error}"[:200]
        CLAUDE_APP["state"] = "installed" if claude_app_installed() else "failed"

    threading.Thread(target=work, daemon=True).start()


def claude_app_status():
    if CLAUDE_APP["state"] != "installing":
        CLAUDE_APP["state"] = "installed" if claude_app_installed() else (
            "failed" if CLAUDE_APP["state"] == "failed" else "missing")
    return dict(CLAUDE_APP, ok=True, system="mac" if IS_MAC else "windows" if IS_WINDOWS else "other")


# --- The person's Claude account ---------------------------------------------------

WORK_DOMAIN = "arizonaroofers.com"
LOGIN = {"running": False}


def claude_cli():
    return shutil.which("claude") or next(
        (str(p) for p in (Path.home() / ".local" / "bin" / "claude", Path.home() / ".local" / "bin" / "claude.exe")
         if p.exists()), None)


def claude_account():
    """Who Claude Code is signed in as on this computer, from `claude auth status`."""
    exe = claude_cli()
    if exe is None:
        return {"ok": True, "state": "no-claude"}
    try:
        done = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30, stdin=subprocess.DEVNULL)
        info = json.loads(done.stdout[done.stdout.index("{"):])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"ok": True, "state": "signed-out", "waiting": LOGIN["running"]}
    if not info.get("loggedIn"):
        return {"ok": True, "state": "signed-out", "waiting": LOGIN["running"]}
    email = str(info.get("email") or "")
    return {
        "ok": True,
        "state": "work" if email.lower().endswith("@" + WORK_DOMAIN) else "other",
        "email": email,
        "org": str(info.get("orgName") or ""),
        "plan": str(info.get("subscriptionType") or ""),
        "waiting": LOGIN["running"],
    }


def claude_login():
    """Start Claude's own sign-in (it opens the browser). The page polls for the result."""
    exe = claude_cli()
    if exe is None or LOGIN["running"]:
        return
    LOGIN["running"] = True

    def work():
        try:
            subprocess.run([exe, "auth", "login", "--claudeai"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            pass
        LOGIN["running"] = False

    threading.Thread(target=work, daemon=True).start()


# --- Connectors (Gmail, Calendar, Drive): which ones Claude can already use ------------

CONNECTORS = {"connected": [], "state": "unknown", "checking": False, "at": 0.0}


def _read_connectors():
    exe = claude_cli()
    found, state = [], "unknown"
    if exe:
        try:
            done = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=120, stdin=subprocess.DEVNULL)
            for line in done.stdout.splitlines():
                match = re.match(r"\s*claude\.ai ([^:]+):.*?(Connected|Needs authentication|Failed)", line)
                if match:
                    state = "known"
                    if match.group(2) == "Connected":
                        found.append(match.group(1).strip())
            if claude_account().get("state") in ("work", "other"):
                state = "known"  # signed in, so an empty list means none are connected yet
        except (OSError, subprocess.TimeoutExpired):
            pass
    CONNECTORS.update(connected=found, state=state, checking=False, at=__import__("time").time())


def connectors_status(fresh=False):
    """What is connected, from the last look. A new look runs in the background."""
    import time
    stale = time.time() - CONNECTORS["at"] > 5
    if (fresh or stale) and not CONNECTORS["checking"]:
        CONNECTORS["checking"] = True
        threading.Thread(target=_read_connectors, daemon=True).start()
    return {"ok": True, "connected": CONNECTORS["connected"], "state": CONNECTORS["state"],
            "checking": CONNECTORS["checking"]}


# --- Software this computer needs, installed while the person fills in the page -------

INSTALLS = []          # one row per piece of software: id, label, state, note
INSTALL_LOCK = threading.Lock()


def _row(step_id):
    return next(r for r in INSTALLS if r["id"] == step_id)


def _mark(step_id, state, note=""):
    with INSTALL_LOCK:
        _row(step_id).update(state=state, note=note)


def refresh_path():
    """Pick up tools installed a moment ago (Windows keeps PATH in the registry)."""
    extra = [str(Path.home() / ".local" / "bin")]
    if IS_WINDOWS:
        import winreg
        for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(root, key) as handle:
                    extra += os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]).split(";")
            except OSError:
                pass
    else:
        extra += ["/opt/homebrew/bin", "/usr/local/bin"]
    have = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(have + [p for p in extra if p and p not in have])


def _run(command, timeout=1800):
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
        return done.returncode == 0, ((done.stderr or done.stdout or "").strip().splitlines() or [""])[-1][:160]
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)[:160]


def _winget(package):
    exe = shutil.which("winget")
    if exe is None:
        return False, "this PC has no winget (App Installer)"
    common = ["-e", "--silent", "--accept-source-agreements", "--accept-package-agreements"]
    worked, note = _run([exe, "install", "--id", package, "--scope", "user"] + common)
    if not worked:  # some packages have no per-user installer
        worked, note = _run([exe, "install", "--id", package] + common)
    refresh_path()
    return worked, note


def _has_git():
    if IS_MAC:  # /usr/bin/git is only a stub until Apple's developer tools are in
        return subprocess.run(["xcode-select", "-p"], capture_output=True).returncode == 0
    return shutil.which("git") is not None or (
        IS_WINDOWS and (Path(os.environ.get("ProgramFiles", "")) / "Git" / "cmd" / "git.exe").exists())


def _get_git():
    if IS_WINDOWS:
        return _winget("Git.Git")
    if IS_MAC:
        import time
        subprocess.run(["xcode-select", "--install"], capture_output=True)
        _mark("git", "working", "A window asked to install Apple's developer tools. Click Install. "
                                "This is the long one; carry on with the page meanwhile.")
        for _ in range(360):  # up to an hour
            if _has_git():
                return True, ""
            time.sleep(10)
        return False, "still not installed after an hour"
    return False, ""


def _has_chrome():
    if IS_MAC:
        return Path("/Applications/Google Chrome.app").exists() or (Path.home() / "Applications" / "Google Chrome.app").exists()
    if IS_WINDOWS:
        return any((Path(os.environ.get(v, "")) / "Google" / "Chrome" / "Application" / "chrome.exe").exists()
                   for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
    return True


def _get_chrome():
    if IS_WINDOWS:
        return _winget("Google.Chrome")
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="chrome-"))
    try:
        dmg, mount = work / "chrome.dmg", work / "mount"
        _download("https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg", dmg)
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-quiet", "-mountpoint", str(mount)], check=True)
        try:
            target = Path("/Applications") if os.access("/Applications", os.W_OK) else Path.home() / "Applications"
            target.mkdir(exist_ok=True)
            subprocess.run(["ditto", str(mount / "Google Chrome.app"), str(target / "Google Chrome.app")], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=False)
        return True, ""
    except Exception as error:
        return False, str(error)[:160]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _get_claude_code():
    if IS_WINDOWS:
        worked, note = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                             "irm https://claude.ai/install.ps1 | iex"])
    else:
        worked, note = _run(["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"])
    refresh_path()
    return worked, note


def _get_claude_app():
    import time
    if IS_WINDOWS and shutil.which("winget"):
        _winget("Anthropic.Claude")
        if claude_app_installed():
            return True, ""
    if IS_WINDOWS and os.environ.get("CI"):
        return False, "no silent installer on this test machine"
    ensure_claude_app()
    while CLAUDE_APP["state"] == "installing":
        time.sleep(2)
    return claude_app_installed(), CLAUDE_APP.get("error", "")


def _get_gh():
    GH_TOOL["tried"] = False
    ensure_gh()
    return gh_path() is not None, ""


def install_plan():
    """What this kind of computer needs, in the order it is fetched."""
    plan = [
        ("claude-code", "Claude Code", lambda: claude_cli() is not None, _get_claude_code, "the engine your assistant runs on"),
        ("claude-app", "The Claude app", claude_app_installed, _get_claude_app, "where you will talk to it"),
        ("chrome", "Google Chrome", _has_chrome, _get_chrome, "for Roofr and the web"),
        ("gh", "GitHub tool", lambda: gh_path() is not None, _get_gh, "for backing up your notes"),
    ]
    if IS_WINDOWS:
        plan.insert(0, ("git", "Git", _has_git, _get_git, "Claude needs it to run commands"))
        plan.append(("node", "Node.js", lambda: shutil.which("node") is not None,
                     lambda: _winget("OpenJS.NodeJS.LTS"), "for add-on skills"))
    elif IS_MAC:
        plan.append(("git", "Apple developer tools (Git)", _has_git, _get_git, "for backups; the slow one"))
    return plan


def run_installs(blocking=False):
    """Fetch whatever is missing. Each row moves waiting -> working -> done or failed."""
    refresh_path()
    plan = install_plan()
    with INSTALL_LOCK:
        if INSTALLS:
            return
        INSTALLS.extend({"id": i, "label": label, "why": why, "state": "waiting", "note": ""} for i, label, _, _, why in plan)

    def one(step):
        step_id, _, have, get, _ = step
        try:
            if have():
                _mark(step_id, "done", "already here")
                return
            _mark(step_id, "working")
            worked, note = get()
            refresh_path()
            _mark(step_id, "done" if have() else "failed", "" if have() else (note or "could not be installed"))
        except Exception as error:
            _mark(step_id, "failed", f"{type(error).__name__}: {error}"[:160])

    def queue(steps):
        for step in steps:
            one(step)

    # Apple's developer tools take many minutes and wait on a click, so they run on their own.
    slow = [step for step in plan if IS_MAC and step[0] == "git"]
    fast = [step for step in plan if step not in slow]
    if blocking:
        queue(fast + ([] if os.environ.get("CI") else slow))
        for step in slow:
            if os.environ.get("CI"):
                _mark(step[0], "done" if step[2]() else "failed", "")
        return
    threading.Thread(target=queue, args=(fast,), daemon=True).start()
    if slow:
        threading.Thread(target=queue, args=(slow,), daemon=True).start()


def installs_status():
    with INSTALL_LOCK:
        rows = [dict(r) for r in INSTALLS]
    settled = sum(1 for r in rows if r["state"] in ("done", "failed"))
    return {"ok": True, "rows": rows, "settled": settled, "total": len(rows),
            "busy": any(r["state"] in ("waiting", "working") for r in rows)}


# --- Other assistants: terminal tools beside Claude, on the same folder and notes ---

POINTER = """# {name}

Read `CLAUDE.md` in this folder first and follow it: it says who you are, who you work
for and how. The notes it points to (`state/`, `company/`) are yours to read and keep up.

The files in `.claude/commands/` are plain instructions. When the person types `/start`
or `/save`, read `.claude/commands/start.md` or `.claude/commands/save.md` and do what it says.
"""

# "never" is the tool's own flag for running without stopping to ask. Antigravity has
# no flag: its choice is written to its settings file instead.
EXTRAS = {
    "agy": {
        "label": "Gemini (Antigravity)", "short": "Antigravity", "command": "agy", "maker": "Google's assistant",
        "account": "your work Google account", "never": "",
        "windows": "irm https://antigravity.google/cli/install.ps1 | iex",
        "unix": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
    },
    "codex": {
        "label": "Codex", "short": "Codex", "command": "codex", "maker": "OpenAI's assistant",
        "account": "a ChatGPT plan of your own", "never": "--dangerously-bypass-approvals-and-sandbox",
        "windows": "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
        "unix": "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh",
    },
    "grok": {
        "label": "Grok", "short": "Grok", "command": "grok", "maker": "xAI's assistant",
        "account": "a Grok plan of your own", "never": "--always-approve",
        "windows": "irm https://x.ai/cli/install.ps1 | iex",
        "unix": "curl -fsSL https://x.ai/cli/install.sh | bash",
    },
}
EXTRA_JOBS = {}
ONE_AT_A_TIME = threading.Lock()  # each installer adds itself to the PATH; two at once can undo each other


def _default_tools():
    """The assistants that start ticked beside Claude. The install file names them; here, none."""
    named = _install_setting("ASSISTANT_DEFAULT_TOOLS", "a-z,")
    other_names = {"gemini": "agy", "antigravity": "agy"}
    wanted = {other_names.get(word, word) for word in named.split(",")}
    return [tool for tool in EXTRAS if tool in wanted]


DEFAULT_TOOLS = _default_tools()


def tool_path(tool):
    """Where the tool is, whether or not this window's PATH has caught up with its installer."""
    found = shutil.which(EXTRAS[tool]["command"])
    if found:
        return found
    home, local = Path.home(), Path(os.environ.get("LOCALAPPDATA", ""))
    if IS_WINDOWS:
        spot = {"agy": local / "agy" / "bin" / "agy.exe",
                "codex": local / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
                "grok": home / ".grok" / "bin" / "grok.exe"}[tool]
    else:
        spot = {"agy": home / ".local" / "bin" / "agy", "codex": home / ".local" / "bin" / "codex",
                "grok": home / ".grok" / "bin" / "grok"}[tool]
    return str(spot) if spot.is_file() else None


def _get_extra(tool):
    """The maker's own installer for the tool."""
    if IS_WINDOWS:
        worked, note = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", EXTRAS[tool]["windows"]])
    else:
        worked, note = _run(["bash", "-c", EXTRAS[tool]["unix"]])
    refresh_path()
    return worked, note


def chosen_extras(a):
    """The assistants picked beside Claude, in a fixed order."""
    picked = {t for t in a["tools"] if isinstance(t, str)} if isinstance(a.get("tools"), list) else set()
    if a.get("agy"):  # answers written before there was a picker
        picked.add("agy")
    return [tool for tool in EXTRAS if tool in picked]


def launcher(tool, workspace):
    return workspace / f"Open {EXTRAS[tool]['short']}{'.cmd' if IS_WINDOWS else '.command'}"


def write_launcher(tool, workspace, never_asks):
    """A file in the folder that opens the tool there. Rewritten each run, so it follows the latest choice."""
    spec = EXTRAS[tool]
    run = spec["command"] + (" " + spec["never"] if never_asks and spec["never"] else "")
    target = launcher(tool, workspace)
    if IS_WINDOWS:
        lines = ["@echo off", f"title {spec['short']}", 'cd /d "%~dp0"',
                 'set "PATH=%LOCALAPPDATA%\\agy\\bin;%LOCALAPPDATA%\\Programs\\OpenAI\\Codex\\bin;'
                 '%USERPROFILE%\\.grok\\bin;%USERPROFILE%\\.local\\bin;%PATH%"',
                 f"call {run}", "if errorlevel 1 pause", ""]
        target.write_bytes("\r\n".join(lines).encode("ascii"))
    else:
        target.write_text('#!/bin/bash\ncd "$(dirname "$0")" || exit 1\n'
                          'export PATH="$HOME/.local/bin:$HOME/.grok/bin:$PATH"\n' + run + "\n", encoding="utf-8")
        target.chmod(0o755)


def write_agy_settings(workspace, never_asks, log):
    """Antigravity's own settings file: trust the assistant's folder, and never ask if that was chosen."""
    path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError:
            settings = None
        if not isinstance(settings, dict) or not isinstance(settings.get("trustedWorkspaces", []), list):
            log.append("Antigravity's settings file could not be read, so it was left alone. Ask for help.")
            return
        backup = path.with_name("settings.json.before-setup")
        if not backup.exists():
            shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    trusted = settings.setdefault("trustedWorkspaces", [])
    if str(workspace) not in trusted:
        trusted.append(str(workspace))
    if never_asks:
        settings["toolPermission"] = "always-proceed"
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def write_extras(a, workspace, name, extras, log):
    """Point each chosen assistant at this folder's notes and leave a file that opens it here."""
    if not extras:
        return
    never_asks = bool(a.get("extrasBypass", a.get("agyBypass", True)))
    for pointer in ["AGENTS.md"] + (["GEMINI.md"] if "agy" in extras else []):
        if not (workspace / pointer).exists():
            (workspace / pointer).write_text(POINTER.format(name=name), encoding="utf-8")
    for tool in extras:
        write_launcher(tool, workspace, never_asks)
    if "agy" in extras:
        write_agy_settings(workspace, never_asks, log)
    names = [EXTRAS[tool]["short"] for tool in extras]
    log.append(" and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)
               + f" set up for this folder: open {'it' if len(names) == 1 else 'each'} with its \"Open ...\" file there"
               + (". Never stops to ask." if never_asks else "."))


def install_extra(tool):
    """Fetch one of the other assistants in the background; its row shows in the page with the other installs."""
    spec = EXTRAS[tool]
    with INSTALL_LOCK:
        if any(r["id"] == tool for r in INSTALLS):
            return
        INSTALLS.append({"id": tool, "label": spec["label"], "why": f"{spec['maker']}, in the terminal",
                         "state": "waiting", "note": ""})

    def work():
        try:
            refresh_path()
            if tool_path(tool):
                _mark(tool, "done", "already here")
                return
            with ONE_AT_A_TIME:
                _mark(tool, "working")
                _, note = _get_extra(tool)
            _mark(tool, "done" if tool_path(tool) else "failed", "" if tool_path(tool) else (note or "could not be installed"))
        except Exception as error:
            _mark(tool, "failed", f"{type(error).__name__}: {error}"[:160])

    EXTRA_JOBS[tool] = threading.Thread(target=work, daemon=True)
    EXTRA_JOBS[tool].start()


def open_extra(tool, folder=""):
    """A terminal window on the assistant's folder, running the tool. Its first run asks for a sign-in."""
    workspace = Path(folder) if folder else None
    if tool not in EXTRAS or not (workspace and workspace.parent == Path.home() and (workspace / ".assistant-name").exists()):
        return False
    file = launcher(tool, workspace)
    if not (tool_path(tool) and file.is_file()):
        return False
    try:
        if IS_WINDOWS:
            subprocess.Popen(["cmd", "/c", "start", "", str(file)], cwd=str(workspace))
            return True
        if IS_MAC:
            return subprocess.run(["open", str(file)], capture_output=True).returncode == 0
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
        port = self.server.server_address[1]
        ok_host = host in ("127.0.0.1", "localhost")
        own = origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
        # A page on another site can post here blind; only this page's own posts count.
        ok_origin = own if self.command == "POST" else (origin is None or own)
        if not (ok_host and ok_origin):
            self.send({"ok": False, "error": "local only"}, code=403)
            return False
        return True

    def do_GET(self):
        if not self.local_only():
            return
        if self.path.split("?")[0] == "/":
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif re.fullmatch(r"/img/[a-z0-9-]+\.png", self.path) and (PAGE.parent / self.path[1:]).is_file():
            self.send((PAGE.parent / self.path[1:]).read_bytes(), "image/png")
        elif self.path == "/options":
            self.send({
                "names": NAMES, "roles": ROLES, "styles": list(STYLES), "colors": {k: v[0] for k, v in COLORS.items()},
                "modes": MODES, "home": str(Path.home()), "sep": os.sep,
                "hasToken": bool(INSTALLER_TOKEN),
                "user": os.environ.get("ASSISTANT_USER_NAME", ""),
                "contact": CONTACT,
                "tools": [{"id": t, "label": s["label"], "maker": s["maker"], "account": s["account"],
                           "on": t in DEFAULT_TOOLS} for t, s in EXTRAS.items()],
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
            body = None
        if not isinstance(body, dict):
            self.send({"ok": False, "error": "Setup could not read the form. Reload the page and try again."})
        elif self.path == "/apply":
            try:
                self.send(configure(body))
            except ValueError as error:  # something the person can fix
                self.send({"ok": False, "error": str(error)})
            except Exception as error:  # the page shows it to the person
                self.send({"ok": False, "error": f"{type(error).__name__}: {error}"})
        elif self.path == "/open":
            self.send({"ok": True, "claude": open_claude(str(body.get("folder") or ""))})
        elif self.path == "/tool/open":
            tool = body.get("tool") if body.get("tool") in EXTRAS else ""
            self.send({"ok": bool(tool), "opened": bool(tool) and open_extra(tool, str(body.get("folder") or "")),
                       "installed": bool(tool) and tool_path(tool) is not None})
        elif self.path == "/connectors/status":
            self.send(connectors_status(bool(body.get("fresh"))))
        elif self.path == "/installs/status":
            self.send(installs_status())
        elif self.path == "/account/status":
            self.send(claude_account())
        elif self.path == "/account/login":
            claude_login()
            self.send(dict(claude_account(), waiting=True))
        elif self.path == "/app/status":
            self.send(claude_app_status())
        elif self.path == "/app/install":
            ensure_claude_app()
            self.send(claude_app_status())
        elif self.path == "/chrome":
            self.send({"ok": body.get("page") in CHROME_PAGES, "chrome": open_in_chrome(body.get("page"))})
        elif self.path == "/github/connect":
            github_connect()
            self.send(dict(GITHUB, ok=True, installed=gh_path() is not None))
        elif self.path == "/github/status":
            ensure_gh()
            github_refresh()
            self.send(dict(GITHUB, ok=True, installed=gh_path() is not None))
        elif self.path == "/github/backup":
            self.send(github_backup(str(body.get("folder") or "")))
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
        run_installs(blocking=True)
        for row in INSTALLS:
            print(f"  {row['label']}: {row['state']}" + (f" ({row['note']})" if row["note"] else ""))
        result = configure(json.loads(Path(args.answers).read_text(encoding="utf-8")))
        for tool, job in EXTRA_JOBS.items():
            job.join()
            print(f"  {EXTRAS[tool]['label']}: " + _row(tool)["state"] + (f" ({_row(tool)['note']})" if _row(tool)["note"] else ""))
        print("\n".join(result["log"]))
        return

    if not os.environ.get("ASSISTANT_SKIP_INSTALLS"):
        run_installs()  # under way while the person fills in the page
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
