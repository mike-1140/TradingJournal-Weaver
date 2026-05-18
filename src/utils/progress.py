import itertools
import logging
import sys
import threading
import time


class ProgressLine:
    """
    Einzeilige Fortschrittsanzeige mit animiertem Spinner im Terminal.
    Der Spinner läuft in einem Background-Thread — kein manuelles update() nötig.
    Console-Logging wird während der Anzeige unterdrückt (File-Handler bleibt aktiv).
    """

    _SPINNER    = ['-', '\\', '|', '/']
    _LINE_WIDTH = 100
    _INTERVAL   = 0.1  # Sekunden pro Spinner-Frame

    def __init__(self, logger: logging.Logger = None):
        self._spinner         = itertools.cycle(self._SPINNER)
        self._logger          = logger
        self._console_handler = None
        self._active          = False
        self._message         = ''
        self._thread: threading.Thread | None = None

    def start(self, message: str = '') -> None:
        """Startet Spinner-Thread und unterdrückt Console-Logging."""
        if self._active:
            self.done('')
        self._message = message
        if self._logger:
            for h in self._logger.handlers[:]:
                if isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr):
                    self._console_handler = h
                    self._logger.removeHandler(h)
                    break
        self._active = True
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()

    def _spin_loop(self) -> None:
        """Läuft im Background-Thread und aktualisiert die Spinner-Zeile."""
        while self._active:
            spin = next(self._spinner)
            sys.stdout.write(f"\r  {spin}  {self._message}".ljust(self._LINE_WIDTH))
            sys.stdout.flush()
            time.sleep(self._INTERVAL)

    def update(self, message: str) -> None:
        """Ändert den angezeigten Text während der Spinner läuft."""
        self._message = message

    def done(self, message: str) -> None:
        """Stoppt Spinner, zeigt Abschlussmeldung, stellt Console-Logging wieder her."""
        self._active = False
        if self._thread:
            self._thread.join(timeout=self._INTERVAL * 2)
        if message:
            sys.stdout.write(f"\r  OK  {message}".ljust(self._LINE_WIDTH) + "\n")
            sys.stdout.flush()
        self._restore()

    def error(self, message: str) -> None:
        """Stoppt Spinner, zeigt Fehlermeldung, stellt Console-Logging wieder her."""
        self._active = False
        if self._thread:
            self._thread.join(timeout=self._INTERVAL * 2)
        sys.stdout.write(f"\r  !!  {message}".ljust(self._LINE_WIDTH) + "\n")
        sys.stdout.flush()
        self._restore()

    def _restore(self) -> None:
        """Console-Handler wieder zum Logger hinzufügen."""
        if self._logger and self._console_handler:
            self._logger.addHandler(self._console_handler)
            self._console_handler = None
