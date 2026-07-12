from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_word_export_generates_native_docx_not_html_doc() -> None:
    source = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")
    package = (ROOT / "package.json").read_text(encoding="utf-8")

    assert '"docx"' in package
    assert "export const buildSummaryDocxDocument = async (md) => {" in source
    assert "await import('docx')" in source
    assert "Packer.toBlob(doc)" in source
    assert "_summary.docx" in source
    assert "application/vnd.ms-word" not in source
    assert "_summary.doc'" not in source
    assert "buildWordSummaryHtml" not in source
    assert "WORD_EXPORT_CSS" not in source


def test_word_export_uses_native_docx_styles_lists_and_tables() -> None:
    source = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert "const DOCX_FONT = 'PingFang SC'" in source
    assert "run: {font: DOCX_FONT" in source
    assert "bullet: {level: 0}" in source
    assert "numbering: {reference: 'ff-numbering', level: 0}" in source
    assert "new docx.Table({" in source
    assert "layout: docx.TableLayoutType.FIXED" in source
    assert "type: docx.WidthType.PERCENTAGE" in source
    assert "renderManualListMarkers: false" in source


def test_word_export_embeds_markdown_images_when_fetchable() -> None:
    source = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert "const fetchDocxImage = async (src) => {" in source
    assert "import {API_BASE, apiFetch} from '../app/apiConfig.js';" in source
    assert "if(API_BASE) return `${API_BASE}${raw}`;" in source
    assert "? await apiFetch(target)" in source
    assert ": await fetch(target, {credentials: 'include'})" in source
    assert "new docx.ImageRun({" in source
    assert "type: image.type" in source
    assert "data: image.data" in source
    assert "altText: {name: caption" in source
    assert "const rewriteExportImageSources = (md) =>" in source
    assert "children.push(...await docxImageBlocks(docx, alt, src));" in source


def test_word_export_reference_records_native_contract() -> None:
    reference = (ROOT / "docs/word_export_format_reference.md").read_text(encoding="utf-8")

    assert "native `.docx`" in reference
    assert "HTML `.doc` compatibility bridge has been" in reference
    assert "PingFang SC" in reference
    assert "native Word table" in reference
    assert "native Word list" in reference
    assert "Markdown image references" in reference
    assert "embedded Word images" in reference


def test_pdf_export_uses_browser_print_not_canvas_capture() -> None:
    download = (ROOT / "frontend/src/lib/download.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")

    assert "const buildPrintableSummaryHtml = (md" in download
    assert "export const createPdfPrintFrame = (html) => {" in download
    assert "frame.srcdoc = html" in download
    assert "printWindow.print()" in download
    assert "simpleMd(rewriteExportImageSources(md), {renderImages: true, renderManualListMarkers: false})" in download
    assert "html2pdf" not in download
    assert "html2pdf" not in index
