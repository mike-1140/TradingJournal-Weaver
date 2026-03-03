@echo off
setlocal enabledelayedexpansion

:: === Konfiguration ===
set MYSQL_BIN="C:\xampp\mysql\bin\mysql.exe"
set DB_NAME=ibkr
set DB_USER=root
set DB_PASSWORD=
set LOCAL_BACKUP_DIR=%~dp0db
set LOCAL_RESTORE_FILE=%LOCAL_BACKUP_DIR%\%DB_NAME%_backup.sql
set USB_DRIVE=

:: === USB-Stick mit Volume "Mike - BIG" suchen ===
echo Suche nach USB-Stick mit Volumennamen "Mike - BIG" ...

for /f "tokens=1 delims=:" %%A in ('wmic logicaldisk where "VolumeName='Mike - BIG'" get DeviceID ^| find ":"') do (
    set USB_DRIVE=%%A:
)

if not defined USB_DRIVE (
    echo FEHLER: USB-Stick mit Volume "Mike - BIG" wurde nicht gefunden!
    pause
    exit /b
)

:: === Prüfen, ob Backup-Datei existiert ===
set USB_BACKUP_FILE=!USB_DRIVE!\db\%DB_NAME%_backup.sql

if not exist "!USB_BACKUP_FILE!" (
    echo FEHLER: Backup-Datei nicht gefunden: !USB_BACKUP_FILE!
    pause
    exit /b
)

:: === Lokalen db-Ordner sicherstellen ===
if not exist "%LOCAL_BACKUP_DIR%" (
    mkdir "%LOCAL_BACKUP_DIR%"
)

:: === Datei vom Stick ins Projekt kopieren ===
echo Kopiere Backup-Datei von USB-Stick ...
copy "!USB_BACKUP_FILE!" "%LOCAL_RESTORE_FILE%"

if %errorlevel% neq 0 (
    echo FEHLER beim Kopieren!
    pause
    exit /b
)

:: === Wiederherstellen in MySQL ===
echo Stelle Datenbank "%DB_NAME%" wieder her ...
%MYSQL_BIN% -u %DB_USER% -p%DB_PASSWORD% %DB_NAME% < "%LOCAL_RESTORE_FILE%"

if %errorlevel%==0 (
    echo Wiederherstellung erfolgreich.
) else (
    echo FEHLER bei der Wiederherstellung!
)

endlocal
pause