"""
Codex2Api 账号上传功能
"""

import logging
from typing import List, Optional, Tuple

from curl_cffi import requests as cffi_requests

from ...database.models import Account
from ...database.session import get_db

logger = logging.getLogger(__name__)


def normalize_codex2api_url(api_url: str) -> str:
    """规范化 Codex2Api 根地址。"""
    return (api_url or "").rstrip("/")


def _build_auth_headers(admin_key: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Admin-Key": admin_key,
    }


def _resolve_proxy_url(account: Account, proxy_url: Optional[str] = None) -> Optional[str]:
    service_proxy = str(proxy_url or "").strip()
    if service_proxy:
        return service_proxy
    account_proxy = str(getattr(account, "proxy_used", "") or "").strip()
    return account_proxy or None


def _extract_error_message(response) -> str:
    error_msg = f"上传失败: HTTP {response.status_code}"
    try:
        payload = response.json()
    except Exception:
        return f"{error_msg} - {response.text[:200]}"

    if isinstance(payload, dict):
        return (
            payload.get("message")
            or payload.get("error")
            or payload.get("detail")
            or error_msg
        )
    return error_msg


def upload_to_codex2api(
    account: Account,
    api_url: str,
    admin_key: str,
    proxy_url: Optional[str] = None,
) -> Tuple[bool, str]:
    """上传单个账号到 Codex2Api 平台。"""
    if not account:
        return False, "账号不存在"
    if not api_url:
        return False, "Codex2Api URL 未配置"
    if not admin_key:
        return False, "Codex2Api Admin Key 未配置"

    effective_proxy_url = _resolve_proxy_url(account, proxy_url)
    payload = {
        "name": account.email or f"account-{getattr(account, 'id', 'unknown')}",
    }
    if effective_proxy_url:
        payload["proxy_url"] = effective_proxy_url

    if getattr(account, "refresh_token", None):
        url = normalize_codex2api_url(api_url) + "/api/admin/accounts"
        payload["refresh_token"] = account.refresh_token
    elif getattr(account, "access_token", None):
        url = normalize_codex2api_url(api_url) + "/api/admin/accounts/at"
        payload["access_token"] = account.access_token
    else:
        return False, "账号缺少 refresh_token 和 access_token，无法上传"

    try:
        response = cffi_requests.post(
            url,
            json=payload,
            headers=_build_auth_headers(admin_key),
            proxies=None,
            timeout=20,
            impersonate="chrome110",
        )
        if response.status_code in (200, 201):
            try:
                data = response.json()
            except Exception:
                data = None
            if isinstance(data, dict) and data.get("success") is False:
                return False, data.get("message") or "上传失败"
            return True, "上传成功"
        return False, _extract_error_message(response)
    except Exception as exc:
        logger.error("Codex2Api 上传异常: %s", exc)
        return False, f"上传异常: {str(exc)}"


def batch_upload_to_codex2api(
    account_ids: List[int],
    api_url: str,
    admin_key: str,
    proxy_url: Optional[str] = None,
) -> dict:
    """批量上传指定 ID 的账号到 Codex2Api 平台。"""
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    }

    with get_db() as db:
        for account_id in account_ids:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                results["failed_count"] += 1
                results["details"].append(
                    {"id": account_id, "email": None, "success": False, "error": "账号不存在"}
                )
                continue

            if not getattr(account, "refresh_token", None) and not getattr(account, "access_token", None):
                results["skipped_count"] += 1
                results["details"].append(
                    {"id": account.id, "email": account.email, "success": False, "error": "缺少 refresh_token 和 access_token"}
                )
                continue

            success, message = upload_to_codex2api(account, api_url, admin_key, proxy_url=proxy_url)
            if success:
                results["success_count"] += 1
                results["details"].append(
                    {"id": account.id, "email": account.email, "success": True, "message": message}
                )
            else:
                results["failed_count"] += 1
                results["details"].append(
                    {"id": account.id, "email": account.email, "success": False, "error": message}
                )

    return results


def test_codex2api_connection(api_url: str, admin_key: str) -> Tuple[bool, str]:
    """测试 Codex2Api 管理连接。"""
    if not api_url:
        return False, "API URL 不能为空"
    if not admin_key:
        return False, "Admin Key 不能为空"

    url = normalize_codex2api_url(api_url) + "/api/admin/accounts?page=1&limit=1"
    try:
        response = cffi_requests.get(
            url,
            headers=_build_auth_headers(admin_key),
            proxies=None,
            timeout=10,
            impersonate="chrome110",
        )
        if response.status_code == 200:
            return True, "Codex2Api 连接测试成功"
        if response.status_code == 401:
            return False, "连接成功，但 Admin Key 无效"
        if response.status_code == 403:
            return False, "连接成功，但权限不足"
        if response.status_code == 404:
            return False, "未找到 Codex2Api 账号管理接口，请检查 API URL"
        return False, f"服务器返回异常状态码: {response.status_code}"
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到服务器: {str(exc)}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as exc:
        return False, f"连接测试失败: {str(exc)}"
