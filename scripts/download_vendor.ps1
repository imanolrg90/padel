# Script para descargar assets de FullCalendar localmente
# Descarga assets vendor localmente (FullCalendar y Chart.js)
$fcOut = Join-Path $PSScriptRoot "..\static\vendor\fullcalendar"
$chartOut = Join-Path $PSScriptRoot "..\static\vendor\chartjs"

foreach ($d in @($fcOut, $chartOut)) { if (!(Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }

$baseFC = "https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8"
$baseChart = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist"

$files = @(
  @{ url = "$baseFC/main.min.css"; out = Join-Path $fcOut "main.min.css" },
  @{ url = "$baseFC/index.global.min.js"; out = Join-Path $fcOut "index.global.min.js" },
  @{ url = "$baseChart/chart.umd.min.js"; out = Join-Path $chartOut "chart.umd.min.js" }
)

foreach ($f in $files) {
  Write-Host "Descargando $($f.url) -> $($f.out)"
  try {
    Invoke-WebRequest -Uri $f.url -OutFile $f.out -UseBasicParsing -ErrorAction Stop
    Write-Host "OK: $($f.out)"
  } catch {
    Write-Warning "No se pudo descargar $($f.url): $_"
  }
}

Write-Host "Descarga completa. Archivos en:"
Write-Host " - $fcOut"
Write-Host " - $chartOut"
