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

- Python 3.7 or higher
- Conda or Miniconda
- Spoolman instance running on your network
- Optional: OpenAI API key for PDF processing

### Dependencies

We recommend using conda to manage dependencies and create isolated environments.

#### Option 1: Using environment.yml (Recommended)

```bash
# Create conda environment from environment.yml
conda env create -f environment.yml

# Activate the environment
conda activate spoolman-importer
```

#### Option 2: Manual conda environment setup

```bash
# Create new conda environment
conda create -n spoolman-importer python=3.9

# Activate the environment
conda activate spoolman-importer

# Install dependencies
conda install -c conda-forge requests python-dotenv
pip install pypdf openai python-dotenv

# For development (optional)
conda install -c conda-forge pytest pytest-mock pytest-cov flake8 black
```

#### Option 3: Using pip in conda environment

```bash
# Create and activate conda environment
conda create -n spoolman-importer python=3.9
conda activate spoolman-importer

# Install all dependencies with pip
pip install -r requirements.txt
```

## Project Structure

```
spoolman-importer/
├── src/
│   ├── spoolman_importer.py      # Main script
│   ├── environment.yml           # Conda environment definition
│   ├── requirements.txt          # Pip requirements file
│   ├── requirements-dev.txt      # Development requirements
│   └── resources/
│       ├── color-data.json       # Color name to hex mapping
│       └── vendor-data.json      # Vendor filament database
├── tests/
│   └── test_spoolman_importer.py # Unit tests
├── examples/
│   └── 250603-Bambu.json         # Example JSON input
└── ReadMe.md                     # This file
```

## Quick Start

1. **Clone or download the project files**
2. **Create and activate conda environment**:
   ```bash
   # Option 1: Using environment.yml (recommended)
   conda env create -f src/environment.yml
   conda activate spoolman-importer
   
   # Option 2: Manual setup
   conda create -n spoolman-importer python=3.9
   conda activate spoolman-importer
   pip install -r src/requirements.txt
   ```
3. **Configure environment** (optional):
   ```bash
   # Create .env file
   cp .env.example .env
   # Edit .env file with your settings
   ```
4. **Ensure Spoolman is running** on your network
5. **Import from JSON**:
   ```bash
   python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab"
   ```

### Environment Management

```bash
# List conda environments
conda env list

# Activate environment
conda activate spoolman-importer

# Deactivate environment
conda deactivate

# Update environment from environment.yml
conda env update -f src/environment.yml

# Remove environment
conda env remove -n spoolman-importer
```

## Usage

### Basic Commands

**Note**: Always activate the conda environment before running commands:
```bash
conda activate spoolman-importer
```

```bash
# Import from JSON file
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Prusa"

# Import from PDF receipt (requires OpenAI API key)
python src/spoolman_importer.py --pdf receipt.pdf --vendor "Amazon"

# Using environment variables
export SPOOLMAN_URL=http://192.168.1.100:7912
export OPENAI_API_KEY=sk-your-api-key-here
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab"

# Dry run to preview what would be imported
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab" --dry-run

# Custom Spoolman URL
python src/spoolman_importer.py --json examples/250603-Bambu.json --spoolman-url http://192.168.1.100:7912
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--json` | Path to JSON file containing filament data | Either --json or --pdf required |
| `--pdf` | Path to PDF receipt file | Either --json or --pdf required |
| `--spoolman-url` | Spoolman instance URL | `SPOOLMAN_URL` env var or `http://localhost:7912` |
| `--vendor` | Vendor name (will prompt if not provided) | None |
| `--openai-key` | OpenAI API key for PDF processing | `OPENAI_API_KEY` env var |
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

### Deleting All Spools

To delete all spools from your Spoolman instance, use the `delete_all_spools.sh` script.

**Usage:**
```bash
./scripts/delete_all_spools.sh [SPOOLMAN_URL]
```

**Example:**
```bash
./scripts/delete_all_spools.sh http://localhost:7912
```

The script will prompt for confirmation before deleting anything.

### Deleting All Filaments

To delete all filaments from your Spoolman instance, use the `delete_all_filaments.sh` script.

**Usage:**
```bash
./scripts/delete_all_filaments.sh [SPOOLMAN_URL]
```

**Example:**
```bash
./scripts/delete_all_filaments.sh http://localhost:7912
```

The script will prompt for confirmation before deleting anything.

**Note:** Deleting a filament will also delete all of its associated spools.

## Testing

To run the test suite, first install the test dependencies from `src/requirements-dev.txt`.

