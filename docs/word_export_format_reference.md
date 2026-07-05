# Word Export Format Reference

This document records the FluentFlow Word export contract.

## Current Contract

FluentFlow exports study notes as native `.docx` files generated in the browser
with the `docx` package. The previous HTML `.doc` compatibility bridge has been
removed because Word and WPS do not reliably preserve browser HTML/CSS layout,
list markers, spacing, fonts, or table widths.

## Native `.docx` Rules

- Generate a real Office Open XML package with `docx`, not an HTML file renamed
  to `.doc`.
- Use PingFang SC as the default run font for Chinese, English, and numbers.
- Convert Markdown headings into Word heading paragraphs.
- Convert Markdown unordered and ordered lists into native Word list structures.
- Convert Markdown pipe tables into native Word table rows and cells with fixed
  full-page width, borders, padding, and wrapping.
- Convert code blocks, blockquotes, horizontal rules, and normal paragraphs into
  document-level Word paragraphs rather than reusing in-app preview DOM.
- Keep export spacing controlled by Word paragraph spacing. Do not emit preview
  `<br/>` placeholders or manual web list-marker spans.

## PDF Export Boundary

PDF export uses the browser's native print pipeline. FluentFlow renders a
dedicated white print document from the edited Markdown note and calls
`window.print()`. The user saves the system print output as PDF.

This intentionally replaces the old `html2pdf` / `html2canvas` screenshot path,
which was fragile for long notes, hidden DOM, dark-mode editor surfaces, tables,
and pagination.

## Known Follow-Up

Markdown image references are currently exported to `.docx` as readable image
captions/links rather than embedded binary images. Embedding screenshots should
be implemented as a separate export-artifact task because it needs stable image
fetching, authentication/cross-origin handling, and failure isolation.
