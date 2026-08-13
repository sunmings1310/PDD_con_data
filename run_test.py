"""无界面实测：1 个关键词，验证最低价+最高销量进详情。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config_manager import ConfigManager
from storage_exporter import StorageExporter
from task_runner import TaskRunner
from utils import setup_logging


def main() -> int:
    setup_logging()
    cfg = ConfigManager().load()
    # 测试稍快一点，但仍保留拟人
    cfg["human_level"] = "normal"
    cfg["list_scroll_times"] = 6
    cfg["max_detail_per_keyword"] = 2
    cfg["enable_price_sort"] = False
    cfg["enable_sales_sort"] = False
    cfg["force_direct"] = True
    cfg["keyword_gap_min_ms"] = 2000
    cfg["keyword_gap_max_ms"] = 4000
    cfg["item_gap_min_ms"] = 2000
    cfg["item_gap_max_ms"] = 4500

    storage = StorageExporter(output_dir=ConfigManager().abs_output_dir())
    logs: list[str] = []

    def log_cb(m: str) -> None:
        print(m, flush=True)
        logs.append(m)

    runner = TaskRunner(cfg, storage, log_cb=log_cb)
    kw = sys.argv[1] if len(sys.argv) > 1 else "矿泉水"
    runner.start_task([kw], task_name=f"实测-{kw}")

    # 等待线程结束
    if runner._thread:
        runner._thread.join(timeout=600)

    task_id = runner.current_task_id
    result = {"task_id": task_id, "logs_tail": logs[-30:]}
    if task_id:
        import sqlite3

        conn = sqlite3.connect(str(ROOT / "workbench.db"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT pick_tag, item_id, title, sell_name, product_name,
                      price, display_price, group_price, deal_price,
                      sales_num, shop_sales_num, comment_num,
                      spec, sku_prices_text, dosage_form, approval_no,
                      manufacturer, brand, shop_name, main_images, item_url
               FROM product_table WHERE task_id=? ORDER BY id""",
            (task_id,),
        ).fetchall()
        result["products"] = [dict(r) for r in rows]
        conn.close()

    out = ROOT / "output_data" / "last_test_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT_FILE", out)
    print("PRODUCTS", len(result.get("products") or []))
    return 0 if result.get("products") else 1


if __name__ == "__main__":
    raise SystemExit(main())
