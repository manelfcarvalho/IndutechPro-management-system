import os
import tempfile
import unittest

from database.db_manager import DatabaseManager


class DatabaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        DatabaseManager._instance = None
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db.close_connection()
        DatabaseManager._instance = None
        self.tmpdir.cleanup()

    def test_repair_creation_abates_stock_atomically(self):
        self.assertTrue(self.db.add_component("TST-1", "Componente Teste", 10.0, 5))
        component = self.db.get_component_by_code("TST-1")

        repair_id = self.db.add_repair_with_stock_update(
            client="Cliente Teste",
            phone="910000000",
            nif="",
            address="",
            description="Teste",
            used_parts=f"{component['id']}:2",
            total=20.0,
            components_to_consume=[(component["id"], 2)],
            hours_worked=1.0,
        )

        self.assertGreater(repair_id, 0)
        self.assertEqual(self.db.get_component_by_id(component["id"])["qty"], 3)

    def test_insufficient_stock_rolls_back_repair_creation(self):
        self.assertTrue(self.db.add_component("TST-2", "Componente Teste 2", 10.0, 3))
        component = self.db.get_component_by_code("TST-2")

        with self.assertRaises(ValueError):
            self.db.add_repair_with_stock_update(
                client="Cliente Teste",
                phone="910000001",
                nif="",
                address="",
                description="Teste",
                used_parts=f"{component['id']}:99",
                total=990.0,
                components_to_consume=[(component["id"], 99)],
                hours_worked=1.0,
            )

        self.assertEqual(self.db.get_component_by_id(component["id"])["qty"], 3)
        self.assertEqual(len(self.db.get_all_repairs(limit=10)), 0)

    def test_stock_entry_cannot_make_quantity_negative(self):
        self.assertTrue(self.db.add_component("TST-3", "Componente Teste 3", 10.0, 3))
        component = self.db.get_component_by_code("TST-3")

        self.assertIsNone(self.db.add_stock_quantity(component["id"], -4))
        self.assertEqual(self.db.get_component_by_id(component["id"])["qty"], 3)


if __name__ == "__main__":
    unittest.main()
