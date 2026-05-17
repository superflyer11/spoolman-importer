import unittest

from src.bambu_parser import parse_bambu_invoice_text


class TestBambuParser(unittest.TestCase):
    def test_parse_bambu_invoice_lines(self):
        text = """
        Invoice INV-123
        Bambu Lab PLA Basic Filament Gray 1kg 1.75mm Qty: 1 $13.99
        Bambu Lab PLA Matte Filament Matte Dark Blue 1KG 1.75mm x 2 $13.99 $27.98
        Bambu Lab PLA-CF Filament Lava Gray 1000g 1.75mm Quantity: 1 $29.99
        Shipping $4.99
        Tax $3.20
        Grand Total $76.15
        """

        result = parse_bambu_invoice_text(text)

        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.filaments), 3)
        self.assertEqual(result.filaments[0], {
            "brand": "Bambu Lab",
            "material": "PLA Basic",
            "color": "Gray",
            "diameter": 1.75,
            "weight": 1000.0,
            "price": 13.99,
            "quantity": 1,
        })
        self.assertEqual(result.filaments[1]["material"], "PLA Matte")
        self.assertEqual(result.filaments[1]["color"], "Matte Dark Blue")
        self.assertEqual(result.filaments[1]["quantity"], 2)
        self.assertEqual(result.filaments[1]["price"], 13.99)
        self.assertEqual(result.filaments[2]["material"], "PLA-CF")
        self.assertEqual(result.filaments[2]["color"], "Lava Gray")

    def test_price_is_divided_when_only_line_total_is_present(self):
        text = "Bambu Lab PETG Basic Filament Transparent Blue 1kg 1.75mm Qty: 2 $39.98"

        result = parse_bambu_invoice_text(text)

        self.assertEqual(len(result.filaments), 1)
        self.assertEqual(result.filaments[0]["quantity"], 2)
        self.assertEqual(result.filaments[0]["price"], 19.99)

    def test_no_rows_returns_warning(self):
        result = parse_bambu_invoice_text("Shipping $4.99\nTotal $4.99")

        self.assertEqual(result.filaments, [])
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
