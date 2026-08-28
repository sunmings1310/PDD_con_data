"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from server.task_state import TaskItemStatus, TaskStatus


class PlatformOut(BaseModel):
    platform_code: str
    platform_name: str
    enabled: int
    sort_no: int
    remark: Optional[str] = None


class DeviceRegisterIn(BaseModel):
    device_key: str = Field(..., min_length=4, max_length=64)
    enrollment_token: Optional[str] = Field(default=None, min_length=20, max_length=256)
    device_name: Optional[str] = None
    platform_code: str = "pinduoduo"
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    model: Optional[str] = None


class DeviceHeartbeatIn(BaseModel):
    device_key: str
    status: str = "online"
    app_version: Optional[str] = None
    current_task_id: Optional[int] = None


class DeviceOut(BaseModel):
    device_id: int
    device_key: str
    device_name: Optional[str] = None
    platform_code: str
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    model: Optional[str] = None
    status: str
    last_ip: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    current_task_id: Optional[int] = None
    online: bool = False
    create_time: Optional[datetime] = None


class TaskTargetIn(BaseModel):
    row_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=32)
    source_row_index: int = Field(ge=0)
    platform_code: Optional[str] = Field(default=None, max_length=32)
    platform_product_id: Optional[str] = Field(default=None, max_length=128)
    keyword: Optional[str] = Field(default=None, max_length=256)
    approval: Optional[str] = Field(default=None, max_length=128)
    name: Optional[str] = Field(default=None, max_length=512)
    spec: Optional[str] = Field(default=None, max_length=256)
    manufacturer: Optional[str] = Field(default=None, max_length=256)
    original_row: Optional[dict[str, Any]] = None
    provenance_row_ids: list[str] = Field(default_factory=list)


class TaskCreateIn(BaseModel):
    task_name: str
    task_type: str = "collect"
    platform_code: str = "pinduoduo"
    keywords: list[str] = Field(default_factory=list)
    targets: list[TaskTargetIn] = Field(default_factory=list)
    submission_id: Optional[str] = Field(default=None, min_length=8, max_length=128)
    source: str = "manual"
    priority: int = 5
    device_id: Optional[int] = None
    target_count: int = 0
    config: Optional[dict[str, Any]] = None


class TaskOut(BaseModel):
    task_id: int
    task_name: str
    task_type: str
    platform_code: str
    status: str
    priority: int
    device_id: Optional[int] = None
    keyword_text: Optional[str] = None
    target_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    error_msg: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    create_time: Optional[datetime] = None


class TaskPullOut(BaseModel):
    task_id: int
    task_name: str
    task_type: str
    platform_code: str
    keywords: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)


class TaskProgressIn(BaseModel):
    device_key: str
    task_id: int
    message: str
    level: str = "info"
    success_delta: int = 0
    fail_delta: int = 0
    item_id: Optional[int] = None
    item_status: Optional[str] = None  # validated by authoritative state service; legacy done supported
    product_id: Optional[int] = None
    # 搜索一次关键词（含价格/销量重搜）计 1
    keyword_delta: int = 0
    # Required for any delta update; persisted server-side for replay protection.
    progress_id: Optional[str] = Field(default=None, min_length=8, max_length=64)


class TaskFinishIn(BaseModel):
    device_key: str
    task_id: int
    status: str = "complete"
    error_msg: Optional[str] = None
    finish_id: Optional[str] = Field(default=None, min_length=8, max_length=128)
    expected_product_count: Optional[int] = Field(default=None, ge=0)
    expected_image_count: Optional[int] = Field(default=None, ge=0)


