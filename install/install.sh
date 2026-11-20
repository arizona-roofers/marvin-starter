#!/bin/bash
# One-step install for Mac: gets Git and Python (Apple's developer tools), Claude
# Code and the Claude app, downloads the starter, then opens the setup page.
#
# Run it by opening the install file Travis sent you, or paste this in Terminal:
#   curl -fsSL https://raw.githubusercontent.com/arizona-roofers/marvin-starter/master/install/install.sh | bash
#
# Safe to run again: it skips what is already installed and keeps your notes.

set -u
REPO="https://github.com/arizona-roofers/marvin-starter"
BRANCH="master"
STARTER="$HOME/.assistant-starter"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[0;32m%s\033[0m\n' "$1"; }
note() { printf '    \033[0;33m%s\033[0m\n' "$1"; }
die()  { printf '\n\033[0;31m%s\033[0m\n' "$1"; exit 1; }

# Everything runs inside main with stdin closed: this script may be arriving on
# stdin (curl | bash), and a tool that reads stdin would swallow the rest of it.
main() {
printf '\n  Setting up your AI assistant. This takes about five minutes.\n'

# Apple's /usr/bin/git and python3 are stubs until the developer tools are installed.
step "Git and Python (Apple developer tools)"
if xcode-select -p >/dev/null 2>&1; then
  ok "already installed"
else
  note "A window will ask to install the developer tools. Click Install, then wait."
  xcode-select --install >/dev/null 2>&1 || true
  waited=0
  until xcode-select -p >/dev/null 2>&1; do
    sleep 10
    waited=$((waited + 10))
    [ "$waited" -ge 1800 ] && die "The developer tools did not finish installing. Run this again when they have."
  done
  ok "installed"
fi
command -v python3 >/dev/null 2>&1 || die "Python is missing. Install it from https://www.python.org/downloads/ and run this again."

step "Claude Code"
if command -v claude >/dev/null 2>&1; then
  ok "already installed"
else
  curl -fsSL https://claude.ai/install.sh | bash || note "Claude Code did not install. Setup will carry on; ask for help with this step."
  command -v claude >/dev/null 2>&1 && ok "installed"
fi

step "Claude desktop app"
if [ -d "/Applications/Claude.app" ] || [ -d "$HOME/Applications/Claude.app" ]; then
  ok "already installed"
elif command -v brew >/dev/null 2>&1 && brew install --cask claude >/dev/null 2>&1; then
  ok "installed"
else
  note "Opening the download page. Install the Claude app from there, then come back."
  open "https://claude.ai/download" || true
fi

step "Node.js and Google Chrome"
if command -v node >/dev/null 2>&1; then ok "Node.js already installed"
elif command -v brew >/dev/null 2>&1 && brew install node >/dev/null 2>&1; then ok "Node.js installed"
else note "Node.js skipped. Only add-on skills need it; get it from https://nodejs.org if you ever do."
fi
if command -v gh >/dev/null 2>&1; then ok "GitHub tool already installed"
elif command -v brew >/dev/null 2>&1 && brew install gh >/dev/null 2>&1; then ok "GitHub tool installed"
else note "GitHub tool skipped. Only the optional backup needs it."
fi
if [ -d "/Applications/Google Chrome.app" ]; then ok "Chrome already installed"
elif command -v brew >/dev/null 2>&1 && brew install --cask google-chrome >/dev/null 2>&1; then ok "Chrome installed"
else note "Chrome is not installed. Get it from https://www.google.com/chrome/ for the Roofr tools."
fi

step "Downloading the starter"
if [ -d "$STARTER/.git" ]; then
  git -C "$STARTER" pull --ff-only --quiet && ok "updated" || note "could not update; using the copy already here"
else
  rm -rf "$STARTER"
  git clone --quiet --depth 1 --branch "$BRANCH" "$REPO.git" "$STARTER" \
    || die "The starter could not be downloaded. Check your internet connection and run this again."
  ok "downloaded"
fi

step "Opening setup in your browser"
first="$(id -F 2>/dev/null | awk '{print $1}')"
export ASSISTANT_USER_NAME="${first:-}"
# ASSISTANT_ANSWERS_FILE (a JSON file of answers) skips the page; the automated test uses it.
if [ -n "${ASSISTANT_ANSWERS_FILE:-}" ]; then
  python3 "$STARTER/install/wizard.py" --answers "$ASSISTANT_ANSWERS_FILE" || die "Setup did not finish."
else
  python3 "$STARTER/install/wizard.py" || die "Setup did not finish."
fi
}

main "$@" </dev/null
