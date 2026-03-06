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
    param([string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Falha em: git $($Args -join ' ')"
    }
}

function Run-Gh {
    param([string[]]$Args)
    & $ghPath @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Falha em: gh $($Args -join ' ')"
    }
}

$notesPath = Join-Path (Get-Location) $NotesFile
if (-not (Test-Path $notesPath)) {
    throw "Arquivo de notas não encontrado: $NotesFile"
}

Invoke-Step "Verificando autenticação gh" {
    Run-Gh -Args @("auth", "status")
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
            Run-Git -Args @("add", "-A")
            Run-Git -Args @("commit", "-m", $CommitMessage)
        }
    }
    else {
        Write-Host "Sem alterações pendentes para commit."
    }
}

if (-not $NoPushMain) {
    Invoke-Step "Enviando branch main" {
        Run-Git -Args @("push", "origin", "main")
    }
}

Invoke-Step "Criando tag anotada" {
    Run-Git -Args @("tag", "-a", $ReleaseVersion, "-m", "$ReleaseVersion")
}

Invoke-Step "Enviando tag" {
    Run-Git -Args @("push", "origin", $ReleaseVersion)
}

Invoke-Step "Criando release no GitHub" {
    Run-Gh -Args @(
        "release", "create", $ReleaseVersion,
        "--repo", $Repo,
        "--title", $ReleaseVersion,
        "--notes-file", $NotesFile
    )
}

Write-Host "`nRelease concluído: $ReleaseVersion"
