import sys
import itertools
import logging


class ProgressLine:
    """
    Einzeilige Fortschrittsanzeige im Terminal.
    Unterdrückt den Console-Handler des Loggers während der Anzeige,
    damit die Log-Ausgaben die Zeile nicht unterbrechen.
    Der File-Handler bleibt aktiv — alle Meldungen gehen weiterhin ins Log.
    """

    _SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    _LINE_WIDTH = 100

    def __init__(self, logger: logging.Logger = None):
        self._spinner = itertools.cycle(self._SPINNER)
        self._logger = logger
        self._console_handler = None
        self._active = False

    def start(self, message: str = ''):
        """Startet die Fortschrittsanzeige und unterdrückt Console-Logging."""
        if self._active:
            return
        if self._logger:
            for h in self._logger.handlers[:]:
                if isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr):
                    self._console_handler = h
                    self._logger.removeHandler(h)
                    break
        self._active = True
        if message:
            self.update(message)

    def update(self, message: str):
        """Aktualisiert die Statuszeile (überschreibt die aktuelle Zeile)."""
        if not self._active:
            return
        spin = next(self._spinner)
        sys.stdout.write(f"\r  {spin}  {message}".ljust(self._LINE_WIDTH))
        sys.stdout.flush()

    def done(self, message: str):
        """Zeigt Abschlussmeldung und stellt Console-Logging wieder her."""
        sys.stdout.write(f"\r  ✓  {message}\n".ljust(self._LINE_WIDTH) + "\n")
        sys.stdout.flush()
        self._restore()

    def error(self, message: str):
        """Zeigt Fehlermeldung und stellt Console-Logging wieder her."""
        sys.stdout.write(f"\r  ✗  {message}\n".ljust(self._LINE_WIDTH) + "\n")
        sys.stdout.flush()
        self._restore()

    def _restore(self):
        """Console-Handler wieder zum Logger hinzufügen."""
        self._active = False
        if self._logger and self._console_handler:
            self._logger.addHandler(self._console_handler)
            self._console_handler = None