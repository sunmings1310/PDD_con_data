"""从列表中选出：最低价第1个 + 最高销量第1个（可同一商品则只保留一条）。"""

from __future__ import annotations

from typing import Any


def select_lowest_price_and_highest_sales(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    返回带 pick_tag 的目标商品（最多 2 条）：
    - lowest_price: 有价格的商品里价格最低者
    - highest_sales: 销量最高者
    """
    valid = [x for x in items if str(x.get("item_id") or "").strip()]
    if not valid:
        return []

    priced = [x for x in valid if x.get("price") is not None]
    if priced:
        lowest = min(priced, key=lambda x: float(x["price"]))
    else:
        lowest = valid[0]

    sold = [x for x in valid if int(x.get("sales_num") or 0) > 0]
    if sold:
        highest = max(sold, key=lambda x: int(x.get("sales_num") or 0))
    else:
        highest = valid[0]

    out: list[dict[str, Any]] = []
    low_id = str(lowest.get("item_id") or "")
    high_id = str(highest.get("item_id") or "")

    low_item = dict(lowest)
    low_item["pick_tag"] = "lowest_price"
    low_item["pick_label"] = "最低价"
    if low_id:
        low_item["item_url"] = f"https://mobile.yangkeduo.com/goods.html?goods_id={low_id}"
    out.append(low_item)

    if high_id and high_id != low_id:
        high_item = dict(highest)
        high_item["pick_tag"] = "highest_sales"
        high_item["pick_label"] = "最高销量"
        high_item["item_url"] = f"https://mobile.yangkeduo.com/goods.html?goods_id={high_id}"
        out.append(high_item)
    elif high_id == low_id:
        out[0]["pick_tag"] = "lowest_price+highest_sales"
        out[0]["pick_label"] = "最低价且最高销量"

    return out
