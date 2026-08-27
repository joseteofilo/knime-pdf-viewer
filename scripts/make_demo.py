"""Generate a sample multi-PDF folder and render the library view HTML.

Run with:  pixi run python scripts/make_demo.py
Open the produced demo/pdf_library_demo.html in a browser to try the viewer
(search, zoom, page navigation, document switching, text selection + copy).
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pymupdf

import extension as ext

FOLDER = "demo/pdfs"
OUT = "demo/pdf_library_demo.html"

LINES = [
    "Chlorogenic acid attenuates oxidative stress in liver tissue.",
    "Invoice total 1234 EUR payable within 30 days of receipt.",
    "Select any text and press Cmd/Ctrl+C or click Copy.",
    "Switch documents from the dropdown on the left of the toolbar.",
]


def make_pdfs():
    if os.path.exists(FOLDER):
        shutil.rmtree(FOLDER)
    os.makedirs(FOLDER)
    for i in range(3):
        doc = pymupdf.open()
        for p in range(2):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 80), f"Report {i + 1} - Page {p + 1}", fontsize=18)
            y = 130
            for _ in range(8):
                for line in LINES:
                    page.insert_text((72, y), line, fontsize=11)
                    y += 18
        doc.save(os.path.join(FOLDER, f"report_{i + 1}.pdf"))
        doc.close()


def build():
    make_pdfs()
    documents = []
    for name in sorted(os.listdir(FOLDER)):
        if not name.lower().endswith(".pdf"):
            continue
        doc = pymupdf.open(os.path.join(FOLDER, name))
        pages = [ext.extract_page_data(doc[i], 110, 70) for i in range(len(doc))]
        doc.close()
        documents.append({"name": name, "pages": pages})
    payload = {
        "title": f"pdfs ({len(documents)} documents)",
        "documents": documents,
    }
    html = ext.build_viewer_html(payload)
    with open(OUT, "w") as fh:
        fh.write(html)
    print(f"wrote {OUT} ({len(html) / 1024 / 1024:.1f} MB, {len(documents)} docs)")


if __name__ == "__main__":
    build()
