# Changelog

All notable changes to `pdf_viewer` are documented here.
For the full text of each release, see the
[GitHub Releases](https://github.com/joseteofilo/knime-pdf-viewer/releases).

## [0.1.0] - 2026-10-17

First public release of the PDF Viewer extension.

### Added
- **PDF Viewer** node (Visualizer): Adobe-like reader view inside KNIME
  with continuous scrolling, page navigation, zoom (fit-width, 25%–400%)
  and full-text search with highlighted matches.
- Single-file mode: page-range selection, DPI / JPEG quality settings,
  progress reporting and clear configuration errors.
- Folder mode: document dropdown, password-protected PDFs skipped,
  per-document and total-size caps to prevent runaway memory.
- Scanned PDFs without a text layer are displayed fine; search is
  disabled with a notice.

[0.1.0]: https://github.com/joseteofilo/knime-pdf-viewer/releases/tag/v0.1.0
