"""任务调度：start / pause / stop，关键词队列 + 列表/详情/过滤/落库。"""

from __future__ import annotations

import threading
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from playwright.sync_api import sync_playwright

from browser_client import BrowserClient
from detail_parser import _extract_spec, parse_detail, parse_detail_on_current_page
from excel_target import (
    clean_and_rank_candidates,
    file_sha1,
    load_excel_targets,
    match_double,
)
from filter_handler import pass_filter
from human_behavior import between_items, between_keywords, pause
from list_parser import extract_list_on_current_page, parse_search_list
from search_sort import (
    collect_first_after_sort,
    collect_top_n_default,
    ensure_default_sort,
    open_search_page,
)
from storage_exporter import StorageExporter


def _friendly_net_error(exc: BaseException) -> str:
    text = str(exc)
    if "ERR_SOCKS_CONNECTION_FAILED" in text or "SOCKS" in text.upper():
        return (
            "BitBrowser 环境的 SOCKS 代理连接失败。"
            "请到比特浏览器 → 该窗口代理设置：关闭代理，或换成可用代理后重试。"
            "也可先在该窗口手动打开 https://mobile.yangkeduo.com 验证能否上网。"
        )
    if "ERR_PROXY_CONNECTION_FAILED" in text or "ERR_TUNNEL_CONNECTION_FAILED" in text:
        return "代理隧道失败，请检查 BitBrowser 窗口的代理地址/账号密码是否有效。"
    if "ERR_NAME_NOT_RESOLVED" in text:
        return "DNS 解析失败，请检查本机/代理网络。"
    if "ERR_CONNECTION" in text or "net::ERR_" in text:
        return f"网络错误：{text.split(chr(10))[0]}"
    return text


class TaskState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSE = "pause"
    STOP = "stop"


# Explicit compatibility mapping. The desktop database remains isolated from
# the server while its production role is UNKNOWN (T003 analysis section 7).
DESKTOP_SERVER_STATUS_MAP = {
    "running": "running",
    "pause": "running",
    "paused": "running",
    "stop": "cancelled",
    "stopped": "cancelled",
    "finished": "complete",
    "failed": "failed",
    "interrupted": "failed",
}


def map_desktop_status_to_server(status: str) -> str:
    try:
        return DESKTOP_SERVER_STATUS_MAP[status]
    except KeyError as exc:
        raise ValueError(f"unknown desktop task status: {status}") from exc


LogCallback = Callable[[str], None]


