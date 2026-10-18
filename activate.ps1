# xml_proj - Komfort-Skript: wechselt in dieses Verzeichnis und aktiviert die venv.
#
# WICHTIG: Immer MIT vorangestelltem Punkt aufrufen (Dot-Sourcing), sonst laufen
# Verzeichniswechsel und venv-Aktivierung nur innerhalb des Skripts ab und wirken danach
# nicht mehr im aufrufenden Fenster:
#
#   . .\activate.ps1
#
# Funktioniert unabhaengig davon, wo der Monorepo-Root-Ordner liegt (siehe
# docs/handbuch/technik/40-installation-windows.md - Pfad ist frei waehlbar), da relativ zum eigenen Skript-Ort
# (xml_proj-Ordner selbst) aufgeloest wird.
#
# Falls PowerShell das Ausfuehren lokaler Skripte blockiert (Fehler in etwa: "kann nicht
# geladen werden, da die Ausfuehrung von Skripts auf diesem System deaktiviert ist"),
# einmalig als Administrator:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

Set-Location $PSScriptRoot

$VenvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"

if (Test-Path $VenvActivate) {
    . $VenvActivate
    Write-Host "xml_proj bereit: $PSScriptRoot (venv aktiv)" -ForegroundColor Green
} else {
    Write-Warning "Keine .venv gefunden unter $VenvActivate - siehe docs/handbuch/technik/50-installation-xml-proj.md Schritt 2 (python -m venv .venv)."
}
