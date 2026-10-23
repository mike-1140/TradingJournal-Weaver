<#
TradingJournal-Weaver - Datenbank-Backup und -Wiederherstellung
===============================================================
Sichert alle Datenbanken als SQL-Dateien - die 5 Environments (Trades, Kampagnen, Kontostaende,
Trade Log, Psychologie) und die der Weboberflaeche (Benutzerkonten) - bzw. spielt die jeweils
neueste Sicherung wieder ein.

Aufruf (aus dem TradingJournal-Weaver-Ordner):
  .\db-backup.ps1                           # Backup aller vorhandenen Datenbanken
  .\db-backup.ps1 -UsbLabel "MEIN-STICK"    # Backup + Kopie auf USB-Laufwerk mit diesem Namen
  .\db-backup.ps1 -Restore -DryRun          # zeigt nur, welche Sicherung eingespielt wuerde
  .\db-backup.ps1 -Restore                  # neueste Sicherung je Datenbank einspielen (mit Rueckfrage)
  .\db-backup.ps1 -Restore -UsbLabel "MEIN-STICK"   # sucht zusaetzlich auf dem USB-Laufwerk

Zugangsdaten: DB_USER/DB_PASS/DB_HOST/DB_PORT und DB_NAME_* aus der .env dieses Ordners,
der Name der Laravel-Datenbank aus ..\TradingJournal\.env (DB_DATABASE, Standard ibkr_laravel).
Das Passwort landet nur in einer temporaeren MySQL-Optionsdatei (nicht auf der
Kommandozeile) und wird danach geloescht.

Sicherungen: database\db\<datenbank>_backup_JJJJMMTT_HHMM.sql (database\ ist gitignored).
Vor jedem Einspielen wird der aktuelle Stand der Datenbank zusaetzlich als
<datenbank>_prerestore_JJJJMMTT_HHMMSS.sql gesichert - ein versehentliches Restore ist
damit umkehrbar.
#>
param(
    [switch]$Restore,
    [switch]$DryRun,
    [string]$UsbLabel = "",
    [string]$BackupDir = (Join-Path $PSScriptRoot "database\db"),
    [string]$MysqlBin = ""
)

$ErrorActionPreference = "Stop"

function Read-DotEnv([string]$Path) {
    $Values = @{}
    if (-not (Test-Path $Path)) { return $Values }
    foreach ($Line in [System.IO.File]::ReadAllLines($Path)) {
        if ($Line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $Value = $Matches[2]
            if ($Value -match '^"(.*)"$' -or $Value -match "^'(.*)'$") { $Value = $Matches[1] }
            $Values[$Matches[1]] = $Value
        }
    }
    return $Values
}

function Find-MysqlBin([string]$Preferred) {
    $Candidates = @()
    if ($Preferred) { $Candidates += $Preferred }
    $InPath = Get-Command mysqldump.exe -ErrorAction SilentlyContinue
    if ($InPath) { $Candidates += (Split-Path $InPath.Source -Parent) }
    $Candidates += "C:\xampp\mysql\bin"
    $Candidates += Get-ChildItem "C:\Program Files\MySQL\MySQL Server *\bin" -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object { $_.FullName }
    foreach ($Dir in $Candidates) {
        if ((Test-Path (Join-Path $Dir "mysqldump.exe")) -and (Test-Path (Join-Path $Dir "mysql.exe"))) { return $Dir }
    }
    throw "mysqldump.exe/mysql.exe nicht gefunden - Ordner per -MysqlBin angeben (z.B. C:\xampp\mysql\bin)."
}

function Get-UsbDir([string]$Label) {
    if (-not $Label) { return $null }
    $Volume = Get-Volume -FileSystemLabel $Label -ErrorAction SilentlyContinue | Where-Object DriveLetter | Select-Object -First 1
    if (-not $Volume) {
        Write-Warning "USB-Laufwerk mit dem Namen '$Label' nicht gefunden."
        return $null
    }
    return "$($Volume.DriveLetter):\db"
}

