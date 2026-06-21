import unittest
from unittest.mock import patch

from ui.theme import icon_button_style, payment_status_badge_style, repair_status_badge_style


class ThemeStyleTests(unittest.TestCase):
    def test_status_badge_styles_are_button_kwargs(self):
        with patch("ui.theme.font", return_value=("font", 11, "bold")):
            for style in (
                repair_status_badge_style("Em Analise"),
                repair_status_badge_style("Aguardar Pecas"),
                repair_status_badge_style("Pronto a Entregar"),
                payment_status_badge_style(True),
                payment_status_badge_style(False),
            ):
                self.assertIn("fg_color", style)
                self.assertIn("hover_color", style)
                self.assertIn("text_color", style)
                self.assertEqual(style["corner_radius"], 999)
                self.assertEqual(style["height"], 28)

    def test_icon_button_style_is_compact_and_self_contained(self):
        with patch("ui.theme.font", return_value=("font", 15, "bold")):
            style = icon_button_style()

        self.assertEqual(style["width"], 38)
        self.assertEqual(style["height"], 28)
        self.assertEqual(style["corner_radius"], 999)


if __name__ == "__main__":
    unittest.main()
