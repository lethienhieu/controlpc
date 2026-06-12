<#
  download_models.ps1 — fetch the local GGUF model(s) CONTROLPC runs on.

  WHY THIS SCRIPT EXISTS
  ----------------------
  The model weights (several GB each) are NOT committed to git. This script
  downloads them into the local `models\` folder so the GPU llama-server can
  load them. The brain/app stays fully local — no Ollama, no cloud inference.

  HOW TO USE
  ----------
  1. Open the $MODELS table below.
  2. For each model you want, paste its DIRECT HuggingFace download URL into `Url`.
     A direct URL looks like:
       https://huggingface.co/<owner>/<repo>/resolve/main/<file>.gguf?download=true
     (Open the model on huggingface.co -> "Files and versions" -> click the .gguf
      -> copy the "download" link.)
  3. Run from the repo root in PowerShell:
       powershell -ExecutionPolicy Bypass -File .\scripts\download_models.ps1
  4. After it finishes, pick the model in the app (Settings -> Model), or set it in
     config\model_settings.json.

  NOTES
  -----
  * Entries with an empty Url are skipped with a warning (fill them in to enable).
  * Existing files are skipped (delete a file to re-download it).
  * The "active" model shipped in config is the Qwen3.5-9B build; it is a
    community/custom model, so you must paste its URL yourself.
#>

$ErrorActionPreference = "Stop"

# Resolve repo root from this script's location (scripts\ -> repo root).
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$ModelsDir = Join-Path $RepoRoot "models"

# ----------------------------------------------------------------------------
# CONFIG: fill in the Url for each model you want to download.
# ----------------------------------------------------------------------------
$MODELS = @(
    @{
        Name = "Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED.Q5_K_M.gguf"
        # Active default model (community/custom build). Paste its HF download URL:
        Url  = ""
    },
    @{
        Name = "Qwen_Qwen3-8B-Q5_K_M.gguf"
        # Official Qwen3-8B GGUF (e.g. from a community GGUF repo). Paste URL:
        Url  = ""
    },
    @{
        Name = "gemma-4-E4B-it-Q4_K_M.gguf"
        # Small/fast fallback model. Paste URL:
        Url  = ""
    }
)
# ----------------------------------------------------------------------------

Write-Host "CONTROLPC model downloader" -ForegroundColor Cyan
Write-Host "Target folder: $ModelsDir`n"

if (-not (Test-Path $ModelsDir)) {
    New-Item -ItemType Directory -Path $ModelsDir | Out-Null
}

$downloaded = 0
$skipped    = 0

foreach ($m in $MODELS) {
    $dest = Join-Path $ModelsDir $m.Name

    if (Test-Path $dest) {
        Write-Host "[skip] already present: $($m.Name)" -ForegroundColor DarkGray
        $skipped++
        continue
    }
    if ([string]::IsNullOrWhiteSpace($m.Url)) {
        Write-Host "[skip] no URL set for: $($m.Name) (edit this script to add one)" -ForegroundColor Yellow
        $skipped++
        continue
    }

    Write-Host "[get ] $($m.Name)" -ForegroundColor Green
    try {
        # curl.exe streams large files more reliably than Invoke-WebRequest, and
        # "-C -" resumes a partially downloaded file instead of restarting at 0.
        $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
        if ($curl) {
            & curl.exe -L --fail -C - -o $dest $m.Url
            if ($LASTEXITCODE -ne 0) { throw "curl exited with code $LASTEXITCODE" }
        } else {
            Invoke-WebRequest -Uri $m.Url -OutFile $dest
        }
        Write-Host "       done -> $dest" -ForegroundColor Green
        $downloaded++
    } catch {
        # Keep the partial file so a re-run can resume it with curl -C -.
        Write-Host "       FAILED (re-run to resume): $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`nDone. Downloaded: $downloaded, skipped: $skipped." -ForegroundColor Cyan
Write-Host "Next: open the app -> Settings -> Model to select one, or edit config\model_settings.json."
