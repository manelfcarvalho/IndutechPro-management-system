import ast
import unittest
from pathlib import Path


class HistoryLayoutTests(unittest.TestCase):
    def test_history_column_weights_are_integers_for_tk_grid(self):
        source = Path("ui/pages/clients_page.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        weights = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "column_weights":
                    value = ast.literal_eval(node.value)
                    if len(value) == 8:
                        weights.append(value)

        self.assertGreaterEqual(len(weights), 2)
        for weight_list in weights:
            self.assertTrue(all(isinstance(weight, int) for weight in weight_list))


if __name__ == "__main__":
    unittest.main()
