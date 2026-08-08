import imaplib
import email
import os
import re
from datetime import datetime
from email.header import decode_header
from dotenv import load_dotenv

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

load_dotenv()

# --- Eingangsordner — Routing erfolgt beim Import per accountId ---
IN_FOLDER_XML_INCOMING = r'C:\Trade_XML\incoming_mail'
IN_FOLDER_CSV_INCOMING = r'C:\Trade_CSV\incoming'

# IMAP-Credentials aus .env
username             = os.getenv("IMAP_USERNAME")
password             = os.getenv("IMAP_PASSWORD")
imap_server          = os.getenv("IMAP_SERVER", "imap.gmx.com")
activity_subject     = os.getenv("IBKR_ACTIVITY_SUBJECT", "Activity Statement")
activity_subject_de  = os.getenv("IBKR_ACTIVITY_SUBJECT_DE", "Kontoauszug")

# Platzhalterwert aus .env.example — falls nie ausgefuellt, soll das Script sauber
# abbrechen statt mit einem imaplib-Authentifizierungsfehler zu crashen
_PLACEHOLDER_USERNAME = "deine@email.at"


def _mail_configured() -> bool:
    """Prueft ob IMAP_USERNAME/IMAP_PASSWORD echt befuellt sind (nicht leer, nicht Platzhalter)."""
    return bool(username) and username != _PLACEHOLDER_USERNAME and bool(password)


def _ensure_dirs():
    """Erstellt Eingangsordner falls nötig."""
    for folder in [IN_FOLDER_XML_INCOMING, IN_FOLDER_CSV_INCOMING]:
        os.makedirs(folder, exist_ok=True)


def clean(text):
    return "".join(c if c.isalnum() else "_" for c in text)


# Erlaubte Zeichen fuer Attachment-Dateinamen (Whitelist)
_FILENAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._ ()-]*$')


def _safe_filename(filename: str) -> str | None:
    """
    Validiert einen Attachment-Dateinamen gegen Path Traversal.
    Der Absender einer Mail ist faelschbar — dem Dateinamen darf daher
    nicht vertraut werden (z.B. '..\\..\\evil.xml' wuerde sonst ausserhalb
    des Zielordners schreiben).
    Legitime IBKR-Anhaenge enthalten nie Pfadanteile → solche Namen werden
    komplett abgelehnt. Gibt den Dateinamen zurueck, oder None wenn ungueltig.
    """
    name = filename.strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not _FILENAME_RE.match(name):
        return None
    return name


def _connect_imap() -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(imap_server)
    imap.login(username, password)
    imap.select("INBOX")
    return imap


def _decode_header_value(value) -> str:
    decoded, enc = decode_header(value)[0]
    if isinstance(decoded, bytes):
        return decoded.decode(enc or 'utf-8')
    return decoded


def _save_attachment(part, filepath: str, logger) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(part.get_payload(decode=True))
    logger.info(f"Anhang gespeichert: {os.path.basename(filepath)} -> {filepath}")


def _process_flexquery_mails(imap: imaplib.IMAP4_SSL, logger) -> int:
    """
    Sucht FlexQuery-Mails (XML/CSV mit Environment-Keyword im Dateinamen)
    und speichert Anhaenge in die XML-Zielordner.
    """
    cnt = 0
    status, data = imap.search(
        None,
        '(FROM "donotreply@interactivebrokers.com")',
        '(OR SUBJECT "Trade Confirmation Flex" SUBJECT "Activity Flex for")'
    )
    if status != 'OK':
        return cnt

    for num in data[0].split():
        status, msg_data = imap.fetch(num, '(RFC822)')
        for response in msg_data:
            if not isinstance(response, tuple):
                continue
            msg = email.message_from_bytes(response[1])
            if not msg.is_multipart():
                imap.store(num, '+FLAGS', '\\Deleted')
                continue

            xml_found = False
            for part in msg.walk():
                if "attachment" not in str(part.get("Content-Disposition")):
                    continue
                filename = part.get_filename()
                if not filename or not filename.lower().endswith('.xml'):
                    continue

                xml_found = True
                safe_name = _safe_filename(filename)
                if not safe_name:
                    logger.warning(f"Anhang mit verdaechtigem Dateinamen uebersprungen: {filename!r}")
                    continue
                filepath = os.path.join(IN_FOLDER_XML_INCOMING, safe_name)
                if os.path.exists(filepath):
                    logger.info(f"Bereits vorhanden, uebersprungen: {safe_name}")
                else:
                    _save_attachment(part, filepath, logger)
                    cnt += 1

            imap.store(num, '+FLAGS', '\\Deleted')
            if not xml_found:
                logger.info(f"Mail ohne XML-Anhang geloescht (Subject: {_decode_header_value(msg.get('Subject', ''))})")

    return cnt


