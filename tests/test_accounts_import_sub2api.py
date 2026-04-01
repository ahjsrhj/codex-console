from datetime import datetime

from src.web.routes import accounts


def test_normalize_import_raw_item_maps_sub2api_export_fields():
    raw_item = {
        "name": "team母号",
        "platform": "openai",
        "type": "oauth",
        "credentials": {
            "access_token": "at-123",
            "refresh_token": "rt-123",
            "id_token": "id-123",
            "client_id": "client-123",
            "chatgpt_account_id": "acct-123",
            "chatgpt_user_id": "user-123",
            "organization_id": "org-123",
            "plan_type": "team",
            "email": "tester@example.com",
            "expires_at": 1775893991,
            "model_mapping": {"gpt-5.4": "gpt-5.4"},
        },
        "extra": {
            "codex_usage_updated_at": "2026-04-01T16:16:09+08:00",
            "privacy_mode": "training_off",
        },
        "priority": 3,
        "concurrency": 10,
        "rate_multiplier": 1,
        "auto_pause_on_expired": True,
    }

    normalized = accounts._normalize_import_raw_item(raw_item)

    assert normalized["email"] == "tester@example.com"
    assert normalized["account_id"] == "acct-123"
    assert normalized["workspace_id"] == "org-123"
    assert normalized["client_id"] == "client-123"
    assert normalized["access_token"] == "at-123"
    assert normalized["refresh_token"] == "rt-123"
    assert normalized["id_token"] == "id-123"
    assert normalized["plan_type"] == "team"
    assert normalized["priority"] == 3
    assert normalized["auth_mode"] == "oauth"
    assert normalized["user_id"] == "user-123"
    assert normalized["account_name"] == "team母号"
    assert normalized["last_refresh"] == "2026-04-01T16:16:09+08:00"
    assert normalized["expires_at"] == 1775893991
    assert normalized["source"] == "sub2api_import"
    assert normalized["metadata"]["import_format"] == "sub2api"
    assert normalized["metadata"]["sub2api"]["extra"]["privacy_mode"] == "training_off"
    assert normalized["metadata"]["sub2api"]["model_mapping"]["gpt-5.4"] == "gpt-5.4"


def test_parse_import_datetime_supports_epoch_seconds():
    parsed = accounts._parse_import_datetime(1775893991)
    assert parsed == datetime(2026, 4, 11, 7, 53, 11)
