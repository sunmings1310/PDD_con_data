"""Read-only Golden Sample verification for P0 product consistency."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.db import get_conn
from server.product_read_model import edit_dto, load_canonical_product
from server.routers.products import list_products
from server.schemas import CaptureEditDTO, ProductDetailDTO, ProductEditDTO

GOLDEN_PLATFORM_PRODUCT_ID = "985843042423"

def main() -> int:
    tenant = SimpleNamespace(enterprise_id=1, workspace_id=1, binds={"enterprise_id": 1, "workspace_id": 1})
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT PRODUCT_ID FROM SJZQ_PRODUCT WHERE ITEM_ID=:item_id
                        AND ENTERPRISE_ID=:enterprise_id AND WORKSPACE_ID=:workspace_id
                        AND NVL(IS_DELETED,0)=0 ORDER BY PRODUCT_ID FETCH FIRST 1 ROWS ONLY""",
                    {"item_id": GOLDEN_PLATFORM_PRODUCT_ID, **tenant.binds})
        row = cur.fetchone(); assert row, "golden sample not found"
        model = load_canonical_product(cur, int(row[0]), tenant)
    detail = ProductDetailDTO.model_validate(model)
    library_edit = ProductEditDTO.model_validate(edit_dto(model, "library"))
    capture_edit = CaptureEditDTO.model_validate(edit_dto(model, "capture"))
    stable_keys = ("platform_title", "canonical_name", "brand", "product_attribute_spec", "approval_number", "manufacturer")
    library_values, capture_values = library_edit.model_dump(), capture_edit.model_dump()
    capture_rows = list_products(task_id=51, page=1, limit=200, tenant=tenant).data["items"]
    library_rows = list_products(item_id=GOLDEN_PLATFORM_PRODUCT_ID, page=1, limit=200, tenant=tenant).data["items"]
    capture_row = next(item for item in capture_rows if item["platform_product_id"] == GOLDEN_PLATFORM_PRODUCT_ID)
    library_row = next(item for item in library_rows if item["platform_product_id"] == GOLDEN_PLATFORM_PRODUCT_ID)
    for key in stable_keys:
        assert library_values[key] == capture_values[key] == getattr(detail.stable_profile, key)
        assert capture_row[key] == library_row[key] == getattr(detail.stable_profile, key)
    assert detail.identity.platform_product_id == GOLDEN_PLATFORM_PRODUCT_ID
    assert detail.latest_observation.list_price == 33.2 and detail.latest_observation.sales == 66000
    assert len(detail.sku.sku_combinations) >= 5 and len(detail.media) == 8
    assert detail.provenance.status == "unavailable"
    output = {"golden_sample": GOLDEN_PLATFORM_PRODUCT_ID, "product_id": detail.identity.product_id,
              "stable_matrix": {key: {"detail": getattr(detail.stable_profile, key),
                                       "capture_list": capture_row[key], "library_list": library_row[key],
                                       "capture_edit": capture_values[key], "product_edit": library_values[key]}
                                for key in stable_keys},
              "detail_observation": detail.latest_observation.model_dump(mode="json"),
              "sku_combination_count": len(detail.sku.sku_combinations), "media_count": len(detail.media),
              "provenance": detail.provenance.model_dump(mode="json"), "result": "PASS"}
    print(json.dumps(output, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
