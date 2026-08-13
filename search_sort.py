"""拼多多搜索页：按价格升序 / 销量降序筛选，并进入第 1 个商品。"""

from __future__ import annotations

import random
from typing import Any, Optional
from urllib.parse import quote

from loguru import logger

from filter_handler import pass_filter
from human_behavior import after_page_ready, before_navigate, human_scroll, micro_mouse, pause
from list_parser import extract_list_on_current_page, parse_search_list


def build_search_url(template: str, keyword: str) -> str:
    return template.format(keyword=quote(keyword))


def open_search_page(page, keyword: str, config: dict[str, Any]) -> None:
    template = config.get("search_url_template") or (
        "https://mobile.yangkeduo.com/search_result.html?search_key={keyword}"
    )
    url = build_search_url(template, keyword)
    logger.info("打开搜索页 keyword={} url={}", keyword, url)
    before_navigate(config)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    after_page_ready(page, config, purpose="list")
    human_scroll(page, config, rounds=random.randint(2, 4), purpose="list")


def _js_click_sort(page, keywords: list[str]) -> dict[str, Any]:
    """用 JS 在可见节点里找排序文案并点击。"""
    return page.evaluate(
        """(keywords) => {
          const want = new Set(keywords);
          const nodes = Array.from(document.querySelectorAll('div,span,a,li,p,button'));
          const hits = [];
          for (const el of nodes) {
            const t = (el.innerText || el.textContent || '').replace(/\\s+/g,' ').trim();
            if (!t || t.length > 8) continue;
            for (const k of want) {
              if (t === k || t.startsWith(k)) {
                const r = el.getBoundingClientRect();
                if (r.width < 8 || r.height < 8) continue;
                if (r.top < 0 || r.top > (window.innerHeight || 900)) continue;
                hits.push({text:t, key:k, x:r.x + r.width/2, y:r.y + r.height/2});
              }
            }
          }
          if (!hits.length) {
            // 再放宽：包含关键字（仍要求在可视区内）
            for (const el of nodes) {
              const t = (el.innerText || '').replace(/\\s+/g,' ').trim();
              if (!t || t.length > 12) continue;
              for (const k of want) {
                if (t.includes(k)) {
                  const r = el.getBoundingClientRect();
                  if (r.width < 8 || r.height < 8) continue;
                  if (r.top < 0 || r.top > (window.innerHeight || 900)) continue;
                  hits.push({text:t, key:k, x:r.x + r.width/2, y:r.y + r.height/2});
                }
              }
            }
          }
          if (!hits.length) return {ok:false, hits:[]};
          // 优先精确短文本
          hits.sort((a,b)=>a.text.length-b.text.length);
          const h = hits[0];
          const el2 = document.elementFromPoint(h.x, h.y);
          if (el2) el2.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
          return {ok:true, clicked:h, sample:hits.slice(0,8)};
        }""",
        keywords,
    )


def _click_sort_ui(page, config: dict[str, Any], labels: list[str], *, again: bool = False) -> bool:
    # 有的页面要先点「筛选」
    try:
        _js_click_sort(page, ["筛选", "综合"])
        pause(config, kind="action")
    except Exception:
        pass

    result = _js_click_sort(page, labels)
    if not result or not result.get("ok"):
        # Playwright get_by_text 再试
        for text in labels:
            try:
                loc = page.get_by_text(text, exact=False)
                if loc.count() == 0:
                    continue
                loc.first.click(timeout=4000)
                pause(config, kind="action")
                logger.info("Playwright 点击排序: {}", text)
                if again:
                    pause(config, kind="think")
                    loc.first.click(timeout=4000)
                    pause(config, kind="action")
                return True
            except Exception:
                continue
        logger.warning("未点到排序入口 labels={} sample={}", labels, (result or {}).get("sample"))
        return False

    logger.info("JS 点击排序: {}", result.get("clicked"))
    pause(config, kind="action")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        page.wait_for_timeout(1000)
    if again:
        pause(config, kind="think")
        _js_click_sort(page, labels)
        pause(config, kind="action")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            page.wait_for_timeout(800)
    return True


def sort_by_price_asc(page, config: dict[str, Any]) -> bool:
    logger.info("切换排序：价格从低到高")
    ok = _click_sort_ui(page, config, ["价格", "价位"], again=True)
    after_page_ready(page, config, purpose="list")
    human_scroll(page, config, rounds=random.randint(2, 4), purpose="list")
    return ok


def sort_by_sales_desc(page, config: dict[str, Any]) -> bool:
    logger.info("切换排序：销量从高到低")
    ok = _click_sort_ui(page, config, ["销量", "销售"], again=False)
    after_page_ready(page, config, purpose="list")
    human_scroll(page, config, rounds=random.randint(2, 4), purpose="list")
    return ok


def get_first_goods_from_list(page) -> dict[str, Any]:
    data = page.evaluate(
        r"""
() => {
  const anchors = Array.from(document.querySelectorAll('a[href*="goods_id="], [data-goods-id]'));
  for (const el of anchors) {
    let id = el.getAttribute('data-goods-id') || '';
    const href = el.getAttribute('href') || '';
    const m = href.match(/goods_id=(\d+)/);
    if (!id && m) id = m[1];
    if (!id) continue;
    const text = (el.innerText || '').trim();
    const title = text.split('\n').map(s=>s.trim()).filter(Boolean)[0] || '';
    return { item_id: String(id), title, item_url: location.origin + '/goods.html?goods_id=' + id };
  }
  return null;
}
"""
    )
    if not data or not data.get("item_id"):
        raise RuntimeError("排序后列表未找到第一个商品")
    data["item_url"] = f"https://mobile.yangkeduo.com/goods.html?goods_id={data['item_id']}"
    return data


