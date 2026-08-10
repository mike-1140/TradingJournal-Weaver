# Regressionstests fuer den Mail-bleibt-haengen-Bug in get_flexquery_emails.py
# (behoben 2026-05-21). Zwei getrennte Ursachen, beide symmetrisch in
# _process_flexquery_mails() und _process_activity_statement_mails() gefixt:
#
#   Ursache 1: das \Deleted-Flag wurde nur gesetzt, wenn eine Datei NEU
#              gespeichert wurde -- existierte CSV/XML schon (z.B. erneuter
#              Lauf), blieb die Mail ungelesen im Posteingang stehen.
#   Ursache 2: die IMAP-Suche matched den Betreff auch bei Mails mit
#              PDF-Anhang statt CSV/XML -- ohne passenden Anhang wurde nie
#              gespeichert, und (siehe Ursache 1) damit auch nie geloescht.
#
# Fix: das \Deleted-Flag wird jetzt einmal pro Mail gesetzt, ausserhalb der
# Anhang-Schleife, unabhaengig davon ob/was gespeichert wurde.
#
# Kein echtes IMAP/Dateisystem noetig: FakeImap ersetzt imaplib.IMAP4_SSL,
# os.path.exists wird fuer Ursache-1-Tests gezielt gemockt.

from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

from src.get_flexquery_emails import _process_flexquery_mails, _process_activity_statement_mails


class FakeImap:
    """
    Minimaler In-Memory-Ersatz fuer imaplib.IMAP4_SSL -- bildet nur search()/
    fetch()/store() nach, die die beiden process_*_mails()-Funktionen
    tatsaechlich aufrufen. Ignoriert die Suchkriterien komplett (liefert
    immer alle uebergebenen Mails) -- fuer isolierte Tests wird pro Test nur
    genau die relevante Mail hineingelegt.
    """
    def __init__(self, mails: dict[str, bytes]):
        self._mails = mails
        self.deleted = set()

    def search(self, charset, *criteria):
        nums = " ".join(self._mails.keys()).encode()
        return "OK", [nums]

    def fetch(self, num, spec):
        key = num.decode() if isinstance(num, bytes) else num
        raw = self._mails[key]
        return "OK", [(b"1 (RFC822)", raw)]

    def store(self, num, flag_action, flag):
        if flag == "\\Deleted":
            key = num.decode() if isinstance(num, bytes) else num
            self.deleted.add(key)
        return "OK", [b"1"]


def _build_mail(subject: str, attachments: list[tuple[str, bytes]] | None = None) -> bytes:
    """Baut eine echte RFC822-Mail (multipart, falls Anhaenge vorhanden)."""
    if not attachments:
        msg = MIMEText("Keine Anhaenge.")
    else:
        msg = MIMEMultipart()
        msg.attach(MIMEText("Anbei die Datei."))
        for filename, content in attachments:
            part = MIMEApplication(content)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

    msg["Subject"] = subject
    msg["From"] = "donotreply@interactivebrokers.com"
    return msg.as_bytes()


class TestUrsache1BereitsVorhandeneDateiWirdTrotzdemGeloescht:
    def test_flexquery_mail_mit_bereits_vorhandenem_xml_wird_geloescht(self, dummy_logger, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda path: True)
        raw = _build_mail("Activity Flex for XYZ", [("flex.123.test.xml", b"<xml/>")])
        imap = FakeImap({"1": raw})

        cnt = _process_flexquery_mails(imap, dummy_logger)

        assert cnt == 0  # nichts NEU gespeichert
        assert "1" in imap.deleted  # Mail trotzdem geloescht

    def test_activity_mail_mit_bereits_vorhandener_csv_wird_geloescht(self, dummy_logger, monkeypatch):
        monkeypatch.setattr("os.path.exists", lambda path: True)
        raw = _build_mail("Kontoauszug", [("autom_money.123.20260513.csv", b"a,b,c")])
        imap = FakeImap({"1": raw})

        cnt = _process_activity_statement_mails(imap, dummy_logger)

        assert cnt == 0
        assert "1" in imap.deleted


class TestUrsache2MailOhnePassendemAnhangWirdTrotzdemGeloescht:
    def test_flexquery_mail_mit_pdf_statt_xml_wird_geloescht(self, dummy_logger):
        # IMAP-Suche matcht den Betreff, aber der Anhang ist kein XML.
        raw = _build_mail("Activity Flex for XYZ", [("kontoauszug.pdf", b"%PDF-1.4")])
        imap = FakeImap({"1": raw})

        cnt = _process_flexquery_mails(imap, dummy_logger)

        assert cnt == 0
        assert "1" in imap.deleted

    def test_activity_mail_mit_pdf_statt_csv_wird_geloescht(self, dummy_logger):
        raw = _build_mail("Kontoauszug", [("kontoauszug.pdf", b"%PDF-1.4")])
        imap = FakeImap({"1": raw})

        cnt = _process_activity_statement_mails(imap, dummy_logger)

        assert cnt == 0
        assert "1" in imap.deleted
