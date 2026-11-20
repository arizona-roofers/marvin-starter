# One-step install for Windows: gets Git, Python, Claude Code and the Claude app,
# downloads the starter, then opens the setup page in the browser.
#
# Run it by double-clicking the install file Travis sent you, or paste this in PowerShell:
#   irm https://raw.githubusercontent.com/arizona-roofers/marvin-starter/master/install/install.ps1 | iex
#
# Safe to run again: it skips what is already installed and keeps your notes.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = 'https://github.com/arizona-roofers/marvin-starter'
$Branch = 'master'
$Starter = Join-Path $HOME '.assistant-starter'

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Write-Note($text) { Write-Host "    $text" -ForegroundColor Yellow }

# Tools installed a moment ago are on the registry PATH but not in this window yet.
function Update-PathFromRegistry {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machine;$user;$HOME\.local\bin"
}

function Test-Tool($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# The "python" Windows ships is a stub that opens the Store. Only a real one counts.
function Get-Python {
  foreach ($candidate in @('python', 'py', 'python3')) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd -or $cmd.Source -like '*\WindowsApps\*') { continue }
    try {
      $version = & $cmd.Source --version 2>$null
      if ($version -match 'Python 3') { return $cmd.Source }
    } catch { }
  }
  return $null
}

function Install-WithWinget($id, $label) {
  if (-not (Test-Tool 'winget')) {
    Write-Note "$label is missing and this PC has no winget to install it. Install 'App Installer' from the Microsoft Store, then run this again."
    return $false
  }
  Write-Host "    Installing $label (this can take a minute)..."
  winget install --id $id -e --silent --scope user --accept-source-agreements --accept-package-agreements | Out-Null
  if ($LASTEXITCODE -ne 0) {
    # Some packages have no per-user installer; try once more the normal way.
    winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
  }
  Update-PathFromRegistry
  return $true
}

Write-Host "`n  Setting up your AI assistant. This takes about five minutes." -ForegroundColor White
Write-Host "  If Windows asks for permission to install something, click Yes.`n"
Update-PathFromRegistry

Write-Step 'Git'
if (Test-Tool 'git') { Write-Ok 'already installed' }
else { [void](Install-WithWinget 'Git.Git' 'Git'); if (Test-Tool 'git') { Write-Ok 'installed' } else { Write-Note 'not installed; carrying on without it' } }

Write-Step 'Python'
$python = Get-Python
if ($python) { Write-Ok 'already installed' }
else {
  [void](Install-WithWinget 'Python.Python.3.13' 'Python')
  $python = Get-Python
  if (-not $python) {
    $guess = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($guess) { $python = $guess.FullName }
  }
  if ($python) { Write-Ok 'installed' }
  else { throw 'Python could not be installed. Install it from https://www.python.org/downloads/ and run this again.' }
}

Write-Step 'Claude Code'
if (Test-Tool 'claude') { Write-Ok 'already installed' }
else {
  Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
  Update-PathFromRegistry
  if (Test-Tool 'claude') { Write-Ok 'installed' } else { Write-Note 'installed, but this window cannot see it yet. That is fine.' }
}

Write-Step 'Claude desktop app'
$hasApp = (Test-Path "$env:LOCALAPPDATA\AnthropicClaude\claude.exe") -or [bool](Get-StartApps | Where-Object { $_.Name -eq 'Claude' })
if ($hasApp) { Write-Ok 'already installed' }
else {
  [void](Install-WithWinget 'Anthropic.Claude' 'the Claude app')
  $hasApp = (Test-Path "$env:LOCALAPPDATA\AnthropicClaude\claude.exe") -or [bool](Get-StartApps | Where-Object { $_.Name -eq 'Claude' })
  if ($hasApp) { Write-Ok 'installed' }
  else { Write-Note 'could not install it automatically. Download it from https://claude.ai/download after setup.' }
}

Write-Step 'Downloading the starter'
if (Test-Path (Join-Path $Starter '.git')) {
  git -C $Starter pull --ff-only --quiet
  if ($LASTEXITCODE -ne 0) { Write-Note 'could not update; using the copy already here' } else { Write-Ok 'updated' }
}
elseif (Test-Tool 'git') {
  if (Test-Path $Starter) { Remove-Item $Starter -Recurse -Force }
  git clone --quiet --depth 1 --branch $Branch "$Repo.git" $Starter
  if ($LASTEXITCODE -ne 0) { throw 'The starter could not be downloaded. Check your internet connection and run this again.' }
  Write-Ok 'downloaded'
}
else {
  $zip = Join-Path $env:TEMP 'assistant-starter.zip'
  $unpacked = Join-Path $env:TEMP 'assistant-starter-unpacked'
  Invoke-WebRequest "$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
  if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
  Expand-Archive $zip -DestinationPath $unpacked
  if (Test-Path $Starter) { Remove-Item $Starter -Recurse -Force }
  Move-Item (Get-ChildItem $unpacked -Directory | Select-Object -First 1).FullName $Starter
  Remove-Item $zip, $unpacked -Recurse -Force -ErrorAction SilentlyContinue
  Write-Ok 'downloaded'
}

Write-Step 'Opening setup in your browser'
$env:ASSISTANT_USER_NAME = (Get-Culture).TextInfo.ToTitleCase(($env:USERNAME -split '[\s._]')[0].ToLower())
& $python (Join-Path $Starter 'install\wizard.py')
