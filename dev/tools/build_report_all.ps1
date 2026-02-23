$ErrorActionPreference = "Stop"

$root = "C:\Users\briay\Financial\Pesa-AI-Logger"
$docs = Join-Path $root "docs"
$miktexBin = "$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64"
$pdflatex = Join-Path $miktexBin "pdflatex.exe"
$initexmf = Join-Path $miktexBin "initexmf.exe"

if (-not (Test-Path $pdflatex)) {
    Write-Error "pdflatex not found at $pdflatex. Install MiKTeX first."
}

if (Test-Path $initexmf) {
    & $initexmf --set-config-value [MPM]AutoInstall=1 | Out-Null
}

Set-Location $docs
& $pdflatex -interaction=nonstopmode -halt-on-error MPESA_Hybrid_System_Report.tex
& $pdflatex -interaction=nonstopmode -halt-on-error MPESA_Hybrid_System_Report.tex

Write-Output "Built PDF: $docs\MPESA_Hybrid_System_Report.pdf"
