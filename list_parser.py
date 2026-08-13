"""搜索 & 列表解析：拟人浏览后提取列表，供选出最低价/最高销量目标。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from loguru import logger

from human_behavior import after_page_ready, before_navigate, human_scroll, micro_mouse, pause
from utils import fen_to_yuan, parse_sales_num


def _is_blocked_page(page) -> str:
    try:
        url = (page.url or "").lower()
        title = ""
        try:
            title = page.title() or ""
        except Exception:
            pass
        html = ""
        try:
            html = page.content()[:4000]
        except Exception:
            pass
        if "login" in url or "登录" in title:
            return "login_required"
        if any(x in html for x in ("请登录", "手机登录", "发送验证码", "打开拼多多APP")):
            return "login_required"
        return ""
    except Exception:
        return ""

LIST_EXTRACT_JS = r"""
() => {
  const out = [];
  const pushItem = (obj) => {
    if (!obj || typeof obj !== 'object') return;
    const item_id = obj.goods_id || obj.goodsId || obj.item_id || obj.itemId || obj.nid || obj.id;
    const title = obj.goods_name || obj.goodsName || obj.title || obj.item_title || obj.name;
    // 必须有数字 goods_id，否则无法进详情
    if (item_id == null || item_id === '') return;
    const idStr = String(item_id);
    if (!/^\d{6,}$/.test(idStr)) return;
    let price = obj.min_group_price || obj.price || obj.group_price || obj.zk_final_price || obj.priceInfo;
    let sales = obj.sales_tip || obj.salesTip || obj.sales || obj.sold || obj.volume || obj.sales_num;
    let shop = obj.mall_name || obj.mallName || obj.shop_name || obj.shopName || obj.nick;
    let link = obj.link_url || obj.link || obj.url || obj.item_url;
    let img = obj.thumb_url || obj.hd_thumb_url || obj.image_url || obj.pic_url;
    out.push({
      item_id: idStr,
      title: title || '',
      price_raw: price,
      sales_raw: sales,
      shop_name: shop || '',
      item_url: link || '',
      image: img || ''
    });
  };

  const walk = (node, depth=0) => {
    if (!node || depth > 10) return;
    if (Array.isArray(node)) {
      if (node.length && typeof node[0] === 'object' && (
        'goods_id' in (node[0]||{}) || 'goodsId' in (node[0]||{}) || 'goods_name' in (node[0]||{})
      )) {
        node.forEach(pushItem);
      } else {
        node.slice(0, 100).forEach(x => walk(x, depth+1));
      }
      return;
    }
    if (typeof node === 'object') {
      // 单个商品对象
      if (('goods_id' in node || 'goodsId' in node) && (node.goods_name || node.goodsName || node.title)) {
        pushItem(node);
      }
      for (const k of Object.keys(node)) {
        const v = node[k];
        if (/goods|item|list|result|data|store|items|itemsInfo/i.test(k)) walk(v, depth+1);
      }
    }
  };

  const roots = [];
  try { if (window.rawData) roots.push(window.rawData); } catch(e) {}
  try { if (window.__NEXT_DATA__) roots.push(window.__NEXT_DATA__); } catch(e) {}
  try { if (window.data) roots.push(window.data); } catch(e) {}
  try {
    for (const k of Object.keys(window)) {
      if (/rawData|__INITIAL|pageData|searchData|listData/i.test(k)) {
        try { roots.push(window[k]); } catch(e) {}
      }
    }
  } catch(e) {}
  roots.forEach(r => walk(r, 0));

  // DOM / HTML：拼多多搜索页常把 goods_id 写在节点 HTML 里，不一定有 <a href>
  const seenG = new Set(out.map(x => x.item_id));
  const parseCardText = (text) => {
    const clean = (text || '').replace(/\u200b/g, '').trim();
    const lines = clean.split('\n').map(s => s.trim()).filter(Boolean);
    const skip = /^(综合|销量|价格|筛选|品牌|商品|百亿|处方药|正品险|假一赔|即将|仅剩|券后|立减|老店|¥|￥|\d+(\.\d+)?|[\d.]+个月.*|\d+个月及.*)$/;
    const title = lines.find(s => s.length >= 10 && !skip.test(s) && !/^[¥￥]/.test(s) && /[\u4e00-\u9fff]/.test(s)) || '';
    let price = '';
    const pm = clean.match(/[¥￥]\s*(\d+(?:\.\d{1,2})?)/);
    if (pm) price = pm[1];
    else {
      const idx = lines.findIndex(s => /^[¥￥]$/.test(s));
      if (idx >= 0 && lines[idx + 1] && /^\d+(?:\.\d{1,2})?$/.test(lines[idx + 1])) {
        price = lines[idx + 1];
      }
    }
    let sales = '';
    const sm = clean.match(/(?:近\s*30\s*天已拼|本店已拼|已拼|全店总售)\s*[\d.]+万?\+?件?/);
    if (sm) sales = sm[0];
    let shop = '';
    const shopLine = lines.find(s => /旗舰店|专营店|专卖店|大药房|药店|药房/.test(s) && s.length <= 36);
    if (shopLine) shop = shopLine;
    return { title, price, sales, shop };
  };

  // 收集「只含一个 goods_id」的较小节点，按面积升序优先（更接近真实卡片）
  const candidates = [];
  const els = Array.from(document.querySelectorAll('div, li, a, section, article'));
  for (const el of els) {
    let oh = '';
    try { oh = el.outerHTML || ''; } catch (e) { continue; }
    if (oh.length < 80 || oh.length > 6000) continue;
    const idMatches = [...oh.matchAll(/goods_id[=:\\"'\/]+(\d{8,})/g)].map(x => x[1]);
    const uniqIds = Array.from(new Set(idMatches));
    if (uniqIds.length !== 1) continue;
    const gid = uniqIds[0];
    if (seenG.has(gid)) continue;
    const text = (el.innerText || '').replace(/\u200b/g, '').trim();
    if (!text || text.length < 12 || text.length > 450) continue;
    if (!/[¥￥]/.test(text)) continue;
    const parsed = parseCardText(text);
    if (!parsed.price) continue;
    if (!parsed.title || parsed.title.length < 8) continue;
    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:9999,height:9999};
    candidates.push({
      gid,
      title: parsed.title,
      price: parsed.price,
      sales: parsed.sales,
      shop: parsed.shop,
      area: Math.max(1, (r.width || 1) * (r.height || 1)),
      tlen: text.length
    });
  }
  candidates.sort((a, b) => a.area - b.area || a.tlen - b.tlen);
  for (const c of candidates) {
    if (seenG.has(c.gid)) continue;
    seenG.add(c.gid);
    out.push({
      item_id: c.gid,
      title: c.title,
      price_raw: '¥' + c.price,
      sales_raw: c.sales,
      shop_name: c.shop,
      item_url: location.origin + '/goods.html?goods_id=' + c.gid,
      image: ''
    });
    if (out.length >= 40) break;
  }

  // 再兜底：整页 HTML 抽 goods_id，正文按「标题+价」块弱绑定
  if (out.filter(x => x.price_raw).length < 3) {
    const html = document.documentElement.innerHTML || '';
    const ids = [];
    const re = /goods_id[=:\\"'\/]+(\d{8,})/g;
    let m;
    while ((m = re.exec(html)) !== null) {
      if (!ids.includes(m[1])) ids.push(m[1]);
      if (ids.length >= 40) break;
    }
    const body = (document.body && document.body.innerText || '').replace(/\u200b/g, '');
    const cardRe = /([^\n]{10,120})\n(?:处方药\n)?(?:[^\n]{0,20}\n){0,6}[¥￥]\s*\n?\s*(\d+(?:\.\d{1,2})?)\n([^\n]*(?:已拼|全店总售)[^\n]*)?/g;
    const cards = [];
    let cm;
    while ((cm = cardRe.exec(body)) !== null) {
      const title = (cm[1] || '').trim();
      if (/^(综合|销量|价格|筛选|品牌|商品|百亿|同仁堂|乐家|胡庆|中药|丸剂)/.test(title) && title.length < 15) continue;
      if (!/丸|盒|片|粒|药|胶囊/.test(title) && !/安宫|牛黄/.test(title)) {
        // 仍接收较长中文标题
        if (title.length < 12) continue;
      }
      cards.push({ title, price: cm[2], sales: (cm[3] || '').trim() });
      if (cards.length >= 40) break;
    }
    const n = Math.min(ids.length, cards.length);
    for (let i = 0; i < n; i++) {
      const gid = ids[i];
      if (seenG.has(gid)) continue;
      seenG.add(gid);
      out.push({
        item_id: gid,
        title: cards[i].title,
        price_raw: '¥' + cards[i].price,
        sales_raw: cards[i].sales,
        shop_name: '',
        item_url: location.origin + '/goods.html?goods_id=' + gid,
        image: ''
      });
    }
  }

  const seen = new Set();
  return out.filter(x => {
    const key = x.item_id;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
"""


def build_search_url(template: str, keyword: str) -> str:
    return template.format(keyword=quote(keyword))


def normalize_list_item(raw: dict[str, Any], platform: str = "pinduoduo") -> dict[str, Any]:
    item_id = str(raw.get("item_id") or "")
    price_raw = raw.get("price_raw")
    if isinstance(price_raw, str) and re.search(r"[¥￥.]", str(price_raw)):
        price = fen_to_yuan(price_raw, assume_fen=False)
    else:
        price = fen_to_yuan(price_raw, assume_fen=True)
    if price is None:
        price = fen_to_yuan(raw.get("price"), assume_fen=False)

    sales_text = str(
        raw.get("sales_raw") if raw.get("sales_raw") is not None else raw.get("sales_num") or ""
    )
    sales_num = 0
    shop_sales_num = 0
    if re.search(r"本店已拼|全店总售|店铺已拼", sales_text):
        shop_sales_num = parse_sales_num(sales_text)
    elif re.search(r"近\s*30\s*天已拼", sales_text) or re.search(r"(?<![本店铺])已拼", sales_text):
        sales_num = parse_sales_num(sales_text)
    else:
        # 模糊文案：带「万」且无「近30天」的更像店铺销，避免灌进商品销量
        if re.search(r"万", sales_text) and not re.search(r"近\s*30", sales_text):
            shop_sales_num = parse_sales_num(sales_text)
        else:
            sales_num = parse_sales_num(sales_text)

    item_url = (raw.get("item_url") or "").strip()
    if item_url.startswith("//"):
        item_url = "https:" + item_url
    elif item_url.startswith("goods.html") or item_url.startswith("/goods"):
        item_url = "https://mobile.yangkeduo.com/" + item_url.lstrip("/")
    elif item_url and not item_url.startswith("http"):
        item_url = "https://mobile.yangkeduo.com/" + item_url.lstrip("/")

    # 拼多多：优先用 goods_id 构造稳定详情地址，避免相对路径无法打开
    if platform == "pinduoduo" and item_id:
        item_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={item_id}"

    return {
        "item_id": item_id,
        "title": (raw.get("title") or "").strip(),
        "price": price,
        "sales_num": sales_num,
        "shop_sales_num": shop_sales_num,
        "shop_name": raw.get("shop_name") or "",
        "item_url": item_url,
        "main_images": [raw["image"]] if raw.get("image") else [],
    }


def parse_search_list(page, keyword: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    template = config.get("search_url_template") or "https://mobile.yangkeduo.com/search_result.html?search_key={keyword}"
    url = build_search_url(template, keyword)
    logger.info("打开搜索页 keyword={} url={}", keyword, url)

    network_hits: list[Any] = []

    def on_response(resp) -> None:
        try:
            u = resp.url
            if resp.status != 200:
                return
            if not any(x in u for x in ("search", "goods", "list", "api")):
                return
            ctype = (resp.headers.get("content-type") or "").lower()
            if "json" not in ctype and "javascript" not in ctype and "text" not in ctype:
                return
            body = resp.text()
            if "goods" not in body.lower() and "item" not in body.lower():
                return
            network_hits.append(json.loads(body))
        except Exception:
            return

    page.on("response", on_response)

    before_navigate(config)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        logger.debug("networkidle 超时，继续拟人浏览")

    after_page_ready(page, config, purpose="list")
    blocked = _is_blocked_page(page)
    if blocked:
        raise RuntimeError(f"搜索页不可用: {blocked}，请先在 BitBrowser 该窗口登录拼多多")

    human_scroll(page, config, purpose="list")
    micro_mouse(page, config)
    pause(config, kind="read")
    after_page_ready(page, config, purpose="list")

    try:
        raw_list = page.evaluate(LIST_EXTRACT_JS) or []
    except Exception as exc:
        logger.error("列表 JS 注入失败: {}", exc)
        raw_list = []

    # 合并网络包里的商品
    for payload in network_hits[:20]:
        try:
            more = page.evaluate(
                """(payload) => {
                  const out=[];
                  const push=(obj)=>{
                    if(!obj||typeof obj!=='object')return;
                    const id=obj.goods_id||obj.goodsId||obj.item_id||obj.id;
                    const title=obj.goods_name||obj.goodsName||obj.title||obj.name;
                    if(!id&&!title)return;
                    out.push({
                      item_id:id!=null?String(id):'',
                      title:title||'',
                      price_raw:obj.min_group_price||obj.price||obj.group_price,
                      sales_raw:obj.sales_tip||obj.sales||obj.sold,
                      shop_name:obj.mall_name||obj.shop_name||'',
                      item_url:obj.link_url||obj.url||'',
                      image:obj.thumb_url||obj.hd_thumb_url||''
                    });
                  };
                  const walk=(n,d=0)=>{
                    if(!n||d>8)return;
                    if(Array.isArray(n)){n.slice(0,100).forEach(x=>walk(x,d+1));return;}
                    if(typeof n==='object'){
                      if('goods_id' in n || 'goods_name' in n || 'title' in n) push(n);
                      Object.values(n).forEach(v=>walk(v,d+1));
                    }
                  };
                  walk(payload);
                  return out;
                }""",
                payload,
            )
            if more:
                raw_list.extend(more)
        except Exception:
            continue

    items = [normalize_list_item(x, config.get("platform", "pinduoduo")) for x in (raw_list or [])]
    # 去重，且必须有 goods_id（否则无法进详情）
    seen = set()
    uniq = []
    for it in items:
        key = it.get("item_id")
        if not key or key in seen:
            continue
        if not str(key).isdigit():
            # 拼多多 goods_id 通常为数字
            if not re.search(r"\d{6,}", str(key)):
                continue
        seen.add(key)
        uniq.append(it)

    logger.info("列表解析完成 keyword={} count={} network_hits={}", keyword, len(uniq), len(network_hits))
    if not uniq:
        blocked = _is_blocked_page(page)
        if blocked:
            raise RuntimeError(f"未解析到商品且页面状态={blocked}")
    return uniq


def extract_list_on_current_page(page, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """不跳转：从当前搜索结果页提取商品列表。"""
    config = config or {}
    try:
        raw_list = page.evaluate(LIST_EXTRACT_JS) or []
    except Exception as exc:
        logger.error("当前页列表 JS 失败: {}", exc)
        raw_list = []
    items = [normalize_list_item(x, config.get("platform", "pinduoduo")) for x in (raw_list or [])]
    seen = set()
    uniq = []
    for it in items:
        key = it.get("item_id")
        if not key or key in seen:
            continue
        if not str(key).isdigit() and not re.search(r"\d{6,}", str(key)):
            continue
        seen.add(key)
        uniq.append(it)
    logger.info("当前页列表 count={}", len(uniq))
    return uniq
