import sys
import logging
from decimal import Decimal
from typing import Tuple
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import contextmanager
from src.logger.emoji_log import EmojiLog

# Das Dictionary ist weiterhin eine gute Idee
LOG_LEVELS = {
    "simple": logging.INFO,
    "detailed": logging.DEBUG,
}


class CustomFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level_tag = "D " if record.levelno == logging.DEBUG else "  "
        return f"{record.getMessage()}"
        # return f"{timestamp} {level_tag}{record.getMessage()}"


@contextmanager
def indented_logger(logger, indent=2):
    """Erzeugt einen Logger, der alle Nachrichten um 'indent' Leerzeichen einrückt."""

    class IndentAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            return f"{' ' * indent}{msg}", kwargs

    adapter = IndentAdapter(logger, {})
    yield adapter


def setup_logging(
        name: str = 'my_app',
        level: str = "simple",
        log_file: Path = None
) -> Tuple[logging.Logger, EmojiLog]:
    """
    Robustes Logging-System mit idempotenter Initialisierung.
    Gibt logger UND EmojiLog zurück.
    """

    logger = logging.getLogger(name)

    # ------------------------------------
    # Idempotenz: Logger bereits konfiguriert?
    # Dann EmojiLog neu bauen und zurückgeben.
    # ------------------------------------
    if logger.hasHandlers():
        return logger, EmojiLog(logger)

    # Loglevel bestimmen
    log_level = LOG_LEVELS.get(level, logging.INFO)
    logger.setLevel(log_level)
    logger.propagate = False

    # Formatter
    formatter = CustomFormatter()

    # --- Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- File Handler ---
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Emoji-Logger erstellen
    emoji_logger = EmojiLog(logger)

    return logger, emoji_logger


def fmt(value, width=0, precision=None, default='N/A', truncate=False, suffix='…'):
    """
    Safely format a value with width, precision, truncation and alignment.

    :param value: Der darzustellende Wert
    :param width: Gesamtbreite (für Padding oder Abschneiden)
    :param precision: Dezimalstellen für Zahlen
    :param default: Fallback für None oder Fehler
    :param truncate: Wenn True, schneidet Strings ab
    :param suffix: Wird angehängt, wenn String abgeschnitten wird (z. B. '…' oder '...')
    :return: formatierter String, rechtsbündig, auf Breite `width`
    """
    try:
        if value is None:
            return default.rjust(width)

        if isinstance(value, (int, float, Decimal)):
            # Zahlenformatierung
            if precision is not None:
                formatted = f"{value:.{precision}f}"
            else:
                formatted = str(value)
            return formatted.rjust(width)

        # String- oder andere Werte
        string_value = str(value)
        if truncate and width > 0:
            suffix_len = len(suffix)
            if len(string_value) > width:
                if width > suffix_len:
                    string_value = string_value[:width - suffix_len] + suffix
                else:
                    string_value = suffix[:width]
        # Immer rechtsbündig auffüllen
        return string_value.rjust(width)

    except Exception:
        return default.rjust(width)


def format_header(columns: list, border: str = "", prefix: str = "") -> str:
    """
    Erzeugt eine formatierte Header-Zeile, die einen Prefix durch Überschreiben einfügt.

    :param columns: Liste von Column-Definitionen (z.B. [{'label': 'Symbol', 'width': 10}])
    :param border: Zeichen für den linken Rand (z.B. '\u2503')
    :param prefix: optionaler Text, der am Anfang (ab Index 2) eingefügt wird.
    :return: Formatierte Kopfzeile
    """
    # 1. Erzeuge die reine Header-Zeile ohne Ränder oder Präfixe
    header_content = " | ".join(
        fmt(col["label"], col.get("width", 0), truncate=True) for col in columns
    )

    # 2. Erzeuge die vollständige Basis-Kopfzeile
    #    WICHTIG: Das Leerzeichen nach dem `border` ist entscheidend für die Indizierung.
    base_header = f"{border} {header_content} |"

    # 3. Wenn ein Präfix vorhanden ist, ersetze den Anfang des Strings
    if prefix:
        prefix_len = len(prefix)
        # Ersetze die Zeichen ab Index 2 durch das Präfix.
        # Nimm den Anfang (:2), füge das Präfix hinzu und dann den Rest des
        # ursprünglichen Strings ab der Position *nach* dem ersetzten Teil.
        return base_header[:2] + prefix + base_header[2 + prefix_len:]
    else:
        # Wenn kein Präfix da ist, gib einfach die Basis-Kopfzeile zurück
        return base_header


def format_row(data: dict, columns: list, border: str = "") -> str:
    line = " | ".join(
        fmt(data.get(col["key"]), col.get("width", 0), col.get("precision"), truncate=True)
        for col in columns
    )
    return f"{border} {line} |" if border else f"{line} |"


def print_log(logger, message: str, force: bool = False):
    if not force:
        return
    with indented_logger(logger, indent=2) as loc_log:
        loc_log.info(message)