class TaskRunner:
    def __init__(
        self,
        config: dict,
        storage: StorageExporter,
        log_cb: LogCallback | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.log_cb = log_cb or (lambda m: None)
        self.state = TaskState.IDLE
        self._thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_flag = threading.Event()
        self.current_task_id: Optional[int] = None
        self._task_type = ""

    def _emit(self, msg: str) -> None:
        logger.info(msg)
        try:
            self.log_cb(msg)
        except Exception:
            pass

    def start_task(self, keywords: list[str], task_name: str = "采集任务") -> None:
        if self.state == TaskState.RUNNING:
            self._emit("任务正在运行中")
            return
        kws = [k.strip() for k in keywords if k.strip()]
        if not kws:
            self._emit("请先输入关键词")
            return

        self._stop_flag.clear()
        self._pause_event.set()
        self.state = TaskState.RUNNING
        self._task_type = "normal"
        self._thread = threading.Thread(target=self._run, args=(kws, task_name), daemon=True)
        self._thread.start()

    def pause_task(self) -> None:
        if self.state != TaskState.RUNNING:
            return
        self.state = TaskState.PAUSE
        self._pause_event.clear()
        self._emit("任务已暂停")

    def resume_task(self) -> None:
        if self.state != TaskState.PAUSE:
            return
        self.state = TaskState.RUNNING
        self._pause_event.set()
        self._emit("任务继续")

    def stop_task(self) -> None:
        self.state = TaskState.STOP
        self._stop_flag.set()
        self._pause_event.set()
        self._emit("正在停止任务…")

    def _wait_if_paused(self) -> None:
        while not self._pause_event.is_set():
            if self._stop_flag.is_set():
                return
            self._pause_event.wait(0.2)

    def _open_detail_human(self, page, item: dict) -> dict:
        """若已点击进入则直接解析；否则直达 URL。"""
        url = item.get("item_url") or ""
        if item.get("entered_by_click"):
            return parse_detail_on_current_page(page, self.config, base=item, fallback_url=url)
        if not url and item.get("item_id"):
            url = f"https://mobile.yangkeduo.com/goods.html?goods_id={item['item_id']}"
        if not url:
            raise RuntimeError("无商品链接可打开")
        return parse_detail(page, url, self.config, base=item)

    def _save_detail(self, page, kw: str, goods: dict, task_id: int, label: str) -> str:
        self._emit(f"【{kw}】打开详情：{label} id={goods.get('item_id')} {str(goods.get('title') or '')[:28]}")
        if not goods.get("entered_by_click"):
            self._emit("直达详情 URL（拟人节奏）")
        detail = self._open_detail_human(page, goods)
        if not detail.get("item_id") and not detail.get("sell_name") and not detail.get("title"):
            raise RuntimeError("详情无有效字段")
        detail["pick_tag"] = goods.get("pick_tag")
        detail["pick_label"] = goods.get("pick_label") or label
        pause(self.config, kind="action")
        self.storage.save_product(task_id, detail, keyword=kw)
        msg = (
            f"成功【{label}】id={detail.get('item_id')} "
            f"售卖名={str(detail.get('sell_name') or '')[:24]} "
            f"列表价={detail.get('price')} 展示价={detail.get('display_price')} "
            f"拼单价={detail.get('group_price')} 单独购买={detail.get('deal_price')} "
            f"销量={detail.get('sales_num')} 店销={detail.get('shop_sales_num')} "
            f"国药准字={detail.get('approval_no') or '-'} "
            f"规格={detail.get('spec') or '-'} 图={len(detail.get('main_images') or [])}"
        )
        self._emit(msg)
        return msg

    def _collect_default_top_n(self, page, kw: str, task_id: int) -> tuple[int, int]:
        """普通模式：综合排序前 N 个。返回 (成功数, 失败数)。"""
        n = int(self.config.get("max_detail_per_keyword") or 8)
        self._emit(f"【{kw}】普通模式：综合排序，采集前 {n} 个")
        goods_list = collect_top_n_default(page, kw, self.config)
        ok_n = fail_n = 0
        retries = int(self.config.get("retry_times") or 2)
        for idx, goods in enumerate(goods_list):
            if self._stop_flag.is_set():
                break
            self._wait_if_paused()
            if self._stop_flag.is_set():
                break
            label = goods.get("pick_label") or f"综合排序-第{idx + 1}个"
            last_err = None
            done = False
            for attempt in range(1, retries + 1):
                try:
                    self._save_detail(page, kw, goods, task_id, label)
                    ok_n += 1
                    done = True
                    break
                except Exception as exc:
                    last_err = exc
                    self._emit(
                        f"采集失败 mode=default idx={idx + 1} attempt={attempt}/{retries} "
                        f"err={_friendly_net_error(exc)}"
                    )
                    pause(self.config, kind="idle")
                    if "SOCKS" in str(exc).upper() or "PROXY" in str(exc).upper():
                        self._emit("代理故障，终止任务")
                        self._stop_flag.set()
                        break
            if not done:
                fail_n += 1
                self._emit(f"本条失败 {label} last_err={last_err}")
            if idx < len(goods_list) - 1 and not self._stop_flag.is_set():
                between_items(self.config)
        return ok_n, fail_n

    def _collect_one_sorted(self, page, kw: str, sort_mode: str, task_id: int) -> tuple[bool, str]:
        """可选：价格升序 / 销量降序 → 第 1 个详情。"""
        label = "价格从低到高-第1个" if sort_mode == "price_asc" else "销量从高到低-第1个"
        self._emit(f"【{kw}】增强模式：{label}")
        goods = collect_first_after_sort(page, kw, self.config, sort_mode=sort_mode, reopen_search=True)
        msg = self._save_detail(page, kw, goods, task_id, label)
        return True, msg

    def _mode_summary(self) -> str:
        parts = ["普通=综合前N"]
        if self.config.get("enable_price_sort"):
            parts.append("价格升序第1")
        if self.config.get("enable_sales_sort"):
            parts.append("销量降序第1")
        return "+".join(parts)

    def _run(self, keywords: list[str], task_name: str) -> None:
        task_id = self.storage.create_task(task_name, keywords)
        self.current_task_id = task_id
        total = success = fail = 0
        browser_api = BrowserClient(
            self.config.get("bitbrowser_api_url", "http://127.0.0.1:54345"),
            self.config.get("bitbrowser_group_id", ""),
            force_direct=bool(self.config.get("force_direct", True)),
        )
        env_id = None
        pw = None
        browser = None
        context = None

        try:
            if not browser_api.health():
                self._emit("BitBrowser API 不可用，请确认比特浏览器已启动且本地 API 开启")
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="failed")
                self.state = TaskState.IDLE
                return

            env_id = browser_api.get_available_env()
            if not env_id:
                self._emit("没有可用隔离环境，请先在 BitBrowser 创建浏览器窗口")
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="failed")
                self.state = TaskState.IDLE
                return

            ws = browser_api.connect_env(env_id)
            if not ws:
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="failed")
                self.state = TaskState.IDLE
                return
            if browser_api.force_direct:
                self._emit("已强制该窗口直连（关闭 SOCKS/HTTP 代理），避免代理失效无法访问")

            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            level = self.config.get("human_level", "strict")
            self._emit(
                f"任务启动 task_id={task_id} 关键词数={len(keywords)} 拟人档位={level} "
                f"规则={self._mode_summary()}"
            )

            for idx, kw in enumerate(keywords):
                if self._stop_flag.is_set():
                    break
                self._wait_if_paused()
                if self._stop_flag.is_set():
                    break

                if idx > 0:
                    self._emit("关键词间隙休息（拟人）…")
                    between_keywords(self.config)

                self._emit(f"======= 开始关键词：{kw} =======")

                # 1) 普通模式：综合排序前 N（始终执行）
                n_cfg = max(1, int(self.config.get("max_detail_per_keyword") or 8))
                total += n_cfg
                try:
                    ok_n, fail_n = self._collect_default_top_n(page, kw, task_id)
                    success += ok_n
                    fail += fail_n
                    # total 按实际尝试条数更准
                    total = total - n_cfg + ok_n + fail_n
                except Exception as exc:
                    fail += 1
                    total = total - n_cfg + 1
                    self._emit(f"普通模式失败 err={_friendly_net_error(exc)}")

                # 2) 可选：价格排序第1
                if self.config.get("enable_price_sort") and not self._stop_flag.is_set():
                    self._emit("拟人休息后执行：价格升序…")
                    between_items(self.config)
                    total += 1
                    retries = int(self.config.get("retry_times") or 2)
                    ok = False
                    last_err = None
                    for attempt in range(1, retries + 1):
                        try:
                            self._collect_one_sorted(page, kw, "price_asc", task_id)
                            success += 1
                            ok = True
                            break
                        except Exception as exc:
                            last_err = exc
                            self._emit(
                                f"采集失败 mode=price_asc attempt={attempt}/{retries} "
                                f"err={_friendly_net_error(exc)}"
                            )
                            pause(self.config, kind="idle")
                    if not ok:
                        fail += 1
                        self._emit(f"本轮失败 mode=price_asc last_err={last_err}")

                # 3) 可选：销量排序第1
                if self.config.get("enable_sales_sort") and not self._stop_flag.is_set():
                    self._emit("拟人休息后执行：销量降序…")
                    between_items(self.config)
                    total += 1
                    retries = int(self.config.get("retry_times") or 2)
                    ok = False
                    last_err = None
                    for attempt in range(1, retries + 1):
                        try:
                            self._collect_one_sorted(page, kw, "sales_desc", task_id)
                            success += 1
                            ok = True
                            break
                        except Exception as exc:
                            last_err = exc
                            self._emit(
                                f"采集失败 mode=sales_desc attempt={attempt}/{retries} "
                                f"err={_friendly_net_error(exc)}"
                            )
                            pause(self.config, kind="idle")
                    if not ok:
                        fail += 1
                        self._emit(f"本轮失败 mode=sales_desc last_err={last_err}")

            status = "stopped" if self._stop_flag.is_set() else "finished"
            self.storage.finish_task(task_id, total=total, success=success, fail=fail, status=status)
            self._emit(f"任务结束 status={status} total={total} success={success} fail={fail}")
        except Exception as exc:
            logger.exception("任务异常")
            self._emit(f"任务异常: {exc}")
            self.storage.finish_task(task_id, total=total, success=success, fail=fail, status="failed")
        finally:
            self._cleanup_browser(browser_api, env_id, pw, browser)
            self.state = TaskState.IDLE
            self._task_type = ""

    def _cleanup_browser(self, browser_api, env_id, pw, browser) -> None:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass
        try:
            browser_api.close_env(env_id)
        except Exception:
            pass
        try:
            browser_api.close()
        except Exception:
            pass

    # ---------- Excel 靶标模式 ----------

    def start_excel_task(self, excel_path: str, resume_task_id: int | None = None) -> None:
        if self.state == TaskState.RUNNING:
            self._emit("任务正在运行中")
            return
        if not resume_task_id and not excel_path:
            self._emit("请先选择 Excel 文件")
            return
        self._stop_flag.clear()
        self._pause_event.set()
        self.state = TaskState.RUNNING
        self._task_type = "excel_target"
        self._thread = threading.Thread(
            target=self._run_excel,
            args=(excel_path, resume_task_id),
            daemon=True,
        )
        self._thread.start()

    def _run_excel(self, excel_path: str, resume_task_id: int | None = None) -> None:
        task_id = 0
        total = success = fail = 0
        browser_api = BrowserClient(
            self.config.get("bitbrowser_api_url", "http://127.0.0.1:54345"),
            self.config.get("bitbrowser_group_id", ""),
            force_direct=bool(self.config.get("force_direct", True)),
        )
        env_id = None
        pw = None
        browser = None

        try:
            if resume_task_id:
                task_id = int(resume_task_id)
                self.current_task_id = task_id
                meta = self.storage.get_excel_task_meta(task_id)
                if not meta:
                    self._emit(f"找不到可续跑的 Excel 任务 task_id={task_id}")
                    self.state = TaskState.IDLE
                    return
                self.storage.reset_running_excel_rows(task_id)
                pending = self.storage.list_excel_rows(
                    task_id, statuses=["pending", "error"]
                )
                self.storage.set_task_status(task_id, "running")
                self._emit(
                    f"续跑 Excel 任务 task_id={task_id} 剩余行={len(pending)} "
                    f"文件={meta.get('excel_path')}"
                )
            else:
                targets = load_excel_targets(excel_path)
                kws = [t["keyword"] for t in targets]
                task_id = self.storage.create_task(
                    f"Excel靶标-{Path(excel_path).name}",
                    kws,
                    task_type="excel_target",
                )
                self.current_task_id = task_id
                self.storage.create_excel_checkpoint(
                    task_id, str(excel_path), file_sha1(excel_path), targets
                )
                pending = self.storage.list_excel_rows(task_id, statuses=["pending"])
                self._emit(
                    f"Excel 靶标任务启动 task_id={task_id} 总行={len(pending)} "
                    f"规则=清洗优选+规格准字双过+命中即停"
                )

            if not pending:
                self._emit("没有待处理行，任务结束")
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="finished")
                self.state = TaskState.IDLE
                return

            if not browser_api.health():
                self._emit("BitBrowser API 不可用，请确认比特浏览器已启动且本地 API 开启")
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="interrupted")
                self.state = TaskState.IDLE
                return

            env_id = browser_api.get_available_env()
            if not env_id:
                self._emit("没有可用隔离环境，请先在 BitBrowser 创建浏览器窗口")
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="interrupted")
                self.state = TaskState.IDLE
                return

            ws = browser_api.connect_env(env_id)
            if not ws:
                self.storage.finish_task(task_id, total=0, success=0, fail=0, status="interrupted")
                self.state = TaskState.IDLE
                return
            if browser_api.force_direct:
                self._emit("已强制该窗口直连（关闭 SOCKS/HTTP 代理），避免代理失效无法访问")

            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            for i, row in enumerate(pending):
                if self._stop_flag.is_set():
                    break
                self._wait_if_paused()
                if self._stop_flag.is_set():
                    break

                if i > 0:
                    self._emit("关键词间隙休息（拟人）…")
                    between_keywords(self.config)

                total += 1
                row_index = int(row["row_index"])
                kw = row["keyword"]
                target_spec = row["target_spec"]
                target_approval = row["target_approval"]
                self.storage.update_excel_row(task_id, row_index, status="running", message="执行中")
                self._emit(
                    f"======= Excel行#{row_index} 关键词={kw} 规格={target_spec} "
                    f"准字={target_approval} ======="
                )
                try:
                    hit, msg, item_id = self._process_excel_row(
                        page, kw, target_spec, target_approval, task_id
                    )
                    if hit:
                        success += 1
                        self.storage.update_excel_row(
                            task_id, row_index, status="hit", item_id=item_id, message=msg
                        )
                        self._emit(f"【命中】{kw} → {msg}")
                    else:
                        fail += 1
                        self.storage.update_excel_row(
                            task_id, row_index, status="miss", item_id="", message=msg
                        )
                        self._emit(f"【未命中】{kw} → {msg}")
                except Exception as exc:
                    fail += 1
                    err = _friendly_net_error(exc)
                    self.storage.update_excel_row(
                        task_id, row_index, status="error", message=err
                    )
                    self._emit(f"【异常】{kw} err={err}")
                    if "SOCKS" in str(exc).upper() or "PROXY" in str(exc).upper():
                        self._emit("代理故障，中断任务（可稍后续跑）")
                        self._stop_flag.set()
                        break

            status = "interrupted" if self._stop_flag.is_set() else "finished"
            # 若还有 pending 也算 interrupted
            left = self.storage.list_excel_rows(task_id, statuses=["pending", "running", "error"])
            if left and status == "finished":
                status = "interrupted"
            self.storage.finish_task(task_id, total=total, success=success, fail=fail, status=status)
            self._emit(f"Excel任务结束 status={status} total={total} hit={success} miss/fail={fail}")
        except Exception as exc:
            logger.exception("Excel 任务异常")
            self._emit(f"Excel 任务异常: {exc}")
            if task_id:
                self.storage.finish_task(
                    task_id, total=total, success=success, fail=fail, status="interrupted"
                )
        finally:
            self._cleanup_browser(browser_api, env_id, pw, browser)
            self.state = TaskState.IDLE
            self._task_type = ""

    def _process_excel_row(
        self,
        page,
        keyword: str,
        target_spec: str,
        target_approval: str,
        task_id: int,
    ) -> tuple[bool, str, str]:
        """
        搜关键词 → 清洗排序列表 → 依次进详情双过匹配 → 命中即停。
        返回 (是否命中, 说明, item_id)
        """
        open_search_page(page, keyword, self.config)
        ensure_default_sort(page, self.config)
        items = extract_list_on_current_page(page, self.config)
        if not items:
            items = parse_search_list(page, keyword, self.config)

        filtered = [x for x in items if pass_filter(x, self.config)]
        ranked = clean_and_rank_candidates(filtered, keyword, target_spec, self.config)
        n = int(self.config.get("max_detail_per_keyword") or 8)
        if n <= 0:
            n = len(ranked)
        candidates = ranked[:n]
        if not candidates:
            return False, "清洗后无候选商品", ""

        self._emit(f"【{keyword}】候选 {len(candidates)} 个（清洗后），开始逐个进详情匹配")
        retries = int(self.config.get("retry_times") or 2)
        last_reason = "候选均未双过"

        for idx, goods in enumerate(candidates):
            if self._stop_flag.is_set():
                return False, "任务已停止", ""
            self._wait_if_paused()
            if self._stop_flag.is_set():
                return False, "任务已停止", ""

            title = str(goods.get("title") or "")[:36]
            self._emit(f"尝试详情 {idx + 1}/{len(candidates)} id={goods.get('item_id')} {title}")
            goods = dict(goods)
            goods["entered_by_click"] = False
            if goods.get("item_id"):
                goods["item_url"] = (
                    f"https://mobile.yangkeduo.com/goods.html?goods_id={goods['item_id']}"
                )

            detail = None
            for attempt in range(1, retries + 1):
                try:
                    detail = self._open_detail_human(page, goods)
                    break
                except Exception as exc:
                    self._emit(f"详情失败 attempt={attempt}/{retries} err={_friendly_net_error(exc)}")
                    pause(self.config, kind="idle")
            if not detail:
                last_reason = "详情打开失败"
                continue

            got_spec = (detail.get("spec") or "").strip()
            if not got_spec:
                got_spec = _extract_spec(str(detail.get("sell_name") or detail.get("title") or ""))
            got_approval = (detail.get("approval_no") or "").strip()
            ok, reason = match_double(got_spec, got_approval, target_spec, target_approval)
            self._emit(
                f"匹配结果: {reason} | 得规格={got_spec or '-'} 得准字={got_approval or '-'}"
            )
            if ok:
                detail["pick_tag"] = "excel_double_hit"
                detail["pick_label"] = f"Excel双过-第{idx + 1}候选"
                detail["spec"] = got_spec or detail.get("spec")
                detail["approval_no"] = got_approval or detail.get("approval_no")
                self.storage.save_product(task_id, detail, keyword=keyword)
                return True, f"双过命中 id={detail.get('item_id')} {reason}", str(
                    detail.get("item_id") or ""
                )
            last_reason = reason
            if idx < len(candidates) - 1:
                between_items(self.config)

        return False, last_reason, ""
