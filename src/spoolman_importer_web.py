"""FastAPI review UI and Paperless webhook integration for Spoolman imports."""

from __future__ import annotations

import hashlib
import json
import os
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from src.bambu_parser import parse_bambu_invoice_text
from src.import_store import ImportStore
from src.spoolman_importer import PdfReader, REQUEST_TIMEOUT, SpoolmanImporter


load_dotenv()

BASE_PATH = os.getenv("IMPORTER_BASE_PATH", "/importer").rstrip("/") or "/importer"
PUBLIC_BASE_URL = os.getenv("IMPORTER_PUBLIC_BASE_URL", "").rstrip("/")
DATA_DIR = Path(os.getenv("IMPORTER_DATA_DIR", "/data"))
DB_PATH = Path(os.getenv("IMPORTER_DB_PATH", DATA_DIR / "imports.sqlite3"))
SPOOLMAN_URL = os.getenv("SPOOLMAN_URL", "http://localhost:7912")
PAPERLESS_URL = os.getenv("PAPERLESS_URL", "").rstrip("/")
PAPERLESS_TOKEN = os.getenv("PAPERLESS_TOKEN", "")
PAPERLESS_IMPORT_TAG = os.getenv("PAPERLESS_IMPORT_TAG", "filament")
WEBHOOK_TOKEN = os.getenv("IMPORTER_WEBHOOK_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

store = ImportStore(DB_PATH)
app = FastAPI(title="Spoolman Importer", docs_url=f"{BASE_PATH}/docs", redoc_url=None, openapi_url=f"{BASE_PATH}/openapi.json")
router = APIRouter(prefix=BASE_PATH)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(_app_url("/"))


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> str:
    rows = store.list_imports()
    body = ["<h1>Spoolman Importer</h1>"]
    body.append("""
<form action="{base}/upload" method="post" enctype="multipart/form-data" class="panel">
  <label>Upload Bambu invoice PDF or importer JSON</label>
  <input type="file" name="file" accept=".pdf,.json,application/pdf,application/json" required>
  <button type="submit">Create Review</button>
</form>
""".format(base=_app_url(request=request)))
    body.append("<h2>Pending and Recent Imports</h2>")
    if not rows:
        body.append("<p>No imports yet.</p>")
    else:
        body.append("<table><thead><tr><th>ID</th><th>Source</th><th>Status</th><th>Rows</th><th>Created</th></tr></thead><tbody>")
        for record in rows:
            source = f"{record['source_type']}:{record['source_ref']}"
            body.append(
                "<tr>"
                f"<td><a href='{_app_url(f'/imports/{record['id']}', request)}'>#{record['id']}</a></td>"
                f"<td>{escape(source)}</td>"
                f"<td>{escape(record['status'])}</td>"
                f"<td>{len(record['rows'])}</td>"
                f"<td>{escape(record['created_at'])}</td>"
                "</tr>"
            )
        body.append("</tbody></table>")
    body.append(_paperless_documents_section(request))
    body.append(_setup_notes())
    return _page("Spoolman Importer", "".join(body))


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> RedirectResponse:
    content = await file.read()
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    source_ref = f"{filename}:{hashlib.sha256(content).hexdigest()[:16]}"

    if suffix == ".json" or file.content_type == "application/json":
        rows, warnings = _rows_from_json_bytes(content)
        import_id = store.create_import("upload-json", source_ref, rows, warnings)
    elif suffix == ".pdf" or file.content_type == "application/pdf":
        text = _text_from_pdf_bytes(content)
        parsed = parse_bambu_invoice_text(text)
        import_id = store.create_import("upload-pdf", source_ref, parsed.filaments, parsed.warnings)
    else:
        raise HTTPException(status_code=400, detail="Upload a .json or .pdf file")

    return RedirectResponse(_app_url(f"/imports/{import_id}", request), status_code=303)


@router.post("/webhooks/paperless")
async def paperless_webhook(request: Request) -> Dict[str, Any]:
    _authorize_webhook(request)
    payload = await request.json()
    document_id = payload.get("document_id") or payload.get("document") or payload.get("id")
    if not document_id:
        raise HTTPException(status_code=400, detail="document_id is required")

    import_id = _create_paperless_review(str(document_id), payload.get("doc_url"))
    record = _require_record(import_id)
    return {"import_id": import_id, "review_url": _app_url(f"/imports/{import_id}"), "rows": len(record["rows"])}


@router.post("/paperless/documents/{document_id}/review")
def create_paperless_document_review(document_id: int, request: Request) -> RedirectResponse:
    import_id = _create_paperless_review(str(document_id))
    return RedirectResponse(_app_url(f"/imports/{import_id}", request), status_code=303)


@router.get("/imports/{import_id}", response_class=HTMLResponse)
def review_import(import_id: int, request: Request) -> str:
    record = _require_record(import_id)
    rows_json = json.dumps(record["rows"], indent=2)
    warnings = list(record["warnings"])
    preview = _build_preview(record)
    warnings.extend(preview.pop("warnings", []))

    body = [f"<h1>Review Import #{record['id']}</h1>"]
    body.append(f"<p><a href='{_app_url(request=request)}'>Back to imports</a></p>")
    body.append("<dl>")
    body.append(f"<dt>Status</dt><dd>{escape(record['status'])}</dd>")
    body.append(f"<dt>Source</dt><dd>{escape(record['source_type'])}:{escape(record['source_ref'])}</dd>")
    if record.get("doc_url"):
        body.append(f"<dt>Paperless</dt><dd><a href='{escape(record['doc_url'])}'>{escape(record['doc_url'])}</a></dd>")
    body.append("</dl>")

    if warnings:
        body.append("<h2>Warnings</h2><ul class='warnings'>")
        for warning in warnings:
            body.append(f"<li>{escape(warning)}</li>")
        body.append("</ul>")

    body.append("<h2>Duplicate Preview</h2>")
    body.append(_preview_table(preview.get("rows", [])))
    body.append("""
<h2>Edit Rows</h2>
<form action="{base}/imports/{id}/import" method="post" class="panel">
  <label>Importer JSON</label>
  <textarea name="rows_json" rows="18" spellcheck="false">{rows}</textarea>
  <button type="submit" {disabled}>Import Approved Rows</button>
</form>
""".format(base=_app_url(request=request), id=record["id"], rows=escape(rows_json), disabled="disabled" if record["status"] == "imported" else ""))
    if record.get("import_log"):
        body.append("<h2>Import Log</h2>")
        body.append(f"<pre>{escape(record['import_log'])}</pre>")
    return _page(f"Review Import #{record['id']}", "".join(body))


@router.post("/imports/{import_id}/import")
async def import_rows(import_id: int, request: Request, rows_json: str = Form(...)) -> RedirectResponse:
    record = _require_record(import_id)
    if record["status"] == "imported":
        return RedirectResponse(_app_url(f"/imports/{import_id}", request), status_code=303)

    rows, warnings = _rows_from_json_text(rows_json)
    if not rows:
        store.update_rows(import_id, rows, [*record["warnings"], *warnings, "No valid rows to import."])
        store.update_status(import_id, "failed", "No valid rows to import.")
        return RedirectResponse(_app_url(f"/imports/{import_id}", request), status_code=303)

    store.update_rows(import_id, rows, [*record["warnings"], *warnings])
    importer = _make_importer()
    existing_filaments = importer.get_filaments()
    source_filename = f"{record['source_type']}-{record['source_ref']}"
    log_lines: List[str] = []
    success_count = 0

    for row in rows:
        vendor = importer._resolve_vendor_name(row, "Bambu Lab")
        if not vendor:
            log_lines.append(f"Skipped {row.get('material')} {row.get('color')}: no vendor")
            continue
        enriched = importer._enrich_filament(row, vendor, interactive=False)
        if not enriched:
            log_lines.append(f"Skipped {vendor} {row.get('material')} {row.get('color')}: no vendor defaults")
            continue
        vendor_id = importer.get_or_create_vendor(vendor)
        if not vendor_id:
            log_lines.append(f"Skipped {vendor} {row.get('material')} {row.get('color')}: vendor create failed")
            continue
        if importer.import_filament(enriched, vendor_id, existing_filaments, source_filename, interactive=False):
            success_count += 1
            log_lines.append(f"Imported {vendor} {enriched['material']} {enriched['color']} x{enriched.get('quantity', 1)}")
        else:
            log_lines.append(f"Failed {vendor} {enriched['material']} {enriched['color']}")

    status = "imported" if success_count == len(rows) else "failed"
    log_lines.append(f"Successfully imported {success_count}/{len(rows)} rows.")
    store.update_status(import_id, status, "\n".join(log_lines))
    return RedirectResponse(_app_url(f"/imports/{import_id}", request), status_code=303)


app.include_router(router)


def _app_url(path: str = "/", request: Request | None = None) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}{suffix}" if suffix != "/" else f"{PUBLIC_BASE_URL}/"
    if request is not None:
        host = request.headers.get("host", "").split(":", 1)[0]
        if host.startswith("spoolman."):
            domain = host.removeprefix("spoolman.")
            base = f"https://home.{domain}{BASE_PATH}"
            return f"{base}{suffix}" if suffix != "/" else f"{base}/"
    return f"{BASE_PATH}{suffix}" if suffix != "/" else f"{BASE_PATH}/"


