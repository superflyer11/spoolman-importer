# Spoolman Receipt Importer

A Python command-line tool that automatically extracts 3D printer filament data from PDF receipts or JSON files and imports them into [Spoolman](https://github.com/Donkie/Spoolman) via its API.

## Features

- **Multiple Input Sources**: Process PDF receipts or structured JSON files
- **Intelligent Data Extraction**: Uses LLM (OpenAI GPT) or pattern matching for PDF processing
- **Vendor Database**: Comprehensive database of filament specifications (spool weight, temperatures, densities)
- **Interactive Handling**: Prompts for missing vendor data with options to reload, stop, or use defaults
- **Batch Processing**: Import multiple filaments from a single receipt
- **Automatic Spool Creation**: Creates both filament types and individual spool instances
- **Dry Run Mode**: Preview imports without actually creating data
- **Temperature Integration**: Stores recommended printing temperatures in Spoolman comments

## Installation

### Requirements

- Docker Compose for the web workflow, or Python 3.9+ for CLI/venv use
- Spoolman instance running on your network
- Optional: Paperless-ngx for invoice-triggered imports
- Optional: OpenAI API key if you later enable LLM fallback paths

### Option 1: Docker web importer (recommended)

```bash
cp .env.example .env
# Edit .env with SPOOLMAN_URL, PAPERLESS_URL, PAPERLESS_TOKEN, and IMPORTER_WEBHOOK_TOKEN
docker compose -f docker-compose.example.yml up --build
```

Open the importer at:

```text
http://localhost:8080/importer/
```

For `https://spoolman.aspiderweb.uk/importer/`, route `/importer/` in your reverse proxy to this container while keeping `/` routed to Spoolman.

### Option 2: Python virtual environment for CLI use

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r src/requirements.txt
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab" --dry-run
```

Conda is no longer required. `src/environment.yml` is kept only for users who already prefer conda.

## Project Structure

```
spoolman-importer/
├── src/
│   ├── spoolman_importer.py      # CLI importer and Spoolman API logic
│   ├── spoolman_importer_web.py  # FastAPI upload/review/Paperless webhook UI
│   ├── bambu_parser.py           # Deterministic Bambu invoice text parser
│   ├── import_store.py           # SQLite pending import store
│   ├── requirements.txt          # Pip requirements file
│   └── resources/
│       ├── color-data.json       # Color name to hex mapping
│       └── vendor-data.json      # Vendor filament database
├── tests/
│   └── test_spoolman_importer.py # Unit tests
├── examples/
│   └── 250603-Bambu.json         # Example JSON input
├── Dockerfile
├── docker-compose.example.yml
└── ReadMe.md                     # This file
```

## Web Importer Workflow

1. Upload a Bambu invoice PDF or importer JSON at `/importer/`, let Paperless create a pending import by webhook, or open `/importer/` and create a review from Paperless documents tagged with `PAPERLESS_IMPORT_TAG`.
2. Review warnings and duplicate preview before writing to Spoolman.
3. Edit the generated JSON rows if OCR or parsing needs correction.
4. Click **Import Approved Rows** to create/reuse Spoolman vendors and filaments, then create non-duplicate spools.

### Paperless-ngx webhook setup

Create a Paperless workflow such as "Bambu Invoice Import" with a **Document Added** trigger filtered by your chosen tag, correspondent, document type, or content rule. Add a webhook action:

- URL: `https://spoolman.aspiderweb.uk/importer/webhooks/paperless`
- Method/body encoding: JSON
- Header: `X-Importer-Token: <IMPORTER_WEBHOOK_TOKEN>`
- Body:

```json
{
  "document_id": "{{ id }}",
  "doc_url": "{{ doc_url }}"
}
```

The importer then fetches Paperless `/api/documents/{id}/`, reads the OCR `content`, parses Bambu filament line items deterministically, and creates a pending review. The importer homepage also lists recent Paperless documents tagged with `PAPERLESS_IMPORT_TAG` so you can create reviews manually after OCR has completed.

## Usage

### Web app

```bash
docker compose -f docker-compose.example.yml up --build
```

Then open `/importer/`, upload a PDF/JSON, review the generated rows, and import. The web app stores pending imports in SQLite under `IMPORTER_DATA_DIR`.

### CLI

```bash
# Import from JSON file
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab"

# Import from PDF receipt. OpenAI is optional and only used when configured.
python src/spoolman_importer.py --pdf receipt.pdf --vendor "Bambu Lab"

# Dry run to preview what would be imported
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab" --dry-run
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SPOOLMAN_URL` | Spoolman API base URL |
| `IMPORTER_BASE_PATH` | Web path prefix, defaults to `/importer` |
| `IMPORTER_PUBLIC_BASE_URL` | Optional canonical browser URL for generated links and redirects |
| `IMPORTER_DATA_DIR` | Directory for SQLite data, defaults to `/data` |
| `IMPORTER_WEBHOOK_TOKEN` | Shared secret required by Paperless webhook |
| `PAPERLESS_URL` | Paperless base URL |
| `PAPERLESS_TOKEN` | Paperless API token |
| `OPENAI_API_KEY` | Optional LLM fallback key |

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--json` | Path to JSON file containing filament data | Either --json or --pdf required |
| `--pdf` | Path to PDF receipt file | Either --json or --pdf required |
| `--spoolman-url` | Spoolman instance URL | `SPOOLMAN_URL` env var or `http://localhost:7912` |
| `--vendor` | Fallback vendor name if not specified in the input file | None |
| `--openai-key` | Optional OpenAI API key for PDF fallback | `OPENAI_API_KEY` env var |
| `--dry-run` | Preview imports without creating data | False |

### JSON Input Format

#### Simple Array Format
```json
[
  {
    "brand": "Bambu Lab",
    "material": "PLA Basic",
    "color": "Galaxy Black",
    "diameter": 1.75,
    "weight": 1000,
    "price": 24.99,
    "quantity": 2,
    "spool_weight": 260
  },
  {
    "brand": "Prusa",
    "material": "PETG",
    "color": "Transparent Blue",
    "weight": 1000,
    "price": 29.99,
    "quantity": 1
  }
]
```

#### Field Descriptions

| Field | Type              | Description | Default |
|-------|-------------------|-------------|---------|
| `brand` | string            | Manufacturer name | "Unknown" |
| `material` | string            | Material type (PLA, PETG, ABS, etc.) | "PLA" |
| `color` | string            | Filament color | "Unknown" |
| `diameter` | number            | Filament diameter in mm | 1.75 |
| `weight` | number            | Filament weight in grams | 1000 |
| `price` | number            | Unit price | 0.0 |
| `quantity` | number            | Number of spools | 1 |
| `spool_weight` | number (optional) | Empty spool weight in grams | From vendor data |

## Vendor Database

The script includes a comprehensive vendor database (`src/resources/vendor-data.json`) with specifications for major filament manufacturers:

### Supported Vendors

- **Bambu Lab**: PLA Basic/Matte/Silk, PETG, ABS, TPU 95A
- **Prusa**: PLA, PETG, ASA, ABS, PC Blend
- **eSUN**: PLA+, PETG, ABS+, SILK PLA, Wood PLA
- **SUNLU**: PLA, PLA+, PETG, ABS, SILK PLA
- **Polymaker**: PolyLite series, PolyTerra (cardboard spools)
- **Generic**: Fallback defaults for unknown brands

### Automatic Data Enrichment

The script automatically adds missing information based on the vendor database:

- **Spool Weight**: Vendor-specific empty spool weights
- **Printing Temperatures**: Recommended extruder and bed temperatures
- **Material Density**: For accurate volume calculations in Spoolman
- **Descriptions**: Vendor-specific product descriptions

### Interactive Handling

When vendor data is missing, the script offers three options:

```
Warning: No vendor data found for 'CustomBrand' - 'PLA+'

Available default material types:
  1. PLA (spool: 250g, ext: 220°C, bed: 60°C, density: 1.24)
  2. PETG (spool: 250g, ext: 240°C, bed: 80°C, density: 1.27)
  3. ABS (spool: 250g, ext: 240°C, bed: 90°C, density: 1.04)
  ...

Options:
  r) Reload vendor-data.json file
  s) Stop import
  1-7) Use material default

Choose option [r/s/1-7]: 
```

## Data Management

### Deleting All Spools or Filaments

The delete helpers are intentionally guarded. They check for `curl` and `jq`, show the target URL and item count, support dry-run, require typing `DELETE ALL`, and require typing the target URL exactly before deleting.

```bash
./scripts/delete_all_spools.sh --dry-run http://localhost:7912
./scripts/delete_all_filaments.sh --dry-run http://localhost:7912
```

Remove `--dry-run` only when you are ready to delete.

**Note:** Deleting filaments can also remove associated spool data depending on Spoolman behavior and constraints.

## Testing

Install development dependencies in a venv or Docker image, then run the suite:

```bash
pip install -r src/requirements-dev.txt
python -m unittest discover -s tests -v
```

FastAPI endpoint tests are skipped if the web dependencies are not installed.

## Configuration

The web app and CLI read `.env` automatically when present. The most important values are:

| Variable | Description | Default |
|----------|-------------|---------|
| `SPOOLMAN_URL` | Spoolman API base URL | `http://localhost:7912` |
| `IMPORTER_BASE_PATH` | Web route prefix | `/importer` |
| `IMPORTER_PUBLIC_BASE_URL` | Canonical browser URL for links/redirects when needed | Empty |
| `IMPORTER_DATA_DIR` | SQLite data directory in Docker | `/data` |
| `IMPORTER_WEBHOOK_TOKEN` | Shared secret for Paperless webhook requests | Empty in code, set in deployment |
| `PAPERLESS_IMPORT_TAG` | Paperless tag name shown on the importer homepage | `filament` |
| `PAPERLESS_URL` | Paperless base URL | None |
| `PAPERLESS_TOKEN` | Paperless API token | None |
| `OPENAI_API_KEY` | Optional LLM fallback key | None |

CLI command-line arguments override environment values for the CLI process.

### Vendor Data Customization

Edit `src/resources/vendor-data.json` to:

- Add new vendors
- Update existing specifications
- Add custom material types
- Modify temperature recommendations

**Example - Adding a new vendor**:
```json
{
  "vendors": {
    "MyVendor": {
      "PLA": {
        "spool_weight": 280,
        "extruder_temp": 210,
        "bed_temp": 65,
        "description": "MyVendor PLA Filament"
      }
    }
  }
}
```

## API Integration

### Spoolman API Endpoints Used

- `GET /api/v1/vendor` - List vendors
- `POST /api/v1/vendor` - Create vendor
- `POST /api/v1/filament` - Create filament type
- `POST /api/v1/spool` - Create spool instance

### Data Mapping

| JSON Field | Spoolman Field | Notes |
|------------|----------------|-------|
| `brand` | `vendor_id` | Vendor looked up/created |
| `material` | `material` | Direct mapping |
| `color` | `name` | Combined with brand/material |
| `diameter` | `diameter` | Direct mapping |
| `weight` | `weight` | Filament weight |
| `price` | `price` | Unit price |
| `spool_weight` | `spool_weight` | Empty spool weight |
| `density` | `density` | Material density |

## Troubleshooting

### Common Issues

**1. "No vendor data found" warnings**
- Update `src/resources/vendor-data.json` with your vendor.
- For Bambu invoices, make sure the parsed material matches a Bambu entry such as `PLA Basic`, `PLA Matte`, `PETG Basic`, or `PLA-CF`.

**2. "Connection refused" errors**
- Check Spoolman is reachable from where the importer runs.
- In Docker, `localhost` means the importer container, not your host. Use a compose service name, `host.docker.internal`, or a real LAN/HTTPS URL.

**3. Webhook returns 401**
- Set the Paperless webhook header `X-Importer-Token` to the exact `IMPORTER_WEBHOOK_TOKEN` value.
- If you rotate the token, restart the importer container.

**4. Paperless webhook creates an empty import**
- Confirm Paperless OCR has completed and `/api/documents/{id}/` contains `content`.
- Use a Document Added workflow rather than Consumption Started if you need OCR text.

**5. Module not found errors in CLI mode**
- Create a venv and install dependencies: `python3 -m venv .venv && . .venv/bin/activate && pip install -r src/requirements.txt`.

**6. Docker build cannot pull base image**
- Authenticate with Docker Hub or wait for the pull rate limit to reset.
- The app image uses `python:3.12-slim`.

## Advanced Usage

### Batch Processing With CLI

```bash
. .venv/bin/activate
for file in receipts/*.json; do
    python src/spoolman_importer.py --json "$file" --vendor "Bambu Lab"
done
```

### Reverse Proxy Sketch

Route `/` to Spoolman and `/importer/` to this service. The exact syntax depends on your proxy, but the importer expects the path prefix to remain `/importer` unless you change `IMPORTER_BASE_PATH`.

## Contributing

### Adding New Vendors

1. Research vendor specifications such as spool weight, density, and temperatures.
2. Add entries to `src/resources/vendor-data.json`.
3. Add sample parser/import tests under `tests/`.

### Development Setup

```bash
git clone <repository-url>
cd spoolman-importer
python3 -m venv .venv
. .venv/bin/activate
pip install -r src/requirements-dev.txt
python -m unittest discover -s tests -v
```

For Docker validation:

```bash
docker compose -f docker-compose.example.yml config
docker build -t spoolman-importer:test .
```

## License

This project is open source. See LICENSE file for details.

## Acknowledgments

- [Spoolman](https://github.com/Donkie/Spoolman) - Excellent 3D printer filament management system
- [OpenAI](https://openai.com) - GPT API for intelligent text extraction
- [pypdf](https://pypdf.readthedocs.io/) - PDF text extraction
- Community contributors for vendor data and testing

## Support

For issues and questions:
1. Check this README
2. Review the test files for usage examples
3. Open an issue with detailed information
4. Join the Spoolman community for general discussion

---

**Happy 3D printing and filament management!** 🖨️