def _process_activity_statement_mails(imap: imaplib.IMAP4_SSL, logger) -> int:
    """
    Sucht IBKR Activity Statement Mails (Betreff enthaelt IBKR_ACTIVITY_SUBJECT)
    und speichert CSV-Anhaenge in die CSV-Zielordner.
    Routing per Env-Keyword im Dateinamen (z.B. autom_money.1961241.20260513.csv).
    """
    cnt = 0
    status, data = imap.search(
        None,
        '(FROM "donotreply@interactivebrokers.com")',
        f'(OR SUBJECT "{activity_subject}" SUBJECT "{activity_subject_de}")'
    )
    if status != 'OK':
        return cnt

    for num in data[0].split():
        status, msg_data = imap.fetch(num, '(RFC822)')
        for response in msg_data:
            if not isinstance(response, tuple):
                continue
            msg = email.message_from_bytes(response[1])
            if not msg.is_multipart():
                # Kein Anhang — Mail trotzdem loeschen (z.B. Benachrichtigungs-Mail ohne CSV)
                imap.store(num, '+FLAGS', '\\Deleted')
                continue

            csv_found = False
            for part in msg.walk():
                if "attachment" not in str(part.get("Content-Disposition")):
                    continue
                filename = part.get_filename()
                if not filename or not filename.lower().endswith('.csv'):
                    continue

                csv_found = True
                safe_name = _safe_filename(filename)
                if not safe_name:
                    logger.warning(f"Anhang mit verdaechtigem Dateinamen uebersprungen: {filename!r}")
                    continue
                filepath = os.path.join(IN_FOLDER_CSV_INCOMING, safe_name)
                if os.path.exists(filepath):
                    logger.info(f"Bereits vorhanden, uebersprungen: {safe_name}")
                else:
                    _save_attachment(part, filepath, logger)
                    cnt += 1
                    logger.info(f"Activity CSV gespeichert: {safe_name} -> incoming/")

            # Mail loeschen sobald sie verarbeitet wurde (unabhaengig ob CSV neu/vorhanden/fehlt)
            imap.store(num, '+FLAGS', '\\Deleted')
            if not csv_found:
                logger.info(f"Mail ohne CSV-Anhang geloescht (Subject: {_decode_header_value(msg.get('Subject', ''))})")

    return cnt


def main():
    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- FlexQueryEmails ({datetime.now().strftime('%Y-%m-%d - %H:%M:%S')})")
    logger.info("=" * 80)
    logger.info(f"Mail-Account: {username}")

    if not _mail_configured():
        logger.error("IMAP_USERNAME/IMAP_PASSWORD nicht konfiguriert oder noch auf Platzhalterwert — Abbruch (siehe .env)")
        logger.error("  .env.example kopieren und IMAP_USERNAME/IMAP_PASSWORD mit echten Werten befuellen")
        return 0

    _ensure_dirs()

    imap = _connect_imap()

    cnt_flex     = _process_flexquery_mails(imap, logger)
    cnt_activity = _process_activity_statement_mails(imap, logger)

    # Geloeschte Mails endgueltig entfernen
    imap.expunge()
    imap.close()
    imap.logout()

    total = cnt_flex + cnt_activity
    logger.info(
        f"Fertig: {cnt_flex} FlexQuery-Datei(en), "
        f"{cnt_activity} Activity-CSV(s) gespeichert"
    )
    return total


if __name__ == '__main__':
    dateien_verarbeitet = main()
    print(f"Fertig, Dateien verarbeitet: {dateien_verarbeitet}")
