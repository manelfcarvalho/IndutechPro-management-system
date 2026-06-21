import unittest

from ui.pages.service_page import _normalize_component


class ServiceComponentNormalizationTests(unittest.TestCase):
    def test_normalizes_numeric_component_fields_from_strings(self):
        component = _normalize_component({
            "id": "12",
            "code": "ABC",
            "name": "Componente",
            "price": "10,50",
            "qty": "3.0",
        })

        self.assertEqual(component["id"], 12)
        self.assertEqual(component["price"], 10.5)
        self.assertEqual(component["qty"], 3)

    def test_invalid_numeric_fields_fall_back_safely(self):
        component = _normalize_component({
            "id": "bad",
            "code": None,
            "name": None,
            "price": "",
            "qty": None,
        })

        self.assertIsNone(component["id"])
        self.assertEqual(component["code"], "N/A")
        self.assertEqual(component["name"], "N/A")
        self.assertEqual(component["price"], 0.0)
        self.assertEqual(component["qty"], 0)


if __name__ == "__main__":
    unittest.main()
