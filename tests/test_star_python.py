"""Python checks of STAR outside the modules' own suites (2026-10-20).

From the STAR folder:   python -m unittest discover -s tests -p "test_*.py"     (run_all_tests.py: suite STAR)

- Every module of BackEnd/runners, BackEnd/modules and BackEnd/ai imports (syntax errors, missing names, import cycles);
  a module whose third-party package is not installed here is skipped, not failed.
- Every Python file of BackEnd and FrontEnd compiles (FrontEnd/star_frontend_v5.py needs pywebview to be imported).
- FrontEnd/web/star_results_frontend_v5.html is what build_results_frontend_html (FrontEnd/star_frontend_v5.py) makes
  from web/star_results_shell_template_v5.html and web/modules/*.html. The app rebuilds it at start-up, so the committed
  copy must follow its sources: on 2026-10-19 it lagged behind the END-003 page by a commit.
"""
import ast
import html
import importlib
import sys
import unittest
from pathlib import Path

STAR = Path(__file__).resolve().parent.parent
BACKEND = STAR / "BackEnd"
WEB = STAR / "FrontEnd" / "web"
OPTIONAL_PACKAGES = {"openai", "yaml", "PIL", "docx", "webview"}     # requirements.txt (and Pillow)

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestBackEnd(unittest.TestCase):
    def test_every_backend_module_imports(self):
        modules = [f"{pkg}.{f.stem}" for pkg in ("runners", "modules", "ai")
                   for f in sorted((BACKEND / pkg).glob("*.py")) if f.stem != "__init__"]
        self.assertGreaterEqual(len(modules), 15)
        for name in modules:
            with self.subTest(module=name):
                try:
                    importlib.import_module(name)
                except ModuleNotFoundError as err:
                    if (err.name or "").split(".")[0] in OPTIONAL_PACKAGES:
                        self.skipTest(f"{name}: package {err.name} not installed")
                    raise

    def test_every_python_file_compiles(self):
        files = sorted(BACKEND.rglob("*.py")) + sorted((STAR / "FrontEnd").rglob("*.py"))
        self.assertGreater(len(files), 20)
        for f in files:
            with self.subTest(file=str(f.relative_to(STAR))):
                compile(f.read_bytes(), str(f), "exec")          # no .pyc written


class TestGeneratedResultsPage(unittest.TestCase):
    def test_results_page_follows_its_sources(self):
        src = (STAR / "FrontEnd" / "star_frontend_v5.py").read_text(encoding="utf-8")
        fn = next((n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "build_results_frontend_html"), None)
        self.assertIsNotNone(fn, "build_results_frontend_html not found in FrontEnd/star_frontend_v5.py")
        ns = {"html": html, "Path": Path}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "build_results_frontend_html", "exec"), ns)
        built = ns["build_results_frontend_html"](WEB).replace("\r\n", "\n")
        committed = (WEB / "star_results_frontend_v5.html").read_text(encoding="utf-8").replace("\r\n", "\n")
        self.assertTrue(built == committed,
                        "FrontEnd/web/star_results_frontend_v5.html does not match web/star_results_shell_template_v5.html + "
                        "web/modules/*.html: start the FrontEnd once (it rebuilds the page) and commit the result")


if __name__ == "__main__":
    unittest.main()
