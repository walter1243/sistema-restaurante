param(
    [string]$WorkspacePath = (Get-Location).Path,
    [string]$PythonPath = "",
    [int[]]$PreferredPorts = @(8012, 8011, 8000, 8090),
    [int]$HealthTimeoutSeconds = 2,
    [int]$StartupWaitSeconds = 18,
    [string]$RequiredOpenApiPath = "/api/pedidos/{pedido_id}/despachar"
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-ApiHealth {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 2
    )

    try {
        $url = "http://127.0.0.1:$Port/health"
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds $url
        if ($resp.StatusCode -eq 200 -and ($resp.Content -like '*"ok":true*')) {
            return $true
        }
    } catch {}

    return $false
}

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen
    return $null -ne $conn
}

function Test-ApiCompatibility {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 3,
        [string]$RequiredPath = ""
    )

    if (-not (Test-ApiHealth -Port $Port -TimeoutSeconds $TimeoutSeconds)) {
        return $false
    }

    if (-not $RequiredPath) {
        return $true
    }

    try {
        $url = "http://127.0.0.1:$Port/openapi.json"
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds $url
        if ($resp.StatusCode -ne 200) { return $false }
        $json = $resp.Content | ConvertFrom-Json
        return $null -ne $json.paths.$RequiredPath
    } catch {
        return $false
    }
}

function Resolve-PythonPath {
    param(
        [string]$Workspace,
        [string]$ExplicitPython
    )

    if ($ExplicitPython -and (Test-Path $ExplicitPython)) {
        return $ExplicitPython
    }

    $venvPython = Join-Path $Workspace '.venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        return $venvPython
    }

    return "python"
}

$workspaceResolved = Resolve-Path $WorkspacePath
$pythonExe = Resolve-PythonPath -Workspace $workspaceResolved -ExplicitPython $PythonPath

Write-Output "[safe-start] Workspace: $workspaceResolved"
Write-Output "[safe-start] Python: $pythonExe"
Write-Output "[safe-start] Política: não derrubar processo existente."

foreach ($port in $PreferredPorts) {
    if (Test-ApiCompatibility -Port $port -TimeoutSeconds $HealthTimeoutSeconds -RequiredPath $RequiredOpenApiPath) {
        Write-Output "[safe-start] API saudável e compatível em http://127.0.0.1:$port (sem reiniciar)."
        Write-Output "[safe-start] Use: index.html?slug=SEU_SLUG&mesa=1&api=http://127.0.0.1:$port"
        Write-Output "[safe-start] Use: admin.html?slug=SEU_SLUG&token=SEU_TOKEN&api=http://127.0.0.1:$port"
        exit 0
    }
}

Write-Output "[safe-start] Nenhuma API compatível encontrada nas portas preferidas."

$portaEscolhida = $null
foreach ($port in $PreferredPorts) {
    if (-not (Test-PortListening -Port $port)) {
        $portaEscolhida = $port
        break
    }
}

if (-not $portaEscolhida) {
    for ($p = 8100; $p -le 8120; $p++) {
        if (-not (Test-PortListening -Port $p)) {
            $portaEscolhida = $p
            break
        }
    }
}

if (-not $portaEscolhida) {
    Write-Output "[safe-start] Nenhuma porta disponível encontrada sem interromper serviços."
    exit 1
}

Write-Output "[safe-start] Nenhuma API saudável encontrada. Iniciando nova instância em $portaEscolhida..."

$proc = Start-Process -FilePath $pythonExe `
    -ArgumentList @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$portaEscolhida") `
    -WorkingDirectory $workspaceResolved `
    -PassThru

if (-not $proc) {
    Write-Output "[safe-start] Falha ao iniciar uvicorn."
    exit 1
}

$ok = $false
for ($i = 0; $i -lt $StartupWaitSeconds; $i++) {
    Start-Sleep -Seconds 1
    if (Test-ApiCompatibility -Port $portaEscolhida -TimeoutSeconds $HealthTimeoutSeconds -RequiredPath $RequiredOpenApiPath) {
        $ok = $true
        break
    }
}

if (-not $ok) {
    Write-Output "[safe-start] Instância iniciada (PID=$($proc.Id)), mas a compatibilidade da API não confirmou no prazo."
    Write-Output "[safe-start] Verifique: http://127.0.0.1:$portaEscolhida/health e /openapi.json"
    exit 1
}

Write-Output "[safe-start] API ativa em http://127.0.0.1:$portaEscolhida (PID=$($proc.Id))."
Write-Output "[safe-start] Use: index.html?slug=SEU_SLUG&mesa=1&api=http://127.0.0.1:$portaEscolhida"
Write-Output "[safe-start] Use: admin.html?slug=SEU_SLUG&token=SEU_TOKEN&api=http://127.0.0.1:$portaEscolhida"
exit 0
