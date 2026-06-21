"""Client-related database operations."""

from typing import Dict, List


class ClientOperationsMixin:
    """CRUD and lookup operations for clients."""

    def add_or_update_client(self, name: str, phone: str, nif: str = "", address: str = "") -> int:
        """
        Add a new client or update an existing one matched by phone.

        Returns the existing or newly created client ID.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM clients WHERE phone = ?", (phone,))
            existing = cursor.fetchone()

            if existing:
                client_id = existing["id"] if isinstance(existing, dict) else existing[0]
                cursor.execute(
                    "UPDATE clients SET name = ?, nif = ?, address = ? WHERE id = ?",
                    (name, nif, address, client_id),
                )
                conn.commit()
                return client_id

            cursor.execute(
                "INSERT INTO clients (name, phone, nif, address) VALUES (?, ?, ?, ?)",
                (name, phone, nif, address),
            )
            client_id = cursor.lastrowid
            conn.commit()
            return client_id

    def update_client(self, client_id: int, name: str, phone: str, nif: str = "", address: str = "") -> int:
        """
        Update an existing client by ID.

        Using the ID avoids creating a duplicate when the phone number changes.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE clients
                SET name = ?, phone = ?, nif = ?, address = ?
                WHERE id = ?
                """,
                (name, phone, nif, address, client_id),
            )
            conn.commit()
            return client_id if cursor.rowcount > 0 else 0

    def get_client_repair_count(self, client_id: int) -> int:
        """Count repairs associated with a client."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM repairs WHERE client_id = ?", (client_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def delete_client(self, client_id: int) -> bool:
        """
        Delete a client only if it has no associated repairs.

        Blocking deletion preserves fiscal/contact links in the repair history.
        """
        repair_count = self.get_client_repair_count(client_id)
        if repair_count > 0:
            raise ValueError(
                f"Este cliente tem {repair_count} reparacao(oes) associada(s). "
                "Nao pode ser apagado sem preservar o historico."
            )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
            return cursor.rowcount > 0

    def search_client(self, query: str) -> List[Dict]:
        """Search clients by name or phone."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{query}%"
            cursor.execute(
                "SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? ORDER BY name LIMIT 20",
                (search_pattern, search_pattern),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def search_clients_smart(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Optimized lookup for the client list.

        Empty query returns the most recent clients; otherwise it searches name,
        NIF and phone.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if not query:
                cursor.execute(
                    "SELECT * FROM clients ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            else:
                pattern = f"%{query}%"
                cursor.execute(
                    """
                    SELECT * FROM clients
                    WHERE name LIKE ? OR nif LIKE ? OR phone LIKE ?
                    ORDER BY name
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit),
                )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_client_by_id(self, client_id: int) -> Dict:
        """Get a client by ID, or None if it does not exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