class ProductUploadIn(BaseModel):
    device_key: str
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=128)
    task_id: Optional[int] = None
    task_item_id: Optional[int] = None
    job_id: Optional[int] = Field(default=None, gt=0)
    attempt_id: Optional[int] = Field(default=None, gt=0)
    worker_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    lease_token: Optional[str] = Field(default=None, min_length=32, max_length=256)
    platform_code: str = "pinduoduo"
    keyword: Optional[str] = None
    item_id: Optional[str] = None
    sell_name: Optional[str] = None
    product_name: Optional[str] = None
    brand: Optional[str] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    price: Optional[float] = None
    display_price: Optional[float] = None
    group_price: Optional[float] = None
    deal_price: Optional[float] = None
    original_price: Optional[float] = None
    sales_num: Optional[int] = None
    shop_sales_num: Optional[int] = None
    comment_num: Optional[int] = None
    spec: Optional[str] = None
    sku_prices_text: Optional[str] = None
    sku_prices: Optional[str] = None
    dosage_form: Optional[str] = None
    approval_no: Optional[str] = None
    manufacturer: Optional[str] = None
    expiry: Optional[str] = None
    category: Optional[str] = None
    coupon_info: Optional[str] = None
    item_url: Optional[str] = None
    pick_tag: Optional[str] = None
    spec_list: Optional[str] = None
    raw_json: Optional[str] = None
    image_urls: list[str] = Field(default_factory=list)
    parse_status: Optional[str] = None
    page_status: Optional[str] = None
    quality_status: Optional[str] = None
    field_sources: dict[str, str] = Field(default_factory=dict)
    parser_version: Optional[str] = Field(default=None, max_length=64)
    quality_rules_version: Optional[str] = Field(default=None, max_length=64)
    raw_capture: Optional[dict[str, Any]] = None


class ProductOut(BaseModel):
    product_id: int
    task_id: Optional[int] = None
    platform_code: str
    keyword: Optional[str] = None
    item_id: Optional[str] = None
    sell_name: Optional[str] = None
    product_name: Optional[str] = None
    brand: Optional[str] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    price: Optional[float] = None
    display_price: Optional[float] = None
    group_price: Optional[float] = None
    deal_price: Optional[float] = None
    original_price: Optional[float] = None
    sales_num: Optional[int] = None
    approval_no: Optional[str] = None
    manufacturer: Optional[str] = None
    item_url: Optional[str] = None
    pick_tag: Optional[str] = None
    collect_time: Optional[datetime] = None
    images: list[dict[str, Any]] = Field(default_factory=list)


class ProductIdentityDTO(BaseModel):
    product_id: int
    platform_code: str
    platform_product_id: Optional[str] = None
    master_product_id: Optional[int] = None
    enterprise_product_id: Optional[int] = None
    source_url: Optional[str] = None


class StableProfileDTO(BaseModel):
    platform_title: Optional[str] = None
    canonical_name: Optional[str] = None
    brand: Optional[str] = None
    product_attribute_spec: Optional[str] = None
    approval_number: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    category: Optional[str] = None
    expiry: Optional[str] = None
    attributes: list[dict[str, str]] = Field(default_factory=list)


class ObservationDTO(BaseModel):
    snapshot_id: Optional[int] = None
    observed_at: Optional[Any] = None
    list_price: Optional[float] = None
    detail_price: Optional[float] = None
    single_purchase_price: Optional[float] = None
    group_price: Optional[float] = None
    original_price: Optional[float] = None
    effective_price: Optional[float] = None
    sales: Optional[int] = None
    shop_sales: Optional[int] = None
    comment_count: Optional[int] = None
    promotion: Optional[str] = None
    availability: Optional[str] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    source: str


class SkuDTO(BaseModel):
    sku_dimensions: list[dict[str, Any]] = Field(default_factory=list)
    sku_dimensions_state: str
    sku_combinations: list[dict[str, Any]] = Field(default_factory=list)
    source: str


class ProvenanceDTO(BaseModel):
    status: str
    reason: Optional[str] = None
    raw_id: Optional[int] = None
    snapshot_id: Optional[int] = None
    field_sources: dict[str, Any] = Field(default_factory=dict)
    parser_version: Optional[str] = None
    quality_rules_version: Optional[str] = None


class SnapshotDTO(ObservationDTO):
    """Immutable observation projection; no write model exists by design."""


class ProductDetailDTO(BaseModel):
    identity: ProductIdentityDTO
    stable_profile: StableProfileDTO
    latest_observation: SnapshotDTO
    sku: SkuDTO
    media: list[dict[str, Any]] = Field(default_factory=list)
    provenance: ProvenanceDTO
    quality: dict[str, Any]
    capture_context: dict[str, Any]


class ProductEditDTO(BaseModel):
    product_id: int
    scope: str = "library"
    platform_title: Optional[str] = None
    canonical_name: Optional[str] = None
    brand: Optional[str] = None
    product_attribute_spec: Optional[str] = None
    approval_number: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    category: Optional[str] = None
    expiry: Optional[str] = None


class CaptureEditDTO(ProductEditDTO):
    scope: str = "capture"


class ProductEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_title: Optional[str] = None
    canonical_name: Optional[str] = None
    brand: Optional[str] = None
    product_attribute_spec: Optional[str] = None
    approval_number: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    category: Optional[str] = None
    expiry: Optional[str] = None


class CaptureResultDTO(ProductDetailDTO):
    """Full collection result; capture_context distinguishes draft/saved state."""


class ResourceReferenceDTO(BaseModel):
    resource_id: Optional[int] = None
    availability: Literal["available", "unavailable"]
    reason: Optional[str] = None


class TaskResultResourcesDTO(BaseModel):
    snapshot: ResourceReferenceDTO
    master_product: ResourceReferenceDTO
    enterprise_product: ResourceReferenceDTO
    product: ResourceReferenceDTO
    raw: ResourceReferenceDTO
    quality: ResourceReferenceDTO
    quarantine: ResourceReferenceDTO


class TaskResultLibraryDTO(BaseModel):
    status: Literal["draft", "saved", "unavailable"]
    product_id: Optional[int] = None
    is_saved: bool = False
    can_save: bool = False
    reason: Optional[str] = None


class TaskResultDTO(BaseModel):
    result_kind: Literal["snapshot", "quarantine", "legacy_product"]
    result_id: int
    task_id: int
    job_id: Optional[int] = None
    attempt_id: Optional[int] = None
    snapshot_id: Optional[int] = None
    master_product_id: Optional[int] = None
    enterprise_product_id: Optional[int] = None
    product_id: Optional[int] = None
    quarantine_id: Optional[int] = None
    raw_id: Optional[int] = None
    quality_result_id: Optional[int] = None
    library_status: Literal["draft", "saved", "unavailable"]
    quality_status: Optional[str] = None
    platform_title: Optional[str] = None
    canonical_name: Optional[str] = None
    product_attribute_spec: Optional[str] = None
    brand: Optional[str] = None
    approval_number: Optional[str] = None
    manufacturer: Optional[str] = None
    failure_reason: Optional[str] = None
    collected_at: Optional[Any] = None
    resources: TaskResultResourcesDTO
    library: TaskResultLibraryDTO


class TaskResultsPageDTO(BaseModel):
    items: list[TaskResultDTO] = Field(default_factory=list)
    total: int
    page: int
    limit: int


class TaskResultResourceDetailDTO(BaseModel):
    resource_kind: Literal["snapshot", "raw", "quality", "quarantine"]
    resource_id: int
    task_id: int
    snapshot_id: Optional[int] = None
    master_product_id: Optional[int] = None
    enterprise_product_id: Optional[int] = None
    product_id: Optional[int] = None
    quarantine_id: Optional[int] = None
    raw_id: Optional[int] = None
    quality_result_id: Optional[int] = None
    resources: TaskResultResourcesDTO
    details: dict[str, Any] = Field(default_factory=dict)


class ApiOk(BaseModel):
    ok: bool = True
    message: str = "ok"
    data: Any = None

# Phase 2 worker Job protocol.  All mutable calls include the authoritative Lease identity.
class JobAcquireIn(BaseModel):
    device_key: str = Field(..., min_length=4, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=128)
    platform_code: Optional[str] = Field(default=None, max_length=32)
    lease_seconds: int = Field(default=120, ge=15, le=900)


class JobLeaseIn(BaseModel):
    device_key: str = Field(..., min_length=4, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=128)
    job_id: int = Field(..., gt=0)
    attempt_id: int = Field(..., gt=0)
    lease_token: str = Field(..., min_length=32, max_length=256)


class JobHeartbeatIn(JobLeaseIn):
    lease_seconds: int = Field(default=120, ge=15, le=900)


class JobCheckpointIn(JobLeaseIn):
    version: int = Field(..., ge=1)
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobCompleteIn(JobLeaseIn):
    result_receipt_key: str = Field(..., min_length=8, max_length=128)
    result_receipt_keys: list[str] = Field(default_factory=list, max_length=200)
    result_product_id: Optional[int] = Field(default=None, gt=0)


class JobFailIn(JobLeaseIn):
    error_class: str = Field(..., min_length=3, max_length=64)
    error_code: str = Field(..., min_length=1, max_length=128)
    error_message: str = Field(default="", max_length=2000)


class JobRecoverIn(BaseModel):
    device_key: str = Field(..., min_length=4, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=128)
