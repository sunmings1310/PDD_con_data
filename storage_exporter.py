"""存储 & 导出：SQLite 增量落库 + xlsx/csv 导出。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger

from utils import ROOT, ensure_dirs

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS task_log (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT,
    start_time TEXT,
    end_time TEXT,
    keyword_list TEXT,
    total_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    status TEXT
);
CREATE TABLE IF NOT EXISTS product_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    item_id TEXT,
    title TEXT,
    sell_name TEXT,
    product_name TEXT,
    price REAL,
    group_price REAL,
    deal_price REAL,
    original_price REAL,
    sales_num INTEGER,
    spec TEXT,
    approval_no TEXT,
    shop_id TEXT,
    shop_name TEXT,
    category TEXT,
    coupon_info TEXT,
    spec_list TEXT,
    main_images TEXT,
    item_url TEXT,
    update_time TEXT,
    keyword TEXT,
    pick_tag TEXT,
    FOREIGN KEY(task_id) REFERENCES task_log(task_id)
);
CREATE TABLE IF NOT EXISTS excel_task (
    task_id INTEGER PRIMARY KEY,
    excel_path TEXT,
    excel_hash TEXT,
    total_rows INTEGER DEFAULT 0,
    current_row INTEGER DEFAULT 0,
    mode TEXT DEFAULT 'excel_target',
    updated_at TEXT,
    FOREIGN KEY(task_id) REFERENCES task_log(task_id)
);
CREATE TABLE IF NOT EXISTS excel_task_row (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    row_index INTEGER,
    keyword TEXT,
    target_spec TEXT,
    target_approval TEXT,
    status TEXT DEFAULT 'pending',
    item_id TEXT,
    message TEXT,
    updated_at TEXT,
    UNIQUE(task_id, row_index),
    FOREIGN KEY(task_id) REFERENCES task_log(task_id)
);
"""

EXTRA_COLS = {
    "sell_name": "TEXT",
    "product_name": "TEXT",
    "group_price": "REAL",
    "deal_price": "REAL",
    "display_price": "REAL",
    "spec": "TEXT",
    "approval_no": "TEXT",
    "pick_tag": "TEXT",
    "manufacturer": "TEXT",
    "brand": "TEXT",
    "dosage_form": "TEXT",
    "expiry": "TEXT",
    "comment_num": "INTEGER",
    "shop_sales_num": "INTEGER",
    "sku_prices": "TEXT",
    "sku_prices_text": "TEXT",
}

# 导出列顺序与中文名（能采到的都导出）
EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("task_id", "任务ID"),
    ("keyword", "关键词"),
    ("item_id", "商品ID"),
    ("sell_name", "售卖名称"),
    ("product_name", "商品名称"),
    ("brand", "品牌"),
    ("shop_name", "店铺名称"),
    ("shop_id", "店铺ID"),
    ("price", "列表价"),
    ("display_price", "详情展示价"),
    ("group_price", "拼单价"),
    ("deal_price", "单独购买价"),
    ("original_price", "原价"),
    ("sales_num", "销量"),
    ("shop_sales_num", "店铺销量"),
    ("comment_num", "评价数"),
    ("spec", "规格"),
    ("sku_prices_text", "多规格价格"),
    ("sku_prices", "多规格价格JSON"),
    ("dosage_form", "剂型"),
    ("approval_no", "国药准字"),
    ("manufacturer", "生产厂家"),
    ("expiry", "有效期"),
    ("category", "类目"),
    ("coupon_info", "优惠信息"),
    ("main_images", "图片"),
    ("item_url", "链接"),
    ("pick_tag", "采集规则"),
    ("spec_list", "属性明细"),
    ("update_time", "采集时间"),
]

TASK_EXTRA_COLS = {
    "task_type": "TEXT",
}


