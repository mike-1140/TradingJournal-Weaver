import imaplib
import email
from email.header import decode_header
import os
from datetime import datetime
from dotenv import load_dotenv

from src.logger_setup import setup_logging
from src.utils.path_utils import get_project_root

load_dotenv()

IN_FOLDER_TEST = r'C:\Trade_XML\test'
IN_FOLDER_PAPER = r'C:\Trade_XML\paper'
IN_FOLDER_MONEY = r'C:\Trade_XML\money'
IN_FOLDER_AUTOM_PAPER = r'C:\Trade_XML\autom_paper'
IN_FOLDER_AUTOM_MONEY = r'C:\Trade_XML\autom_money'

# Credentials aus .env laden
username = os.getenv("IMAP_USERNAME")
password = os.getenv("IMAP_PASSWORD")
imap_server = os.getenv("IMAP_SERVER", "imap.gmx.com")


def clean(text):
    # Sonderzeichen fuer Ordnernamen bereinigen
    return "".join(c if c.isalnum() else "_" for c in text)


def main():
    # Logging
    log_file = get_project_root() / "log/app.log"
    logger, _ = setup_logging('my_app', level="simple", log_file=log_file)
    logger.info("=" * 80)
    logger.info(f"---- FlexQueryEmails (" + datetime.now().strftime('%Y-%m-%d - %H:%M:%S') + ")")
    logger.info("=" * 80)

    logger.info('Start Process Flex Query Mails')
    logger.info('Process Mail-Account: ' + username)
    cnt = 0

    # IMAP-Verbindung mit SSL aufbauen
    imap = imaplib.IMAP4_SSL(imap_server)
    imap.login(username, password)
    imap.select("INBOX")

    # Suche: Mails von IBKR mit einem der beiden Subjects
    # OR verknuepft genau zwei Kriterien — FROM als aeusseres AND korrekt verschachtelt
    status, data = imap.search(
        None,
        '(FROM "donotreply@interactivebrokers.com")',
        '(OR SUBJECT "Trade Confirmation Flex" SUBJECT "Activity Flex for")'
    )

    if status == 'OK':
        for num in data[0].split():
            status, msg = imap.fetch(num, '(RFC822)')
            for response in msg:
                if isinstance(response, tuple):
                    # Bytes-Email in Message-Objekt parsen
                    msg = email.message_from_bytes(response[1])

                    # Subject dekodieren
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or 'utf-8')

                    # Absender dekodieren
                    From, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(From, bytes):
                        From = From.decode(encoding or 'utf-8')

                    # Multipart-Mail verarbeiten
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))

                            try:
                                body = part.get_payload(decode=True).decode()
                            except Exception:
                                pass

                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                pass
                            elif "attachment" in content_disposition:
                                filename = part.get_filename()
                                filepath = ""

                                if filename and ("xml" in filename or "csv" in filename):
                                    # Reihenfolge wichtig: autom_* vor den einfachen Namen pruefen
                                    if "autom_money" in filename:
                                        filepath = os.path.join(IN_FOLDER_AUTOM_MONEY, filename)
                                        cnt += 1
                                    elif "autom_paper" in filename:
                                        filepath = os.path.join(IN_FOLDER_AUTOM_PAPER, filename)
                                        cnt += 1
                                    elif "money" in filename:
                                        filepath = os.path.join(IN_FOLDER_MONEY, filename)
                                        cnt += 1
                                    elif "paper" in filename:
                                        filepath = os.path.join(IN_FOLDER_PAPER, filename)
                                        cnt += 1
                                    elif "test" in filename:
                                        filepath = os.path.join(IN_FOLDER_TEST, filename)
                                        cnt += 1

                                if filepath:
                                    # Anhang speichern (with-Statement schliesst File-Handle sicher)
                                    with open(filepath, "wb") as f:
                                        f.write(part.get_payload(decode=True))
                                    logger.info('Attachment saved: ' + filename)
                                    # Mail vom Server loeschen
                                    imap.store(num, '+FLAGS', '\\Deleted')

    # Verbindung schliessen
    imap.close()
    imap.logout()
    logger.info('End Process Flex Query Mails\n')
    return cnt


if __name__ == '__main__':
    dateien_verarbeitet = main()
    print('Fertig, Dateien verarbeitet: ' + str(dateien_verarbeitet))
