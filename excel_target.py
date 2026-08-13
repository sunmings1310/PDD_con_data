"""Excel 靶标：导入、规格/国药准字双过匹配、列表清洗优选。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

# 列表标题常见垃圾词（可再被 config 黑名单叠加）
DEFAULT_JUNK_WORDS = [
    "空盒",
    "包装盒",
    "说明书",
    "仿品",
    "高仿",
    "假货",
    "展示",
    "非卖品",
    "玩具",
    "模型",
    "海报",
    "贴纸",
]


def file_sha1(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_approval(text: str) -> str:
    """国药准字规范化：去前缀/空格，大写。"""
    if not text:
        return ""
    s = str(text).strip().upper().replace(" ", "").replace("　", "")
    s = s.replace("国药准字", "")
    s = re.sub(r"^准字", "", s)
    m = re.search(r"[A-Z]?\d{5,}", s)
    if m:
        prefix = re.match(r"^([A-Z]+)", s)
        num = re.search(r"(\d{5,})", s)
        if prefix and num:
            return f"{prefix.group(1)}{num.group(1)}"
        return m.group(0)
    return s


def normalize_spec(text: str) -> str:
    """规格轻度规范化：符号/单位统一，去空格。"""
    if not text:
        return ""
    s = str(text).strip().lower()
    s = s.replace("　", "").replace(" ", "")
    s = s.replace("＊", "*").replace("×", "*").replace("x", "*").replace("Ｘ", "*")
    s = s.replace("克", "g")
    s = s.replace("毫升", "ml")
    s = re.sub(r"规格[:：]?", "", s)
    return s


def spec_core(text: str) -> str:
    """抽取规格核心，如 3g*1丸。"""
    s = normalize_spec(text)
    m = re.search(
        r"(\d+(?:\.\d+)?(?:g|ml)\*\d+(?:丸|片|粒|袋|盒|瓶))",
        s,
        flags=re.I,
    )
    return m.group(1) if m else s


def match_approval(got: str, target: str) -> bool:
    a, b = normalize_approval(got), normalize_approval(target)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def match_spec(got: str, target: str) -> bool:
    """规范化全等，或核心片段互相包含（轻度模糊）。"""
    g, t = normalize_spec(got), normalize_spec(target)
    if not g or not t:
        return False
    if g == t:
        return True
    gc, tc = spec_core(got), spec_core(target)
    if gc and tc and (gc == tc or gc in t or tc in g or gc in tc or tc in gc):
        return True
    if len(g) >= 4 and len(t) >= 4 and (g in t or t in g):
        return True
    return False


def match_double(
    got_spec: str,
    got_approval: str,
    target_spec: str,
    target_approval: str,
) -> tuple[bool, str]:
    """双过：规格 + 国药准字。返回 (是否通过, 说明)。"""
    ok_a = match_approval(got_approval, target_approval)
    ok_s = match_spec(got_spec, target_spec)
    if ok_a and ok_s:
        return True, "双过"
    parts = []
    if not ok_a:
        parts.append(f"准字不符(得={got_approval or '-'} 目标={target_approval})")
    if not ok_s:
        parts.append(f"规格不符(得={got_spec or '-'} 目标={target_spec})")
    return False, "; ".join(parts)


def _guess_columns(df: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cols = list(df.columns)
    for c in cols:
        name = str(c).strip().lower()
        raw = str(c).strip()
        if any(k in raw for k in ("关键词", "关键字", "品名", "搜索词")) or name in ("keyword", "kw"):
            mapping["keyword"] = c
        elif "规格" in raw or name in ("spec",):
            mapping["spec"] = c
        elif any(k in raw for k in ("国药准字", "批准文号", "准字")) or name in ("approval", "approval_no"):
            mapping["approval"] = c
    if len(mapping) < 3 and len(cols) >= 3:
        mapping.setdefault("keyword", cols[0])
        mapping.setdefault("spec", cols[1])
        mapping.setdefault("approval", cols[2])
    return mapping


def load_excel_targets(path: str | Path) -> list[dict[str, Any]]:
    """
    读取 Excel：关键词 | 规格 | 国药准字。
    返回 [{row_index, keyword, target_spec, target_approval}, ...]
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Excel 不存在: {p}")
    df = pd.read_excel(p, dtype=str)
    df = df.fillna("")
    if df.empty:
        raise ValueError("Excel 为空")
    colmap = _guess_columns(df)
    if "keyword" not in colmap or "spec" not in colmap or "approval" not in colmap:
        raise ValueError("Excel 需包含三列：关键词、规格、国药准字（或可识别的列名）")

    out: list[dict[str, Any]] = []
    for i, row in df.iterrows():
        kw = str(row[colmap["keyword"]]).strip()
        spec = str(row[colmap["spec"]]).strip()
        approval = str(row[colmap["approval"]]).strip()
        if not kw:
            continue
        if not spec or not approval:
            logger.warning("第 {} 行缺少规格或准字，跳过 keyword={}", i, kw)
            continue
        out.append(
            {
                "row_index": int(i) if isinstance(i, int) else len(out),
                "keyword": kw,
                "target_spec": spec,
                "target_approval": approval,
            }
        )
    if not out:
        raise ValueError("Excel 无有效数据行")
    logger.info("Excel 靶标加载 {} 行 path={}", len(out), p)
    return out


def clean_and_rank_candidates(
    items: list[dict[str, Any]],
    keyword: str,
    target_spec: str,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """清洗乱名/垃圾标题，并按与靶标相关度排序，供依次进详情。"""
    config = config or {}
    junk = list(DEFAULT_JUNK_WORDS)
    junk.extend(str(w).strip() for w in (config.get("filter_black_words") or []) if str(w).strip())
    junk = [j for j in junk if j]

    kw = (keyword or "").strip()
    kw_core = kw[:6] if len(kw) > 6 else kw
    spec_n = normalize_spec(target_spec)
    spec_c = spec_core(target_spec)

    scored: list[tuple[int, dict[str, Any]]] = []
    for it in items:
        title = str(it.get("title") or it.get("sell_name") or "")
        if not it.get("item_id"):
            continue
        if len(title.strip()) < 2:
            continue
        if any(j in title for j in junk):
            continue
        if kw and (kw not in title) and (kw_core and kw_core not in title):
            shared = False
            if len(kw) >= 2:
                for i in range(len(kw) - 1):
                    if kw[i : i + 2] in title:
                        shared = True
                        break
            if not shared:
                continue

        score = 0
        if kw and kw in title:
            score += 50
        elif kw_core and kw_core in title:
            score += 30
        title_n = normalize_spec(title)
        if spec_c and spec_c in title_n:
            score += 40
        elif spec_n and spec_n in title_n:
            score += 25
        try:
            sales = int(it.get("sales_num") or 0)
        except (TypeError, ValueError):
            sales = 0
        score += min(sales // 1000, 20)
        scored.append((score, it))

    scored.sort(key=lambda x: (-x[0], -int(x[1].get("sales_num") or 0)))
    out = [x[1] for x in scored]
    logger.info(
        "列表清洗 keyword={} 原始={} 保留={} 目标规格={}",
        keyword,
        len(items),
        len(out),
        target_spec,
    )
    return out


def create_sample_excel(path: str | Path) -> Path:
    """生成示例模板。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "关键词": "安宫牛黄丸",
                "规格": "3g*1丸/盒",
                "国药准字": "国药准字Z11020193",
            },
            {
                "关键词": "示例药品",
                "规格": "0.25g*24片/盒",
                "国药准字": "国药准字H12345678",
            },
        ]
    )
    df.to_excel(p, index=False)
    return p
