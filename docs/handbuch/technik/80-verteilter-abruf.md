# Verteilter Abruf — minimaler Client für den Datenabruf

**Nur relevant, wenn du bereits [Server-Betrieb — TradingJournal auf einem eigenen Server](70-server-betrieb.md) umgesetzt
hast** und zusätzlich von einem zweiten, leichtgewichtigen Gerät (Reise-Notebook, Tablet
mit Windows, etc.) aus IBKR-Daten abrufen und zum Server übertragen willst — **ohne** auf
diesem zweiten Gerät die komplette App (MySQL/PHP/Apache/Node.js) zu installieren.

**Typisches Szenario:** Dein Hauptrechner (der sonst Mail-Abruf + Import erledigt) ist
unterwegs nicht verfügbar oder ausgeschaltet. Der Server läuft aber weiter und soll
trotzdem täglich neue Daten bekommen.

## Warum das minimal bleiben kann

`get_flexquery_emails.py`/`get_flexquery_api.py` laden nur Rohdaten (XML/CSV) in einen
lokalen Ordner herunter — sie brauchen **keine** Datenbankverbindung und kein
`accounts.toml`/`pipeline.toml`. Das komplette User/Environment-Routing passiert erst beim
`import`-Step, der auf dem Server läuft. Der Client braucht deshalb nur:

- Python 3.14
- Zwei Pakete: `python-dotenv`, `requests` (**nicht** die volle `requirements.txt` — die
  zieht zusätzlich `pandas`/`sqlalchemy`/`pymysql`, für reines Abrufen unnötig)
- Eine `.env` mit den IMAP-/API-Zugangsdaten
- Einen SSH-Client, um die Dateien zum Server zu übertragen

Kein MySQL, kein PHP, kein Apache, kein Node.js.

---

## Server-Seite: SSH-Empfang einrichten (einmalig)

Auf dem Server, der bereits nach „Server-Betrieb — TradingJournal auf einem eigenen Server“ eingerichtet ist —
**[PowerShell – Administrator]**:
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

New-NetFirewallRule -DisplayName "SSH (VPN only)" `
  -Direction Inbound -LocalPort 22 -Protocol TCP `
  -RemoteAddress 100.64.0.0/10 -Action Allow
```
(Adressbereich `100.64.0.0/10` ist Tailscales Standard — bei anderem VPN entsprechend anpassen.)

---

## Client-Seite: Minimal-Installation

### 1. Python 3.14

Download: https://www.python.org/downloads/ — **"Add python.exe to PATH"** +
**"Install for all users"** aktivieren.

### 2. Git for Windows

Download: https://git-scm.com/install/windows („Click here to download“), Standardoptionen.

### 3. Nur `TradingJournal-Weaver` klonen

```powershell
mkdir C:\trading
cd C:\trading
git clone https://github.com/mike-1140/TradingJournal-Weaver.git
```

### 4. Minimal-Dependencies

```powershell
cd C:\trading\TradingJournal-Weaver
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install python-dotenv requests
```
Der venv-Python wird bewusst direkt über seinen Pfad aufgerufen statt über `activate` — das
funktioniert auch ohne Skript-Ausführungsrechte und ohne Aktivierung.

### 5. `.env` anlegen

```ini
IMAP_USERNAME=deine@email.at
IMAP_PASSWORD=DEIN_MAIL_PASSWORT
IMAP_SERVER=imap.deinanbieter.de

# Optional — zweiter, gleichwertiger Kanal falls der Mail-Abruf mal nicht geht:
IBKR_FLEX_QUERIES=DEIN_TOKEN:QUERY_ID_1,DEIN_TOKEN:QUERY_ID_2,...
```
`C:\Trade_XML\incoming_mail\` und `C:\Trade_CSV\incoming\` werden von den Skripten
automatisch angelegt, kein manueller Schritt nötig.

Für die Fetch-Skripte reichen nur die IMAP-Zeilen und/oder `IBKR_FLEX_QUERIES` — keine
Datenbank-Zugangsdaten.

**Achtung:** Der Mail-Abruf löscht die IBKR-Mails nach dem Herunterladen im Postfach. Ein
"Testlauf" ist deshalb ein echter Lauf — die XMLs liegen danach nur lokal in
`C:\Trade_XML\incoming_mail` und müssen mit dem Push-Skript (Schritt 7) zum Server.

**Vorsicht beim FlexQuery-API-Kanal:** Wiederholte fehlgeschlagene Abrufversuche können bei
IBKR zu einer temporären Sperre führen ("Too many failed attempts"). Nicht wiederholt
manuell testen, falls ein Abruf einmal fehlschlägt — meist löst sich das von selbst
innerhalb von Stunden.

### 6. SSH-Client + eigener Schlüssel

Meist bereits vorinstalliert (Windows 10/11). Prüfen: `ssh -V`. Falls nicht vorhanden:
Windows-Einstellungen → Apps → Optionale Features → "OpenSSH-Client".

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\fetch_client
```

Public Key zum Server übertragen und dort hinterlegen. **Wichtig bei Administrator-Konten
unter Windows:** Falls das Server-Konto Mitglied der Administrators-Gruppe ist (prüfen mit
`whoami /groups | findstr "Administrators"` auf dem Server), greift **nicht**
`~\.ssh\authorized_keys`, sondern eine zentrale Datei:
`C:\ProgramData\ssh\administrators_authorized_keys`.

