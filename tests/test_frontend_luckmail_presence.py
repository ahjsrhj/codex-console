from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_services_template_contains_luckmail_account_list_inputs():
    content = (ROOT / "templates" / "email_services.html").read_text(encoding="utf-8")
    assert "custom-lm-account-list" in content
    assert "edit-lm-account-list" in content
    assert "custom-lm-prefer-existing-account-list" in content
    assert "edit-lm-prefer-existing-account-list" in content


def test_email_services_script_handles_luckmail_account_list_text():
    content = (ROOT / "static" / "js" / "email_services.js").read_text(encoding="utf-8")
    assert "lm_account_list" in content
    assert "account_list_text" in content
    assert "lm_prefer_existing_account_list" in content
    assert "prefer_existing_account_list" in content
