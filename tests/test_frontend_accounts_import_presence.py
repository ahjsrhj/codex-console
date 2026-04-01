from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_accounts_page_contains_import_modal_and_dropzone():
    content = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    assert 'id="import-btn"' in content
    assert 'id="import-modal"' in content
    assert 'id="import-dropzone"' in content
    assert 'id="import-file-input"' in content
    assert 'id="submit-import-btn"' in content


def test_accounts_script_contains_import_handlers():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "function openImportModal()" in content
    assert "async function loadImportAccountsFromFile(file)" in content
    assert "async function submitImportAccounts()" in content
