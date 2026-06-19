import unittest

from ui.pdf_exporter import _calculate_items_table_widths


class PdfLayoutTests(unittest.TestCase):
    def test_code_column_expands_for_longest_code(self):
        available_width = 515.0
        short_widths = _calculate_items_table_widths(
            [{"code": "A1"}, {"code": "B2"}],
            available_width,
        )
        long_widths = _calculate_items_table_widths(
            [{"code": "IPHONE-15-PRO-MAX-A3108-MAINBOARD"}],
            available_width,
        )

        self.assertGreater(long_widths[0], short_widths[0])
        self.assertAlmostEqual(sum(long_widths), available_width)

    def test_widths_sum_to_available_width(self):
        available_width = 515.0
        widths = _calculate_items_table_widths(
            [{"code": "VERY-LONG-CODE-" * 8}],
            available_width,
        )

        self.assertAlmostEqual(sum(widths), available_width)

    def test_numeric_columns_are_kept_compact(self):
        widths = _calculate_items_table_widths(
            [{"code": "LONG-CODE-1234567890"}],
            515.0,
        )

        self.assertEqual(widths[2:], [34.0, 70.0, 70.0])


if __name__ == "__main__":
    unittest.main()
