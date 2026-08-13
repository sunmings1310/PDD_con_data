"""上传图片内容过滤：识别并拦截药品经营许可证等证照图。"""

from __future__ import annotations

import io
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("sjzq.image_filter")

# 命中任一强关键词 → 直接拦截
_STRONG_KEYWORDS = (
    "药品经营许可证",
    "药品生产许可证",
    "国家药品监督管理局监制",
)

# 证照常见字段；累计得分达到阈值则拦截（应对 OCR 漏读标题）
_SCORE_MARKERS: tuple[tuple[str, int], ...] = (
    ("药品经营许可", 5),
    ("经营许可证", 4),
    ("药品监督管理局", 3),
    ("社会信用代码", 2),
    ("信用代码", 2),
    ("许可证编号", 2),
    ("证编号", 1),
    ("发证机关", 2),
    ("经营范围", 1),
    ("经营地址", 1),
    ("有效期至", 1),
    ("企业名称", 1),
    ("NMPA", 2),
    ("拼多多专用", 1),
)

_SCORE_THRESHOLD = 5


def _configure_tesseract() -> bool:
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract 未安装，证照图片过滤不可用")
        return False

    cmd = os.environ.get("TESSERACT_CMD", "").strip()
    if not cmd:
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "tesseract",
        ]
        for c in candidates:
            if c == "tesseract" or Path(c).is_file():
                cmd = c
                break
    if cmd and cmd != "tesseract":
        pytesseract.pytesseract.tesseract_cmd = cmd
    return True


@lru_cache(maxsize=1)
def _ocr_ready() -> bool:
    return _configure_tesseract()


def _normalize(text: str) -> str:
    t = text.upper()
    t = re.sub(r"\s+", "", t)
    # 常见 OCR 形近/误读
    repl = {
        "編": "编",
        "號": "号",
        "許": "许",
        "證": "证",
        "營": "营",
        "藥": "药",
        "監": "监",
        "督": "督",
        "機": "机",
        "關": "关",
        "編号": "编号",
        "编號": "编号",
        "许可证编凶": "许可证编号",
        "许可证编嗎": "许可证编号",
        "许可证编吗": "许可证编号",
    }
    for a, b in repl.items():
        t = t.replace(a, b)
    return t


def _ocr_image_bytes(data: bytes) -> str:
    from PIL import Image, ImageEnhance, ImageOps
    import pytesseract

    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    # 控制体积，加快识别
    img.thumbnail((1400, 1400))
    gray = ImageOps.grayscale(img)
    gray = ImageEnhance.Contrast(gray).enhance(1.8)

    chunks: list[str] = []
    for im, cfg in (
        (gray, "--psm 6"),
        (gray.point(lambda x: 0 if x < 150 else 255), "--psm 6"),
    ):
        try:
            chunks.append(
                pytesseract.image_to_string(im, lang="chi_sim+eng", config=cfg) or ""
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("OCR 失败: %s", e)
    return "\n".join(chunks)


def classify_license_text(text: str) -> tuple[bool, str]:
    """返回 (是否证照应拦截, 原因)。"""
    norm = _normalize(text)
    if not norm:
        return False, ""
    for kw in _STRONG_KEYWORDS:
        if kw in norm:
            return True, kw
    score = 0
    hits: list[str] = []
    for kw, w in _SCORE_MARKERS:
        if kw.upper() in norm if kw.isascii() else kw in norm:
            score += w
            hits.append(f"{kw}+{w}")
    # 「药品」与「许可证」同时出现，额外加权
    if "药品" in norm and "许可证" in norm:
        score += 3
        hits.append("药品+许可证+3")
    if score >= _SCORE_THRESHOLD:
        return True, f"score={score}({'/'.join(hits)})"
    return False, ""


def is_blocked_license_image(data: bytes) -> tuple[bool, str]:
    """
    判断图片是否为药品经营许可证等证照。
    返回 (blocked, reason)。OCR 不可用时放行，避免误伤上传。
    """
    if not data or len(data) < 200:
        return False, ""
    if not _ocr_ready():
        return False, "ocr_unavailable"
    try:
        text = _ocr_image_bytes(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("读图/OCR 异常: %s", e)
        return False, ""
    blocked, reason = classify_license_text(text)
    if blocked:
        logger.info("拦截证照图片: %s", reason)
    return blocked, reason


def is_blocked_license_file(path: Path | str) -> tuple[bool, str]:
    p = Path(path)
    try:
        return is_blocked_license_image(p.read_bytes())
    except Exception as e:  # noqa: BLE001
        logger.warning("读取图片失败 %s: %s", p, e)
        return False, ""
