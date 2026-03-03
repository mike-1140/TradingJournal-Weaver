
@echo off
setlocal enabledelayedexpansion
:: === Konfiguration ===
set MYSQL_BIN="C:\xampp\mysql\bin\mysqldump.exe"
set DB_NAME=ibkr
set DB_USER=root
set DB_PASSWORD=
set BACKUP_DIR=%~dp0db
set BACKUP_FILE=%BACKUP_DIR%\%DB_NAME%_backup.sql

:: === Backup-Verzeichnis prüfen ===
if not exist %BACKUP_DIR% (
    mkdir %BACKUP_DIR%
)

:: === Backup ausführen ===
echo Erstelle Backup von Datenbank "%DB_NAME%" ...
%MYSQL_BIN% -u %DB_USER% -p%DB_PASSWORD% %DB_NAME% > %BACKUP_FILE%

if %errorlevel%==0 (
    echo Backup erfolgreich: %BACKUP_FILE%
) else (
    echo FEHLER beim Backup!
    pause
    exit /b
)

:: === Benutzerabfrage ===
set /p USBFRAGE=Backup auf USB-Stick "Mike - BIG" kopieren (j/n)?

if /i "!USBFRAGE!"=="j" (
    echo Suche nach USB-Stick mit Volumennamen "Mike - BIG" ...

    for /f "tokens=1 delims=:" %%A in ('wmic logicaldisk where "VolumeName='Mike - BIG'" get DeviceID ^| find ":"') do (
        set USB_DRIVE=%%A:
    )

    if defined USB_DRIVE (
        echo USB-Stick gefunden: !USB_DRIVE!
        if not exist "!USB_DRIVE!\db" (
            mkdir "!USB_DRIVE!\db"
        )
        echo Kopiere Datei nach !USB_DRIVE!\db\%DB_NAME%_backup.sql ...
        copy "%BACKUP_FILE%" "!USB_DRIVE!\db\%DB_NAME%_backup.sql"
        echo Backup wurde auf USB-Stick kopiert.
    ) else (
        echo FEHLER: USB-Stick mit Volume "Mike - BIG" nicht gefunden!
    )
) else (
    echo Keine USB-Kopie erstellt.
)

endlocal
pause
