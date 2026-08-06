"""
get_flexquery_api.py — holt IBKR FlexQuery-XMLs direkt über die FlexWeb-Service-API

Läuft parallel zur Mail-Pipeline (get_flexquery_emails.py), NICHT als Ersatz — beide
Wege sind gleichzeitig aktiv (siehe pipeline.toml). Die API liefert die "act_money_per_api"-
Query (Trades + EquitySummary + CashReport + MTMPerformance).
  - import (import_ibkr_trades.py) liest daraus die Trades nach trades_raw (gleichwertig
    zu den Mail-XMLs, Checksum-Dedup verhindert doppelte Trades) UND ist fuer
    processed/deleted verantwortlich.
  - snapshot_import (import_flexquery_snapshot.py) koennte daraus zusaetzlich
    account_snapshots (EquitySummary/CashReport/MTM) fuellen, ist aber Stand 2026-08-05
    BEWUSST NICHT in der Standard-Pipeline (siehe pipeline.toml) — der FlexQuery-API-Weg
    fuer Snapshots funktioniert noch nicht zuverlaessig, account_snapshots kommt aktuell
    nur ueber snapshot_csv (Mail + Activity-Report).
  Fehlendes OptionEAE/BookTrades in dieser Query bedeutet: Assignment-/Expiry-Events
  kommen weiterhin nur aus den Mail-XMLs — die API ist kein vollstaendiger Ersatz dafuer.

Schreibt nach OUT_FOLDER_XML_API (C:\\Trade_XML\\incoming_api\\), getrennt von
get_flexquery_emails.py's C:\\Trade_XML\\incoming_mail\\ — beide Ordner werden vom
import-Step gleichwertig gescannt (siehe import_ibkr_trades.py).

Unterstützt mehrere Konten/Logins (money, paper, autom_money, autom_paper, karola ...).
Das Routing zum richtigen Environment erfolgt automatisch über die accountId im XML
(ACCOUNT_MAP in config.py) — kein manuelles Zuordnen nötig.

Ablauf pro Query:
  1. SendRequest  → IBKR gibt einen ReferenceCode zurück
  2. GetStatement → IBKR liefert das fertige XML (ggf. nach kurzer Wartezeit)

Konfiguration in .env:
  IBKR_FLEX_QUERIES = kommagetrennte Liste von "token:query_id" Paaren

  Beispiele:
    Ein Konto, eine Query:
      IBKR_FLEX_QUERIES=ABC123TOKEN:111111

    Selbes Login, zwei Queries (z.B. Trade + Activity):
      IBKR_FLEX_QUERIES=ABC123TOKEN:111111,ABC123TOKEN:222222

    Mehrere Logins (money/paper + autom-Konto):
      IBKR_FLEX_QUERIES=ABC123TOKEN:111111,ABC123TOKEN:222222,XYZ789TOKEN:333333

  Token:    IBKR Portal → Settings → Account Settings → Flex Web Service → Token
  Query-ID: IBKR Portal → Reports → Flex Queries → (Query auswählen) → ID in der Liste

  Ist IBKR_FLEX_QUERIES nicht gesetzt, beendet sich das Script folgenlos (kein Fehler,
  Exit-Code 0) — der Schritt ist dann im Pipeline-Lauf einfach ein No-Op.
"""

import os
import re
import time
import requests
from datetime import datetime
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

load_dotenv()

_session = requests.Session()

# Bewusst getrennt von get_flexquery_emails.py's C:\Trade_XML\incoming_mail\ (siehe Docstring oben).
OUT_FOLDER_XML_API = r'C:\Trade_XML\incoming_api'

_SEND_URL  = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
_GET_URL   = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

MAX_RETRIES  = 5
RETRY_DELAY  = 10   # Sekunden zwischen Retries (Processing / Data incomplete)
QUERY_DELAY  = 2    # Sekunden Pause zwischen Queries desselben Tokens (IBKR Rate-Limit: 1 Req/s pro Token)
TOKEN_DELAY  = 30   # Sekunden Pause vor Wechsel auf einen anderen Token — Sicherheitsabstand
                     # gegen IBKR-Fehler 1025 "Too many failed attempts" (beobachtet 2026-08-03,
                     # nach mehreren dicht aufeinanderfolgenden Fehlversuchen über mehrere Tokens)


