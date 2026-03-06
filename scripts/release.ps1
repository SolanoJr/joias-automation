param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseVersion,

    [string]$Repo = "SolanoJr/joias-automation",

    [string]$NotesFile,

    [string]$CommitMessage,

    [switch]$NoCommit,

    [switch]$NoPushMain,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ReleaseVersion)) {
    throw "Parâmetro obrigatório ausente: -ReleaseVersion"
}

if ($ReleaseVersion -notmatch "^v") {
    $ReleaseVersion = "v$ReleaseVersion"
}

if (-not $NotesFile) {
    $NotesFile = "docs/release_notes_$ReleaseVersion.md"
}

if (-not $CommitMessage) {
    $CommitMessage = "chore: release $ReleaseVersion"
}

$ghPath = "C:\Program Files\GitHub CLI\gh.exe"
if (-not (Test-Path $ghPath)) {
    throw "GitHub CLI não encontrado em '$ghPath'."
}

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    Write-Host "`n==> $Label"
    if ($DryRun) {
        Write-Host "[DRY-RUN] etapa simulada"
        return
    }

    & $Action
}

function Run-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Falha em: git $($GitArgs -join ' ')"
    }
}

function Run-Gh {
    param([string[]]$GhArgs)
    & $ghPath @GhArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Falha em: gh $($GhArgs -join ' ')"
    }
}

$notesPath = Join-Path (Get-Location) $NotesFile
if (-not (Test-Path $notesPath)) {
    throw "Arquivo de notas não encontrado: $NotesFile"
}

Invoke-Step "Verificando autenticação gh" {
    Run-Gh -GhArgs @("auth", "status")
}

$localTag = "$(& git tag --list $ReleaseVersion)"
if ($localTag -match "\S") {
    throw "Tag local já existe: $ReleaseVersion"
}

$remoteTag = "$(& git ls-remote --tags origin $ReleaseVersion)"
if ($remoteTag -match "\S") {
    throw "Tag remota já existe: $ReleaseVersion"
}

if (-not $NoCommit) {
    $status = "$(& git status --porcelain)"
    if ($status -match "\S") {
        Invoke-Step "Commitando alterações pendentes" {
            Run-Git -GitArgs @("add", "-A")
            Run-Git -GitArgs @("commit", "-m", $CommitMessage)
        }
    }
    else {
        Write-Host "Sem alterações pendentes para commit."
    }
}

if (-not $NoPushMain) {
    Invoke-Step "Enviando branch main" {
        Run-Git -GitArgs @("push", "origin", "main")
    }
}

Invoke-Step "Criando tag anotada" {
    Run-Git -GitArgs @("tag", "-a", $ReleaseVersion, "-m", "$ReleaseVersion")
}

Invoke-Step "Enviando tag" {
    Run-Git -GitArgs @("push", "origin", $ReleaseVersion)
}

Invoke-Step "Criando release no GitHub" {
    Run-Gh -GhArgs @(
        "release", "create", $ReleaseVersion,
        "--repo", $Repo,
        "--title", $ReleaseVersion,
        "--notes-file", $NotesFile
    )
}

Write-Host "`nRelease concluído: $ReleaseVersion"
