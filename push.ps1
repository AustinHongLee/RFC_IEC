# push.ps1 - one-click: first run sets everything up, then commit & push.
# Usage:  powershell -ExecutionPolicy Bypass -File .\push.ps1
#    or:  powershell -ExecutionPolicy Bypass -File .\push.ps1 "your own message"

$ErrorActionPreference = "Continue"
$RepoUrl = "https://github.com/AustinHongLee/RFC_IEC.git"

# run from the folder this script lives in (the repo root)
Set-Location $PSScriptRoot

# 0) is git installed?
$hasGit = $false
try { git --version 2>$null | Out-Null; $hasGit = ($LASTEXITCODE -eq 0) } catch { $hasGit = $false }
if (-not $hasGit) {
  Write-Host "[ERROR] Git is not installed (or not on PATH)." -ForegroundColor Red
  Write-Host "        Install Git for Windows: https://git-scm.com/download/win" -ForegroundColor Red
  Write-Host "        Then close and reopen PowerShell and run this again." -ForegroundColor Red
  Read-Host "Press Enter to exit"; exit 1
}

# 0b) trust this folder even if .git is owned by Administrators (fixes "dubious ownership")
$safe = @(git config --global --get-all safe.directory 2>$null)
if ($safe -notcontains '*') { git config --global --add safe.directory '*' }

# 1) initialize repo on first run
git rev-parse --is-inside-work-tree 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "First run: initializing git repository..." -ForegroundColor Cyan
  git init | Out-Null
  git branch -M main
}

# 2) make sure an identity is set (needed to commit)
if (-not (git config user.name))  { git config user.name  "AustinHongLee" }
if (-not (git config user.email)) { git config user.email "lizonghong084@gmail.com" }

# 3) make sure .gitignore exists
if (-not (Test-Path ".gitignore")) {
@"
.venv/
__pycache__/
*.pyc
*.log
backup/
"@ | Out-File -FilePath ".gitignore" -Encoding ascii
}

# 4) make sure the remote is linked
git remote get-url origin 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Linking remote: $RepoUrl" -ForegroundColor Cyan
  git remote add origin $RepoUrl
}

# 5) commit if there is anything to commit
$changes = git status --porcelain
if ($changes) {
  $count = ($changes | Measure-Object -Line).Lines
  $phrases = @("save progress","routine update","tidy up","checkpoint",
               "another pass","incremental update","wip","keep it rolling","daily backup")
  $flavor  = $phrases | Get-Random
  $stamp   = Get-Date -Format "yyyy-MM-dd HH:mm"
  if ($args.Count -gt 0) { $msg = ($args -join " ") } else { $msg = "update: $stamp ($count files) - $flavor" }
  Write-Host "Committing $count change(s)..." -ForegroundColor Cyan
  git add -A
  git commit -m "$msg" | Out-Null
} else {
  Write-Host "No new changes to commit." -ForegroundColor Yellow
  $msg = "(no new commit)"
}

# 6) push (first time may need to merge an existing README on the remote)
git branch -M main 2>$null
$branch = (git rev-parse --abbrev-ref HEAD)
Write-Host "Pushing to origin/$branch ..." -ForegroundColor Cyan
git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
  Write-Host "Push rejected - merging remote first, then retrying..." -ForegroundColor Yellow
  git pull origin $branch --allow-unrelated-histories --no-edit
  git push -u origin $branch
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Push failed. Check your GitHub login / network, then run again." -ForegroundColor Red
    Read-Host "Press Enter to exit"; exit 1
  }
}

Write-Host ""
Write-Host "Done  ->  $msg" -ForegroundColor Green
Read-Host "Press Enter to exit"