def _parse_queries() -> list[tuple[str, str]]:
    """
    Liest IBKR_FLEX_QUERIES aus .env und gibt Liste von (token, query_id) zurück.
    Format: "token1:qid1,token1:qid2,token2:qid3"
    """
    raw = os.getenv("IBKR_FLEX_QUERIES", "").strip()
    if not raw:
        return []
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        token, query_id = entry.split(":", 1)
        if token.strip() and query_id.strip():
            result.append((token.strip(), query_id.strip()))
    return result


# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen
# ---------------------------------------------------------------------------

def _ensure_dirs():
    os.makedirs(OUT_FOLDER_XML_API, exist_ok=True)


def _elapsed(t_start: float) -> str:
    """Formatiert die seit t_start (time.monotonic()) vergangene Zeit für Log-Ausgaben."""
    return f"{time.monotonic() - t_start:.1f}s"


def _send_request(token: str, query_id: str, logger) -> tuple[str, str]:
    """
    Schritt 1: Stellt Anfrage an IBKR.
    Gibt (ReferenceCode, GetUrl) zurück.
    Transiente Fehler werden mit Retry-Logik behandelt.
    """
    # 1001 = Rate-Limit, 1004 = incomplete, 1006 = FIFO P/L not ready, 1007 = MTM P/L not ready, 1008 = Server busy
    RETRYABLE = {"1001", "1004", "1006", "1007", "1008"}
    t_start = time.monotonic()
    last_error_code, last_error_msg = "", ""

    for attempt in range(1, MAX_RETRIES + 1):
        now = datetime.now().strftime("%H:%M:%S")
        try:
            resp = _session.get(_SEND_URL, params={"t": token, "q": query_id, "v": "3"}, timeout=30)
            resp.raise_for_status()
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as ce:
            logger.warning(
                f"[{now}] Query {query_id}: Netzwerkfehler (Versuch {attempt}/{MAX_RETRIES}, "
                f"seit {_elapsed(t_start)}): {ce}"
            )
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)
            continue

        root   = ET.fromstring(resp.text)
        status = root.findtext("Status")

        if status == "Success":
            ref_code    = root.findtext("ReferenceCode")
            server_url  = root.findtext("Url")
            get_url     = server_url or _GET_URL
            # Diagnose: zeigt, ob IBKR eine eigene GetStatement-URL vorgibt (z.B. anderes
            # Rechenzentrum/Domain als der Default) — falls GetStatement dauerhaft "in
            # progress" liefert, hier prüfen ob server_url vom Default _GET_URL abweicht.
            logger.info(
                f"[{now}] Query {query_id}: Anfrage OK nach {attempt} Versuch(en)/{_elapsed(t_start)} "
                f"— HTTP {resp.status_code}, ReferenceCode={ref_code}, "
                f"GetStatement-URL={get_url} ({'von IBKR vorgegeben' if server_url else 'Default'})"
            )
            return ref_code, get_url

        last_error_code = root.findtext("ErrorCode") or ""
        last_error_msg  = root.findtext("ErrorMessage") or ""

        if last_error_code in RETRYABLE:
            logger.info(
                f"[{now}] Query {query_id}: Transient [{last_error_code}] {last_error_msg} "
                f"(Versuch {attempt}/{MAX_RETRIES}, seit {_elapsed(t_start)}), warte {RETRY_DELAY}s ..."
            )
            time.sleep(RETRY_DELAY)
            continue

        raise RuntimeError(
            f"SendRequest fehlgeschlagen [{last_error_code}]: {last_error_msg} "
            f"(Versuch {attempt}/{MAX_RETRIES}, nach {_elapsed(t_start)})"
        )

    raise RuntimeError(
        f"Query {query_id}: Daten noch nicht verfügbar nach {MAX_RETRIES} Versuchen "
        f"({_elapsed(t_start)}) — letzter Fehler [{last_error_code}] {last_error_msg}. "
        f"EOD-Processing evtl. noch nicht abgeschlossen. Bitte später nochmal versuchen."
    )