```bash
pip install -r src/requirements-dev.txt
```

Then, run the tests using the following command:

```bash
python -m unittest tests/test_spoolman_importer.py
```

## Configuration

### Environment Variables

The script supports configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SPOOLMAN_URL` | Spoolman instance URL | `http://localhost:7912` |
| `OPENAI_API_KEY` | OpenAI API key for PDF processing | None |

### Method 1: System Environment Variables

```bash
# Set environment variables system-wide
export SPOOLMAN_URL="http://192.168.1.100:7912"
export OPENAI_API_KEY="sk-your-openai-api-key-here"

# Run the script (no need to specify URL or key)
python src/spoolman_importer.py --json examples/250603-Bambu.json --vendor "Bambu Lab"
```

### Method 2: .env File (Recommended)

Create a `.env` file in the project directory:

```bash
# .env file
SPOOLMAN_URL=http://localhost:7912
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**Install python-dotenv for .env file support:**
```bash
pip install python-dotenv
```

**Example .env configurations:**

```bash
# Local development
SPOOLMAN_URL=http://localhost:7912
OPENAI_API_KEY=sk-your-development-key

# Network setup
SPOOLMAN_URL=http://192.168.1.100:7912
OPENAI_API_KEY=sk-your-production-key

# Remote/cloud setup
SPOOLMAN_URL=https://spoolman.example.com
OPENAI_API_KEY=sk-your-cloud-key
```

### Method 3: Command Line Override

Command line arguments always take precedence over environment variables:

```bash
# Override environment variables
python src/spoolman_importer.py --json examples/250603-Bambu.json \
  --spoolman-url http://different-server:7912 \
  --openai-key sk-different-key \
  --vendor "Bambu Lab"
```

### Configuration Priority

1. **Command line arguments** (highest priority)
2. **Environment variables** (system or .env file)
3. **Default values** (lowest priority)

### Configuration Display

The script shows which configuration is being used:

```
Configuration:
  Spoolman URL: http://192.168.1.100:7912
  OpenAI API Key: configured
  (Using SPOOLMAN_URL environment variable)
```

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
- Solution: Update `src/resources/vendor-data.json` with your vendor
- Alternative: Choose from available material defaults

**2. "Connection refused" errors**
- Check Spoolman is running: `http://localhost:7912`
- Verify URL with `--spoolman-url` parameter
- Ensure conda environment is activated: `conda activate spoolman-importer`

**3. "Module not found" errors**
- Activate conda environment: `conda activate spoolman-importer`
- Check if dependencies are installed: `conda list`
- Reinstall dependencies: `pip install -r src/requirements.txt`

**3. PDF processing fails**
- Ensure OpenAI API key is valid
- Check PDF is text-based (not scanned image)
- Try pattern matching fallback
- Verify conda environment is activated

**4. "OpenAI API key not configured" warnings**
- Set `OPENAI_API_KEY` environment variable
- Or create `.env` file with the key
- Or use `--openai-key` parameter
- PDF processing will use pattern matching fallback without key

**5. ".env file not loading"**
- Install python-dotenv: `pip install python-dotenv`
- Ensure `.env` file is in the same directory as the script
- Check .env file syntax (no spaces around =)

**7. "Environment not activated" issues**
- Always activate before running: `conda activate spoolman-importer`
- Check current environment: `conda info --envs`
- Verify Python path: `which python` (should show conda environment path)


## Advanced Usage

### Batch Processing

Process multiple receipts:

```bash
# Activate environment first
conda activate spoolman-importer

# Process all JSON files in a directory
for file in receipts/*.json; do
    python src/spoolman_importer.py --json "$file" --vendor "Auto"
done
```


## Contributing

### Adding New Vendors

1. Research vendor specifications (spool weight, temperatures)
2. Add to `src/resources/vendor-data.json`
3. Test with sample data
4. Add test cases to `tests/test_spoolman_importer.py`

### Reporting Issues

Please include:
- Command used
- Input files (sanitized)
- Error messages
- Spoolman version
- Python version

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd spoolman-importer

# Create and activate conda environment
conda env create -f src/environment.yml
conda activate spoolman-importer

# Or create manually
conda create -n spoolman-importer python=3.9
conda activate spoolman-importer
pip install -r src/requirements-dev.txt

# Create development .env file
cp .env.example .env
# Edit .env with your development settings

# Run tests
python -m unittest tests/test_spoolman_importer.py

# Run linting
flake8 src/spoolman_importer.py
black src/spoolman_importer.py

# Check conda environment
conda list
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
