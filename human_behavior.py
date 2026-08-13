"""拟人浏览节奏：随机停留、分段滚动、鼠标微动、偶发回看与长停顿。

原则：
- 禁止固定间隔、禁止加载完瞬时读数关闭
- 用非均匀分布（偏向短停 + 偶发长停）模拟真人注意力
- 所有页面操作都走本模块，避免各处硬编码 sleep
"""

from __future__ import annotations

import random
import time
from typing import Any, Optional

from loguru import logger


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _profile(config: dict[str, Any]) -> dict[str, float]:
    """
    human_level: gentle | normal | strict
    数值越大越慢、越像真人逛店。
    """
    level = str(config.get("human_level") or "strict").lower()
    base_min = int(config.get("delay_min") or 1200)
    base_max = int(config.get("delay_max") or 3500)
    if base_max < base_min:
        base_max = base_min

    presets = {
        "gentle": {"mult": 0.85, "long_pause_p": 0.08, "idle_p": 0.05, "backscroll_p": 0.12},
        "normal": {"mult": 1.0, "long_pause_p": 0.15, "idle_p": 0.10, "backscroll_p": 0.18},
        "strict": {"mult": 1.35, "long_pause_p": 0.22, "idle_p": 0.16, "backscroll_p": 0.25},
    }
    p = presets.get(level, presets["strict"])
    return {
        "delay_min": base_min * p["mult"],
        "delay_max": base_max * p["mult"],
        "long_pause_p": p["long_pause_p"],
        "idle_p": p["idle_p"],
        "backscroll_p": p["backscroll_p"],
        "think_min": float(config.get("think_min_ms") or 600),
        "think_max": float(config.get("think_max_ms") or 2200),
        "read_min": float(config.get("read_min_ms") or 1500),
        "read_max": float(config.get("read_max_ms") or 4500),
        "keyword_gap_min": float(config.get("keyword_gap_min_ms") or 4000),
        "keyword_gap_max": float(config.get("keyword_gap_max_ms") or 12000),
        "item_gap_min": float(config.get("item_gap_min_ms") or 2500),
        "item_gap_max": float(config.get("item_gap_max_ms") or 7000),
    }


def human_sleep_ms(low_ms: float, high_ms: float, *, bias: str = "short") -> float:
    """
    非均匀随机停留。
    bias=short: 多数偏短，偶尔偏长（逛列表）
    bias=long:  多数偏中长（读详情）
    """
    low = max(50.0, float(low_ms))
    high = max(low, float(high_ms))
    span = high - low
    if bias == "long":
        # Beta 分布偏向中后段
        r = random.betavariate(2.2, 1.6)
    else:
        # 多数短停 + 长尾
        r = random.betavariate(1.4, 2.8)
    ms = low + span * r
    # 8% 概率插入一次「走神」长停
    if random.random() < 0.08:
        ms *= random.uniform(1.6, 2.8)
    seconds = ms / 1000.0
    time.sleep(seconds)
    return seconds


def pause(config: dict[str, Any], *, kind: str = "action") -> float:
    """统一暂停入口。kind: think/action/read/idle/keyword/item"""
    p = _profile(config)
    mapping = {
        "think": (p["think_min"], p["think_max"], "short"),
        "action": (p["delay_min"], p["delay_max"], "short"),
        "read": (p["read_min"], p["read_max"], "long"),
        "idle": (p["delay_max"], p["delay_max"] * 2.2, "long"),
        "keyword": (p["keyword_gap_min"], p["keyword_gap_max"], "long"),
        "item": (p["item_gap_min"], p["item_gap_max"], "long"),
    }
    low, high, bias = mapping.get(kind, (p["delay_min"], p["delay_max"], "short"))
    # 偶发 idle
    if kind in ("action", "read") and random.random() < p["idle_p"]:
        low, high, bias = mapping["idle"]
        logger.debug("拟人：插入走神停顿")
    sec = human_sleep_ms(low, high, bias=bias)
    logger.debug("拟人停顿 kind={} {:.2f}s", kind, sec)
    return sec


def micro_mouse(page, config: dict[str, Any] | None = None) -> None:
    """鼠标轻微漂移，避免完全静止。"""
    try:
        vp = page.viewport_size or {"width": 390, "height": 844}
        w, h = int(vp.get("width", 390)), int(vp.get("height", 844))
        x = random.randint(int(w * 0.15), int(w * 0.85))
        y = random.randint(int(h * 0.20), int(h * 0.75))
        steps = random.randint(8, 22)
        page.mouse.move(x, y, steps=steps)
        if random.random() < 0.35:
            page.mouse.move(
                _clamp(x + random.randint(-40, 40), 5, w - 5),
                _clamp(y + random.randint(-30, 30), 5, h - 5),
                steps=random.randint(5, 14),
            )
    except Exception as exc:
        logger.debug("鼠标微动跳过: {}", exc)


def human_scroll(
    page,
    config: dict[str, Any],
    *,
    rounds: Optional[int] = None,
    purpose: str = "list",
) -> None:
    """
    分段滚动：距离不一、中途停顿、偶发回滚，模拟真人刷列表/看详情。
    """
    p = _profile(config)
    if rounds is None:
        if purpose == "detail":
            rounds = random.randint(3, 7)
        else:
            base = int(config.get("list_scroll_times") or 10)
            # 不要每次都滚固定次数
            rounds = max(3, int(base * random.uniform(0.65, 1.15)))

    logger.info("拟人滚动 purpose={} rounds={}", purpose, rounds)
    for i in range(rounds):
        micro_mouse(page, config)
        # 分段小滚，而不是一次滚很大
        bursts = random.randint(2, 4)
        for _ in range(bursts):
            delta = random.randint(180, 520) if purpose == "list" else random.randint(120, 380)
            # 偶发轻微左右抖动（移动端几乎无感，但轨迹更不机械）
            dx = random.randint(-8, 8) if random.random() < 0.2 else 0
            page.mouse.wheel(dx, delta)
            human_sleep_ms(120, 420, bias="short")

        # 偶发向上回看
        if random.random() < p["backscroll_p"]:
            page.mouse.wheel(0, -random.randint(80, 260))
            pause(config, kind="action")
            logger.debug("拟人：回看上一段")

        # 滚完一段后停留「扫一眼」
        if purpose == "detail":
            pause(config, kind="read" if i == 0 else "action")
        else:
            pause(config, kind="action")
            if random.random() < p["long_pause_p"]:
                pause(config, kind="idle")


def before_navigate(config: dict[str, Any]) -> None:
    """跳转页面前先想一下，禁止点完立刻下一跳。"""
    pause(config, kind="think")


def after_page_ready(page, config: dict[str, Any], *, purpose: str = "list") -> None:
    """
    页面 ready 后：先微动 + 阅读停顿，再允许解析。
    禁止 networkidle 后瞬时 evaluate。
    """
    micro_mouse(page, config)
    pause(config, kind="read" if purpose == "detail" else "action")
    if random.random() < 0.4:
        micro_mouse(page, config)


def between_keywords(config: dict[str, Any]) -> None:
    pause(config, kind="keyword")


def between_items(config: dict[str, Any]) -> None:
    pause(config, kind="item")


# 兼容旧调用名
def random_delay(delay_min: int, delay_max: int) -> float:
    return human_sleep_ms(delay_min, delay_max, bias="short")
