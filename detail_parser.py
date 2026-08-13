"""详情页解析：售卖名称/销量/商品名称/规格/国药准字/拼单价/成交价/图片。"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from human_behavior import after_page_ready, before_navigate, human_scroll, pause
from utils import fen_to_yuan, parse_sales_num

DETAIL_EXTRACT_JS = r"""
() => {
  const pushVal = (acc, v) => {
    if (v == null || v === '' || v === 0 || v === '0') return;
    if (Array.isArray(v)) {
      v.forEach(x => {
        if (typeof x === 'number' || (typeof x === 'string' && /\d/.test(x))) acc.push(x);
        else if (x && typeof x === 'object' && (x.price != null || x.group_price != null)) {
          pushVal(acc, x.price != null ? x.price : x.group_price);
        }
      });
      return;
    }
    if (typeof v === 'object') {
      if (v.price != null) pushVal(acc, v.price);
      if (v.group_price != null) pushVal(acc, v.group_price);
      if (v.min_group_price != null) pushVal(acc, v.min_group_price);
      return;
    }
    acc.push(v);
  };
  const digAll = (obj, keys, acc=[], depth=0) => {
    if (!obj || depth > 10) return acc;
    if (Array.isArray(obj)) {
      obj.slice(0, 80).forEach(x => digAll(x, keys, acc, depth+1));
      return acc;
    }
    if (typeof obj === 'object') {
      for (const k of Object.keys(obj)) {
        if (keys.includes(k)) pushVal(acc, obj[k]);
      }
      Object.values(obj).forEach(v => digAll(v, keys, acc, depth+1));
    }
    return acc;
  };

  const collectProps = (obj, acc=[], depth=0) => {
    if (!obj || depth > 10) return acc;
    if (Array.isArray(obj)) {
      obj.slice(0, 100).forEach(x => collectProps(x, acc, depth+1));
      return acc;
    }
    if (typeof obj === 'object') {
      const name = obj.key || obj.name || obj.property_name || obj.label || obj.title || obj.ref_key;
      const val = obj.value || obj.desc || obj.property_value || obj.content || obj.text || obj.ref_value;
      if (name && val != null && typeof name === 'string') {
        acc.push({ name: String(name), value: String(val) });
      }
      Object.values(obj).forEach(v => collectProps(v, acc, depth+1));
    }
    return acc;
  };

  const roots = [];
  try { if (window.rawData) roots.push(window.rawData); } catch(e) {}
  try { if (window.__NEXT_DATA__) roots.push(window.__NEXT_DATA__); } catch(e) {}
  try { if (window.data) roots.push(window.data); } catch(e) {}
  try {
    for (const k of Object.keys(window)) {
      if (/rawData|goods|detail|__INITIAL|oak/i.test(k)) {
        try { roots.push(window[k]); } catch(e) {}
      }
    }
  } catch(e) {}
  const root = { roots };
  const props = collectProps(root, []);
  const bodyText = document.body ? (document.body.innerText || '') : '';

  const findProp = (preds) => {
    for (const p of props) {
      for (const pred of preds) {
        if (pred.test(p.name)) return p.value;
      }
    }
    return '';
  };

  let approval = findProp([/国药准字/, /批准文号/]);
  if (!approval) {
    const m = bodyText.match(/国药准字[A-Za-z]?字?[A-Za-z]?\d+/);
    if (m) approval = m[0];
  }

  let spec = findProp([/^规格$/, /包装规格/, /规格型号/, /规格/]);
  if (!spec) {
    const m2 = bodyText.match(/规格[:：]\s*([^\n]{2,40})/);
    if (m2) spec = m2[1].trim();
  }
  let productName = findProp([/^名称$/, /通用名称/, /商品名称/, /药品名称/]);

  const sellName = (digAll(root, ['goods_name','goodsName','share_title','item_title'], [])[0])
    || (document.querySelector('meta[property="og:title"]')||{}).content
    || document.title || '';

  const groupCandidates = digAll(root, [
    'min_group_price','sku_group_price','group_price','activity_price',
    'max_group_price','on_sale_group_price','minOnSaleGroupPrice','minGroupPrice'
  ], []);
  // 单独购买价相关字段
  const singleCandidates = digAll(root, [
    'min_normal_price','normal_price','market_price','origin_price',
    'old_price','single_price','alone_price','minNormalPrice','normalPrice'
  ], []);
  const dealCandidates = digAll(root, [
    'min_on_sale_group_price','side_sales_price','coupon_price','zk_final_price',
    'minOnSaleGroupPrice'
  ], []);
  const normalCandidates = singleCandidates;
  const salesCandidates = digAll(root, ['sales_tip','salesTip','side_sales_tip','sales','sold_quantity'], []);

  // DOM 可见价：¥ / ￥，并尝试抓「单独买」旁价格
  const domPrices = [];
  const singleDomPrices = [];
  const priceNodes = document.querySelectorAll('[class*="price"], [class*="Price"], span, div');
  priceNodes.forEach(el => {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 40) return;
    if (/[¥￥]/.test(t) && /\d/.test(t)) {
      domPrices.push(t);
      const nearby = ((el.parentElement && el.parentElement.innerText) || t).replace(/\s+/g,' ');
      if (/单独/.test(nearby) && !/拼单|多人|团/.test(nearby.split(/[¥￥]/)[0] || '')) {
        singleDomPrices.push(t);
      }
    }
  });
  // 正文：单独购买 ¥xx / ¥xx 单独买 / 单买价
  const aloneRe = bodyText.match(/单独(?:购买|买)|单买价[^0-9¥￥]{0,12}[¥￥]\s*(\d+(?:\.\d{1,2})?)/);
  if (aloneRe && aloneRe[1]) singleDomPrices.push('¥' + aloneRe[1]);
  const aloneRe1b = bodyText.match(/单独(?:购买|买)[^0-9¥￥]{0,12}[¥￥]\s*(\d+(?:\.\d{1,2})?)/);
  if (aloneRe1b) singleDomPrices.push('¥' + aloneRe1b[1]);
  const aloneRe2 = bodyText.match(/[¥￥]\s*(\d+(?:\.\d{1,2})?)[^。\n]{0,10}单独(?:购买|买)/);
  if (aloneRe2) singleDomPrices.push('¥' + aloneRe2[1]);
  // 页面常有两行价：较大的常为单买，较小组为拼单（仅作候选，不直接定论）
  const groupRe = bodyText.match(/(?:拼单价|发起拼单|多人团)[^0-9¥￥]{0,12}[¥￥]\s*(\d+(?:\.\d{1,2})?)/);
  const bodyPriceMatch = bodyText.match(/[¥￥]\s*(\d+(?:\.\d+)?)/g) || [];
  if (groupRe) domPrices.unshift('¥' + groupRe[1]);

  let images = digAll(root, ['gallery','thumb_url','hd_thumb_url','image_url','main_image','pic_url'], []);
  let flatImgs = [];
  images.forEach(x => {
    if (typeof x === 'string') flatImgs.push(x);
    else if (Array.isArray(x)) x.forEach(i => {
      if (typeof i === 'string') flatImgs.push(i);
      else if (i && (i.url || i.img || i.src)) flatImgs.push(i.url || i.img || i.src);
    });
    else if (x && (x.url || x.img || x.src)) flatImgs.push(x.url || x.img || x.src);
  });
  if (!flatImgs.length) {
    const og = document.querySelector('meta[property="og:image"]');
    if (og && og.content) flatImgs.push(og.content);
    document.querySelectorAll('img').forEach(img => {
      const s = img.src || img.getAttribute('data-src') || '';
      if (s && /pddpic|goods|mms-material|mms-goods/.test(s) && !/share_logo|brand|promo|gexinghua|shangxiang/.test(s)) {
        flatImgs.push(s);
      }
    });
  }
  flatImgs = Array.from(new Set(flatImgs)).slice(0, 12);

  const ids = digAll(root, ['goods_id','goodsId','item_id','itemId'], []);
  const shopKeys = digAll(root, [
    'mall_name','mallName','shop_name','shopName','store_name',
    'merchant_name','mall_title','mallTitle','shop_title'
  ], []);
  const mallIds = digAll(root, ['mall_id','mallId','shop_id','shopId'], []);
  let shopName = '';
  for (const s of shopKeys) {
    const t = String(s || '').trim();
    if (!t || t.length > 48) continue;
    if (/https?:|pddpic|\.png|\.jpg|logo|null|undefined/i.test(t)) continue;
    shopName = t;
    break;
  }
  // DOM：店铺/进店
  if (!shopName) {
    const nodes = Array.from(document.querySelectorAll('a,div,span,p'));
    for (const el of nodes) {
      const t = (el.innerText || '').replace(/\s+/g,' ').trim();
      if (!t || t.length > 40) continue;
      if (/进店|进店铺/.test(t)) {
        const prev = (el.previousElementSibling && (el.previousElementSibling.innerText||'').trim()) || '';
        const parent = (el.parentElement && (el.parentElement.innerText||'').replace(/\s+/g,' ').trim()) || '';
        let cand = prev || parent.split(/进店/)[0].trim();
        cand = cand.replace(/进店.*$/,'').trim();
        if (cand && cand.length >= 2 && cand.length <= 36) {
          shopName = cand;
          break;
        }
      }
    }
  }
  if (!shopName) {
    const mShop = bodyText.match(/([^\n]{2,28}(?:旗舰店|专营店|专卖店|大药房|药店|药房))/);
    if (mShop) shopName = mShop[1].trim();
  }
  // 评价数
  const commentCands = digAll(root, [
    'review_num','comment_num','goods_review_number','reviewNumber',
    'number_of_reviews','side_comment_tip','comment_tip'
  ], []);
  let commentRaw = commentCands.length ? String(commentCands[0]) : '';
  if (!commentRaw) {
    const mc = bodyText.match(/(\d+(?:\.\d+)?万?)\s*评价/);
    if (mc) commentRaw = mc[1] + '评价';
  }
  // 商品销量 vs 店铺销量
  let productSalesRaw = '';
  let shopSalesRaw = '';
  const mProd = bodyText.match(/近\s*30\s*天已拼\s*([\d.]+万?\+?)/);
  if (mProd) productSalesRaw = mProd[1];
  if (!productSalesRaw) {
    const allP = bodyText.matchAll(/(.{0,4})已拼\s*([\d.]+万?\+?)/g);
    for (const x of allP) {
      if (/本店|店铺|全店/.test(x[1] || '')) continue;
      productSalesRaw = x[2];
      break;
    }
  }
  const mShop = bodyText.match(/(?:近期)?本店已拼\s*([\d.]+万?\+?)/)
    || bodyText.match(/店铺已拼\s*([\d.]+万?\+?)/)
    || bodyText.match(/全店总售\s*([\d.]+万?\+?)/);
  if (mShop) shopSalesRaw = mShop[1];
  // dig 的 sales_tip 若含「本店/全店」则归店铺，否则可作商品销兜底
  const salesTip = salesCandidates.length ? String(salesCandidates[0]) : '';
  if (!productSalesRaw && salesTip && !/本店|店铺|全店/.test(salesTip)) productSalesRaw = salesTip;
  if (!shopSalesRaw && salesTip && /本店|店铺|全店/.test(salesTip)) shopSalesRaw = salesTip;

  // 是否页面上明确有拼单语义
  const hasGroupBuy = /发起拼单|拼单价|多人团|邀请好友/.test(bodyText);
  const hasSingleBuy = /单独(?:购买|买)|单买价/.test(bodyText);

  // 详情大字展示价（优先页面顶部大价）
  let displayPrice = '';
  const bigPrice = bodyText.match(/^[^\n]{0,80}?[¥￥]\s*(\d+(?:\.\d{1,2})?)/m)
    || bodyText.match(/[¥￥]\s*(\d{2,}(?:\.\d{1,2})?)/);
  if (bigPrice) displayPrice = bigPrice[1];

  // 优惠
  const couponCands = digAll(root, [
    'coupon_promo_desc','coupon_text','discount_text','activity_desc',
    'promo_desc','couponDisplayName'
  ], []);
  let couponInfo = couponCands.length ? String(couponCands[0]) : '';
  if (!couponInfo) {
    const mc2 = bodyText.match(/满\d+减\d+|券后|优惠券|立减\d+/);
    if (mc2) couponInfo = mc2[0];
  }
  const cats = digAll(root, ['cat_name','category_name','cate_name','opt_name'], []);
  const brands = digAll(root, ['brand_name','brandName','brand'], []);

  const pickByLabel = (label) => {
    const re = new RegExp(label + '[\\s\\n:：]*([^\\n]{1,50})');
    const m = bodyText.match(re);
    return m ? m[1].replace(/查看全部.*$/,'').trim() : '';
  };

  let manufacturer = findProp([/生产厂家/, /生产企业/, /上市许可持有人/, /制造商/])
    || pickByLabel('生产企业') || pickByLabel('生产厂家') || pickByLabel('上市许可持有人');
  let dosageForm = findProp([/产品剂型/, /^剂型$/, /剂型/])
    || pickByLabel('产品剂型') || pickByLabel('剂型');
  let expiry = findProp([/有效期/, /保质期/]) || pickByLabel('有效期') || pickByLabel('保质期');
  let brand = findProp([/^品牌$/, /品牌名称/]) || pickByLabel('品牌')
    || (brands.length ? String(brands[0]) : '');
  let productName2 = productName || findProp([/药品通用名/, /通用名称/]) || pickByLabel('药品通用名') || pickByLabel('通用名称');
  let approval2 = approval || pickByLabel('批准文号') || pickByLabel('国药准字');
  let spec2 = spec || pickByLabel('药品规格') || pickByLabel('规格');
  let medicineCat = pickByLabel('药品类别') || findProp([/药品类别/]);

  // —— 多规格 SKU 价格（如 1盒装/3盒装/5盒装）——
  const skuRows = [];
  const pushSku = (s) => {
    if (!s || typeof s !== 'object') return;
    const specs = s.specs || s.spec || s.sku_specs || s.spec_list || [];
    let specName = '';
    if (Array.isArray(specs)) {
      specName = specs.map(x => {
        if (!x) return '';
        if (typeof x === 'string') return x;
        return x.spec_value || x.specValue || x.spec_name || x.specName || x.value || x.name || '';
      }).filter(Boolean).join('/');
    } else if (typeof specs === 'string') {
      specName = specs;
    }
    if (!specName) {
      specName = String(s.spec_value || s.sku_name || s.name || s.spec_name || '').trim();
    }
    const gp = s.group_price != null ? s.group_price
      : (s.sku_group_price != null ? s.sku_group_price
      : (s.multi_price != null ? s.multi_price
      : (s.min_group_price != null ? s.min_group_price : s.activity_price)));
    const np = s.normal_price != null ? s.normal_price
      : (s.price != null ? s.price : s.single_price);
    if (!specName && gp == null && np == null) return;
    skuRows.push({
      sku_id: s.sku_id != null ? String(s.sku_id) : (s.skuId != null ? String(s.skuId) : ''),
      spec: specName,
      group_price_raw: gp,
      normal_price_raw: np
    });
  };
  const walkSku = (obj, depth=0) => {
    if (!obj || depth > 9) return;
    if (Array.isArray(obj)) {
      if (obj.length && typeof obj[0] === 'object' && obj[0] && (
        'sku_id' in obj[0] || 'skuId' in obj[0] || 'specs' in obj[0] || 'spec' in obj[0] || 'multi_price' in obj[0]
      )) {
        obj.slice(0, 80).forEach(pushSku);
      } else {
        obj.slice(0, 60).forEach(x => walkSku(x, depth+1));
      }
      return;
    }
    if (typeof obj === 'object') {
      for (const k of Object.keys(obj)) {
        if (/^skus?$|sku_list|skuList|sku_info/i.test(k)) walkSku(obj[k], depth+1);
      }
      // 浅层也扫一遍常见挂载
      if (depth < 3) Object.values(obj).slice(0, 40).forEach(v => {
        if (v && typeof v === 'object') walkSku(v, depth+1);
      });
    }
  };
  walkSku(root);

  // DOM：规格弹层里的「1盒装」「3盒装」等按钮文案
  const packSpecs = [];
  document.querySelectorAll('div,span,button,li,a').forEach(el => {
    const t = (el.innerText || '').replace(/\s+/g,'').trim();
    if (!t || t.length > 20) return;
    if (/^\d+盒装/.test(t) || /^\d+件装/.test(t) || /^\d+瓶装/.test(t)) {
      const name = (t.match(/^\d+(?:盒|件|瓶)装/) || [t])[0];
      packSpecs.push(name);
    }
  });

  // 弹层当前展示价
  let panelPrice = '';
  const panelM2 = bodyText.match(/限量低价\s*[¥￥]\s*(\d+(?:\.\d{1,2})?)/)
    || bodyText.match(/确认款式[\s\S]{0,160}?[¥￥]\s*(\d+(?:\.\d{1,2})?)/)
    || bodyText.match(/已选择[：:][^\n]{0,30}/);
  if (panelM2 && panelM2[1]) panelPrice = panelM2[1];
  if (!panelPrice && displayPrice) panelPrice = displayPrice;
  const restoreM = bodyText.match(/即将恢复\s*(\d+(?:\.\d{1,2})?)\s*元/);
  // 多规格价格区间（如 ¥860-4300），用去空白后的正文更稳
  const compactBody = bodyText.replace(/\s+/g, '');
  const rangeM = compactBody.match(/[¥￥](\d+(?:\.\d{1,2})?)[-~～](\d+(?:\.\d{1,2})?)/)
    || bodyText.match(/[¥￥]\s*(\d+(?:\.\d{1,2})?)\s*[-~～]\s*(\d+(?:\.\d{1,2})?)/);

  return {
    item_id: ids.length ? String(ids[0]) : '',
    sell_name: String(sellName || ''),
    product_name: productName2 || productName || '',
    sales_raw: productSalesRaw || '',
    shop_sales_raw: shopSalesRaw || '',
    spec: spec2 || spec || '',
    approval_no: approval2 || approval || '',
    group_price_candidates: groupCandidates.slice(0, 20),
    deal_price_candidates: dealCandidates.slice(0, 20),
    single_price_candidates: singleCandidates.slice(0, 20),
    single_dom_prices: Array.from(new Set(singleDomPrices)).slice(0, 10),
    original_candidates: normalCandidates.slice(0, 10),
    dom_prices: Array.from(new Set(domPrices.concat(bodyPriceMatch))).slice(0, 20),
    main_images: flatImgs,
    shop_name: shopName || '',
    shop_id: mallIds.length ? String(mallIds[0]) : '',
    manufacturer: manufacturer || '',
    brand: brand || '',
    dosage_form: dosageForm || '',
    expiry: expiry || '',
    comment_raw: commentRaw || '',
    coupon_info: couponInfo || '',
    category: medicineCat || (cats.length ? String(cats[0]) : ''),
    has_group_buy: !!hasGroupBuy,
    has_single_buy: !!hasSingleBuy,
    display_price: displayPrice || '',
    sku_rows: skuRows.slice(0, 60),
    pack_specs_dom: Array.from(new Set(packSpecs)).slice(0, 20),
    panel_price: panelPrice || '',
    restore_price: restoreM ? restoreM[1] : '',
    price_range: rangeM ? [rangeM[1], rangeM[2]] : [],
    props,
    page_url: location.href,
    body_snippet: bodyText.slice(0, 4500)
  };
}
"""


def _clean_approval(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"国药准字[A-Za-z]?字?[A-Za-z]?\d+", text)
    return m.group(0) if m else ""


def _pick_price(candidates: Any, *, prefer_fen: bool = True) -> Optional[float]:
    """从候选里选出合理价格（>0）。拼多多接口多为分。"""
    if candidates is None:
        return None
    values: list[Any] = []
    if isinstance(candidates, list):
        for c in candidates:
            if isinstance(c, (list, tuple)):
                values.extend(list(c))
            else:
                values.append(c)
    else:
        values = [candidates]

    parsed: list[float] = []
    for v in values:
        if v is None or v == "" or v == 0 or v == "0":
            continue
        # 分：仅在 prefer_fen 时把 >=100 的整数当「分」
        if (
            prefer_fen
            and isinstance(v, (int, float))
            and float(v).is_integer()
            and abs(float(v)) >= 100
        ):
            p = fen_to_yuan(v, assume_fen=True)
        elif isinstance(v, str) and re.search(r"[¥￥.]", v):
            p = fen_to_yuan(v, assume_fen=False)
        else:
            p = fen_to_yuan(v, assume_fen=prefer_fen)
            if p is not None and prefer_fen and p < 0.5:
                p2 = fen_to_yuan(v, assume_fen=False)
                if p2 and p2 >= 0.5:
                    p = p2
        if p is not None and p > 0:
            parsed.append(round(p, 2))

    if not parsed:
        return None
    uniq = sorted(set(parsed))
    # 丢掉极低噪声：若有 >=10 元的价，忽略 <2 元的候选
    substantial = [p for p in uniq if p >= 10]
    if substantial:
        return min(substantial)
    mid = [p for p in uniq if p >= 2]
    if mid:
        return min(mid)
    return min(uniq)


def _extract_spec(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"规格[:：]\s*([^\n，,]{2,40})",
        r"(\d+\s*[gG克]\s*[*＊×xX]\s*\d+\s*丸(?:/[^\s，,]{1,8})?)",
        r"(\d+\s*[gG克]\s*[*＊×xX]\s*\d+\s*[片粒袋盒瓶](?:/[^\s，,]{1,8})?)",
        r"(\d+\s*ml\s*[*＊×xX]\s*\d+\s*瓶(?:/[^\s，,]{1,8})?)",
        r"((?:每盒|每板)?\d+(?:\.\d+)?\s*(?:g|克|ml|mL)\s*[*＊×xX]\s*\d+\s*(?:丸|片|粒|袋|盒|瓶))",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return re.sub(r"\s+", "", m.group(1) if m.lastindex else m.group(0))
    return ""


def _format_sku_prices(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """把多规格 SKU 整理成列表 + 可读文本。"""
    rows: list[dict[str, Any]] = []
    for s in raw.get("sku_rows") or []:
        if not isinstance(s, dict):
            continue
        spec = str(s.get("spec") or "").strip()
        gp = _pick_price([s.get("group_price_raw")]) if s.get("group_price_raw") not in (None, "") else None
        np = _pick_price([s.get("normal_price_raw")]) if s.get("normal_price_raw") not in (None, "") else None
        # 有的字段已是元（带 ¥ 或小数）
        if gp is None and s.get("group_price_raw") not in (None, ""):
            gp = _pick_price([s.get("group_price_raw")], prefer_fen=False)
        if np is None and s.get("normal_price_raw") not in (None, ""):
            np = _pick_price([s.get("normal_price_raw")], prefer_fen=False)
        if not spec and gp is None and np is None:
            continue
        rows.append(
            {
                "sku_id": str(s.get("sku_id") or ""),
                "spec": spec,
                "group_price": gp,
                "normal_price": np,
            }
        )

    # DOM 只有规格名、没有价时也列出，便于对照
    for name in raw.get("pack_specs_dom") or []:
        name = str(name).strip()
        if not name:
            continue
        if any(r.get("spec") == name for r in rows):
            continue
        rows.append({"sku_id": "", "spec": name, "group_price": None, "normal_price": None})

    # 弹层当前价：仅在尚无任何规格价时，挂到第一个包装规格（避免把选中价误挂到其它盒装）
    panel = raw.get("panel_price")
    try:
        panel_f = float(panel) if panel not in (None, "") else None
    except (TypeError, ValueError):
        panel_f = None
    if panel_f is not None:
        has_priced = any(
            r.get("group_price") is not None or r.get("normal_price") is not None for r in rows
        )
        if not has_priced:
            for r in rows:
                if re.search(r"盒装|件装|瓶装", str(r.get("spec") or "")):
                    r["normal_price"] = panel_f
                    break
            if not rows:
                rows.append(
                    {"sku_id": "", "spec": "当前选中规格", "group_price": None, "normal_price": panel_f}
                )

    # 去重
    seen = set()
    uniq = []
    for r in rows:
        key = (r.get("spec"), r.get("group_price"), r.get("normal_price"), r.get("sku_id"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    has_group = bool(raw.get("has_group_buy"))
    parts = []
    for r in uniq:
        bits = [r.get("spec") or "未命名规格"]
        if r.get("group_price") is not None and has_group:
            bits.append(f"拼单¥{r['group_price']}")
        if r.get("normal_price") is not None:
            bits.append(f"售价¥{r['normal_price']}")
        elif r.get("group_price") is not None and not has_group:
            # 接口误标成 group 的价，按售价展示
            bits.append(f"售价¥{r['group_price']}")
        parts.append("=".join(bits) if len(bits) == 1 else f"{bits[0]}({','.join(bits[1:])})")
    text = " | ".join(parts)

    # 有区间价且各规格价未齐时，附上区间避免误把最低价套到每一档
    pr = raw.get("price_range") or []
    try:
        if isinstance(pr, (list, tuple)) and len(pr) >= 2:
            lo, hi = float(pr[0]), float(pr[1])
            priced_n = sum(
                1
                for r in uniq
                if r.get("normal_price") is not None or r.get("group_price") is not None
            )
            if hi > lo and priced_n < max(2, len(uniq)):
                tip = f"价格区间¥{lo:g}-{hi:g}"
                text = f"{text} | {tip}" if text else tip
    except (TypeError, ValueError):
        pass
    return uniq, text


def _walk_price_keys(obj: Any, acc: list[Any] | None = None, depth: int = 0) -> list[Any]:
    if acc is None:
        acc = []
    if obj is None or depth > 10:
        return acc
    if isinstance(obj, list):
        for x in obj[:80]:
            _walk_price_keys(x, acc, depth + 1)
        return acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {
                "min_group_price",
                "sku_group_price",
                "group_price",
                "price",
                "min_on_sale_group_price",
                "activity_price",
                "on_sale_group_price",
                "side_sales_price",
            }:
                if isinstance(v, list):
                    acc.extend([x for x in v if isinstance(x, (int, float, str))])
                elif v not in (None, "", 0, "0"):
                    acc.append(v)
            else:
                _walk_price_keys(v, acc, depth + 1)
    return acc


def _attach_price_listener(page, bucket: list[Any]):
    def on_response(resp) -> None:
        try:
            if resp.status != 200:
                return
            u = resp.url
            if not any(x in u for x in ("goods", "oak", "detail", "api", "proxy")):
                return
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct and "javascript" not in ct and "text" not in ct:
                return
            body = resp.text()
            if not body or len(body) > 8_000_000:
                return
            if "min_group_price" not in body and "group_price" not in body and "sku_group_price" not in body:
                return
            import json

            try:
                bucket.append(json.loads(body))
            except Exception:
                # 非纯 JSON 时用正则捞分价
                for m in re.finditer(
                    r'"(?:min_group_price|sku_group_price|group_price|min_on_sale_group_price)"\s*:\s*(\[.*?\]|\d+)',
                    body,
                ):
                    chunk = m.group(1)
                    if chunk.startswith("["):
                        try:
                            arr = json.loads(chunk)
                            bucket.append({"min_group_price": arr})
                        except Exception:
                            pass
                    else:
                        bucket.append({"min_group_price": int(chunk)})
        except Exception:
            return

    page.on("response", on_response)
    return on_response


def _merge_network_prices(raw: dict[str, Any], network_payloads: list[Any]) -> None:
    if not network_payloads:
        return
    cand = list(raw.get("group_price_candidates") or [])
    for payload in network_payloads[:12]:
        cand.extend(_walk_price_keys(payload))
    raw["group_price_candidates"] = cand


def _read_sku_panel_price(page) -> str:
    """只读当前选中规格的售价；忽略 ¥860-4300 这类区间价。"""
    try:
        return (
            page.evaluate(
                """() => {
                  const isRange = (t, idx) => {
                    // 匹配位置后是否紧跟 -数字（区间价）
                    const tail = t.slice(idx, idx + 24);
                    return /[¥￥]\\s*\\d+(?:\\.\\d{1,2})?\\s*[-~～]\\s*\\d/.test(tail);
                  };
                  const pickSingle = (t) => {
                    if (!t) return '';
                    let m = t.match(/限量低价\\s*[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)/);
                    if (m) return m[1];
                    m = t.match(/券后价?\\s*[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)/);
                    if (m) return m[1];
                    m = t.match(/拼单价\\s*[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)/);
                    if (m) return m[1];
                    // 所有货币价，跳过区间左端
                    const re = /[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)/g;
                    let hit;
                    const cands = [];
                    while ((hit = re.exec(t)) !== null) {
                      if (isRange(t, hit.index)) continue;
                      const n = parseFloat(hit[1]);
                      if (n >= 1) cands.push(hit[1]);
                    }
                    return cands.length ? cands[0] : '';
                  };

                  // 1) 含包装数量/确认款式的弹层（较短优先）
                  const nodes = Array.from(document.querySelectorAll('div,section,aside'));
                  const panels = [];
                  for (const el of nodes) {
                    const t = (el.innerText || '').replace(/\\u200b/g, '').trim();
                    if (!t || t.length < 8 || t.length > 2500) continue;
                    if (!/(确认款式|已选择|包装数量|限量低价|请选择包装)/.test(t)) continue;
                    if (!/[¥￥]/.test(t)) continue;
                    panels.push({ t, len: t.length });
                  }
                  panels.sort((a, b) => a.len - b.len);
                  for (const p of panels.slice(0, 10)) {
                    const price = pickSingle(p.t);
                    if (price) return price;
                  }

                  // 2) 页面顶部展示价（选中规格后通常不再是区间）
                  const body = (document.body && document.body.innerText || '').replace(/\\u200b/g, '');
                  const head = body.slice(0, 500);
                  const top = pickSingle(head);
                  if (top) return top;

                  return '';
                }"""
            )
            or ""
        )
    except Exception:
        return ""


def _click_sku_option(page, name: str) -> bool:
    """点击精确的 N盒装/件装/瓶装 选项。"""
    # 1) Playwright 文本点击更稳
    try:
        loc = page.get_by_text(name, exact=True)
        n = loc.count()
        for i in range(min(n, 6)):
            try:
                target = loc.nth(i)
                target.scroll_into_view_if_needed(timeout=2000)
                target.click(timeout=2500, force=True)
                return True
            except Exception:
                continue
    except Exception:
        pass
    # 2) JS：文本节点可能宽高为0，向上找可点父级
    try:
        return bool(
            page.evaluate(
                """(name) => {
                  const nodes = Array.from(document.querySelectorAll('div,span,button,li,a,p'));
                  const hits = [];
                  for (const el of nodes) {
                    const t = (el.innerText || '').replace(/\\s+/g, '').replace(/\\u200b/g, '').trim();
                    if (!t) continue;
                    if (t !== name && !t.startsWith(name)) continue;
                    if (t.length > name.length + 8) continue;
                    hits.push({ el, tlen: t.length });
                  }
                  if (!hits.length) return false;
                  hits.sort((a, b) => a.tlen - b.tlen);
                  let el = hits[0].el;
                  for (let i = 0; i < 6 && el; i++) {
                    const r = el.getBoundingClientRect();
                    if (r.width >= 8 && r.height >= 8) break;
                    el = el.parentElement;
                  }
                  if (!el) return false;
                  try {
                    el.scrollIntoView({ block: 'center', inline: 'nearest' });
                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    el.click();
                    return true;
                  } catch (e) { return false; }
                }""",
                name,
            )
        )
    except Exception:
        return False


def _infer_pack_prices_from_range(
    names: list[str], lo: float, hi: float
) -> dict[str, float]:
    """
    当页面展示 ¥低-高 且 高≈低×最大盒数时，按「单价×盒数」反推各档总价。
    例：860-4300 且有 1/3/5盒装 → 860/2580/4300。
    """
    packs: list[tuple[str, int]] = []
    for name in names:
        m = re.match(r"(\d+)", str(name))
        if not m:
            continue
        packs.append((str(name), int(m.group(1))))
    if len(packs) < 2 or lo <= 0 or hi <= lo:
        return {}
    max_n = max(n for _, n in packs)
    min_n = min(n for _, n in packs)
    # 高价 ≈ 单价 × 最大盒数（允许 2% 误差）
    unit = lo / min_n if min_n else lo
    expected_hi = unit * max_n
    if abs(expected_hi - hi) > max(1.0, unit * 0.02):
        return {}
    return {name: round(unit * n, 2) for name, n in packs}


def _read_price_range(page) -> list[float]:
    try:
        pair = page.evaluate(
            """() => {
              const raw = (document.body && document.body.innerText || '').replace(/\\u200b/g, '');
              const compact = raw.replace(/\\s+/g, '');
              let m = compact.match(/[¥￥](\\d+(?:\\.\\d{1,2})?)[-~～](\\d+(?:\\.\\d{1,2})?)/);
              if (!m) m = raw.match(/[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)\\s*[-~～]\\s*(\\d+(?:\\.\\d{1,2})?)/);
              if (!m) {
                const html = document.documentElement.innerHTML || '';
                m = html.match(/[¥￥]\\s*(\\d+(?:\\.\\d{1,2})?)\\s*[-~～]\\s*(\\d+(?:\\.\\d{1,2})?)/);
              }
              if (!m) return null;
              const lo = parseFloat(m[1]), hi = parseFloat(m[2]);
              if (!(hi > lo) || lo < 1) return null;
              return [String(lo), String(hi)];
            }"""
        )
        if pair and len(pair) >= 2:
            return [float(pair[0]), float(pair[1])]
    except Exception:
        pass
    return []


def _list_sku_option_names(page) -> list[str]:
    return (
        page.evaluate(
            """() => {
              const out = [];
              document.querySelectorAll('div,span,button,li,a,p').forEach(el => {
                const t = (el.innerText || '').replace(/\\s+/g,'').replace(/\\u200b/g,'').trim();
                if (!t || t.length > 16) return;
                const m = t.match(/^(\\d+(?:盒|件|瓶)装)/);
                if (!m) return;
                // 允许后面跟少量状态字，排除整段长文
                if (t.length > m[1].length + 8) return;
                out.push(m[1]);
              });
              const uniq = Array.from(new Set(out));
              uniq.sort((a, b) => (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0));
              return uniq.slice(0, 8);
            }"""
        )
        or []
    )


def _ensure_sku_panel_open(page, config: dict[str, Any]) -> None:
    """确保规格弹层打开（优先点立即购买/发起拼单，才会出现实时价）。"""
    try:
        opened = page.evaluate(
            """() => {
              const body = (document.body && document.body.innerText || '');
              if (/确认款式/.test(body) && /限量低价|[¥￥]\\s*\\d+/.test(body) && /\\d+盒装/.test(body.replace(/\\s+/g,''))) {
                return 'already';
              }
              const nodes = Array.from(document.querySelectorAll('div,span,a,button'));
              // 顺序很重要：立即购买/发起拼单才会弹出带价规格层
              const keys = ['立即购买', '发起拼单', '确认款式', '已选择', '请选择包装数量', '包装数量', '选择规格'];
              for (const key of keys) {
                for (const el of nodes) {
                  const t = (el.innerText || '').replace(/\\s+/g,' ').trim();
                  if (!t || t.length > 20) continue;
                  if (t !== key && !t.startsWith(key)) continue;
                  const r = el.getBoundingClientRect();
                  if (r.width < 8 || r.height < 8) continue;
                  if (r.top < 0 || r.top > (window.innerHeight || 900)) continue;
                  try { el.click(); return key; } catch (e) {}
                }
              }
              return '';
            }"""
        )
        if opened and opened != "already":
            pause(config, kind="action")
            time.sleep(0.6)
            logger.info("已打开规格弹层 via={}", opened)
    except Exception:
        pass


def _harvest_sku_prices_by_click(
    page, config: dict[str, Any], price_range: list | None = None
) -> list[dict[str, Any]]:
    """在规格弹层里逐个点 N盒装，读取弹层当前价（等价格变化）。"""
    _ensure_sku_panel_open(page, config)
    names = _list_sku_option_names(page)
    if not names:
        _ensure_sku_panel_open(page, config)
        time.sleep(0.5)
        names = _list_sku_option_names(page)
    logger.info("规格选项识别: {}", names or [])
    if not names:
        return []

    # 优先用详情解析时抓到的区间（点击后区间常消失）
    range_before: list[float] = []
    if isinstance(price_range, (list, tuple)) and len(price_range) >= 2:
        try:
            range_before = [float(price_range[0]), float(price_range[1])]
        except (TypeError, ValueError):
            range_before = []
    if not range_before:
        range_before = _read_price_range(page)
    if range_before:
        logger.info("多规格价格区间: {}-{}", range_before[0], range_before[1])

    net_prices: list[float] = []

    def on_response(resp) -> None:
        try:
            if resp.status != 200:
                return
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct and "text" not in ct and "javascript" not in ct:
                return
            body = resp.text()
            if not body or len(body) > 2_000_000:
                return
            if "price" not in body and "Price" not in body:
                return
            for m in re.finditer(
                r'"(?:sku_group_price|min_group_price|group_price|price|normal_price|activity_price)"\s*:\s*(\d+)',
                body,
            ):
                v = int(m.group(1))
                yuan = round(v / 100.0, 2) if v >= 1000 else float(v)
                if 1 <= yuan <= 200000:
                    net_prices.append(yuan)
        except Exception:
            return

    try:
        page.on("response", on_response)
    except Exception:
        pass

    rows: list[dict[str, Any]] = []
    if not range_before:
        range_before = _read_price_range(page)
    prev_price = _read_sku_panel_price(page)
    for name in names:
        try:
            net_prices.clear()
            if not _click_sku_option(page, name):
                logger.info("规格选项未点到: {}", name)
                continue
            # 等待弹层价刷新（短轮询）
            price_txt = ""
            for _ in range(12):
                time.sleep(0.22)
                cur = _read_sku_panel_price(page)
                if not cur:
                    continue
                price_txt = cur
                if prev_price and cur != prev_price:
                    break
                if not prev_price and cur:
                    time.sleep(0.25)
                    cur2 = _read_sku_panel_price(page)
                    if cur2:
                        price_txt = cur2
                    break

            # 弹层没变化时，尝试用本轮网络回包里新出现的价
            if (not price_txt or (prev_price and price_txt == prev_price)) and net_prices:
                diff = [p for p in net_prices if not prev_price or abs(p - float(prev_price)) > 0.01]
                pick = max(diff) if diff else max(net_prices)
                price_txt = str(pick)

            if price_txt:
                rows.append({"spec": name, "price": float(price_txt)})
                logger.info("规格点击采价 {} -> {} (prev={})", name, price_txt, prev_price or "-")
                prev_price = price_txt
            else:
                logger.info("规格点击采价 {} -> 未读到弹层价", name)
        except Exception as exc:
            logger.debug("规格 {} 点击失败: {}", name, exc)

    try:
        page.remove_listener("response", on_response)
    except Exception:
        pass

    def _range_now() -> list[float]:
        return _read_price_range(page) or range_before

    # 若全部同价：用页面「¥低-高」且高≈低×最大盒数时，按盒数反推总价
    priced = [r for r in rows if r.get("price") is not None]
    if len(priced) >= 2:
        vals = {round(float(r["price"]), 2) for r in priced}
        if len(vals) == 1:
            pr = _range_now()
            inferred = _infer_pack_prices_from_range(names, pr[0], pr[1]) if len(pr) >= 2 else {}
            if inferred and len(set(inferred.values())) > 1:
                logger.info("多规格点击同价，已按价格区间反推: {}", inferred)
                rows = [{"spec": k, "price": v} for k, v in inferred.items()]
            else:
                logger.warning(
                    "多规格采价全部相同 {}，未找到可反推区间；仅保留首个标价",
                    next(iter(vals)),
                )
                keep = priced[0]["spec"]
                for r in rows:
                    if r.get("spec") != keep:
                        r["price"] = None
    elif len(priced) <= 1:
        pr = _range_now()
        if len(pr) >= 2:
            inferred = _infer_pack_prices_from_range(names, pr[0], pr[1])
            if inferred and len(set(inferred.values())) > 1:
                logger.info("点击分档价不足，按价格区间反推: {}", inferred)
                rows = [{"spec": k, "price": v} for k, v in inferred.items()]
    return rows


def parse_detail_on_current_page(
    page,
    config: dict[str, Any],
    base: dict[str, Any] | None = None,
    fallback_url: str = "",
    network_bucket: list[Any] | None = None,
) -> dict[str, Any]:
    base = base or {}
    after_page_ready(page, config, purpose="detail")
    human_scroll(page, config, purpose="detail")
    pause(config, kind="read")

    own_bucket: list[Any] = []
    listener = None
    if network_bucket is None:
        # 点击进入详情时接口可能已结束，不再 reload（易跳登录），靠 DOM/脚本/列表价兜底
        network_bucket = own_bucket

    try:
        # 1) 点「查看全部 / 商品参数」拉剂型、厂家等
        page.evaluate(
            """() => {
              const nodes = Array.from(document.querySelectorAll('div,span,a,button,p'));
              for (const el of nodes) {
                const t = (el.innerText||'').replace(/\\s+/g,' ').trim();
                if (!t || t.length > 16) continue;
                if (/^(查看全部|商品参数|规格参数)$/.test(t) || t === '查看全部') {
                  try { el.click(); return t; } catch(e) {}
                }
              }
              // 弱匹配
              for (const el of nodes) {
                const t = (el.innerText||'').trim();
                if (t.includes('查看全部') && t.length < 12) {
                  try { el.click(); return t; } catch(e) {}
                }
              }
              return '';
            }"""
        )
        pause(config, kind="read")
        # 2) 再点规格/确认款式弹层
        page.evaluate(
            """() => {
              const nodes = Array.from(document.querySelectorAll('div,span,a,button'));
              const keys = ['已选择', '确认款式', '包装数量', '选择规格', '发起拼单', '立即购买'];
              for (const el of nodes) {
                const t = (el.innerText||'').replace(/\\s+/g,' ').trim();
                if (!t || t.length > 24) continue;
                if (keys.some(k => t.includes(k))) {
                  const r = el.getBoundingClientRect();
                  if (r.width < 8 || r.height < 8) continue;
                  try { el.click(); return t; } catch(e) {}
                }
              }
              return '';
            }"""
        )
        pause(config, kind="action")
        page.mouse.wheel(0, 300)
        pause(config, kind="read")
    except Exception:
        pass

    try:
        raw = page.evaluate(DETAIL_EXTRACT_JS) or {}
    except Exception as exc:
        logger.error("详情 JS 注入失败: {}", exc)
        raw = {}

    # 逐个点「N盒装」读取弹层价，补全多规格价格
    try:
        clicked_skus = _harvest_sku_prices_by_click(
            page, config, price_range=raw.get("price_range")
        )
        if clicked_skus:
            existing = {str(x.get("spec") or ""): x for x in (raw.get("sku_rows") or []) if isinstance(x, dict)}
            for row in clicked_skus:
                spec = str(row.get("spec") or "")
                if not spec:
                    continue
                # 点击采到的弹层价优先覆盖（页面元价更准）
                yuan = row.get("price")
                existing[spec] = {
                    "sku_id": (existing.get(spec) or {}).get("sku_id") or "",
                    "spec": spec,
                    "group_price_raw": None,
                    "normal_price_raw": f"¥{yuan}" if yuan not in (None, "") else None,
                }
            raw["sku_rows"] = list(existing.values())
            raw.setdefault("pack_specs_dom", [])
            for row in clicked_skus:
                if row.get("spec") and row["spec"] not in raw["pack_specs_dom"]:
                    raw["pack_specs_dom"].append(row["spec"])
            if clicked_skus and not raw.get("panel_price"):
                raw["panel_price"] = str(clicked_skus[0].get("price") or "")
            # 若无拼单语义，勿把点击价写进拼单候选
            if clicked_skus and not raw.get("has_group_buy"):
                raw["display_price"] = raw.get("display_price") or str(clicked_skus[0].get("price") or "")
    except Exception as exc:
        logger.debug("点击规格采价跳过: {}", exc)

    # 脚本标签兜底
    try:
        scripts = page.evaluate(
            """() => Array.from(document.scripts).map(s => s.textContent||'').filter(t =>
              t.includes('min_group_price') || t.includes('goods_name') || t.includes('rawData')
            ).slice(0, 6)"""
        ) or []
        import json as _json

        for sc in scripts:
            for m in re.finditer(r"window\.rawData\s*=\s*(\{[\s\S]*?\});?\s*(?:window\.|</script>)", sc[:500000]):
                try:
                    payload = _json.loads(m.group(1))
                    _merge_network_prices(raw, [payload])
                except Exception:
                    continue
            for m in re.finditer(
                r'"(?:min_group_price|sku_group_price|group_price)"\s*:\s*(\[.*?\]|\d+)',
                sc[:500000],
            ):
                chunk = m.group(1)
                try:
                    if chunk.startswith("["):
                        arr = _json.loads(chunk)
                        raw.setdefault("group_price_candidates", []).extend(arr)
                    else:
                        raw.setdefault("group_price_candidates", []).append(int(chunk))
                except Exception:
                    continue
    except Exception:
        pass

    _merge_network_prices(raw, network_bucket)

    if listener is not None:
        try:
            page.remove_listener("response", listener)
        except Exception:
            pass

    return _compose_detail(raw, base, fallback_url or page.url)


def _compose_detail(raw: dict[str, Any], base: dict[str, Any], item_url: str) -> dict[str, Any]:
    sell_name = (raw.get("sell_name") or "").strip()
    bad = {"拼多多", "拼多多商城", "登录", "login", "商品", "加载中"}
    if (not sell_name) or (sell_name in bad) or sell_name.endswith("商城"):
        sell_name = (base.get("title") or base.get("sell_name") or sell_name or "").strip()

    product_name = (raw.get("product_name") or "").strip() or sell_name
    snippet = str(raw.get("body_snippet") or "")

    # 1) 列表价
    list_price = None
    if base.get("price") not in (None, "", 0, 0.0):
        list_price = fen_to_yuan(base.get("price"), assume_fen=False)

    # 2) 详情展示价（大字价 / 弹层价）
    display_price = None
    if raw.get("display_price") not in (None, ""):
        try:
            display_price = float(raw.get("display_price"))
        except (TypeError, ValueError):
            display_price = fen_to_yuan(raw.get("display_price"), assume_fen=False)
    if display_price is None and raw.get("panel_price") not in (None, ""):
        try:
            display_price = float(raw.get("panel_price"))
        except (TypeError, ValueError):
            display_price = fen_to_yuan(raw.get("panel_price"), assume_fen=False)

    has_group_buy = bool(raw.get("has_group_buy")) or bool(
        re.search(r"发起拼单|拼单价|多人团", snippet)
    )
    has_single_buy = bool(raw.get("has_single_buy")) or bool(
        re.search(r"单独(?:购买|买)|单买价", snippet)
    )

    # 3) 拼单价：仅页面明确有拼单语义时才填
    group_price = None
    if has_group_buy:
        group_price = _pick_price(raw.get("group_price_candidates"))
        if group_price is None:
            m = re.search(r"(?:拼单价|发起拼单)[^0-9¥￥]{0,12}[¥￥]\s*(\d+(?:\.\d{1,2})?)", snippet)
            if m:
                group_price = float(m.group(1))
        if group_price is None and display_price is not None:
            group_price = display_price

    # 4) 单独购买价：仅有单独买语义时才填
    single_price = None
    if has_single_buy:
        single_price = _pick_price(raw.get("single_price_candidates"))
        if single_price is None:
            single_price = _pick_price(raw.get("single_dom_prices"), prefer_fen=False)
        if single_price is None:
            m = re.search(
                r"单独(?:购买|买)[^0-9¥￥]{0,12}[¥￥]\s*(\d+(?:\.\d{1,2})?)",
                snippet,
            ) or re.search(
                r"[¥￥]\s*(\d+(?:\.\d{1,2})?)[^。\n]{0,10}单独(?:购买|买)",
                snippet,
            )
            if m:
                single_price = float(m.group(1))

    # 单独购买价识别不出时：用详情价（与 App DetailReader 约定一致）
    deal_price = single_price if single_price is not None else display_price
    original = _pick_price(raw.get("original_candidates"))
    if original is None and raw.get("restore_price") not in (None, ""):
        try:
            original = float(raw.get("restore_price"))
        except (TypeError, ValueError):
            original = fen_to_yuan(raw.get("restore_price"), assume_fen=False)

    # 5) 销量：商品销 / 店铺销
    sales_num = parse_sales_num(raw.get("sales_raw"))
    shop_sales_num = parse_sales_num(raw.get("shop_sales_raw"))
    if not sales_num and base.get("sales_num"):
        sales_num = int(base.get("sales_num") or 0)
    if not shop_sales_num and base.get("shop_sales_num"):
        shop_sales_num = int(base.get("shop_sales_num") or 0)

    images = raw.get("main_images") or []
    if isinstance(images, str):
        images = [images]
    images = [u for u in images if u and "share_logo" not in str(u)]
    if not images and base.get("main_images"):
        images = list(base.get("main_images") or [])

    approval = _clean_approval(str(raw.get("approval_no") or ""))
    if not approval and raw.get("body_snippet"):
        approval = _clean_approval(str(raw.get("body_snippet")))

    spec = (raw.get("spec") or "").strip()
    manufacturer = str(raw.get("manufacturer") or "").strip()
    brand = str(raw.get("brand") or "").strip()
    dosage_form = str(raw.get("dosage_form") or "").strip()
    expiry = str(raw.get("expiry") or "").strip()
    category = str(raw.get("category") or "").strip()
    coupon_info = str(raw.get("coupon_info") or "").strip()
    shop_name = str(raw.get("shop_name") or base.get("shop_name") or "").strip()
    shop_id = str(raw.get("shop_id") or base.get("shop_id") or "").strip()
    # 去掉粘在店名上的「已拼/销量」尾巴
    if shop_name:
        shop_name = re.split(r"\s*(?:已拼|销量|人付款|评价|全店总售)", shop_name)[0].strip()
        shop_name = re.sub(r"[\d.]+万?\+?\s*$", "", shop_name).strip()
        shop_name = re.sub(r"\s*本店\s*$", "", shop_name).strip()
    comment_num = parse_sales_num(raw.get("comment_raw"))

    for p in raw.get("props") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "")
        val = str(p.get("value") or "").strip()
        if not val:
            continue
        if not spec and "规格" in name:
            spec = val
        if not approval and ("国药准字" in name or "批准文号" in name):
            approval = _clean_approval(val)
        if ("通用名称" in name or "商品名称" in name or name in ("名称", "药品名称")) and val:
            product_name = val
        if not manufacturer and any(k in name for k in ("生产厂家", "生产企业", "上市许可持有人", "制造商")):
            manufacturer = val
        if not brand and "品牌" in name:
            brand = val
        if not dosage_form and "剂型" in name:
            dosage_form = val
        if not expiry and ("有效期" in name or "保质期" in name):
            expiry = val

    if not shop_name:
        snippet = str(raw.get("body_snippet") or "")
        m = re.search(r"([^\n]{2,28}(?:旗舰店|专营店|专卖店|大药房|药店|药房))", snippet)
        if m:
            shop_name = m.group(1).strip()
        if not shop_name:
            m2 = re.search(r"^【([^】]{2,20})】", sell_name)
            if m2 and any(k in m2.group(1) for k in ("店", "药房", "药业", "旗舰")):
                shop_name = m2.group(1)

    if not manufacturer:
        m = re.search(
            r"(?:生产厂家|生产企业|上市许可持有人)[:：]\s*([^\n]{2,60})",
            str(raw.get("body_snippet") or ""),
        )
        if m:
            manufacturer = m.group(1).strip()
    if not dosage_form:
        m = re.search(
            r"(?:产品剂型|剂型)[:：]\s*([^\n]{1,20})",
            str(raw.get("body_snippet") or ""),
        )
        if m:
            dosage_form = re.split(
                r"\s*(?:生产|品牌|批准|有效期|保质期|规格|通用)",
                m.group(1).strip(),
            )[0].strip()

    if not spec:
        spec = _extract_spec(sell_name) or _extract_spec(str(raw.get("body_snippet") or ""))
    if not spec:
        m = re.search(
            r"(\d+(?:\.\d+)?\s*(?:mg|g|ml|%|克)\s*[*＊×xX:：]?\s*\d*\s*(?:片|粒|丸|袋|盒|支|瓶)?(?:/[^\s，,]{0,8})?)",
            sell_name,
            flags=re.I,
        )
        if m:
            spec = re.sub(r"\s+", "", m.group(1))

    sku_prices, sku_prices_text = _format_sku_prices(raw)
    restore_price = None
    if raw.get("restore_price") not in (None, ""):
        try:
            restore_price = float(raw.get("restore_price"))
        except (TypeError, ValueError):
            restore_price = fen_to_yuan(raw.get("restore_price"), assume_fen=False)

    logger.info(
        "详情字段汇总 id={} 店={} 列表价={} 展示价={} 拼单价={} 单独购买={} 销量={} 店销={} 规格={} 准字={} SKU数={}",
        raw.get("item_id") or base.get("item_id"),
        shop_name or "-",
        list_price,
        display_price,
        group_price,
        deal_price,
        sales_num,
        shop_sales_num,
        spec or "-",
        approval or "-",
        len(sku_prices),
    )

    return {
        "item_id": str(raw.get("item_id") or base.get("item_id") or ""),
        "sell_name": sell_name,
        "title": sell_name,
        "product_name": product_name,
        "sales_num": sales_num,
        "shop_sales_num": shop_sales_num,
        "comment_num": comment_num,
        "spec": spec,
        "approval_no": approval,
        "group_price": group_price,
        "deal_price": deal_price,
        "display_price": display_price,
        "price": list_price,
        "original_price": original if original is not None else restore_price,
        "main_images": images,
        "shop_name": shop_name,
        "shop_id": shop_id,
        "manufacturer": manufacturer,
        "brand": brand,
        "dosage_form": dosage_form,
        "expiry": expiry,
        "category": category,
        "coupon_info": coupon_info,
        "sku_prices": sku_prices,
        "sku_prices_text": sku_prices_text,
        "spec_list": raw.get("props") or [],
        "item_url": raw.get("page_url") or item_url,
        "update_time": datetime.now().isoformat(timespec="seconds"),
        "pick_tag": base.get("pick_tag") or "",
        "pick_label": base.get("pick_label") or "",
    }


def parse_detail(page, item_url: str, config: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    base = base or {}
    logger.info("打开详情页 {}", item_url)
    before_navigate(config)
    network_bucket: list[Any] = []
    listener = _attach_price_listener(page, network_bucket)
    page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    try:
        detail = parse_detail_on_current_page(
            page, config, base=base, fallback_url=item_url, network_bucket=network_bucket
        )
    finally:
        try:
            page.remove_listener("response", listener)
        except Exception:
            pass
    return detail
