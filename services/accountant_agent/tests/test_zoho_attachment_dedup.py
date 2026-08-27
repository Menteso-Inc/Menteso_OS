from types import SimpleNamespace

from src.zoho_client import ZohoClient


class Response:
    def __init__(self, data=None, content=b"", status_code=200):
        self._data = data or {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def client():
    value = object.__new__(ZohoClient)
    value._cfg = SimpleNamespace(zoho_api_base="https://zoho.test/crm/v6")
    value._headers = lambda: {"Authorization": "test"}
    return value


def test_identical_invoice_attachment_is_not_uploaded(monkeypatch):
    pdf = b"same-pdf"
    responses = iter([
        Response({"data": [{
            "id": "a1", "File_Name": "invoice-PID1-INV1 27-Aug.pdf",
            "Size": len(pdf),
        }]}),
        Response(content=pdf),
    ])
    monkeypatch.setattr("src.zoho_client.requests.get", lambda *a, **k: next(responses))
    uploaded = []
    zoho = client()
    zoho._attach = lambda *args: uploaded.append(args)

    changed = zoho._attach_if_changed("Deals", "d1", "invoice-PID1-INV1.pdf", pdf, "PID1", "INV1")

    assert changed is False
    assert uploaded == []


def test_corrected_invoice_attachment_is_uploaded(monkeypatch):
    old_pdf = b"old-pdf!"
    new_pdf = b"new-pdf!"
    responses = iter([
        Response({"data": [{
            "id": "a1", "File_Name": "invoice-PID1-INV1.pdf",
            "Size": len(new_pdf),
        }]}),
        Response(content=old_pdf),
    ])
    monkeypatch.setattr("src.zoho_client.requests.get", lambda *a, **k: next(responses))
    uploaded = []
    zoho = client()
    zoho._attach = lambda *args: uploaded.append(args)

    changed = zoho._attach_if_changed("Deals", "d1", "invoice-PID1-INV1.pdf", new_pdf, "PID1", "INV1")

    assert changed is True
    assert len(uploaded) == 1