function Invoke-Mysql([string]$Exe, [string[]]$Arguments, [string]$StdinFile = "") {
    # Start-Process statt Umleitung: PowerShell 5.1 wuerde mit > bzw. | die SQL-Daten
    # als UTF-16 umkodieren; die Eingabedatei geht so unveraendert an mysql.
    $Params = @{ FilePath = $Exe; ArgumentList = $Arguments; NoNewWindow = $true; Wait = $true; PassThru = $true }
    if ($StdinFile) { $Params.RedirectStandardInput = $StdinFile }
    $Proc = Start-Process @Params
    return $Proc.ExitCode
}

# --- Konfiguration einlesen ---------------------------------------------------
$WeaverEnv = Read-DotEnv (Join-Path $PSScriptRoot ".env")
if ($WeaverEnv.Count -eq 0) { throw ".env nicht gefunden unter $PSScriptRoot - siehe .env.example." }
$LaravelEnv = Read-DotEnv (Join-Path (Split-Path $PSScriptRoot -Parent) "TradingJournal\.env")

$Databases = @(
    $(if ($LaravelEnv["DB_DATABASE"]) { $LaravelEnv["DB_DATABASE"] } else { "ibkr_laravel" })
    $(if ($WeaverEnv["DB_NAME_MONEY"]) { $WeaverEnv["DB_NAME_MONEY"] } else { "ibkr_money" })
    $(if ($WeaverEnv["DB_NAME_PAPER"]) { $WeaverEnv["DB_NAME_PAPER"] } else { "ibkr_paper" })
    $(if ($WeaverEnv["DB_NAME_TEST"]) { $WeaverEnv["DB_NAME_TEST"] } else { "ibkr_test" })
    $(if ($WeaverEnv["DB_NAME_AUTOM_MONEY"]) { $WeaverEnv["DB_NAME_AUTOM_MONEY"] } else { "ibkr_autom_money" })
    $(if ($WeaverEnv["DB_NAME_AUTOM_PAPER"]) { $WeaverEnv["DB_NAME_AUTOM_PAPER"] } else { "ibkr_autom_paper" })
) | Select-Object -Unique

$Bin = Find-MysqlBin $MysqlBin
$MysqlDump = Join-Path $Bin "mysqldump.exe"
$Mysql = Join-Path $Bin "mysql.exe"

# Temporaere Optionsdatei: Passwort nicht auf der Kommandozeile (in der Prozessliste sichtbar)
function Format-OptionValue([string]$Value) { '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"' }
$OptionFile = Join-Path $env:TEMP ("tj-mysql-" + [guid]::NewGuid().ToString("N") + ".cnf")
$OptionText = "[client]`r`n" +
    "user=" + (Format-OptionValue $(if ($WeaverEnv["DB_USER"]) { $WeaverEnv["DB_USER"] } else { "root" })) + "`r`n" +
    "password=" + (Format-OptionValue ([string]$WeaverEnv["DB_PASS"])) + "`r`n" +
    "host=" + $(if ($WeaverEnv["DB_HOST"]) { $WeaverEnv["DB_HOST"] } else { "127.0.0.1" }) + "`r`n" +
    "port=" + $(if ($WeaverEnv["DB_PORT"]) { $WeaverEnv["DB_PORT"] } else { "3306" }) + "`r`n" +
    "default-character-set=utf8mb4`r`n"