**Bei Admin-Konto:**
```powershell
# Auf dem Server, nach Übertragung von fetch_client.pub:
$key = Get-Content C:\temp\fetch_client.pub
Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value $key

icacls C:\ProgramData\ssh\administrators_authorized_keys /inheritance:r
icacls C:\ProgramData\ssh\administrators_authorized_keys /grant "SYSTEM:F"
icacls C:\ProgramData\ssh\administrators_authorized_keys /grant "Administrators:F"
```
Die `icacls`-Befehle sind zwingend — sshd verweigert den Key sonst mit "Bad owner or
permissions" bei zu offenen (geerbten) Dateirechten. Mehrere Clients können denselben
Server nutzen: einfach jeden weiteren Public Key zusätzlich anhängen (`Add-Content`),
nicht überschreiben.

**Bei normalem (Nicht-Admin-)Konto:**
```powershell
Get-Content $env:USERPROFILE\.ssh\fetch_client.pub | ssh <konto>@<server-vpn-ip> "cat >> ~/.ssh/authorized_keys"
```
Fragt beim ersten Mal noch nach dem Windows-Passwort (Key-Login ist ja noch nicht
eingerichtet) — danach klappt's per Key.

**Kontrolle:** `ssh-keygen -lf <pfad-zur-datei>` auf beiden Seiten, Fingerprints müssen
übereinstimmen.

### 7. Push-Skript

**Hinweise für Windows PowerShell 5.1:**
- Das Skript darf in den Zeichenketten **nur ASCII** enthalten (kein Gedankenstrich `—`, keine
  typografischen Anführungszeichen). Eine ohne BOM gespeicherte Datei liest PowerShell 5.1
  als ANSI; ein `—` wird zu `”` und beendet den String vorzeitig. Die Fehlermeldungen
  (`&&` "kein gültiges Anweisungstrennzeichen", "kein Abschlusszeichen", "`}` fehlt")
  zeigen dann auf andere Stellen als die eigentliche Ursache.
- Mit Notepad bearbeiten (nicht WordPad/Word) und alten Inhalt vollständig ersetzen.
  Speicherort in diesem Beispiel: `C:\trading\push-to-server.ps1`.
- Auf frischen Windows-Rechnern einmalig erlauben:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

```powershell
$ErrorActionPreference = "Stop"

$ServerIp     = "<server-vpn-ip>"
$ServerUser   = "<konto>"
$KeyPath      = "$env:USERPROFILE\.ssh\fetch_client"
$RemoteTarget = "$ServerUser@$ServerIp"

# Lokaler Ordner -> Ordner auf dem Server (ohne abschliessenden Slash).
# incoming_mail = get_flexquery_emails, incoming_api = get_flexquery_api; die Pipeline liest beide.
$Folders = @(
    @{ Local = "C:\Trade_XML\incoming_mail"; Remote = "C:/Trade_XML/incoming_mail" },
    @{ Local = "C:\Trade_XML\incoming_api";  Remote = "C:/Trade_XML/incoming_api" }
)

function Assert-LastExit($step) {
    # PowerShell faengt Exit-Codes externer Tools (scp/ssh) mit
    # $ErrorActionPreference="Stop" nicht automatisch ab -> manuell pruefen.
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FEHLER bei '$step' (Exit-Code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

$total = 0
foreach ($f in $Folders) {
    $xmlFiles = @(Get-ChildItem -Path $f.Local -Filter "*.xml" -ErrorAction SilentlyContinue)
    if ($xmlFiles.Count -eq 0) {
        Write-Host "Keine XML-Dateien in $($f.Local)"
        continue
    }
    $total += $xmlFiles.Count
    Write-Host "Uebertrage $($xmlFiles.Count) Datei(en) aus $($f.Local) ..."

    # Zielordner auf dem Server anlegen, falls er fehlt (incoming_api existiert dort evtl. noch nicht)
    $remoteWin = $f.Remote.Replace("/", "\")
    ssh -i $KeyPath $RemoteTarget "if not exist $remoteWin mkdir $remoteWin"
    Assert-LastExit "Zielordner anlegen (Server)"

    scp -i $KeyPath "$($f.Local)\*.xml" "${RemoteTarget}:$($f.Remote)/"
    Assert-LastExit "scp"
}

if ($total -eq 0) {
    Write-Host "Keine XML-Dateien gefunden - nichts zu tun."
    exit 0
}

ssh -i $KeyPath $RemoteTarget "cd C:\trading\TradingJournal-Weaver && .venv\Scripts\python run_pipeline.py"
Assert-LastExit "run_pipeline.py (Server)"

Write-Host "Fertig." -ForegroundColor Green
```

Bricht bei jedem Fehler mit klarer Meldung ab (Exit-Code-Check), statt stillschweigend
weiterzulaufen.

---

## Täglicher Ablauf

```powershell
cd C:\trading\TradingJournal-Weaver
.\.venv\Scripts\python.exe -m src.get_flexquery_emails

cd C:\trading
.\push-to-server.ps1   # oder wie das Skript aus Schritt 7 benannt wurde
```
