#!/usr/bin/env python3
"""Build the install files you hand to a new hire, with the Roofr token inside.

    python install/build-installer.py              token from ROOFR_EXTERNAL_TOKEN or ./.env
    python install/build-installer.py --token XXX

Writes to dist/ (never committed):
    Install Assistant.cmd          Windows: double-click
    Install Assistant (Mac).zip    Mac: unzip, right-click the file inside, Open

The files hold the token, so share them only with Arizona Roofers staff
(a Google Drive link limited to arizonaroofers.com).
"""
import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/arizona-roofers/marvin-starter/master/install"

WINDOWS = """@echo off
title Install your AI assistant
set "ROOFR_EXTERNAL_TOKEN={token}"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; irm {raw}/install.ps1 | iex"
if errorlevel 1 (
  echo.
  echo Setup hit a problem. Take a screenshot of this window and send it to Travis.
  pause
)
"""

MAC = """#!/bin/bash
export ROOFR_EXTERNAL_TOKEN='{token}'
curl -fsSL {raw}/install.sh | bash
status=$?
if [ "$status" -ne 0 ]; then
  echo
  echo "Setup hit a problem. Take a screenshot of this window and send it to Travis."
  read -r -p "Press Enter to close." _
fi
"""


def find_token(given):
    if given:
        return given
    if os.environ.get("ROOFR_EXTERNAL_TOKEN"):
        return os.environ["ROOFR_EXTERNAL_TOKEN"]
    for env in (Path.cwd() / ".env", ROOT / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ROOFR_EXTERNAL_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token")
    args = parser.parse_args()

    token = find_token(args.token)
    if not token:
        sys.exit("No token. Pass --token, or put ROOFR_EXTERNAL_TOKEN=... in .env")
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", token):
        sys.exit("That token has characters an install file cannot carry safely.")

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)

    windows = dist / "Install Assistant.cmd"
    windows.write_text(WINDOWS.format(token=token, raw=RAW).replace("\n", "\r\n"), encoding="ascii", newline="")

    # A zip keeps the Mac file's "can be run" flag, which a bare download loses.
    mac_zip = dist / "Install Assistant (Mac).zip"
    info = zipfile.ZipInfo("Install Assistant.command")
    info.external_attr = 0o755 << 16
    info.create_system = 3
    with zipfile.ZipFile(mac_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(info, MAC.format(token=token, raw=RAW))

    print(f"Built:\n  {windows}\n  {mac_zip}\n\nBoth hold the Roofr token. Share them with staff only.")


if __name__ == "__main__":
    main()