def _get_statement(token: str, ref_code: str, get_url: str, query_id: str, logger) -> str:
    """
    Schritt 2: Holt das fertige Statement mit Retry-Logik.
    IBKR liefert Status=Processing solange die Query noch berechnet wird.
    Gibt den XML-Inhalt als String zurück.
    """
    t_start = time.monotonic()
    last_marker = ""

    for attempt in range(1, MAX_RETRIES + 1):
        now = datetime.now().strftime("%H:%M:%S")
        try:
            resp = _session.get(get_url, params={"t": token, "q": ref_code, "v": "3"}, timeout=30)
            resp.raise_for_status()
            content = resp.text.strip()
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as ce:
            logger.warning(
                f"[{now}] Query {query_id}: Netzwerkfehler (Versuch {attempt}/{MAX_RETRIES}, "
                f"seit {_elapsed(t_start)}): {ce}"
            )
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)
            continue

        # Kurzantwort (Status/Fehler) vs. echtes FlexQuery-XML unterscheiden
        if content.startswith("<FlexStatementResponse"):
            root = ET.fromstring(content)
            status = root.findtext("Status")
            err_code = root.findtext("ErrorCode")
            last_marker = err_code or status or ""

            # Status 'Processing' ODER ErrorCode 1019 bedeutet: Weiter warten!
            if status == "Processing" or err_code in ("1019", "1018"):
                logger.info(
                    f"[{now}] Query {query_id}: Noch in Verarbeitung/Bereitstellung [{last_marker}] "
                    f"(Versuch {attempt}/{MAX_RETRIES}, seit {_elapsed(t_start)}), warte {RETRY_DELAY}s ..."
                )
                time.sleep(RETRY_DELAY)
                continue

            # Erst bei echten Fehlern (z.B. falsches Token, ungültige QID) abbrechen
            error_msg = root.findtext("ErrorMessage")
            raise RuntimeError(
                f"GetStatement fehlgeschlagen [{err_code}]: {error_msg} "
                f"(Versuch {attempt}/{MAX_RETRIES}, nach {_elapsed(t_start)})"
            )

        # Sanity-Check: alles, was hier ankommt, sollte echtes FlexQuery-XML sein.
        # Ohne diese Prüfung würde eine leere/kaputte Antwort (z.B. HTML-Fehlerseite
        # von einem Proxy) unbemerkt als "erfolgreich" nach incoming_api/ geschrieben.
        if not content.startswith("<?xml") and not content.startswith("<FlexQueryResponse"):
            snippet = content[:300].replace("\n", " ")
            logger.warning(
                f"[{now}] Query {query_id}: Unerwartete Antwort (kein FlexQueryResponse, "
                f"{len(content)} Zeichen, Versuch {attempt}/{MAX_RETRIES}): {snippet!r}"
            )
            raise RuntimeError(f"GetStatement lieferte unerwarteten Inhalt: {snippet!r}")

        logger.info(
            f"[{now}] Query {query_id}: Statement erhalten nach {attempt} Versuch(en)/"
            f"{_elapsed(t_start)} — HTTP {resp.status_code}, {len(content):,} Zeichen"
        )
        return content

    raise RuntimeError(
        f"Query {query_id}: Statement nach {MAX_RETRIES} Versuchen ({_elapsed(t_start)}) "
        f"noch nicht fertig — letzter Status [{last_marker}]. IBKR-Server beschäftigt. "
        f"Bitte später nochmal versuchen."
    )


def _normalize_date(raw: str) -> str:
    """
    Normalisiert IBKR-Datumsformate → YYYYMMDD.
    Bekannte Formate: YYYYMMDD, YYYY-MM-DD, DD/MM/YYYY
    """
    raw = raw.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    # Fallback: Tagesdatum — unbekanntes Format soll keinen korrumpierten Namen erzeugen
    return datetime.now().strftime("%Y%m%d")