[System.IO.File]::WriteAllText($OptionFile, $OptionText, (New-Object System.Text.UTF8Encoding $false))
$DefaultsArg = "--defaults-extra-file=`"$OptionFile`""

try {
    # Welche Datenbanken gibt es auf diesem Server tatsaechlich?
    $ListFile = Join-Path $env:TEMP ("tj-dblist-" + [guid]::NewGuid().ToString("N") + ".txt")
    $Proc = Start-Process -FilePath $Mysql -ArgumentList @($DefaultsArg, "-N", "-B", "-e", "`"SHOW DATABASES`"") `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput $ListFile
    if ($Proc.ExitCode -ne 0) { throw "Verbindung zur Datenbank fehlgeschlagen (Exit $($Proc.ExitCode)) - Zugangsdaten in .env pruefen." }
    $Existing = [System.IO.File]::ReadAllLines($ListFile) | ForEach-Object { $_.Trim() }
    Remove-Item $ListFile -Force

    $UsbDir = Get-UsbDir $UsbLabel
    if (-not (Test-Path $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }

    if (-not $Restore) {
        # --- Backup -----------------------------------------------------------
        $Stamp = Get-Date -Format "yyyyMMdd_HHmm"
        $Written = @()
        foreach ($Db in $Databases) {
            if ($Existing -notcontains $Db) {
                Write-Host "uebersprungen  $Db (existiert auf diesem Server nicht)" -ForegroundColor DarkGray
                continue
            }
            $File = Join-Path $BackupDir "${Db}_backup_$Stamp.sql"
            $Code = Invoke-Mysql $MysqlDump @($DefaultsArg, "--single-transaction", "--routines", "--triggers",
                "--result-file=`"$File`"", $Db)
            if ($Code -ne 0) { throw "Backup von $Db fehlgeschlagen (Exit $Code)." }
            Write-Host ("gesichert      {0,-20} {1:N0} KB  {2}" -f $Db, ((Get-Item $File).Length / 1KB), $File) -ForegroundColor Green
            $Written += $File
        }
        if ($UsbDir) {
            if (-not (Test-Path $UsbDir)) { New-Item -ItemType Directory -Path $UsbDir | Out-Null }
            foreach ($File in $Written) { Copy-Item $File $UsbDir }
            Write-Host "Auf USB kopiert: $UsbDir ($($Written.Count) Dateien)" -ForegroundColor Green
        }
        Write-Host "Backup abgeschlossen: $($Written.Count) Datenbanken." -ForegroundColor Cyan
        return
    }

    # --- Restore --------------------------------------------------------------
    $SearchDirs = @($BackupDir) + @($UsbDir | Where-Object { $_ -and (Test-Path $_) })
    $Pattern = '_backup_(\d{8}_\d{4})\.sql$'
    foreach ($Db in $Databases) {
        $Candidates = foreach ($Dir in $SearchDirs) {
            Get-ChildItem -Path $Dir -Filter "${Db}_backup_*.sql" -File -ErrorAction SilentlyContinue |
                ForEach-Object {
                    if ($_.Name -match ('^' + [regex]::Escape($Db) + $Pattern)) {
                        [pscustomobject]@{ Stamp = $Matches[1]; File = $_ }
                    }
                }
        }
        $Newest = $Candidates | Sort-Object Stamp -Descending | Select-Object -First 1
        Write-Host ""
        if (-not $Newest) {
            Write-Host "keine Sicherung  $Db" -ForegroundColor DarkGray
            continue
        }
        Write-Host ("neueste Sicherung fuer {0}: {1} ({2:N0} KB)" -f $Db, $Newest.File.FullName, ($Newest.File.Length / 1KB)) -ForegroundColor Cyan
        if ($DryRun) { continue }

        $Answer = Read-Host "  $Db damit UEBERSCHREIBEN? [j/N]"
        if ($Answer -notmatch '^[jJ]$') {
            Write-Host "  uebersprungen" -ForegroundColor Yellow
            continue
        }
        if ($Existing -contains $Db) {
            $SafetyFile = Join-Path $BackupDir ("${Db}_prerestore_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".sql")
            $Code = Invoke-Mysql $MysqlDump @($DefaultsArg, "--single-transaction", "--routines", "--triggers",
                "--result-file=`"$SafetyFile`"", $Db)
            if ($Code -ne 0) { throw "Sicherung des aktuellen Stands von $Db fehlgeschlagen (Exit $Code) - Restore abgebrochen." }
            Write-Host "  aktueller Stand gesichert: $SafetyFile" -ForegroundColor DarkGray
        } else {
            $Code = Invoke-Mysql $Mysql @($DefaultsArg, "-e", "`"CREATE DATABASE ``$Db`` CHARACTER SET utf8mb4`"")
            if ($Code -ne 0) { throw "Anlegen der Datenbank $Db fehlgeschlagen (Exit $Code)." }
        }
        $Code = Invoke-Mysql $Mysql @($DefaultsArg, $Db) $Newest.File.FullName
        if ($Code -ne 0) { throw "Einspielen von $Db fehlgeschlagen (Exit $Code)." }
        Write-Host "  $Db wiederhergestellt." -ForegroundColor Green
    }
    if ($DryRun) { Write-Host "`nTrockenlauf - nichts eingespielt." -ForegroundColor Cyan }
}
finally {
    Remove-Item $OptionFile -Force -ErrorAction SilentlyContinue
}
