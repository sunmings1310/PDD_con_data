"""配置管理模块：读取 / 写入 config.json。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from utils import ROOT, ensure_dirs

DEFAULT_CONFIG: dict[str, Any] = {
    "browser_path": "",
    "bitbrowser_api_url": "http://127.0.0.1:54345",
    "output_dir": "./output_data",
    "max_concurrent": 1,
    "human_level": "strict",
    "delay_min": 1500,
    "delay_max": 4200,
    "think_min_ms": 800,
    "think_max_ms": 2800,
    "read_min_ms": 2000,
    "read_max_ms": 5500,
    "keyword_gap_min_ms": 5000,
    "keyword_gap_max_ms": 15000,
    "item_gap_min_ms": 3000,
    "item_gap_max_ms": 9000,
    "max_detail_per_keyword": 8,
    # 普通模式：综合排序采集前 N 个（始终开启）
    # 下列两项为可选增强：勾选才额外跑「价格升序第1」「销量降序第1」
    "enable_price_sort": False,
    "enable_sales_sort": False,
    "price_min": 0,
    "price_max": 99999,
    "sales_min": 0,
    "filter_black_words": [],
    "filter_skip_shop": False,
    "retry_times": 2,
    "platform": "pinduoduo",
    "search_url_template": "https://mobile.yangkeduo.com/search_result.html?search_key={keyword}",
    "list_scroll_times": 8,
    "bitbrowser_group_id": "",
    "force_direct": True,
}


class ConfigManager:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else ROOT / "config.json"
        self._data: dict[str, Any] = deepcopy(DEFAULT_CONFIG)

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            merged = deepcopy(DEFAULT_CONFIG)
            merged.update(raw or {})
            self._data = merged
        else:
            self._data = deepcopy(DEFAULT_CONFIG)
            self.save()
        self.ensure_runtime_dirs()
        return self._data

    def save(self, data: dict[str, Any] | None = None) -> None:
        if data is not None:
            self._data.update(data)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.ensure_runtime_dirs()

    def get(self) -> dict[str, Any]:
        return self._data

    def ensure_runtime_dirs(self) -> None:
        out = Path(self._data.get("output_dir") or "./output_data")
        if not out.is_absolute():
            out = ROOT / out
        ensure_dirs(out, ROOT / "logs")
        self._data["_output_dir_abs"] = str(out)

    def abs_output_dir(self) -> Path:
        self.ensure_runtime_dirs()
        return Path(self._data["_output_dir_abs"])
