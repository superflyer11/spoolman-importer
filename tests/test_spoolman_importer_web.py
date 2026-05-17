import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from fastapi.testclient import TestClient
    HAS_FASTAPI = True
except Exception:
    TestClient = None
    HAS_FASTAPI = False


@unittest.skipUnless(HAS_FASTAPI, "FastAPI is not installed")
class TestSpoolmanImporterWeb(unittest.TestCase):
    def load_app(self, tmp):
        env = {
            "IMPORTER_DB_PATH": str(Path(tmp) / "imports.sqlite3"),
            "IMPORTER_BASE_PATH": "/importer",
            "SPOOLMAN_URL": "http://spoolman:7912",
            "PAPERLESS_URL": "http://paperless:8000",
            "PAPERLESS_TOKEN": "paper-token",
            "IMPORTER_WEBHOOK_TOKEN": "webhook-secret",
        }
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules.pop("src.spoolman_importer_web", None)
        module = importlib.import_module("src.spoolman_importer_web")
        return module, TestClient(module.app)

    def test_health_and_upload_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, client = self.load_app(tmp)

            health = client.get("/importer/health")
            self.assertEqual(health.status_code, 200)

            response = client.post(
                "/importer/upload",
                files={"file": ("filaments.json", b'[{"brand":"Bambu Lab","material":"PLA Basic","color":"Gray"}]', "application/json")},
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 303)
            self.assertEqual(len(module.store.list_imports()), 1)
            self.assertEqual(module.store.list_imports()[0]["rows"][0]["material"], "PLA Basic")

    def test_paperless_webhook_fetches_content_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, client = self.load_app(tmp)
            paperless_response = MagicMock()
            paperless_response.json.return_value = {
                "id": 123,
                "content": "Bambu Lab PLA Basic Filament Gray 1kg 1.75mm Qty: 1 $13.99",
            }
            paperless_response.raise_for_status.return_value = None

            with patch.object(module.requests, "get", return_value=paperless_response) as mock_get:
                first = client.post(
                    "/importer/webhooks/paperless",
                    headers={"X-Importer-Token": "webhook-secret"},
                    json={"document_id": 123, "doc_url": "https://paperless/doc/123"},
                )
                second = client.post(
                    "/importer/webhooks/paperless",
                    headers={"X-Importer-Token": "webhook-secret"},
                    json={"document_id": 123, "doc_url": "https://paperless/doc/123"},
                )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(first.json()["import_id"], second.json()["import_id"])
            self.assertEqual(len(module.store.list_imports()), 1)
            self.assertEqual(module.store.list_imports()[0]["rows"][0]["color"], "Gray")
            mock_get.assert_called_with(
                "http://paperless:8000/api/documents/123/",
                headers={"Authorization": "Token paper-token", "Accept": "application/json"},
                params=None,
                timeout=10,
            )


    def test_index_lists_paperless_tagged_documents_and_creates_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, client = self.load_app(tmp)
            tags_response = MagicMock()
            tags_response.json.return_value = {"results": [{"id": 9, "name": "filament"}], "next": None}
            tags_response.raise_for_status.return_value = None
            documents_response = MagicMock()
            documents_response.json.return_value = {
                "results": [{"id": 321, "title": "Bambu receipt", "created": "2026-05-16"}],
                "next": None,
            }
            documents_response.raise_for_status.return_value = None
            document_response = MagicMock()
            document_response.json.return_value = {
                "id": 321,
                "content": "Bambu Lab PLA Basic Filament Gray 1kg 1.75mm Qty: 2 $13.99",
            }
            document_response.raise_for_status.return_value = None

            with patch.object(module.requests, "get", side_effect=[tags_response, documents_response, document_response]) as mock_get:
                page = client.get("/importer/")
                response = client.post("/importer/paperless/documents/321/review", follow_redirects=False)

            self.assertEqual(page.status_code, 200)
            self.assertIn("Bambu receipt", page.text)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/importer/imports/1")
            self.assertEqual(module.store.list_imports()[0]["source_ref"], "321")
            self.assertEqual(module.store.list_imports()[0]["rows"][0]["quantity"], 2)
            mock_get.assert_any_call(
                "http://paperless:8000/api/tags/",
                headers={"Authorization": "Token paper-token", "Accept": "application/json"},
                params={"page_size": 100},
                timeout=10,
            )
            mock_get.assert_any_call(
                "http://paperless:8000/api/documents/",
                headers={"Authorization": "Token paper-token", "Accept": "application/json"},
                params={"tags__id__all": 9, "page_size": 25, "ordering": "-created"},
                timeout=10,
            )

    def test_webhook_requires_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            module, client = self.load_app(tmp)

            response = client.post("/importer/webhooks/paperless", json={"document_id": 123})

            self.assertEqual(response.status_code, 401)
            self.assertEqual(module.store.list_imports(), [])


if __name__ == "__main__":
    unittest.main()
