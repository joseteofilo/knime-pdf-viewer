import json
import types

import pymupdf as fitz
import pytest

import extension as ext


def make_pdf(path, pages=3, password=None):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 90), f"Sample Invoice {i + 1}", fontsize=16)
        page.insert_text((72, 120), "Invoice total 1234 EUR payable within 30 days", fontsize=11)
        page.insert_text((72, 140), f"Page number {i + 1} of {pages}", fontsize=11)
    if password:
        doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        doc.save(path)
    doc.close()


class FakeCtx:
    def __init__(self, workflow_data_area, flow_variables=None):
        self._workflow_data_area = workflow_data_area
        self.progress = []
        self.warnings = []
        self.flow_variables = flow_variables or {}

    def get_workflow_data_area_dir(self):
        return self._workflow_data_area

    def set_progress(self, value):
        self.progress.append(value)

    def set_warning(self, message):
        self.warnings.append(message)


def make_node(pdf_path, dpi=96, quality=70, max_docs=50, pages_per_doc=0):
    node = ext.PdfViewerNode()
    node.pdf_path = str(pdf_path)
    node.page_selection = types.SimpleNamespace(first_page=1, last_page=0)
    node.rendering = types.SimpleNamespace(render_dpi=dpi, jpeg_quality=quality)
    node.folder_limits = types.SimpleNamespace(
        max_documents=max_docs, pages_per_document=pages_per_doc
    )
    return node


def make_folder_pdfs(path, names=("a.pdf", "b.pdf")):
    path.mkdir(parents=True, exist_ok=True)
    for name in names:
        make_pdf(path / name, pages=1)


def test_extract_page_data(tmp_path):
    pdf = tmp_path / "sample.pdf"
    make_pdf(pdf)
    doc = fitz.open(pdf)
    data = ext.extract_page_data(doc[0], dpi=96, jpeg_quality=70)
    doc.close()

    assert data["width"] == pytest.approx(595)
    assert data["height"] == pytest.approx(842)
    assert data["img"].startswith("data:image/jpeg;base64,")
    assert len(data["lines"]) > 0
    text = " ".join(line["text"] for line in data["lines"])
    assert "Invoice total 1234 EUR" in text
    for line in data["lines"]:
        assert len(line["words"]) == len(line["text"].split(" "))
        for box in line["words"]:
            assert all(0.0 <= v <= 1.0000001 for v in box)


def test_build_viewer_html_roundtrip(tmp_path):
    pdf = tmp_path / "sample.pdf"
    make_pdf(pdf, pages=2)
    doc = fitz.open(pdf)
    pages = [ext.extract_page_data(doc[i], dpi=72, jpeg_quality=60) for i in range(len(doc))]
    doc.close()

    html = ext.build_viewer_html({"title": "sample.pdf", "documents": [{"name": "sample.pdf", "pages": pages}]})
    assert html.startswith("<!DOCTYPE html>")
    assert "__PAYLOAD__" not in html
    assert 'id="pdf-data"' in html

    marker = 'id="pdf-data">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    data = json.loads(html[start:end].replace("<\\/", "</"))
    assert data["title"] == "sample.pdf"
    assert len(data["documents"][0]["pages"]) == 2


def test_script_tag_injection_is_neutralized(tmp_path):
    pdf = tmp_path / "sample.pdf"
    make_pdf(pdf, pages=1)
    doc = fitz.open(pdf)
    pages = [ext.extract_page_data(doc[0], dpi=72, jpeg_quality=60)]
    doc.close()

    evil = {"title": 'a</script><img src=x onerror=alert(1)>', "documents": [{"name": "x", "pages": pages}]}
    html = ext.build_viewer_html(evil)
    payload_region = html.split('id="pdf-data">', 1)[1].split("</script>", 1)[0]
    assert "<script>" not in payload_region
    assert "</script" not in payload_region


def test_execute_end_to_end(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, pages=2)
    node = make_node(pdf, dpi=72, quality=60)
    ctx = FakeCtx(str(tmp_path / "wf" / "data"))

    result = node.execute(ctx)
    kind, html = result
    assert kind == "view_html"
    assert html.startswith("<!DOCTYPE html>")
    assert len(ctx.progress) == 2
    assert ctx.progress[-1] == pytest.approx(1.0)


def test_page_range_selection(tmp_path):
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, pages=5)
    node = make_node(pdf, dpi=48, quality=50)
    node.page_selection.first_page = 2
    node.page_selection.last_page = 3
    ctx = FakeCtx(str(tmp_path / "wf" / "data"))

    _, html = node.execute(ctx)
    marker = 'id="pdf-data">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    data = json.loads(html[start:end])
    assert len(data["documents"][0]["pages"]) == 2


