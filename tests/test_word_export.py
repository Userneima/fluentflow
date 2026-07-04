from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_word_export_uses_word_page_and_font_slots() -> None:
    source = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert "export const buildWordSummaryHtml = (md) => {" in source
    assert "@page WordSection1" in source
    assert 'mso-fareast-font-family: "Microsoft YaHei"' in source
    assert 'mso-ascii-font-family: "Segoe UI"' in source
    assert 'mso-hansi-font-family: "Segoe UI"' in source
    assert '<w:DoNotOptimizeForBrowser/>' in source


def test_word_export_tables_are_bounded_for_word_import() -> None:
    source = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert ".ff-word-summary table" in source
    assert "table-layout: fixed" in source
    assert "mso-table-lspace: 0pt" in source
    assert "mso-table-rspace: 0pt" in source
    assert "overflow-wrap: anywhere" in source
    assert "max-width: 100%" in source


def test_word_export_reference_records_cause_and_upgrade_path() -> None:
    reference = (ROOT / "docs/word_export_format_reference.md").read_text(encoding="utf-8")

    assert "Word / WPS do not interpret browser-oriented" in reference
    assert "HTML and CSS" in reference
    assert "w:rFonts" in reference
    assert "mso-table-lspace/rspace: 0pt" in reference
    assert "native `.docx` generation" in reference
