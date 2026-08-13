"""工具函数与日志初始化。"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent


def ensure_dirs(*paths: str | Path) -> None:
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def setup_logging(log_dir: str | Path | None = None) -> None:
    log_path = Path(log_dir) if log_dir else ROOT / "logs"
    ensure_dirs(log_path)
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}\n",
        colorize=True,
    )
    logger.add(
        str(log_path / "app_{time:YYYYMMDD}.log"),
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}",
    )


def random_delay(delay_min: int, delay_max: int) -> float:
    """兼容旧调用；内部走拟人非均匀停顿。"""
    from human_behavior import human_sleep_ms

    return human_sleep_ms(delay_min, delay_max, bias="short")


def parse_sales_num(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "").replace("+", "")
    if "万" in text:
        import re

        m = re.search(r"([\d.]+)", text)
        return int(float(m.group(1)) * 10000) if m else 0
    import re

    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else 0


def fen_to_yuan(value, assume_fen: bool | None = None) -> float | None:
    if value is None or value == "":
        return None
    text = str(value)
    # 带货币符号或小数，按元
    if assume_fen is None:
        assume_fen = not (re.search(r"[¥￥]", text) or ("." in text and not text.strip().isdigit()))
    try:
        num = float(value)
    except (TypeError, ValueError):
        m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
        if not m:
            return None
        num = float(m.group(1))
        if "." in m.group(1):
            return round(num, 2)
    if assume_fen:
        return round(num / 100.0, 2)
    return round(num, 2)
