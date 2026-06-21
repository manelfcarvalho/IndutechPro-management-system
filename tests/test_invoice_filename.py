import unittest

from ui.pages.clients_page import ClientsPage


class InvoiceFilenameTests(unittest.TestCase):
    def test_default_invoice_filename_includes_client_id_and_date(self):
        filename = ClientsPage._build_default_invoice_filename(
            {
                "id": 42,
                "client": "Manel",
                "date": "2026-06-20 14:35:00",
            }
        )

        self.assertEqual(filename, "Fatura_Manel_42_20-06-2026.pdf")

    def test_default_invoice_filename_removes_invalid_windows_characters(self):
        filename = ClientsPage._build_default_invoice_filename(
            {
                "id": 7,
                "client": "Cliente/Teste: Loja",
                "date": "2026-06-20",
            }
        )

        self.assertEqual(filename, "Fatura_Cliente_Teste_Loja_7_20-06-2026.pdf")


if __name__ == "__main__":
    unittest.main()
