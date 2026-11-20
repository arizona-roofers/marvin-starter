#!/usr/bin/env python3
"""Checks what the installer built, for the automated test.

    python check-install.py first    after the first run
    python check-install.py again    after a second run over a changed workspace
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

home = Path.home()
work = home / "friday"
failed = []
notes = []


def check(label, ok):
    print(("  ok    " if ok else "  FAIL  ") + label)
    if not ok:
        failed.append(label)


def note(label, ok):
    """Something worth knowing that the test machine may not be able to do."""
    print(("  ok    " if ok else "  note  ") + label)
    if not ok:
        notes.append(label)


def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


print("Workspace")
check("starter downloaded to ~/.assistant-starter", (home / ".assistant-starter" / "install" / "wizard.py").exists())
check("workspace folder ~/friday", work.is_dir())
check("CLAUDE.md names the assistant and the person", "FRIDAY" in read(work / "CLAUDE.md") and "Pat" in read(work / "CLAUDE.md"))
check("START-HERE.md written", "/save" in read(work / "START-HERE.md"))
check("/save command present, /end gone",
      (work / ".claude" / "commands" / "save.md").exists() and not (work / ".claude" / "commands" / "end.md").exists())
check("Roofr skill present", (work / ".claude" / "skills" / "roofr-api" / "SKILL.md").exists())
check("swarm layer left out", not (work / ".claude" / "agents" / "the-boys.md").exists())
check("Roofr token in .env", "ROOFR_EXTERNAL_TOKEN=test_token_not_real_0000000000" in read(work / ".env"))
check("token not in CLAUDE.md or START-HERE.md",
      "test_token" not in read(work / "CLAUDE.md") + read(work / "START-HERE.md"))

print("Role kit and company knowledge")
claude_md = read(work / "CLAUDE.md")
check("role focus in CLAUDE.md", "Running appointments and closing jobs" in claude_md)
check("Roofr name in CLAUDE.md", "Pat Example" in claude_md)
check("role examples in START-HERE.md", "Show me my open jobs" in read(work / "START-HERE.md"))
check("knowledge pack unpacked", (work / "company" / "README.md").exists() and (work / "company" / "sops" / "booking.md").exists())
check("skill from the pack installed", (work / ".claude" / "skills" / "roofr-changes" / "SKILL.md").exists() and "Changing things in Roofr" in claude_md)
check("CLAUDE.md points at the pack", "company/README.md" in claude_md and "company/sops/booking.md" in claude_md)

print("Color modes")
topics = read(work / ".mods" / "session-tint" / "hooks" / "topics.js")
check("mod copied into the workspace", (work / ".mods" / "session-tint" / "hooks" / "register.ts").exists())
check("topics hold the assistant and Arizona Roofers", '"label": "Friday"' in topics and '"id": "azr"' in topics)
check("assistant color is teal", "#2a9d8f" in topics)

print("Claude settings")
try:
    settings = json.loads(read(home / ".claude" / "settings.json") or "{}")
except ValueError:
    settings = {}
check("bypass permissions on", settings.get("permissions", {}).get("defaultMode") == "bypassPermissions")
check("remote control on", settings.get("remoteControlAtStartup") is True)
check("starting model set for the role", settings.get("model") == "sonnet")
check("chat history kept", settings.get("cleanupPeriodDays") == 3650)
check("mod folder registered", "session-tint" in settings.get("env", {}).get("CLAUDE_CODE_PLUGIN_DIRS", ""))

print("Shortcut and tools")
desktops = [home / "Desktop"] + sorted(home.glob("OneDrive*/Desktop"))
check("desktop shortcut made", any((d / n).exists() for d in desktops for n in ("Friday.cmd", "Friday.command")))
os.environ["PATH"] = str(home / ".local" / "bin") + os.pathsep + os.environ.get("PATH", "")
claude = shutil.which("claude")
check("Claude Code installed", claude is not None)
if claude:
    version = subprocess.run([claude, "--version"], capture_output=True, text=True)
    check("Claude Code runs (" + version.stdout.strip()[:40] + ")", version.returncode == 0)
    valid = subprocess.run([claude, "plugin", "validate", str(work / ".mods" / "session-tint")],
                           capture_output=True, text=True)
    check("Claude accepts the color mod", valid.returncode == 0)
check("git on this machine", shutil.which("git") is not None)
note("node on this machine", shutil.which("node") is not None)
if sys.platform == "darwin":
    note("Claude desktop app installed", Path("/Applications/Claude.app").exists())
    note("Chrome installed", Path("/Applications/Google Chrome.app").exists())
elif os.name == "nt":
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    note("Claude desktop app installed", (local / "AnthropicClaude" / "claude.exe").exists())

print("Chrome")
EXT = "fcoeoabgfenejglbffodgkkbkcdhcgfn"
if os.name == "nt":
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\Extensions" + "\\" + EXT)
        offered = "clients2.google.com" in winreg.QueryValueEx(key, "update_url")[0]
    except OSError:
        offered = False
else:
    offered = "clients2.google.com" in read(
        home / "Library" / "Application Support" / "Google" / "Chrome" / "External Extensions" / (EXT + ".json"))
check("Claude extension offered to Chrome", offered)

if sys.argv[1:] == ["again"]:
    print("Second run")
    check("the person's own note survived", "my own note" in read(work / "state" / "goals.md"))
    check("settings backup kept", (home / ".claude" / "settings.json.before-setup").exists())
    check("token still there once", read(work / ".env").count("ROOFR_EXTERNAL_TOKEN=") == 1)

print()
if notes:
    print("Not done on this test machine: " + "; ".join(notes))
if failed:
    print(str(len(failed)) + " check(s) failed: " + "; ".join(failed))
    sys.exit(1)
print("All checks passed.")
