"""Exercise the native index path past Chroma's in-memory buffering threshold."""
from io import BytesIO
from pathlib import Path
import subprocess
import sys

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_pdf() -> bytes:
    writer = PdfWriter()
    for number in range(130):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td (Upload evidence page {number + 1}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_large_pdf_upload_then_query_reindex_and_health(client):
    # >=100 chunks triggers real HNSW insertion; a one-chunk test can miss it.
    response = client.post("/upload", files={"file": ("中文上传测试.pdf", make_pdf(), "application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["chunks"] >= 100
    assert client.get("/health").status_code == 200
    result = client.post("/ask", json={"question": "Upload evidence page 130", "search_mode": "vector"})
    assert result.status_code == 200, result.text
    assert result.json()["citations"]
    assert client.post("/sources/中文上传测试.pdf/reindex").status_code == 200
    assert client.post("/upload", files={"file": ("second.txt", b"Second document evidence")}).status_code == 200
    assert len(client.get("/sources").json()) == 2
    assert client.get("/health").status_code == 200


def test_native_runtime_preflight():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", str(project / "scripts" / "check_runtime.py")],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Native runtime OK" in result.stdout
