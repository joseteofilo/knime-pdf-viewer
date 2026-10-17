# knime-pdf-viewer

A pure-Python [KNIME](https://www.knime.com) extension that adds a **PDF Viewer** node:
an Adobe-like reader view inside KNIME with continuous scrolling, page navigation,
zoom (fit-width, 25%–400%) and full-text search with highlighted matches.

Built on the [KNIME Python Extension API](https://docs.knime.com/developers/latest/create_a_node_with_python)
and [PyMuPDF](https://pymupdf.readthedocs.io/). The view is a fully self-contained
HTML document, so it works in KNIME Analytics Platform without external resources.

## Node

**PDF Viewer** (`Visualizer`, no ports) — settings:

| Setting | Default | Description |
|---|---|---|
| PDF file path | – | Path to a `.pdf` **or a folder** of PDFs; relative paths resolve against the workflow directory |
| First / Last page | 1 / 0 | Page range to render for a single file; ignored in folder mode |
| Render resolution | 144 DPI | Rasterization sharpness vs. view size |
| JPEG quality | 80 % | Compression of the rendered page images |
| Max documents | 50 | Folder mode: cap on PDFs rendered into one view |
| Pages per document | 0 | Folder mode: cap on pages per PDF (0 = all) |

### Folder mode

Point *PDF file path* at a folder, then execute:

- The view opens with a **dropdown listing every PDF** in the folder — pick one
  to render it instantly with the same search / zoom / page navigation.
- Password-protected PDFs are **skipped** (with a warning); a single protected
  file raises an error.
- Caps prevent runaway memory on huge folders: if the folder holds more than
  *Max documents* PDFs, the node errors out (raise the limit or use a subfolder);
  if the total view exceeds ~120 MB it errors with guidance to lower the DPI /
  JPEG quality / pages-per-document.

Scanned PDFs without a text layer are displayed fine; search is disabled with a
notice. Password-protected files raise a configuration error (folder mode skips them).

## Development

```bash
pixi install            # create the environment
pixi run pytest         # run offline tests (no KNIME needed)
pixi run format         # ruff formatting

# test inside KNIME: register for debugging, then restart AP
pixi run register-debug-in-knime
```

For debug registration, add to `knime.ini` (before `-vmargs`):

```
-Dknime.python.extension.config=/absolute/path/to/this/folder/config.yml
```

`config.yml` already points at this folder's pixi environment.

## Bundling

A pre-built update site is attached to each [GitHub Release](https://github.com/joseteofilo/knime-pdf-viewer/releases):
download and unzip `pdf_viewer-<version>-update-site.zip`, then install from
the unzipped folder via *Help → Install KNIME Extensions* after registering it
under *Preferences → Install/Update → Available Software Sites → Add * (the
folder containing `artifacts.jar`/`content.jar`).

To build locally instead (or for pushing to KNIME's Jenkins build):

```bash
pixi run build                      # -> ./local-update-site
# or: pixi run build --dest /some/dir
```

Install from the update site via *Help → Install KNIME Extensions* after registering
the folder under *Preferences → Install/Update → Available Software Sites → Add…*
(the folder containing `artifacts.jar`/`content.jar`).