def _rows_from_json_bytes(content: bytes) -> tuple[List[Dict], List[str]]:
    try:
        return _rows_from_json_text(content.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON upload must be UTF-8") from exc


def _rows_from_json_text(text: str) -> tuple[List[Dict], List[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    rows = _make_importer()._validate_filaments(data)
    warnings = [] if rows else ["No valid filament rows found in JSON."]
    return rows, warnings


def _text_from_pdf_bytes(content: bytes) -> str:
    if PdfReader is None:
        raise HTTPException(status_code=500, detail="pypdf is not installed; PDF upload is unavailable")
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}") from exc


def _authorize_webhook(request: Request) -> None:
    if not WEBHOOK_TOKEN:
        return
    auth = request.headers.get("authorization", "")
    token = request.headers.get("x-importer-token", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
    if token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid webhook token")


def _create_paperless_review(document_id: str, doc_url: str | None = None) -> int:
    document = _fetch_paperless_document(document_id)
    content = document.get("content") or ""
    if not doc_url:
        doc_url = document.get("doc_url") or _paperless_document_url(document_id)

    parsed = parse_bambu_invoice_text(content)
    warnings = list(parsed.warnings)
    if not content.strip():
        warnings.append("Paperless document content was empty; OCR may not have completed yet.")

    return store.create_import("paperless", document_id, parsed.filaments, warnings, doc_url=doc_url)


def _paperless_headers() -> Dict[str, str]:
    return {"Authorization": f"Token {PAPERLESS_TOKEN}", "Accept": "application/json"}


def _paperless_document_url(document_id: str | int) -> str | None:
    return f"{PAPERLESS_URL}/documents/{document_id}/details" if PAPERLESS_URL else None


def _paperless_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not PAPERLESS_URL or not PAPERLESS_TOKEN:
        raise HTTPException(status_code=500, detail="PAPERLESS_URL and PAPERLESS_TOKEN are required")
    response = requests.get(
        f"{PAPERLESS_URL}{path}",
        headers=_paperless_headers(),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _paperless_results(path: str, params: Dict[str, Any] | None = None, max_pages: int = 5) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    next_url: str | None = f"{PAPERLESS_URL}{path}"
    request_params = dict(params or {})
    for _ in range(max_pages):
        if not next_url:
            break
        response = requests.get(next_url, headers=_paperless_headers(), params=request_params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            results.extend(item for item in data if isinstance(item, dict))
            break
        if isinstance(data, dict):
            page_results = data.get("results", [])
            results.extend(item for item in page_results if isinstance(item, dict))
            next_url = data.get("next")
            request_params = {}
            if not next_url:
                break
        else:
            break
    return results


def _find_paperless_tag(tag_name: str) -> Dict[str, Any] | None:
    target = tag_name.strip().casefold()
    if not target:
        return None
    tags = _paperless_results("/api/tags/", {"page_size": 100})
    for tag in tags:
        if str(tag.get("name", "")).casefold() == target:
            return tag
    return None


def _fetch_tagged_paperless_documents(tag_name: str, limit: int = 25) -> tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    if not PAPERLESS_URL or not PAPERLESS_TOKEN or PAPERLESS_TOKEN.startswith("change-me"):
        return [], ["Set PAPERLESS_URL and a valid PAPERLESS_TOKEN to list tagged Paperless documents."]
    tag = _find_paperless_tag(tag_name)
    if not tag:
        return [], [f"Paperless tag '{tag_name}' was not found."]

    documents = _paperless_results(
        "/api/documents/",
        {"tags__id__all": tag["id"], "page_size": limit, "ordering": "-created"},
        max_pages=1,
    )
    return documents[:limit], warnings


def _fetch_paperless_document(document_id: str) -> Dict[str, Any]:
    return _paperless_get(f"/api/documents/{document_id}/")


def _build_preview(record: Dict) -> Dict[str, Any]:
    importer = _make_importer()
    warnings: List[str] = []
    previews: List[Dict] = []
    try:
        existing_filaments = importer.get_filaments()
        for row in record["rows"]:
            vendor = importer._resolve_vendor_name(row.copy(), "Bambu Lab") or "Bambu Lab"
            enriched = importer._enrich_filament(row, vendor, interactive=False) or row
            vendor_id = importer.find_vendor_id(vendor)
            existing = importer.find_existing_filament(enriched, vendor_id, existing_filaments) if vendor_id else None
            existing_spools = importer.get_spools_for_filament(existing["id"]) if existing else []
            duplicate_count = 0
            for index in range(enriched.get("quantity", 1)):
                import_id = importer._generate_import_id(f"{record['source_type']}-{record['source_ref']}", enriched, index)
                if any(import_id in spool.get("comment", "") for spool in existing_spools):
                    duplicate_count += 1
            previews.append({
                "vendor": vendor,
                "material": enriched.get("material"),
                "color": enriched.get("color"),
                "quantity": enriched.get("quantity", 1),
                "price": enriched.get("price"),
                "filament": "reuse" if existing else "create",
                "duplicates": duplicate_count,
            })
    except Exception as exc:
        warnings.append(f"Could not build Spoolman duplicate preview: {exc}")
    return {"rows": previews, "warnings": warnings}


def _preview_table(rows: List[Dict]) -> str:
    if not rows:
        return "<p>No preview rows available.</p>"
    html = ["<table><thead><tr><th>Vendor</th><th>Material</th><th>Color</th><th>Qty</th><th>Price</th><th>Filament</th><th>Duplicate spools</th></tr></thead><tbody>"]
    for row in rows:
        html.append(
            "<tr>"
            f"<td>{escape(str(row['vendor']))}</td>"
            f"<td>{escape(str(row['material']))}</td>"
            f"<td>{escape(str(row['color']))}</td>"
            f"<td>{escape(str(row['quantity']))}</td>"
            f"<td>{escape(str(row['price']))}</td>"
            f"<td>{escape(str(row['filament']))}</td>"
            f"<td>{escape(str(row['duplicates']))}</td>"
            "</tr>"
        )
    html.append("</tbody></table>")
    return "".join(html)


def _require_record(import_id: int) -> Dict:
    record = store.get_import(import_id)
    if not record:
        raise HTTPException(status_code=404, detail="Import not found")
    return record


def _make_importer() -> SpoolmanImporter:
    return SpoolmanImporter(SPOOLMAN_URL, OPENAI_API_KEY)


def _paperless_documents_section(request: Request | None = None) -> str:
    html = [f"<h2>Paperless Filament Documents</h2>"]
    html.append(f"<p>Showing Paperless documents tagged <code>{escape(PAPERLESS_IMPORT_TAG)}</code>.</p>")
    try:
        documents, warnings = _fetch_tagged_paperless_documents(PAPERLESS_IMPORT_TAG)
    except Exception as exc:
        documents, warnings = [], [f"Could not load Paperless documents: {exc}"]

    if warnings:
        html.append("<ul class='warnings'>")
        for warning in warnings:
            html.append(f"<li>{escape(str(warning))}</li>")
        html.append("</ul>")

    if not documents:
        html.append("<p>No matching Paperless documents found.</p>")
        return "".join(html)

    html.append("<table><thead><tr><th>Document</th><th>Created</th><th>Review</th></tr></thead><tbody>")
    for document in documents:
        document_id = document.get("id")
        title = document.get("title") or document.get("original_file_name") or f"Document {document_id}"
        created = document.get("created") or document.get("added") or ""
        existing = store.get_by_source("paperless", str(document_id)) if document_id is not None else None
        paperless_url = _paperless_document_url(document_id) if document_id is not None else None
        if existing:
            action = f"<a href='{_app_url(f'/imports/{existing['id']}', request)}'>Open review #{existing['id']}</a>"
        elif document_id is not None:
            action = (
                f"<form action='{_app_url(f'/paperless/documents/{document_id}/review', request)}' method='post'>"
                "<button type='submit'>Create Review</button>"
                "</form>"
            )
        else:
            action = "Missing document ID"

        title_html = escape(str(title))
        if paperless_url:
            title_html = f"<a href='{escape(paperless_url)}'>{title_html}</a>"
        html.append(
            "<tr>"
            f"<td>{title_html}</td>"
            f"<td>{escape(str(created))}</td>"
            f"<td>{action}</td>"
            "</tr>"
        )
    html.append("</tbody></table>")
    return "".join(html)


def _setup_notes() -> str:
    return """
<h2>Paperless Webhook</h2>
<pre>{
  "document_id": "{{ id }}",
  "doc_url": "{{ doc_url }}"
}</pre>
<p>Send it to <code>/importer/webhooks/paperless</code> with <code>X-Importer-Token</code> set to <code>IMPORTER_WEBHOOK_TOKEN</code>.</p>
"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }}
    body {{ margin: 0; padding: 2rem; max-width: 1180px; }}
    h1, h2 {{ line-height: 1.2; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border-bottom: 1px solid #9995; padding: .55rem; text-align: left; vertical-align: top; }}
    .panel {{ border: 1px solid #9995; padding: 1rem; margin: 1rem 0; border-radius: 6px; }}
    label {{ display: block; font-weight: 650; margin-bottom: .5rem; }}
    input, textarea, button {{ font: inherit; }}
    textarea {{ box-sizing: border-box; width: 100%; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    button {{ margin-top: .75rem; padding: .55rem .8rem; cursor: pointer; }}
    button:disabled {{ cursor: not-allowed; opacity: .5; }}
    .warnings li {{ margin: .35rem 0; }}
    pre {{ white-space: pre-wrap; overflow-x: auto; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0 0 .6rem 0; }}
  </style>
</head>
<body>{body}</body>
</html>"""
