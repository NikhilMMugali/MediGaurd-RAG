import fitz


def _make_pdf_bytes(text: str = "Patient P999 has a diagnosis of Hypertension.") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _login(client, seeded_doctor):
    response = client.post(
        "/api/auth/login",
        json={"username": "doctor01", "password": "secret123", "role": "DOCTOR"},
    )
    return response.json()["access_token"]


def test_upload_requires_auth(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.pdf", _make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_rejects_non_pdf(client, seeded_doctor):
    token = _login(client, seeded_doctor)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("test.txt", b"not a pdf", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_upload_extracts_pdf_text(client, seeded_doctor):
    token = _login(client, seeded_doctor)
    response = client.post(
        "/api/documents/upload",
        files={"file": ("patient_p999.pdf", _make_pdf_bytes(), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "EXTRACTED"
    assert body["page_count"] == 1
