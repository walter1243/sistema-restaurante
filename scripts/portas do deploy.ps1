param(
    [int[]]$Ports = @(8012, 8011, 8000, 8010, 8090),
    [int]$TimeoutSeconds = 4
)

$ErrorActionPreference = 'SilentlyContinue'

function Test-JsonHealth {
    param([int]$Port)

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds "http://127.0.0.1:$Port/health"
        if ($resp.StatusCode -ne 200) { return $false }
        $body = $resp.Content | ConvertFrom-Json
        return ($body.ok -eq $true)
    } catch {
        return $false
    }
}

function Test-OpenApiPath {
    param(
        [int]$Port,
        [string]$Path
    )

    try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec $TimeoutSeconds "http://127.0.0.1:$Port/openapi.json"
        if ($resp.StatusCode -ne 200) { return $false }
        $json = $resp.Content | ConvertFrom-Json
        return ($null -ne $json.paths.$Path)
    } catch {
        return $false
    }
}

Write-Output "=== PORTAS DO DEPLOY ==="
Write-Output ""

$results = @()
foreach ($port in $Ports) {
    $health = Test-JsonHealth -Port $port
    $temDespachar = $false
    $temDespachoAuto = $false

    if ($health) {
        $temDespachar = Test-OpenApiPath -Port $port -Path '/api/pedidos/{pedido_id}/despachar'
        $temDespachoAuto = Test-OpenApiPath -Port $port -Path '/api/admin/pedidos/{slug}/{pedido_id}/despacho-automatico'
    }

    $compat = ($health -and $temDespachar)
    $results += [PSCustomObject]@{
        Port = $port
        Health = $health
        CompatDespachar = $temDespachar
        CompatDespachoAuto = $temDespachoAuto
        Url = "http://127.0.0.1:$port"
        Score = if ($compat) { 2 } elseif ($health) { 1 } else { 0 }
    }
}

$results |
    Sort-Object -Property Score, Port -Descending |
    Select-Object Port, Health, CompatDespachar, CompatDespachoAuto, Url |
    Format-Table -AutoSize | Out-String | Write-Output

$melhor = $results | Sort-Object -Property Score, Port -Descending | Select-Object -First 1

if (-not $melhor -or -not $melhor.Health) {
    Write-Output "Nenhuma API saudável encontrada nas portas verificadas."
    Write-Output "Dica: rode .\\scripts\\start_api_safe.ps1"
    exit 1
}

Write-Output "API recomendada agora: $($melhor.Url)"

if (-not $melhor.CompatDespachar) {
    Write-Output "Aviso: API saudável, mas sem endpoint novo /api/pedidos/{pedido_id}/despachar"
}

Write-Output ""
Write-Output "Links locais sugeridos:"
Write-Output "- Cardápio: index.html?slug=SEU_SLUG&mesa=1&api=$($melhor.Url)"
Write-Output "- Admin:    admin.html?slug=SEU_SLUG&token=SEU_TOKEN&api=$($melhor.Url)"
Write-Output "- Motoboy:  entregador.html?slug=SEU_SLUG&token=TOKEN_MOTOBOY&api=$($melhor.Url)"

Write-Output ""
Write-Output "Checklist rápido p/ deploy (Vercel):"
Write-Output "1) Definir NEXT_PUBLIC_API_URL (ou VITE_API_URL) apontando para API pública"
Write-Output "2) Backend com CORS liberando domínio *.vercel.app e domínio final"
Write-Output "3) Nunca usar portas locais (:8000/:8012) em produção"

exit 0
