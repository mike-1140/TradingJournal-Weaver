# Tests fuer _safe_filename() — Schutz gegen Path Traversal beim E-Mail-Import
import pytest

from src.get_flexquery_emails import _safe_filename


@pytest.mark.parametrize("filename", [
    "flex.1381127.autom_paper_30.20260304.20260313.xml",
    "autom_money.1961241.20260513.csv",
    "U23465466_20260513 (1).csv",
    "normal name-2026.csv",
])
def test_gueltige_dateinamen_bleiben_erhalten(filename):
    assert _safe_filename(filename) == filename


@pytest.mark.parametrize("filename", [
    r"..\..\evil.xml",           # Windows-Traversal
    "../../evil.xml",            # Unix-Traversal
    r"C:\Windows\evil.xml",      # absoluter Windows-Pfad
    "/etc/passwd.xml",           # absoluter Unix-Pfad
    "sub/dir.xml",               # relativer Pfadanteil
    ".hidden.xml",               # fuehrender Punkt
    "a..b.xml",                  # eingebettetes '..'
    "name;rm.xml",               # Sonderzeichen ausserhalb Whitelist
    "",                          # leer
    "   ",                       # nur Whitespace
])
def test_verdaechtige_dateinamen_werden_abgelehnt(filename):
    assert _safe_filename(filename) is None