def test_relative_path_resolution(tmp_path):
    workflow_data = tmp_path / "my_workflow" / "data"
    workflow_data.mkdir(parents=True)
    pdf = tmp_path / "my_workflow" / "doc.pdf"
    make_pdf(pdf, pages=1)

    node = make_node("doc.pdf", dpi=48, quality=50)
    _, html = node.execute(FakeCtx(str(workflow_data)))
    assert html.startswith("<!DOCTYPE html>")


def test_missing_file_raises(tmp_path):
    node = make_node(tmp_path / "does_not_exist.pdf")
    with pytest.raises(FileNotFoundError):
        node.execute(FakeCtx(str(tmp_path / "wf" / "data")))


def test_password_protected_raises(tmp_path):
    pdf = tmp_path / "secret.pdf"
    make_pdf(pdf, pages=1, password="hunter2")
    node = make_node(pdf)
    with pytest.raises(ValueError, match="password"):
        node.execute(FakeCtx(str(tmp_path / "wf" / "data")))


def test_configure_reports_pages(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, pages=4)
    node = make_node(pdf)
    node.configure(FakeCtx(str(tmp_path / "wf" / "data")))
    assert any("4 pages" in record.getMessage() for record in caplog.records)


def _payload(html):
    marker = 'id="pdf-data">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    return json.loads(html[start:end].replace("<\\/", "</"))


def test_folder_library_two_docs(tmp_path):
    folder = tmp_path / "docs"
    make_folder_pdfs(folder, names=("a.pdf", "b.pdf"))
    node = make_node(folder, dpi=48, quality=50)

    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    data = _payload(html)
    assert len(data["documents"]) == 2
    assert [d["name"] for d in data["documents"]] == ["a.pdf", "b.pdf"]
    assert 'id="docSelect"' in html and "hidden" in html  # dropdown shown


def test_folder_single_doc_hides_dropdown(tmp_path):
    folder = tmp_path / "docs"
    make_folder_pdfs(folder, names=("only.pdf",))
    node = make_node(folder, dpi=48, quality=50)

    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    data = _payload(html)
    assert len(data["documents"]) == 1


def test_folder_empty_raises(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir(parents=True)
    node = make_node(folder)

    with pytest.raises(ValueError, match="No PDF files"):
        node.execute(FakeCtx(str(tmp_path / "wf" / "data")))


def test_folder_exceeds_max_documents_raises(tmp_path):
    folder = tmp_path / "docs"
    make_folder_pdfs(folder, names=("a.pdf", "b.pdf", "c.pdf"))
    node = make_node(folder, max_docs=2)

    with pytest.raises(ValueError, match="3 PDFs"):
        node.execute(FakeCtx(str(tmp_path / "wf" / "data")))


def test_folder_pages_per_document_caps(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir(parents=True)
    make_pdf(folder / "a.pdf", pages=5)
    node = make_node(folder, dpi=48, quality=50, pages_per_doc=2)

    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    data = _payload(html)
    assert len(data["documents"][0]["pages"]) == 2


def test_folder_password_skipped(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir(parents=True)
    make_pdf(folder / "locked.pdf", pages=1, password="pw")
    make_pdf(folder / "open.pdf", pages=1)

    node = make_node(folder, dpi=48, quality=50)
    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    data = _payload(html)
    assert [d["name"] for d in data["documents"]] == ["open.pdf"]


def test_folder_case_insensitive_discovery(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir(parents=True)
    make_pdf(folder / "Z.pdf", pages=1)
    make_pdf(folder / "a.PDF", pages=1)

    node = make_node(folder, dpi=48, quality=50)
    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    data = _payload(html)
    assert sorted(d["name"] for d in data["documents"]) == ["Z.pdf", "a.PDF"]


def test_configure_folder_counts_pdfs(tmp_path, caplog):
    import logging

    caplog.set_level(logging.INFO)
    folder = tmp_path / "docs"
    make_folder_pdfs(folder, names=("a.pdf", "b.pdf"))
    node = make_node(folder)
    node.configure(FakeCtx(str(tmp_path / "wf" / "data")))
    assert any("2 PDF" in record.getMessage() for record in caplog.records)


def test_file_mode_ignores_folder_limits(tmp_path):
    pdf = tmp_path / "single.pdf"
    make_pdf(pdf, pages=1)
    node = make_node(pdf, dpi=48, quality=50, max_docs=0, pages_per_doc=1)

    _, html = node.execute(FakeCtx(str(tmp_path / "wf" / "data")))
    assert html.startswith("<!DOCTYPE html>")


def test_configure_empty_path_no_error(tmp_path):
    node = make_node("")
    node.configure(FakeCtx(str(tmp_path / "wf" / "data")))
    assert node is not None


def test_configure_missing_path_warns(tmp_path):
    node = make_node(tmp_path / "does_not_exist.pdf")
    ctx = FakeCtx(str(tmp_path / "wf" / "data"))
    node.configure(ctx)
    assert ctx.warnings
    assert "not found" in ctx.warnings[-1].lower() or "does not exist" in ctx.warnings[-1].lower()
