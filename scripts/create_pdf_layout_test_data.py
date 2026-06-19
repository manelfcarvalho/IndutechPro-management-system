import os
import sys


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from database.db_manager import DatabaseManager
from ui.pdf_exporter import generate_repair_pdf


DB_PATH = os.path.join(ROOT_DIR, "database", "test_pdf_layout.db")
PDF_PATH = os.path.join(ROOT_DIR, "test_outputs", "fatura_teste_codigo_longo.pdf")


def remove_previous_test_db():
    for suffix in ("", "-wal", "-shm"):
        path = DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)


def add_component(db, code, name, price, qty):
    db.add_component(code=code, name=name, price=price, qty=qty)
    return db.get_component_by_code(code)


def main():
    remove_previous_test_db()
    os.makedirs(os.path.dirname(PDF_PATH), exist_ok=True)

    DatabaseManager._instance = None
    db = DatabaseManager(DB_PATH)

    try:
        components = [
            add_component(db, "A1", "Conector simples", 8.50, 10),
            add_component(
                db,
                "IPHONE-15-PRO-MAX-A3108-MAINBOARD",
                "Mainboard iPhone 15 Pro Max",
                189.90,
                5,
            ),
            add_component(
                db,
                "SAMSUNG-SM-G998B-USB-C-FLEX-REV2",
                "Flex USB-C Samsung S21 Ultra",
                34.75,
                7,
            ),
        ]

        used_parts = ",".join(
            f"{component['id']}:{qty}"
            for component, qty in zip(components, [1, 1, 2])
        )

        repair_id = db.add_repair_with_stock_update(
            client="Cliente Teste PDF",
            phone="910000000",
            nif="123456789",
            address="Rua de Teste, 123",
            description=(
                "Teste de layout com codigos compridos para validar a largura "
                "dinamica da coluna Codigo."
            ),
            used_parts=used_parts,
            total=0.0,
            components_to_consume=[
                (components[0]["id"], 1),
                (components[1]["id"], 1),
                (components[2]["id"], 2),
            ],
            payment_status="Pendente",
            hours_worked=1.5,
            problem_summary="Smartphone",
            device_imei="TEST-IMEI-000000",
            repair_status="Pronto a Entregar",
            electricity_hours=0.5,
            package_weight=0.35,
            transport_cost=4.90,
            labor_type="labor1",
            warranty_number="GAR-TESTE-001",
            horas_teste=0.5,
            preco_hora_teste=12.0,
        )

        repair = db.get_repair_by_id(repair_id)
        generate_repair_pdf(repair, PDF_PATH, db_manager=db)

        print(f"Test database created: {DB_PATH}")
        print(f"Test PDF created: {PDF_PATH}")
    finally:
        db.close_connection()
        DatabaseManager._instance = None


if __name__ == "__main__":
    main()
