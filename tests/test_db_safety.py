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

    def test_repair_update_adjusts_each_component_stock(self):
        self.assertTrue(self.db.add_component("TST-4A", "Componente Teste 4A", 10.0, 10))
        self.assertTrue(self.db.add_component("TST-4B", "Componente Teste 4B", 5.0, 5))
        component_a = self.db.get_component_by_code("TST-4A")
        component_b = self.db.get_component_by_code("TST-4B")

        repair_id = self.db.add_repair_with_stock_update(
            client="Cliente Teste",
            phone="910000002",
            nif="",
            address="",
            description="Teste",
            used_parts=f"{component_a['id']}:2",
            total=20.0,
            components_to_consume=[(component_a["id"], 2)],
            hours_worked=1.0,
        )

        self.assertTrue(self.db.update_repair_with_stock_validation(
            repair_id,
            {
                "used_parts": f"{component_a['id']}:1,{component_b['id']}:3",
                "total": 25.0,
            },
        ))

        self.assertEqual(self.db.get_component_by_id(component_a["id"])["qty"], 9)
        self.assertEqual(self.db.get_component_by_id(component_b["id"])["qty"], 2)

    def test_repair_update_restores_stock_when_parts_removed(self):
        self.assertTrue(self.db.add_component("TST-5", "Componente Teste 5", 10.0, 10))
        component = self.db.get_component_by_code("TST-5")

        repair_id = self.db.add_repair_with_stock_update(
            client="Cliente Teste",
            phone="910000003",
            nif="",
            address="",
            description="Teste",
            used_parts=f"{component['id']}:4",
            total=40.0,
            components_to_consume=[(component["id"], 4)],
            hours_worked=1.0,
        )

        self.assertTrue(self.db.update_repair_with_stock_validation(
            repair_id,
            {
                "used_parts": "Nenhum",
                "total": 0.0,
            },
        ))

        self.assertEqual(self.db.get_component_by_id(component["id"])["qty"], 10)

    def test_repair_update_stock_error_keeps_original_state(self):
        self.assertTrue(self.db.add_component("TST-6", "Componente Teste 6", 10.0, 5))
        component = self.db.get_component_by_code("TST-6")

        repair_id = self.db.add_repair_with_stock_update(
            client="Cliente Teste",
            phone="910000004",
            nif="",
            address="",
            description="Teste",
            used_parts=f"{component['id']}:2",
            total=20.0,
            components_to_consume=[(component["id"], 2)],
            hours_worked=1.0,
        )

        with self.assertRaises(ValueError):
            self.db.update_repair_with_stock_validation(
                repair_id,
                {
                    "used_parts": f"{component['id']}:99",
                    "total": 990.0,
                },
            )

        self.assertEqual(self.db.get_component_by_id(component["id"])["qty"], 3)
        self.assertEqual(self.db.get_repair_by_id(repair_id)["used_parts"], f"{component['id']}:2")


if __name__ == "__main__":
    unittest.main()
