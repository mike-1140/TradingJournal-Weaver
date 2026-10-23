# TradingJournal-Weaver - einmalig ausfuehren, um eine Desktop-Verknuepfung anzulegen.
#
# Doppelklick auf die erzeugte Verknuepfung oeffnet PowerShell, wechselt in den
# TradingJournal-Weaver-Ordner und aktiviert die venv - danach z.B. direkt "python run_pipeline.py"
# eintippen.
#
# Aufruf (einmalig, aus dem TradingJournal-Weaver-Ordner heraus):
#   . .\create-desktop-shortcut.ps1
# oder im Explorer: Rechtsklick auf die Datei -> "Mit PowerShell ausfuehren"
#
# Ein einfacher Doppelklick auf DIESE Datei (create-desktop-shortcut.ps1) startet sie
# NICHT automatisch - .ps1-Dateien oeffnen sich per Doppelklick standardmaessig in einem
# Text-Editor (Windows-Sicherheitsmechanismus). Genau deshalb legt dieses Skript stattdessen
# eine echte Desktop-Verknuepfung (.lnk) an, die per Doppelklick zuverlaessig funktioniert.

$WeaverDir = $PSScriptRoot
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "TradingJournal-Weaver Pipeline.lnk"

$VenvActivate = Join-Path $WeaverDir ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    Write-Warning "Keine .venv gefunden unter $VenvActivate - siehe docs/handbuch/technik/50-installation-weaver.md Schritt 2 (python -m venv .venv). Verknuepfung wird trotzdem angelegt."
}

# Apostroph im Pfad (z.B. Benutzerordner "O'Brien") verdoppeln, sonst endet der String zu frueh
$InnerCommand = "Set-Location '$($WeaverDir.Replace("'", "''"))'; . '$($VenvActivate.Replace("'", "''"))'"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -Command `"$InnerCommand`""
$Shortcut.WorkingDirectory = $WeaverDir
$Shortcut.IconLocation = "powershell.exe,0"
$Shortcut.Description = "TradingJournal-Weaver: PowerShell mit aktivierter venv oeffnen"
$Shortcut.Save()

Write-Host "Desktop-Verknuepfung erstellt: $ShortcutPath" -ForegroundColor Green
Write-Host "Doppelklick darauf oeffnet PowerShell, bereits im TradingJournal-Weaver-Ordner mit aktiver venv." -ForegroundColor Green