def click_first_goods(page, config: dict[str, Any], goods: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    goods = goods or get_first_goods_from_list(page)
    item_id = str(goods.get("item_id") or "")
    clicked = False
    try:
        loc = page.locator(f"a[href*='goods_id={item_id}'], [data-goods-id='{item_id}']").first
        if loc.count() > 0:
            micro_mouse(page, config)
            pause(config, kind="think")
            loc.scroll_into_view_if_needed(timeout=4000)
            pause(config, kind="action")
            loc.click(timeout=6000)
            clicked = True
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            logger.info("已点击进入第1个商品 goods_id={}", item_id)
    except Exception as exc:
        logger.warning("点击第1个商品失败，将直达详情: {}", exc)
    goods["entered_by_click"] = clicked
    return goods


def _fallback_pick_from_list(page, keyword: str, config: dict[str, Any], sort_mode: str) -> dict[str, Any]:
    """页面点不到排序时：解析列表后按价格/销量选第1个（降级，日志标明）。"""
    logger.warning("排序 UI 不可用，降级为列表数据{}排序", "价格" if sort_mode == "price_asc" else "销量")
    items = parse_search_list(page, keyword, config)
    if not items:
        raise RuntimeError("降级排序失败：列表为空")
    if sort_mode == "price_asc":
        priced = [x for x in items if x.get("price") is not None]
        goods = min(priced, key=lambda x: float(x["price"])) if priced else items[0]
        pick_tag, pick_label = "price_asc_first_fallback", "价格从低到高-第1个(列表降级)"
    else:
        sold = [x for x in items if int(x.get("sales_num") or 0) > 0]
        goods = max(sold, key=lambda x: int(x.get("sales_num") or 0)) if sold else items[0]
        pick_tag, pick_label = "sales_desc_first_fallback", "销量从高到低-第1个(列表降级)"
    goods = dict(goods)
    goods["pick_tag"] = pick_tag
    goods["pick_label"] = pick_label
    goods["item_url"] = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods['item_id']}"
    goods["entered_by_click"] = False
    goods["keyword"] = keyword
    return goods


def ensure_default_sort(page, config: dict[str, Any]) -> None:
    """尽量点回「综合」排序（点不到也不阻断）。"""
    try:
        # 已是综合/默认排序时不必再点，避免误点导致列表刷新丢失
        try:
            u = (page.url or "").lower()
            if "sort_type=default" in u or "sort_type=" not in u:
                logger.info("当前已是综合/默认排序，跳过点击")
                return
        except Exception:
            pass
        ok = _click_sort_ui(page, config, ["综合"], again=False)
        if ok:
            logger.info("已切换/确认综合排序")
            after_page_ready(page, config, purpose="list")
            human_scroll(page, config, rounds=random.randint(1, 3), purpose="list")
    except Exception as exc:
        logger.debug("综合排序点击跳过: {}", exc)


def collect_top_n_default(
    page,
    keyword: str,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    普通模式：搜索关键词 → 综合排序 → 取前 N 个（过滤 + max_detail_per_keyword）。
    """
    open_search_page(page, keyword, config)
    ensure_default_sort(page, config)
    items = extract_list_on_current_page(page, config)
    if not items:
        # 兜底：完整 parse（含网络包）
        items = parse_search_list(page, keyword, config)

    filtered = [x for x in items if pass_filter(x, config)]
    n = int(config.get("max_detail_per_keyword") or 8)
    if n <= 0:
        n = len(filtered)
    selected = filtered[:n]
    out: list[dict[str, Any]] = []
    for i, it in enumerate(selected):
        g = dict(it)
        g["pick_tag"] = f"default_top_{i + 1}"
        g["pick_label"] = f"综合排序-第{i + 1}个"
        g["entered_by_click"] = False
        g["keyword"] = keyword
        if g.get("item_id"):
            g["item_url"] = f"https://mobile.yangkeduo.com/goods.html?goods_id={g['item_id']}"
        out.append(g)
    logger.info(
        "普通模式候选 {} 个（过滤后 {}/列表 {}）keyword={}",
        len(out),
        len(filtered),
        len(items),
        keyword,
    )
    if not out:
        raise RuntimeError("普通模式：综合列表为空或全部被过滤")
    return out


def collect_first_after_sort(
    page,
    keyword: str,
    config: dict[str, Any],
    *,
    sort_mode: str,
    reopen_search: bool = True,
) -> dict[str, Any]:
    if reopen_search:
        open_search_page(page, keyword, config)

    ui_ok = False
    if sort_mode == "price_asc":
        ui_ok = sort_by_price_asc(page, config)
        pick_tag, pick_label = "price_asc_first", "价格从低到高-第1个"
    elif sort_mode == "sales_desc":
        ui_ok = sort_by_sales_desc(page, config)
        pick_tag, pick_label = "sales_desc_first", "销量从高到低-第1个"
    else:
        raise ValueError(f"未知排序模式: {sort_mode}")

    if ui_ok:
        try:
            goods = get_first_goods_from_list(page)
            goods = click_first_goods(page, config, goods)
            goods["pick_tag"] = pick_tag
            goods["pick_label"] = pick_label
            goods["keyword"] = keyword
            return goods
        except Exception as exc:
            logger.warning("UI 排序后取第1个失败，转降级: {}", exc)

    return _fallback_pick_from_list(page, keyword, config, sort_mode)
