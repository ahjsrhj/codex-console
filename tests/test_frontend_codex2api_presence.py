from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_contains_codex2api_service_management_ui():
    content = (ROOT / "templates" / "settings.html").read_text(encoding="utf-8")
    assert "add-codex2api-service-btn" in content
    assert "codex2api-services-table" in content
    assert "codex2api-service-edit-modal" in content


def test_index_page_contains_codex2api_auto_upload_ui():
    content = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "auto-upload-codex2api" in content
    assert "codex2api-service-select-group" in content
    assert "codex2api-service-select" in content


def test_accounts_page_contains_codex2api_upload_entries():
    content = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    assert "batch-upload-codex2api-item" in content
    assert "codex2api-service-modal" in content


def test_accounts_js_contains_codex2api_upload_handlers():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "selectCodex2ApiService" in content
    assert "uploadToCodex2Api" in content
    assert "handleBatchUploadCodex2Api" in content


def test_settings_and_registration_js_reference_codex2api_service_lists():
    settings_js = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "loadCodex2ApiServices" in settings_js
    assert "/codex2api-services?enabled=true" in app_js
    assert "auto_upload_codex2api" in app_js
