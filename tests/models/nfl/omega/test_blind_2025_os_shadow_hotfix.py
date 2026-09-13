import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts/nfl/build_omega_tackle_012_blind_2025.py"

class TestBlind2025OsShadowHotfix(unittest.TestCase):
    def test_main_does_not_rebind_imported_os_module(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        rebound = []
        for n in ast.walk(main):
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id == "os":
                        rebound.append(n.lineno)
            elif isinstance(n, (ast.For, ast.AsyncFor)) and isinstance(n.target, ast.Name) and n.target.id == "os":
                rebound.append(n.lineno)
            elif isinstance(n, ast.comprehension) and isinstance(n.target, ast.Name) and n.target.id == "os":
                rebound.append(n.lineno)
        self.assertEqual(rebound, [], f"main() shadows imported os at lines {rebound}")

    def test_atomic_publish_still_uses_os_replace(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("os.replace(staging,out)", text)
        self.assertIn("off_share=family_share", text)
        self.assertIn("def_share=family_share", text)

if __name__ == "__main__":
    unittest.main()