def _sanitize_for_filename(raw: str) -> str:
    """Ersetzt alles außer [A-Za-z0-9_-] durch '_', für die Verwendung im Dateinamen."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")


def _build_filename(xml_content: str, query_id: str) -> str:
    """
    Dateiname: {accountId}_{toDate}_{queryName}_{letzte4 der QueryID}.xml
    queryName kommt aus dem Attribut auf <FlexQueryResponse> (vom IBKR-Portal, z.B.
    "act_money_per_api") — macht den Dateinamen lesbar wie bei den Mail-XMLs
    ("flex.<qid>.<name>.xml"). accountId+Datum+qid-Suffix bleiben für Eindeutigkeit
    (mehrere Queries desselben Kontos am selben Tag) und für den
    _already_fetched_today-Check (der nur auf den qid-Suffix matcht).
    Fallback: flexquery_{query_id}_{datum}.xml
    """
    qid_suffix = query_id[-4:]
    try:
        root       = ET.fromstring(xml_content)
        query_name = _sanitize_for_filename(root.get("queryName", ""))
        stmt       = root.find(".//FlexStatement")
        if stmt is not None:
            account_id = stmt.get("accountId", "")
            to_date    = stmt.get("toDate", "")
            if account_id and to_date:
                name_part = f"_{query_name}" if query_name else ""
                return f"{account_id}_{_normalize_date(to_date)}{name_part}_{qid_suffix}.xml"
    except ET.ParseError:
        pass

    return f"flexquery_{query_id}_{datetime.now().strftime('%Y%m%d')}.xml"


def _already_fetched_today(query_id: str) -> str | None:
    """
    Prüft, ob bereits heute eine Datei für diese Query existiert (anhand QID-Suffix).
    Gibt den Dateinamen zurück, wenn gefunden, sonst None.
    Verhindert unnötige API-Calls gegen IBKRs Daily-Regeneration-Limit (Error 1001).
    """
    suffix = f"_{query_id[-4:]}.xml"
    today  = datetime.now().date()
    for fname in os.listdir(OUT_FOLDER_XML_API):
        if not fname.endswith(suffix):
            continue
        fpath = os.path.join(OUT_FOLDER_XML_API, fname)
        if datetime.fromtimestamp(os.path.getmtime(fpath)).date() == today:
            return fname
    return None


def _fetch_query(token: str, query_id: str, logger) -> bool:
    """
    Holt eine einzelne FlexQuery und speichert sie als XML.
    Gibt True zurück, wenn eine neue Datei gespeichert wurde.
    """
    existing = _already_fetched_today(query_id)
    if existing:
        logger.info(f"Query {query_id}: Heute bereits geholt, übersprungen: {existing}")
        return False

    t_start = time.monotonic()
    try:
        ref_code, get_url = _send_request(token, query_id, logger)
        xml_content       = _get_statement(token, ref_code, get_url, query_id, logger)
        filename          = _build_filename(xml_content, query_id)
        filepath          = os.path.join(OUT_FOLDER_XML_API, filename)

        if os.path.exists(filepath):
            logger.info(f"Query {query_id}: Bereits vorhanden, übersprungen: {filename}")
            return False

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(xml_content)
        # Gesamtdauer SendRequest+GetStatement — Grundlage, um RETRY_DELAY/MAX_RETRIES
        # später anhand echter Werte zu optimieren statt zu schätzen.
        logger.info(f"Query {query_id}: Erfolgreich nach {_elapsed(t_start)} gesamt → {filepath}")
        return True

    except Exception as e:
        logger.error(f"Query {query_id}: Fehler nach {_elapsed(t_start)} gesamt — {e}")
        return False


# ---------------------------------------------------------------------------
# Öffentliche Hilfsfunktion (für direkte Weiterverarbeitung ohne Disk-Speicherung)
# ---------------------------------------------------------------------------

def fetch_query_to_string(token: str, query_id: str, logger) -> str | None:
    """Holt eine FlexQuery und gibt den XML-Inhalt direkt als String zurück."""
    try:
        ref_code, get_url = _send_request(token, query_id, logger)
        return _get_statement(token, ref_code, get_url, query_id, logger)
    except Exception as e:
        logger.error(f"Query {query_id}: Fehler — {e}")
        return None


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> int:
    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- FlexQueryAPI ({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info("=" * 80)

    queries = _parse_queries()
    if not queries:
        logger.error("IBKR_FLEX_QUERIES nicht gesetzt oder leer — Abbruch (siehe .env)")
        logger.error("  Format: IBKR_FLEX_QUERIES=token1:query_id1,token2:query_id2")
        return 0

    # Token-Übersicht im Log (nur letzte 4 Zeichen sichtbar)
    unique_tokens = {t[-4:] for t, _ in queries}
    logger.info(f"{len(queries)} Queries konfiguriert | Tokens: {sorted(unique_tokens)}")
    _ensure_dirs()

    t_run_start = time.monotonic()
    cnt = 0
    prev_token = None
    for i, (token, qid) in enumerate(queries):
        if i > 0:
            if token != prev_token:
                logger.info(f"Token-Wechsel — warte {TOKEN_DELAY}s zur Sicherheit ...")
                time.sleep(TOKEN_DELAY)
            else:
                time.sleep(QUERY_DELAY)
        cnt += _fetch_query(token, qid, logger)
        prev_token = token
    logger.info(f"Fertig: {cnt} neue FlexQuery-Datei(en) gespeichert — Laufzeit gesamt {_elapsed(t_run_start)}")
    return cnt


if __name__ == '__main__':
    result = main()
    print(f"Fertig, Dateien gespeichert: {result}")
