# Word Export Format Reference

This document records the current FluentFlow Word export contract. It exists
because the product exports study notes as Word-readable HTML (`.doc`) instead
of a native `.docx` package, and Word / WPS do not interpret browser-oriented
HTML and CSS the same way as Chrome.

## Sources Checked

- Microsoft Support: Word Web Page export has document features that do not map
  cleanly to browser HTML, so layout can change after conversion.
  <https://support.microsoft.com/en-us/topic/limitations-when-you-save-a-word-document-as-a-web-page-f361de08-ca4c-bc53-11ef-138c0e405c44>
- Microsoft Learn: WordprocessingML uses `w:rFonts` for run fonts; Latin and
  East Asian text can be assigned through separate font attributes such as
  `ascii`, `hAnsi`, and `eastAsia`.
  <https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.runfonts?view=openxml-3.0.1>
- Microsoft Learn: `RunFonts.Ascii` maps to the `w:ascii` schema attribute,
  confirming that Word's font model is not just one browser `font-family`.
  <https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.runfonts.ascii?view=openxml-3.0.1>
- Mailchimp Email Design Reference: Word-based Outlook rendering may add table
  side spacing, and `mso-table-lspace` / `mso-table-rspace` are the common
  Office-specific controls for table side spacing.
  <https://templates.mailchimp.com/development/css/client-specific-styles/>

## Current Root Cause

The previous Word export reused the same HTML generated for the in-app Markdown
preview. That HTML contains Tailwind utility classes and browser wrappers such
as horizontal overflow containers. The downloaded `.doc` file only included a
small generic CSS block, so Word / WPS ignored most layout intent.

Observed risks:

- Font fallback varied because the export only set a generic CSS `font-family`
  and did not give Word-compatible Latin / East Asian font hints.
- Tables could exceed or shift outside the visible page because the export did
  not define a Word page section, fixed table width, fixed table layout, or
  Office-specific table side spacing.
- Browser-only wrappers such as `overflow-x-auto` have no reliable meaning in a
  Word document and should not be the source of table layout truth.

## Export Rules

Until FluentFlow moves to real `.docx` generation, Word exports must follow
these rules:

- Use a Word page section with explicit A4 size and margins instead of body
  `max-width`, centered layout, or browser padding.
- Define one unified font stack and include Word-compatible `mso-*` font hints:
  Chinese / East Asian text uses Microsoft YaHei first; Latin and numbers use
  Segoe UI first.
- Tables must be page-width bounded with `width: 100%`,
  `border-collapse: collapse`, `table-layout: fixed`, and
  `mso-table-lspace/rspace: 0pt`.
- Table cells must use explicit border, padding, vertical alignment, and
  wrapping rules so long Chinese, English, or code-like terms do not push a
  column outside the page.
- Keep the exported Word document independent from in-app Tailwind classes; the
  export CSS must be able to render readable notes even if utility class names
  are ignored.

## Future Upgrade

The more durable commercial-grade route is native `.docx` generation with real
WordprocessingML styles, table grids, and `w:rFonts` settings. The current HTML
`.doc` path is a compatibility bridge, not the final export architecture.
