import tempfile
import unittest
from pathlib import Path

from src.import_store import ImportStore


class TestImportStore(unittest.TestCase):
    def test_create_and_get_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ImportStore(Path(tmp) / "imports.sqlite3")

            import_id = store.create_import(
                "paperless",
                "123",
                [{"brand": "Bambu Lab", "material": "PLA Basic", "color": "Gray"}],
                ["warning"],
                doc_url="https://paperless/doc/123",
            )
            record = store.get_import(import_id)

            self.assertEqual(record["source_type"], "paperless")
            self.assertEqual(record["rows"][0]["material"], "PLA Basic")
            self.assertEqual(record["warnings"], ["warning"])
            self.assertEqual(record["doc_url"], "https://paperless/doc/123")

    def test_duplicate_source_returns_existing_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ImportStore(Path(tmp) / "imports.sqlite3")

            first = store.create_import("paperless", "123", [{"a": 1}], [])
            second = store.create_import("paperless", "123", [{"a": 2}], ["new"])

            self.assertEqual(first, second)
            self.assertEqual(len(store.list_imports()), 1)
            self.assertEqual(store.get_import(first)["rows"], [{"a": 1}])

    def test_update_rows_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ImportStore(Path(tmp) / "imports.sqlite3")
            import_id = store.create_import("upload-json", "abc", [], [])

            store.update_rows(import_id, [{"brand": "Bambu Lab"}], ["ok"])
            store.update_status(import_id, "imported", "done")
            record = store.get_import(import_id)

            self.assertEqual(record["status"], "imported")
            self.assertEqual(record["rows"], [{"brand": "Bambu Lab"}])
            self.assertEqual(record["warnings"], ["ok"])
            self.assertEqual(record["import_log"], "done")


if __name__ == "__main__":
    unittest.main()
