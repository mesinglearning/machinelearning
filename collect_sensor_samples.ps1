param(
    [string]$Label = "busuk",
    [int]$Samples = 12,
    [int]$IntervalSeconds = 10,
    [string]$ServerUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"

$datasetDir = Join-Path $PSScriptRoot "data"
if (-not (Test-Path $datasetDir)) {
    New-Item -ItemType Directory -Path $datasetDir | Out-Null
}

$outputPath = Join-Path $datasetDir "sensor_calibration_samples.csv"
$hasHeader = Test-Path $outputPath

if (-not $hasHeader) {
    "label,captured_at,temperature,humidity,gas_status,gas_value,source,age_seconds,is_stale" |
        Out-File -FilePath $outputPath -Encoding utf8
}

for ($i = 1; $i -le $Samples; $i++) {
    $response = Invoke-RestMethod -Uri "$ServerUrl/api/sensor/latest" -TimeoutSec 8
    $data = $response.data

    $row = [PSCustomObject]@{
        label = $Label
        captured_at = (Get-Date).ToString("s")
        temperature = $data.temperature
        humidity = $data.humidity
        gas_status = $data.gas_status
        gas_value = $data.gas_value
        source = $data.source
        age_seconds = $data.age_seconds
        is_stale = $data.is_stale
    }

    $line = '"{0}","{1}",{2},{3},"{4}",{5},"{6}",{7},{8}' -f `
        $row.label,
        $row.captured_at,
        $row.temperature,
        $row.humidity,
        $row.gas_status,
        $row.gas_value,
        $row.source,
        $row.age_seconds,
        $row.is_stale

    $line | Out-File -FilePath $outputPath -Append -Encoding utf8
    Write-Host "[$i/$Samples] $Label gas=$($row.gas_value) status=$($row.gas_status) age=$($row.age_seconds)s stale=$($row.is_stale)"

    if ($i -lt $Samples) {
        Start-Sleep -Seconds $IntervalSeconds
    }
}

Write-Host "Saved samples to $outputPath"
