"""
get_flexquery_api.py — Holt IBKR FlexQuery-XMLs direkt über die FlexWeb-Service-API

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
"""

import os
import time
import requests
from datetime import datetime
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

load_dotenv()

IN_FOLDER_XML_INCOMING = r'C:\Trade_XML\incoming'

_SEND_URL  = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
_GET_URL   = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"

MAX_RETRIES  = 3
RETRY_DELAY  = 5   # Sekunden zwischen Retries (Processing / Data incomplete)
QUERY_DELAY  = 2   # Sekunden Pause zwischen Queries (IBKR Rate-Limit: 1 Req/s pro Token)


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
    os.makedirs(IN_FOLDER_XML_INCOMING, exist_ok=True)


def _send_request(token: str, query_id: str, logger) -> tuple[str, str]:
    """
    Schritt 1: Stellt Anfrage an IBKR.
    Gibt (ReferenceCode, GetUrl) zurück.
    Transiente Fehler (1001, 1008) werden mit Retry-Logik behandelt.
    """
    # Fehlercodes die einen Retry rechtfertigen (Daten noch nicht verfügbar)
    # 1001 = Rate-Limit, 1004 = incomplete, 1006 = FIFO P/L not ready, 1007 = MTM P/L not ready
    RETRYABLE = {"1001", "1004", "1006", "1007"}

    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(_SEND_URL, params={"t": token, "q": query_id, "v": "3"}, timeout=30)
        resp.raise_for_status()

        root   = ET.fromstring(resp.text)
        status = root.findtext("Status")

        if status == "Success":
            ref_code = root.findtext("ReferenceCode")
            get_url  = root.findtext("Url") or _GET_URL
            logger.info(f"Query {query_id}: Anfrage OK — ReferenceCode={ref_code}")
            return ref_code, get_url

        error_code = root.findtext("ErrorCode") or ""
        error_msg  = root.findtext("ErrorMessage") or ""

        if error_code in RETRYABLE:
            logger.info(
                f"Query {query_id}: Transient [{error_code}] {error_msg} "
                f"(Versuch {attempt}/{MAX_RETRIES}), warte {RETRY_DELAY}s ..."
            )
            time.sleep(RETRY_DELAY)
            continue

        raise RuntimeError(f"SendRequest fehlgeschlagen [{error_code}]: {error_msg}")

    raise RuntimeError(
        f"Query {query_id}: Daten noch nicht verfügbar nach {MAX_RETRIES} Versuchen "
        f"({MAX_RETRIES * RETRY_DELAY}s) — EOD-Processing evtl. noch nicht abgeschlossen. "
        f"Bitte später nochmal versuchen."
    )


def _get_statement(token: str, ref_code: str, get_url: str, query_id: str, logger) -> str:
    """
    Schritt 2: Holt das fertige Statement mit Retry-Logik.
    IBKR liefert Status=Processing solange die Query noch berechnet wird.
    Gibt den XML-Inhalt als String zurück.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(get_url, params={"t": token, "q": ref_code, "v": "3"}, timeout=30)
        resp.raise_for_status()
        content = resp.text.strip()

        # Kurzantwort (Status/Fehler) vs. echtes FlexQuery-XML unterscheiden
        if content.startswith("<FlexStatementResponse"):
            root   = ET.fromstring(content)
            status = root.findtext("Status")

            if status == "Processing":
                logger.info(
                    f"Query {query_id}: Noch in Verarbeitung "
                    f"(Versuch {attempt}/{MAX_RETRIES}), warte {RETRY_DELAY}s ..."
                )
                time.sleep(RETRY_DELAY)
                continue

            error_code = root.findtext("ErrorCode")
            error_msg  = root.findtext("ErrorMessage")
            raise RuntimeError(f"GetStatement fehlgeschlagen [{error_code}]: {error_msg}")

        logger.info(f"Query {query_id}: Statement erhalten ({len(content):,} Zeichen)")
        return content

    raise RuntimeError(
        f"Query {query_id}: Statement nach {MAX_RETRIES} Versuchen ({MAX_RETRIES * RETRY_DELAY}s) "
        f"noch nicht fertig — IBKR-Server beschäftigt. Bitte später nochmal versuchen."
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
    # Fallback: alle Nicht-Ziffern entfernen
    return "".join(c for c in raw if c.isdigit())


def _build_filename(xml_content: str, query_id: str) -> str:
    """
    Dateiname: {accountId}_{toDate}_{letzte4 der QueryID}.xml
    Eindeutig auch wenn dasselbe Konto mehrere Queries hat (z.B. Trade + Activity).
    Fallback: flexquery_{query_id}_{datum}.xml
    """
    qid_suffix = query_id[-4:]
    try:
        root = ET.fromstring(xml_content)
        stmt = root.find(".//FlexStatement")
        if stmt is not None:
            account_id = stmt.get("accountId", "")
            to_date    = stmt.get("toDate", "")
            if account_id and to_date:
                return f"{account_id}_{_normalize_date(to_date)}_{qid_suffix}.xml"
    except ET.ParseError:
        pass

    return f"flexquery_{query_id}_{datetime.now().strftime('%Y%m%d')}.xml"


def _already_fetched_today(query_id: str) -> str | None:
    """
    Prüft ob bereits heute eine Datei für diese Query existiert (anhand QID-Suffix).
    Gibt den Dateinamen zurück wenn gefunden, sonst None.
    Verhindert unnötige API-Calls gegen IBKRs Daily-Regeneration-Limit (Error 1001).
    """
    suffix = f"_{query_id[-4:]}.xml"
    today  = datetime.now().date()
    for fname in os.listdir(IN_FOLDER_XML_INCOMING):
        if not fname.endswith(suffix):
            continue
        fpath = os.path.join(IN_FOLDER_XML_INCOMING, fname)
        if datetime.fromtimestamp(os.path.getmtime(fpath)).date() == today:
            return fname
    return None


def _fetch_query(token: str, query_id: str, logger) -> bool:
    """
    Holt eine einzelne FlexQuery und speichert sie als XML.
    Gibt True zurück wenn eine neue Datei gespeichert wurde.
    """
    existing = _already_fetched_today(query_id)
    if existing:
        logger.info(f"Query {query_id}: Heute bereits geholt, übersprungen: {existing}")
        return False

    try:
        ref_code, get_url = _send_request(token, query_id, logger)
        xml_content       = _get_statement(token, ref_code, get_url, query_id, logger)
        filename          = _build_filename(xml_content, query_id)
        filepath          = os.path.join(IN_FOLDER_XML_INCOMING, filename)

        if os.path.exists(filepath):
            logger.info(f"Query {query_id}: Bereits vorhanden, übersprungen: {filename}")
            return False

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(xml_content)
        logger.info(f"Query {query_id}: Gespeichert → {filepath}")
        return True

    except Exception as e:
        logger.error(f"Query {query_id}: Fehler — {e}")
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

    cnt = 0
    for i, (token, qid) in enumerate(queries):
        if i > 0:
            time.sleep(QUERY_DELAY)
        cnt += _fetch_query(token, qid, logger)
    logger.info(f"Fertig: {cnt} neue FlexQuery-Datei(en) gespeichert")
    return cnt


if __name__ == '__main__':
    result = main()
    print(f"Fertig, Dateien gespeichert: {result}")
