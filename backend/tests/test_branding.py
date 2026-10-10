"""The product is MediGuard RAG. The misspelling "MediGaurd" must not return in
project-owned text.

Deliberately NOT flagged, because they are technical identifiers rather than
branding (renaming them would break stored data, sessions, or the remote):
  * the repository slug / URL  "MediGaurd-RAG"
  * the stored demo document   "MediGaurd_Demo_Patient_Report.pdf"
  * lowercase "medigaurd"      (database name/user/password, the sessionStorage
                                key, the demo password, dev database files)
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".venv", ".git", "dist", "__pycache__", ".pytest_cache", "data", ".claude"}
SUFFIXES = {".py", ".ts", ".tsx", ".html", ".md", ".yml", ".yaml", ".example", ".json", ".svg", ".toml", ".ini"}
MISSPELLING = re.compile(r"MediGaurd(?!-RAG|_)")


def _project_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix in SUFFIXES or path.name.endswith(".example"):
            yield path


def test_the_misspelled_brand_name_does_not_appear_in_project_files():
    offenders = []
    for path in _project_files():
        if path.name == "package-lock.json" or path.name == "test_branding.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if MISSPELLING.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert not offenders, "Use 'MediGuard': " + ", ".join(offenders[:10])


def test_the_correct_brand_is_used_in_the_user_facing_entry_points():
    assert "<title>MediGuard RAG</title>" in (ROOT / "frontend/index.html").read_text()
    assert "MediGuard" in (ROOT / "frontend/src/pages/Login.tsx").read_text()
    assert "MediGuard" in (ROOT / "frontend/src/components/layout/Sidebar.tsx").read_text()
    assert 'app_name: str = "MediGuard RAG"' in (ROOT / "backend/app/config.py").read_text()


def test_technical_identifiers_were_not_renamed():
    """Guards the other half of the rename: these must keep working."""
    assert 'sessionStorage.getItem("medigaurd_token")' in (ROOT / "frontend/src/api/client.ts").read_text()
    assert 'DEMO_PASSWORD = "medigaurd123"' in (ROOT / "scripts/seed_users.py").read_text()
    assert "POSTGRES_DB: medigaurd" in (ROOT / "docker-compose.yml").read_text()
