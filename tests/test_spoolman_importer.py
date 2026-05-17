
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

sys.path.append(str(Path(__file__).parent.parent))
from src.spoolman_importer import REQUEST_TIMEOUT, SpoolmanImporter


VENDOR_DATA = {
    "vendors": {
        "TestVendor": {
            "PLA": {
                "spool_weight": 200,
                "extruder_temp": 210,
                "bed_temp": 60,
                "density": 1.24,
            }
        }
    },
    "material_defaults": {
        "PLA": {
            "spool_weight": 250,
            "extruder_temp": 220,
            "bed_temp": 60,
            "density": 1.24,
        },
        "PETG": {
            "spool_weight": 250,
            "extruder_temp": 240,
            "bed_temp": 80,
            "density": 1.27,
        },
    },
}

COLOR_DATA = {
    "colors": {
        "black": "#000000",
        "blue": "#0000FF",
        "galaxy-black": "#2E2E2E",
        "light-blue": "#ADD8E6",
        "red": "#FF0000",
    }
}


def make_response(json_data, status_code=200):
    response = MagicMock()
    response.json.return_value = json_data
    response.status_code = status_code
    response.reason = "OK"
    response.raise_for_status.return_value = None
    return response


class TestSpoolmanImporter(unittest.TestCase):
    def setUp(self):
        vendor_patcher = patch('src.spoolman_importer.SpoolmanImporter.load_vendor_data', return_value=VENDOR_DATA)
        color_patcher = patch('src.spoolman_importer.SpoolmanImporter.load_color_data', return_value=COLOR_DATA)
        self.addCleanup(vendor_patcher.stop)
        self.addCleanup(color_patcher.stop)
        vendor_patcher.start()
        color_patcher.start()
        self.importer = SpoolmanImporter('http://localhost:7912')

    def test_request_uses_timeout(self):
        self.importer.session.request = MagicMock(return_value=make_response([]))

        self.importer._request("GET", "/api/v1/filament")

        self.importer.session.request.assert_called_once_with(
            "GET",
            "http://localhost:7912/api/v1/filament",
            timeout=REQUEST_TIMEOUT,
        )

    def test_extract_base_material(self):
        self.assertEqual(self.importer.extract_base_material("PLA"), "PLA")
        self.assertEqual(self.importer.extract_base_material("PLA+"), "PLA")
        self.assertEqual(self.importer.extract_base_material("PETG"), "PETG")
        self.assertEqual(self.importer.extract_base_material("ABS"), "ABS")
        self.assertEqual(self.importer.extract_base_material("UNKNOWN"), "PLA")

    @patch('builtins.open', new_callable=mock_open, read_data='[{"brand": "TestVendor", "material": "PLA", "color": "Red"}]')
    def test_load_filaments_from_json(self, mock_file):
        filaments = self.importer.load_filaments_from_json('dummy.json')
        self.assertEqual(len(filaments), 1)
        self.assertEqual(filaments[0]['brand'], 'TestVendor')
        self.assertEqual(filaments[0]['material'], 'PLA')
        self.assertEqual(filaments[0]['quantity'], 1)

    @patch('src.spoolman_importer.PdfReader')
    def test_extract_text_from_pdf(self, mock_pdf_reader):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sample PDF text"
        mock_pdf_reader.return_value.pages = [mock_page]

        with patch('builtins.open', new_callable=mock_open):
            text = self.importer.extract_text_from_pdf('dummy.pdf')
            self.assertEqual(text.strip(), "Sample PDF text")

    def test_get_color_hex(self):
        self.assertEqual(self.importer.get_color_hex("Red", interactive=False), "#FF0000")
        self.assertEqual(self.importer.get_color_hex("bLaCk", interactive=False), "#000000")
        self.assertEqual(self.importer.get_color_hex("Light Blue", interactive=False), "#ADD8E6")
        self.assertEqual(self.importer.get_color_hex("Galaxy Black", interactive=False), "#2E2E2E")
        self.assertEqual(self.importer.get_color_hex("Deep Blue", interactive=False), "#0000FF")
        self.assertIsNone(self.importer.get_color_hex("Chartreuse", interactive=False))

    def test_color_resource_hex_values_are_valid(self):
        color_path = Path(__file__).parent.parent / 'src' / 'resources' / 'color-data.json'
        colors = json.loads(color_path.read_text(encoding='utf-8'))['colors']

        invalid = {name: value for name, value in colors.items() if not re.fullmatch(r'#[0-9A-Fa-f]{6}', value)}

        self.assertEqual(invalid, {})

    def test_vendor_resource_json_is_valid(self):
        vendor_path = Path(__file__).parent.parent / 'src' / 'resources' / 'vendor-data.json'
        vendor_data = json.loads(vendor_path.read_text(encoding='utf-8'))

        self.assertIn('Bambu Lab', vendor_data['vendors'])
        self.assertIn('PLA Basic', vendor_data['vendors']['Bambu Lab'])

    def test_llm_json_decoder_handles_fenced_array_with_prose(self):
        content = 'Here you go:\n```json\n[{"brand":"TestVendor","material":"PLA","color":"Red"}]\n```'

        filaments = self.importer._validate_filaments(self.importer._decode_llm_json(content))

        self.assertEqual(len(filaments), 1)
        self.assertEqual(filaments[0]['brand'], 'TestVendor')

    def test_invalid_llm_json_is_rejected(self):
        with self.assertRaises(ValueError):
            self.importer._decode_llm_json('No useful JSON here')

    def test_unknown_brand_uses_vendor_fallback(self):
        filament = {"brand": "Unknown", "material": "PLA", "color": "Red"}

        vendor = self.importer._resolve_vendor_name(filament, "FallbackVendor")

        self.assertEqual(vendor, "FallbackVendor")
        self.assertEqual(filament['brand'], "FallbackVendor")

    def test_known_brand_is_not_overridden_by_vendor_fallback(self):
        filament = {"brand": "TestVendor", "material": "PLA", "color": "Red"}

        vendor = self.importer._resolve_vendor_name(filament, "FallbackVendor")

        self.assertEqual(vendor, "TestVendor")
        self.assertEqual(filament['brand'], "TestVendor")

    def test_import_filament_with_temperatures(self):
        self.importer.session.request = MagicMock(side_effect=[
            make_response({'id': 102, 'name': 'PLA Blue'}),
            make_response([]),
            make_response({'id': 201}),
        ])

        filament_data = {
            "brand": "TestVendor",
            "material": "PLA",
            "color": "Blue",
            "diameter": 1.75,
            "weight": 1000,
            "price": 25.0,
            "quantity": 1,
            "extruder_temp": 215,
            "bed_temp": 65,
            "spool_weight": 200,
        }

        self.assertTrue(self.importer.import_filament(filament_data, 1, [], 'dummy.json', interactive=False))

        filament_creation_call = self.importer.session.request.call_args_list[0]
        self.assertEqual(filament_creation_call.args[0], 'POST')
        self.assertEqual(filament_creation_call.args[1], 'http://localhost:7912/api/v1/filament')
        self.assertEqual(filament_creation_call.kwargs['timeout'], REQUEST_TIMEOUT)
        sent_json = filament_creation_call.kwargs['json']
        self.assertEqual(sent_json['settings_extruder_temp'], 215)
        self.assertEqual(sent_json['settings_bed_temp'], 65)

    def test_reimport_skips_duplicate_spools(self):
        existing_filaments = [{'id': 101, 'name': 'PLA Red', 'vendor': {'id': 1, 'name': 'TestVendor'}}]
        existing_spools = [{'id': 201, 'comment': 'ImportID: [imported_from:dummy.json|item:TestVendor-PLA-Red-0.0|index:0]'}]

        with patch.object(self.importer, 'get_filaments', return_value=existing_filaments), \
             patch.object(self.importer, 'get_spools_for_filament', return_value=existing_spools), \
             patch.object(self.importer, 'get_vendors', return_value=[{'id': 1, 'name': 'TestVendor'}]), \
             patch.object(self.importer, '_request') as mock_request, \
             patch('builtins.open', new_callable=mock_open, read_data='[{"brand": "TestVendor", "material": "PLA", "color": "Red", "quantity": 1, "weight": 1000, "diameter": 1.75, "price": 0.0}]'):
            success = self.importer.process_receipt(json_path='dummy.json')

        self.assertTrue(success)
        mock_request.assert_not_called()

    def test_dry_run_builds_payloads_without_posting(self):
        with patch.object(self.importer, 'get_filaments', return_value=[]), \
             patch.object(self.importer, 'get_vendors', return_value=[]), \
             patch.object(self.importer, '_request') as mock_request, \
             patch('builtins.open', new_callable=mock_open, read_data='[{"brand": "Unknown", "material": "PLA", "color": "Red", "quantity": 1, "weight": 1000, "diameter": 1.75, "price": 0.0}]'):
            success = self.importer.process_receipt(json_path='dummy.json', vendor_name='TestVendor', dry_run=True)

        self.assertTrue(success)
        mock_request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