class StorageExporter:
    def __init__(self, db_path: str | Path | None = None, output_dir: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else ROOT / "workbench.db"
        self.output_dir = Path(output_dir) if output_dir else ROOT / "output_data"
        ensure_dirs(self.output_dir, self.db_path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(product_table)").fetchall()}
            for name, typ in EXTRA_COLS.items():
                if name not in cols:
                    conn.execute(f"ALTER TABLE product_table ADD COLUMN {name} {typ}")
            tcols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}
            for name, typ in TASK_EXTRA_COLS.items():
                if name not in tcols:
                    conn.execute(f"ALTER TABLE task_log ADD COLUMN {name} {typ}")
            conn.commit()

    def create_task(self, task_name: str, keywords: list[str], task_type: str = "normal") -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO task_log(task_name, start_time, keyword_list, status, task_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_name, now, json.dumps(keywords, ensure_ascii=False), "running", task_type),
            )
            conn.commit()
            return int(cur.lastrowid)

    def create_excel_checkpoint(
        self,
        task_id: int,
        excel_path: str,
        excel_hash: str,
        rows: list[dict[str, Any]],
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO excel_task(task_id, excel_path, excel_hash, total_rows, current_row, mode, updated_at)
                VALUES (?, ?, ?, ?, 0, 'excel_target', ?)
                """,
                (task_id, excel_path, excel_hash, len(rows), now),
            )
            for r in rows:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO excel_task_row(
                        task_id, row_index, keyword, target_spec, target_approval,
                        status, item_id, message, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', '', '', ?)
                    """,
                    (
                        task_id,
                        int(r["row_index"]),
                        r["keyword"],
                        r["target_spec"],
                        r["target_approval"],
                        now,
                    ),
                )
            conn.commit()

    def list_resumable_excel_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """未完成的 Excel 靶标任务（有 pending/running/error 行）。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, e.excel_path, e.total_rows, e.current_row,
                       (SELECT COUNT(*) FROM excel_task_row r
                        WHERE r.task_id=t.task_id AND r.status IN ('pending','running','error')) AS left_rows
                FROM task_log t
                JOIN excel_task e ON e.task_id = t.task_id
                WHERE t.task_type='excel_target'
                  AND t.status IN ('running','interrupted','paused','failed')
                  AND EXISTS (
                    SELECT 1 FROM excel_task_row r
                    WHERE r.task_id=t.task_id AND r.status IN ('pending','running','error')
                  )
                ORDER BY t.task_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_excel_task_meta(self, task_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM excel_task WHERE task_id=?",
                (task_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_excel_rows(
        self,
        task_id: int,
        *,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if statuses:
                placeholders = ",".join("?" * len(statuses))
                rows = conn.execute(
                    f"""
                    SELECT * FROM excel_task_row
                    WHERE task_id=? AND status IN ({placeholders})
                    ORDER BY row_index ASC
                    """,
                    (task_id, *statuses),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM excel_task_row WHERE task_id=? ORDER BY row_index ASC",
                    (task_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_excel_row(
        self,
        task_id: int,
        row_index: int,
        *,
        status: str,
        item_id: str = "",
        message: str = "",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE excel_task_row
                SET status=?, item_id=?, message=?, updated_at=?
                WHERE task_id=? AND row_index=?
                """,
                (status, item_id, message, now, task_id, row_index),
            )
            conn.execute(
                "UPDATE excel_task SET current_row=?, updated_at=? WHERE task_id=?",
                (row_index, now, task_id),
            )
            conn.commit()

    def reset_running_excel_rows(self, task_id: int) -> None:
        """续跑前：把中断时卡在 running 的行改回 pending。"""
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE excel_task_row SET status='pending', updated_at=?
                WHERE task_id=? AND status='running'
                """,
                (now, task_id),
            )
            conn.commit()


    def set_task_status(self, task_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE task_log SET status=? WHERE task_id=?",
                (status, task_id),
            )
            conn.commit()

    def finish_task(
        self,
        task_id: int,
        *,
        total: int,
        success: int,
        fail: int,
        status: str = "finished",
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE task_log
                SET end_time=?, total_count=?, success_count=?, fail_count=?, status=?
                WHERE task_id=?
                """,
                (now, total, success, fail, status, task_id),
            )
            conn.commit()

    def save_product(self, task_id: int, item: dict[str, Any], keyword: str = "") -> None:
        images = item.get("main_images") or []
        if isinstance(images, list):
            images_text = json.dumps(images, ensure_ascii=False)
        else:
            images_text = str(images)

        spec_list = item.get("spec_list")
        if isinstance(spec_list, (list, dict)):
            spec_list_text = json.dumps(spec_list, ensure_ascii=False)
        else:
            spec_list_text = str(spec_list or "")

        sku_prices = item.get("sku_prices")
        if isinstance(sku_prices, (list, dict)):
            sku_prices_json = json.dumps(sku_prices, ensure_ascii=False)
        else:
            sku_prices_json = str(sku_prices or "")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO product_table(
                    task_id, item_id, title, sell_name, product_name,
                    price, display_price, group_price, deal_price, original_price,
                    sales_num, shop_sales_num, comment_num, spec, approval_no,
                    shop_id, shop_name, manufacturer, brand, dosage_form, expiry,
                    category, coupon_info, sku_prices, sku_prices_text,
                    spec_list, main_images, item_url,
                    update_time, keyword, pick_tag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    str(item.get("item_id") or ""),
                    item.get("sell_name") or item.get("title"),
                    item.get("sell_name") or item.get("title"),
                    item.get("product_name") or "",
                    item.get("price"),
                    item.get("display_price"),
                    item.get("group_price"),
                    item.get("deal_price"),
                    item.get("original_price"),
                    item.get("sales_num") or 0,
                    item.get("shop_sales_num") or 0,
                    item.get("comment_num") or 0,
                    item.get("spec") or "",
                    item.get("approval_no") or "",
                    item.get("shop_id") or "",
                    item.get("shop_name") or "",
                    item.get("manufacturer") or "",
                    item.get("brand") or "",
                    item.get("dosage_form") or "",
                    item.get("expiry") or "",
                    item.get("category") or "",
                    str(item.get("coupon_info") or ""),
                    sku_prices_json,
                    item.get("sku_prices_text") or "",
                    spec_list_text,
                    images_text,
                    item.get("item_url"),
                    item.get("update_time") or datetime.now().isoformat(timespec="seconds"),
                    keyword,
                    item.get("pick_tag") or item.get("pick_label") or "",
                ),
            )
            conn.commit()

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM task_log ORDER BY task_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def export_task(self, task_id: int, fmt: str = "xlsx") -> Optional[Path]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM product_table WHERE task_id=? ORDER BY id ASC",
                (task_id,),
            ).fetchall()
        if not rows:
            logger.warning("任务无数据可导出 task_id={}", task_id)
            return None

        df = pd.DataFrame([dict(r) for r in rows])
        # 按固定中文列导出（能采到的字段都进表）
        out_cols = []
        rename_map = {}
        for key, cn in EXPORT_COLUMNS:
            if key in df.columns:
                out_cols.append(key)
                rename_map[key] = cn
        export_df = df[out_cols].rename(columns=rename_map)
        ensure_dirs(self.output_dir)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt.lower() == "csv":
            path = self.output_dir / f"task_{task_id}_{stamp}.csv"
            export_df.to_csv(path, index=False, encoding="utf-8-sig")
        else:
            path = self.output_dir / f"task_{task_id}_{stamp}.xlsx"
            export_df.to_excel(path, index=False)
        logger.info("已导出 {}", path)
        return path
