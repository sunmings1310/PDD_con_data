"""过滤规则模块。"""

from __future__ import annotations

from typing import Any


def pass_filter(item: dict[str, Any], config: dict[str, Any]) -> bool:
    """
    True=保留，False=丢弃。
    规则：价格区间、销量阈值、标题黑名单词、可选跳过店铺。
    """
    title = str(item.get("title") or "")
    price = item.get("price")
    sales = item.get("sales_num") or item.get("sales") or 0
    shop_name = str(item.get("shop_name") or "")

    try:
        price_val = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_val = None

    price_min = float(config.get("price_min") or 0)
    price_max = float(config.get("price_max") or 99999)
    if price_val is not None:
        if price_val < price_min or price_val > price_max:
            return False

    sales_min = int(config.get("sales_min") or 0)
    try:
        sales_val = int(sales)
    except (TypeError, ValueError):
        from utils import parse_sales_num

        sales_val = parse_sales_num(sales)
    if sales_val < sales_min:
        return False

    black_words = config.get("filter_black_words") or []
    for word in black_words:
        w = str(word).strip()
        if w and w in title:
            return False

    if config.get("filter_skip_shop") and not shop_name:
        return False

    return True
