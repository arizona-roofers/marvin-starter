# MARVIN Starter — AI Chief of Staff + The Boys

**MARVIN** = Manages Appointments, Reads Various Important Notifications

This is a team-ready starter built on [Sterling Chin's MARVIN template](https://github.com/SterlingChin/marvin-template), extended with a battle-tested **multi-AI swarm workflow ("The Boys")** that keeps your paid Claude usage lean by fanning research and drafting out to free CLI workers (Codex + Gemini-class via Antigravity).

## Install (Arizona Roofers staff)

One file, about five minutes, Windows or Mac. You need a Claude seat on the company plan first (ask Travis).

1. Open the install file Travis sent you.
   - **Windows:** double-click `Install Assistant.cmd`. If Windows shows a blue "protected your PC" box, click **More info**, then **Run anyway**.
   - **Mac:** unzip `Install Assistant (Mac).zip`, then **right-click** the file inside and choose **Open** (a plain double-click is blocked the first time).
2. It installs Git, Python, Claude Code and the Claude app, then opens a setup page in your browser.
3. On the setup page, pick your assistant's name (Jarvis, HAL, WALL-E, or your own), its color, and how it should talk. Click **Set up**.
4. Open the Claude app, sign in with your work email, click the **Code** tab, choose the folder the page shows, and type `/start`.

What you get: your assistant in its own folder, chats colored by topic with a matching shape on each title, no permission prompts, remote control from your phone, and read-only access to the Roofr job pipeline.

Running the install file again is safe. It updates the tools and keeps your notes.

No install file? Paste one line instead, and the setup page will ask for the Roofr token.

- Windows (PowerShell): `irm https://raw.githubusercontent.com/arizona-roofers/marvin-starter/master/install/install.ps1 | iex`
- Mac (Terminal): `curl -fsSL https://raw.githubusercontent.com/arizona-roofers/marvin-starter/master/install/install.sh | bash`

### For Travis: building the install file

```bash
python install/build-installer.py        # reads ROOFR_EXTERNAL_TOKEN from .env
```

This writes `dist/Install Assistant.cmd` and `dist/Install Assistant (Mac).zip` with the Roofr token inside. `dist/` is never committed. Share the files from Google Drive limited to arizonaroofers.com. To change the token, rebuild and resend.

---

## What this starter adds on top of the vanilla template

- **The Boys protocol** (`.claude/agents/the-boys.md`) — Claude acts as PM; 5+ free AI workers (Gemini via Antigravity OAuth, Codex via ChatGPT) do the exploration, research, and drafting in parallel; a free Gemini reviewer synthesizes; you approve before any code lands.
- **Worker tooling** (`tools/agy-call.sh`, `tools/agy-extract.py`) — the wrapper that makes the Antigravity CLI usable headlessly.
- **Operational rules** baked into `CLAUDE.md` — CLI-first dispatch, failure handling, token economics, when to swarm vs. when to just do it.
- **Setup guide** — [`docs/the-boys-setup.md`](docs/the-boys-setup.md) gets the worker CLIs installed and authenticated in ~15 minutes.

Everything below is the standard MARVIN experience.

---

An AI assistant that remembers your conversations, tracks your goals, and helps you stay organized. Like having a personal chief of staff who never forgets anything.

## Why MARVIN?

MARVIN extends Claude Code with capabilities designed for getting things done:

- **Session continuity** - Pick up where you left off, even days later. Every conversation builds on the last.
- **Goal tracking** - Set work and personal goals, MARVIN monitors progress and nudges you forward.
- **Tool integrations** - Connect to Google Workspace, Microsoft 365, Atlassian, Slack, Linear, Notion, Telegram, and more.
- **Extensibility** - Add commands, agents, and skills tailored to your workflow. Create new capabilities with simple markdown files.
- **Thought partner** - MARVIN pushes back on weak ideas, asks probing questions, and helps you think through decisions. Not just a yes-man.

## Quick Start with Claude Code

1. Clone this repository:
   ```bash
   git clone <this-repo-url> marvin
   cd marvin
   ```

2. Open in Claude Code:
   ```bash
   claude
   ```

3. Ask MARVIN to help you set up:
   > "Help me set up MARVIN"

That's it. MARVIN walks you through the rest: your profile, goals, workspace location, and optional integrations.

## Getting Started with GitHub Copilot CLI

Want to use Copilot CLI to set up MARVIN quickly? Here's how:

### Prerequisites

- [GitHub Copilot CLI](https://cli.github.com/) installed and authenticated

### Quick Setup

Use these Copilot commands to get started:

```bash
# Navigate to your projects directory
gh copilot suggest "clone marvin template repository"

# Run the setup script
gh copilot suggest "run setup script for marvin"

# Start MARVIN
gh copilot suggest "start marvin AI assistant"
```

The `.marvin/setup.sh` script handles the MARVIN workspace setup: prerequisites, workspace creation, profile setup, and shell aliases. It does **not** install the worker CLIs for The Boys — do that separately via [`docs/the-boys-setup.md`](docs/the-boys-setup.md).

For additional integrations (Google Workspace, Slack, etc.), use:

```bash
gh copilot suggest "configure marvin integrations"
```

## What You Get

### Daily Workflow

Start your day with `/start` for a briefing: priorities, deadlines, progress toward goals. Work naturally throughout the day, MARVIN remembers everything. End with `/end` to save context for next time.

Between sessions, `/update` saves progress without ending.

> **Note on `/sync`:** this starter is a fork of the upstream MARVIN template. `/sync` pulls updates from the upstream template, which knows nothing about The Boys layer — review sync diffs before applying so they don't clobber `CLAUDE.md`'s Operational Rules or `.claude/agents/the-boys.md`.

### Commands

| Command | What It Does |
|---------|--------------|
| `/start` | Start your day with a briefing |
| `/end` | End session and save everything |
| `/update` | Quick checkpoint (save progress) |
| `/report` | Generate a weekly summary |
| `/commit` | Review and commit git changes |
| `/status` | Check integration & workspace health |
| `/sync` | Get updates from the template |
| `/help` | Show all commands and integrations |

### Integrations

MARVIN connects to tools you already use:

| Integration | What It Provides |
|-------------|------------------|
| [Google Workspace](.marvin/integrations/google-workspace/) | Gmail, Calendar, Drive |
| [Microsoft 365](.marvin/integrations/ms365/) | Outlook, Calendar, OneDrive, Teams |
| [Atlassian](.marvin/integrations/atlassian/) | Jira, Confluence |
| [Slack](.marvin/integrations/slack/) | Channel monitoring, posting |
| [Linear](.marvin/integrations/linear/) | Issue tracking |
| [Notion](.marvin/integrations/notion/) | Page reading, database queries |
| [Telegram](.marvin/integrations/telegram/) | Chat with MARVIN from your phone |
| [Parallel Search](.marvin/integrations/parallel-search/) | Web search capabilities |

Each integration includes setup instructions in its directory.

### Skills and Agents

MARVIN uses a `.claude/` directory structure for extensibility:

- **Commands** (`.claude/commands/`) - User-triggered workflows you invoke with slash commands
- **Agents** (`.claude/agents/`) - Specialized subagents MARVIN spawns for delegated work
- **Skills** (`.claude/skills/`) - Reusable capabilities Claude Code invokes contextually

Templates are included for each type. Just say "create a skill for X" and MARVIN generates the file.

## How It Works

MARVIN separates your workspace from the template:

```
~/marvin/                    Your workspace (your data lives here)
├── CLAUDE.md               Your profile and preferences
├── state/                  Your goals and priorities
├── sessions/               Your daily session logs
└── ...

~/marvin-template/          Template (get updates here)
├── .marvin/                Setup scripts and integrations
├── .claude/                Command and agent templates
└── ...
```

Your workspace holds all personal data. The template provides updates. Run `/sync` from your workspace to pull new features without overwriting your data.

## Migrating from Older Versions

If you were using MARVIN before the workspace separation:

```bash
cd marvin-template
./.marvin/migrate.sh
```

The script copies your profile, goals, sessions, reports, and custom skills to a new workspace. Nothing is deleted from your old installation. Verify the new workspace works, then clean up the old one.

## Contributing

MARVIN welcomes contributions in three areas:

1. **Integrations** - Add support for new tools. See [.marvin/integrations/CLAUDE.md](.marvin/integrations/CLAUDE.md) for patterns and security requirements.
2. **Commands, agents, skills** - Extend MARVIN's capabilities. Templates are in `.claude/commands/`, `.claude/agents/`, and `.claude/skills/`.
3. **Bug fixes** - Found an issue? Submit a PR with the fix and a test case.

Fork the repo, create a branch, and submit a PR. All contributions are reviewed.

## About

MARVIN is named after the Paranoid Android from The Hitchhiker's Guide to the Galaxy.

Created by [Sterling Chin](https://sterlingchin.com).
