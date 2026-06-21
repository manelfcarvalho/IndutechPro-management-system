import os
import tempfile
import unittest
from types import SimpleNamespace

from database.db_manager import DatabaseManager
from ui.pages.client_list_page import ClientListPage


class ClientEditTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        DatabaseManager._instance = None
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close_connection()
        DatabaseManager._instance = None
        self.tmpdir.cleanup()

    def test_update_client_by_id_allows_phone_change_without_duplicate(self):
        client_id = self.db.add_or_update_client(
            "Cliente Original",
            "910000000",
            "123456789",
            "Rua Antiga",
        )

        updated_id = self.db.update_client(
            client_id,
            "Cliente Editado",
            "920000000",
            "987654321",
            "Rua Nova",
        )

        self.assertEqual(updated_id, client_id)
        clients = self.db.search_clients_smart("", limit=10)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["id"], client_id)
        self.assertEqual(clients[0]["name"], "Cliente Editado")
        self.assertEqual(clients[0]["phone"], "920000000")
        self.assertEqual(clients[0]["nif"], "987654321")
        self.assertEqual(clients[0]["address"], "Rua Nova")

    def test_delete_client_without_repairs_removes_contact(self):
        client_id = self.db.add_or_update_client(
            "Cliente Sem Historico",
            "930000000",
            "",
            "",
        )

        self.assertTrue(self.db.delete_client(client_id))
        self.assertIsNone(self.db.get_client_by_id(client_id))

    def test_delete_client_with_repairs_is_blocked(self):
        client_id = self.db.add_or_update_client(
            "Cliente Com Historico",
            "940000000",
            "",
            "",
        )
        self.db.add_repair(
            client="Cliente Com Historico",
            description="Teste",
            used_parts="Nenhum",
            total=0.0,
            client_id=client_id,
        )

        with self.assertRaises(ValueError):
            self.db.delete_client(client_id)

        self.assertIsNotNone(self.db.get_client_by_id(client_id))
        self.assertEqual(self.db.get_client_repair_count(client_id), 1)

    def test_client_page_uses_update_when_editing_existing_client(self):
        calls = []

        class FakeDbManager:
            def update_client(self, client_id, name, phone, nif, address):
                calls.append(("update", client_id, name, phone, nif, address))
                return client_id

            def add_or_update_client(self, name, phone, nif, address):
                calls.append(("add", name, phone, nif, address))
                return 99

        page = ClientListPage.__new__(ClientListPage)
        page.app = SimpleNamespace(db_manager=FakeDbManager())

        result = page._save_client_record(7, "Cliente Editado", "920000000", "987654321", "Rua Nova")

        self.assertEqual(result, 7)
        self.assertEqual(
            calls,
            [("update", 7, "Cliente Editado", "920000000", "987654321", "Rua Nova")],
        )


if __name__ == "__main__":
    unittest.main()
