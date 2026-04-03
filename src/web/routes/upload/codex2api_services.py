"""
Codex2Api 服务管理 API 路由
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ....core.upload.codex2api_upload import batch_upload_to_codex2api, test_codex2api_connection
from ....database import crud
from ....database.session import get_db

router = APIRouter()


class Codex2ApiServiceCreate(BaseModel):
    name: str
    api_url: str
    admin_key: str
    proxy_url: Optional[str] = None
    enabled: bool = True
    priority: int = 0


class Codex2ApiServiceUpdate(BaseModel):
    name: Optional[str] = None
    api_url: Optional[str] = None
    admin_key: Optional[str] = None
    proxy_url: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class Codex2ApiServiceResponse(BaseModel):
    id: int
    name: str
    api_url: str
    proxy_url: Optional[str] = None
    has_admin_key: bool
    enabled: bool
    priority: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Codex2ApiTestRequest(BaseModel):
    api_url: Optional[str] = None
    admin_key: Optional[str] = None


class Codex2ApiUploadRequest(BaseModel):
    account_ids: List[int]
    service_id: Optional[int] = None


def _to_response(service) -> Codex2ApiServiceResponse:
    return Codex2ApiServiceResponse(
        id=service.id,
        name=service.name,
        api_url=service.api_url,
        proxy_url=getattr(service, "proxy_url", None),
        has_admin_key=bool(getattr(service, "admin_key", None)),
        enabled=service.enabled,
        priority=service.priority,
        created_at=service.created_at.isoformat() if service.created_at else None,
        updated_at=service.updated_at.isoformat() if service.updated_at else None,
    )


@router.get("", response_model=List[Codex2ApiServiceResponse])
async def list_codex2api_services(enabled: Optional[bool] = None):
    """获取 Codex2Api 服务列表。"""
    with get_db() as db:
        services = crud.get_codex2api_services(db, enabled=enabled)
        return [_to_response(service) for service in services]


@router.post("", response_model=Codex2ApiServiceResponse)
async def create_codex2api_service(request: Codex2ApiServiceCreate):
    """新增 Codex2Api 服务。"""
    with get_db() as db:
        service = crud.create_codex2api_service(
            db,
            name=request.name,
            api_url=request.api_url,
            admin_key=request.admin_key,
            proxy_url=request.proxy_url,
            enabled=request.enabled,
            priority=request.priority,
        )
        return _to_response(service)


@router.get("/{service_id}", response_model=Codex2ApiServiceResponse)
async def get_codex2api_service(service_id: int):
    """获取单个 Codex2Api 服务详情。"""
    with get_db() as db:
        service = crud.get_codex2api_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Codex2Api 服务不存在")
        return _to_response(service)


@router.get("/{service_id}/full")
async def get_codex2api_service_full(service_id: int):
    """获取 Codex2Api 服务完整配置。"""
    with get_db() as db:
        service = crud.get_codex2api_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Codex2Api 服务不存在")
        return {
            "id": service.id,
            "name": service.name,
            "api_url": service.api_url,
            "admin_key": service.admin_key,
            "proxy_url": getattr(service, "proxy_url", None),
            "enabled": service.enabled,
            "priority": service.priority,
        }


@router.patch("/{service_id}", response_model=Codex2ApiServiceResponse)
async def update_codex2api_service(service_id: int, request: Codex2ApiServiceUpdate):
    """更新 Codex2Api 服务配置。"""
    with get_db() as db:
        service = crud.get_codex2api_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Codex2Api 服务不存在")

        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        if request.api_url is not None:
            update_data["api_url"] = request.api_url
        if request.admin_key:
            update_data["admin_key"] = request.admin_key
        if request.proxy_url is not None:
            update_data["proxy_url"] = request.proxy_url
        if request.enabled is not None:
            update_data["enabled"] = request.enabled
        if request.priority is not None:
            update_data["priority"] = request.priority

        updated = crud.update_codex2api_service(db, service_id, **update_data)
        return _to_response(updated)


@router.delete("/{service_id}")
async def delete_codex2api_service(service_id: int):
    """删除 Codex2Api 服务。"""
    with get_db() as db:
        service = crud.get_codex2api_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Codex2Api 服务不存在")
        crud.delete_codex2api_service(db, service_id)
        return {"success": True, "message": f"Codex2Api 服务 {service.name} 已删除"}


@router.post("/{service_id}/test")
async def test_codex2api_service(service_id: int):
    """测试 Codex2Api 服务连接。"""
    with get_db() as db:
        service = crud.get_codex2api_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Codex2Api 服务不存在")
        success, message = test_codex2api_connection(service.api_url, service.admin_key)
        return {"success": success, "message": message}


@router.post("/test-connection")
async def test_codex2api_connection_direct(request: Codex2ApiTestRequest):
    """直接测试 Codex2Api 连接。"""
    if not request.api_url or not request.admin_key:
        raise HTTPException(status_code=400, detail="api_url 和 admin_key 不能为空")
    success, message = test_codex2api_connection(request.api_url, request.admin_key)
    return {"success": success, "message": message}


@router.post("/upload")
async def upload_accounts_to_codex2api(request: Codex2ApiUploadRequest):
    """批量上传账号到 Codex2Api 平台。"""
    if not request.account_ids:
        raise HTTPException(status_code=400, detail="账号 ID 列表不能为空")

    with get_db() as db:
        if request.service_id:
            service = crud.get_codex2api_service_by_id(db, request.service_id)
        else:
            services = crud.get_codex2api_services(db, enabled=True)
            service = services[0] if services else None

        if not service:
            raise HTTPException(status_code=400, detail="未找到可用的 Codex2Api 服务")

    return batch_upload_to_codex2api(
        request.account_ids,
        service.api_url,
        service.admin_key,
        getattr(service, "proxy_url", None),
    )
