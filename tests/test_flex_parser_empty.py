# Regressionstest: Bei leerer oder unlesbarer XML-Datei lieferte process_flex_file nur eine Zahl, die
# Aufrufer erwarten aber (eingefuegt, gefunden) -- der Import brach mit TypeError ab.

from src.parsers.flex_parser import process_flex_file


class _Logger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def test_datei_ohne_statements(tmp_path):
    f = tmp_path / "leer.xml"
    f.write_text('<FlexQueryResponse><FlexStatements count="0"></FlexStatements></FlexQueryResponse>')

    assert process_flex_file(f, None, None, _Logger(), "test") == (0, 0)


def test_unlesbare_datei(tmp_path):
    f = tmp_path / "kaputt.xml"
    f.write_text("<FlexQueryResponse><nicht geschlossen")

    assert process_flex_file(f, None, None, _Logger(), "test") == (0, 0)
