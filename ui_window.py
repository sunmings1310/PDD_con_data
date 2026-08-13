"""PyQt6 主界面。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config_manager import ConfigManager
from storage_exporter import StorageExporter
from task_runner import TaskRunner, TaskState
from utils import ROOT


class MainWindow(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("平台数据采集工作台（拟人节奏加强版）")
        self.resize(1180, 760)

        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load()
        self.storage = StorageExporter(output_dir=self.config_mgr.abs_output_dir())
        self.runner = TaskRunner(self.config, self.storage, log_cb=self.log_signal.emit)
        self.log_signal.connect(self.append_log)

        self._build_ui()
        self._load_config_to_ui()
        self.refresh_tasks()
        self.refresh_resumable()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_state)
        self._timer.start(1000)
        self._last_runner_state = TaskState.IDLE

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        splitter.addWidget(left)

        # 配置区
        cfg_box = QGroupBox("配置")
        cfg_form = QFormLayout(cfg_box)
        self.api_url = QLineEdit()
        self.output_dir = QLineEdit()
        btn_out = QPushButton("选择目录")
        btn_out.clicked.connect(self.choose_output_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_dir)
        out_row.addWidget(btn_out)
        self.delay_min = QSpinBox()
        self.delay_min.setRange(200, 60000)
        self.delay_max = QSpinBox()
        self.delay_max.setRange(200, 60000)
        self.retry_times = QSpinBox()
        self.retry_times.setRange(1, 10)
        self.scroll_times = QSpinBox()
        self.scroll_times.setRange(1, 50)
        self.human_level = QComboBox()
        self.human_level.addItems(["gentle", "normal", "strict"])
        self.max_detail = QSpinBox()
        self.max_detail.setRange(0, 100)
        self.max_detail.setToolTip("每个关键词最多进详情条数，0=不限制；建议先用 5~8")
        cfg_form.addRow("BitBrowser API", self.api_url)
        cfg_form.addRow("输出目录", out_row)
        cfg_form.addRow("拟人档位", self.human_level)
        cfg_form.addRow("动作延时最小(ms)", self.delay_min)
        cfg_form.addRow("动作延时最大(ms)", self.delay_max)
        cfg_form.addRow("每词最多详解", self.max_detail)
        cfg_form.addRow("失败重试", self.retry_times)
        cfg_form.addRow("列表滚动基准", self.scroll_times)
        left_layout.addWidget(cfg_box)

        # 采集模式
        mode_box = QGroupBox("采集模式")
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.addWidget(
            QLabel("普通模式（始终开启）：搜索后按综合排序，采集前 N 个商品")
        )
        self.chk_price_sort = QCheckBox("额外：按价格升序采集第 1 个（勾选才开）")
        self.chk_sales_sort = QCheckBox("额外：按销量降序采集第 1 个（勾选才开）")
        mode_layout.addWidget(self.chk_price_sort)
        mode_layout.addWidget(self.chk_sales_sort)
        left_layout.addWidget(mode_box)

        # 过滤
        flt_box = QGroupBox("过滤规则")
        flt_form = QFormLayout(flt_box)
        self.price_min = QSpinBox()
        self.price_min.setRange(0, 999999)
        self.price_max = QSpinBox()
        self.price_max.setRange(0, 999999)
        self.sales_min = QSpinBox()
        self.sales_min.setRange(0, 99999999)
        self.black_words = QTextEdit()
        self.black_words.setPlaceholderText("黑名单词，一行一个")
        self.black_words.setFixedHeight(70)
        self.skip_shop = QCheckBox("跳过无店铺名商品")
        flt_form.addRow("最低价", self.price_min)
        flt_form.addRow("最高价", self.price_max)
        flt_form.addRow("最低销量", self.sales_min)
        flt_form.addRow("黑名单词", self.black_words)
        flt_form.addRow("", self.skip_shop)
        left_layout.addWidget(flt_box)

        # 关键词（普通模式）
        kw_box = QGroupBox("普通模式：关键词（一行一个）")
        kw_layout = QVBoxLayout(kw_box)
        self.keywords = QTextEdit()
        self.keywords.setPlaceholderText(
            "一行一个关键词\n默认：综合排序采前 N 个；可勾选额外价格/销量第1个"
        )
        kw_layout.addWidget(self.keywords)
        left_layout.addWidget(kw_box)

        # Excel 靶标模式
        excel_box = QGroupBox("Excel 靶标模式（新版）")
        excel_layout = QVBoxLayout(excel_box)
        excel_layout.addWidget(
            QLabel("列：关键词 | 规格 | 国药准字；双过匹配，命中即停，可断点续跑")
        )
        self.excel_path = QLineEdit()
        self.excel_path.setPlaceholderText("选择含三列的 Excel…")
        btn_excel = QPushButton("选择 Excel")
        btn_excel.clicked.connect(self.choose_excel)
        btn_tpl = QPushButton("生成模板")
        btn_tpl.clicked.connect(self.make_excel_template)
        excel_row = QHBoxLayout()
        excel_row.addWidget(self.excel_path)
        excel_row.addWidget(btn_excel)
        excel_row.addWidget(btn_tpl)
        excel_layout.addLayout(excel_row)
        self.resume_combo = QComboBox()
        self.resume_combo.setMinimumWidth(200)
        btn_refresh_resume = QPushButton("刷新可续跑")
        btn_refresh_resume.clicked.connect(self.refresh_resumable)
        resume_row = QHBoxLayout()
        resume_row.addWidget(QLabel("可续跑任务"))
        resume_row.addWidget(self.resume_combo, stretch=1)
        resume_row.addWidget(btn_refresh_resume)
        excel_layout.addLayout(resume_row)
        excel_btn_row = QHBoxLayout()
        self.btn_start_excel = QPushButton("启动 Excel 靶标")
        self.btn_resume_excel = QPushButton("续跑选中任务")
        self.btn_start_excel.clicked.connect(self.on_start_excel)
        self.btn_resume_excel.clicked.connect(self.on_resume_excel)
        excel_btn_row.addWidget(self.btn_start_excel)
        excel_btn_row.addWidget(self.btn_resume_excel)
        excel_layout.addLayout(excel_btn_row)
        left_layout.addWidget(excel_box)

        # 按钮
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("启动普通任务")
        self.btn_pause = QPushButton("暂停")
        self.btn_stop = QPushButton("停止")
        self.btn_export = QPushButton("导出数据")
        self.btn_save_cfg = QPushButton("保存配置")
        self.btn_start.clicked.connect(self.on_start)
        self.btn_pause.clicked.connect(self.on_pause)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_export.clicked.connect(self.on_export)
        self.btn_save_cfg.clicked.connect(self.on_save_config)
        for b in (self.btn_start, self.btn_pause, self.btn_stop, self.btn_export, self.btn_save_cfg):
            btn_row.addWidget(b)
        left_layout.addLayout(btn_row)

        self.state_label = QLabel("状态：idle")
        left_layout.addWidget(self.state_label)

        # 右侧：日志 + 任务表
        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        right_layout.addWidget(QLabel("运行日志"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        right_layout.addWidget(self.log_view, stretch=3)

        right_layout.addWidget(QLabel("历史任务（选中后可导出）"))
        self.task_table = QTableWidget(0, 6)
        self.task_table.setHorizontalHeaderLabels(
            ["task_id", "名称", "状态", "成功", "失败", "开始时间"]
        )
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        right_layout.addWidget(self.task_table, stretch=2)

        btn_refresh = QPushButton("刷新任务列表")
        btn_refresh.clicked.connect(self.refresh_tasks)
        right_layout.addWidget(btn_refresh)

    def _load_config_to_ui(self) -> None:
        c = self.config
        self.api_url.setText(c.get("bitbrowser_api_url", ""))
        self.output_dir.setText(c.get("output_dir", "./output_data"))
        self.delay_min.setValue(int(c.get("delay_min", 1500)))
        self.delay_max.setValue(int(c.get("delay_max", 4200)))
        self.retry_times.setValue(int(c.get("retry_times", 2)))
        self.scroll_times.setValue(int(c.get("list_scroll_times", 8)))
        level = str(c.get("human_level") or "strict")
        idx = self.human_level.findText(level)
        self.human_level.setCurrentIndex(idx if idx >= 0 else 2)
        self.max_detail.setValue(int(c.get("max_detail_per_keyword") or 8))
        self.chk_price_sort.setChecked(bool(c.get("enable_price_sort")))
        self.chk_sales_sort.setChecked(bool(c.get("enable_sales_sort")))
        self.price_min.setValue(int(c.get("price_min", 0)))
        self.price_max.setValue(int(c.get("price_max", 99999)))
        self.sales_min.setValue(int(c.get("sales_min", 0)))
        words = c.get("filter_black_words") or []
        self.black_words.setPlainText("\n".join(str(w) for w in words))
        self.skip_shop.setChecked(bool(c.get("filter_skip_shop")))

    def _ui_to_config(self) -> dict:
        words = [w.strip() for w in self.black_words.toPlainText().splitlines() if w.strip()]
        data = {
            "bitbrowser_api_url": self.api_url.text().strip(),
            "output_dir": self.output_dir.text().strip() or "./output_data",
            "human_level": self.human_level.currentText(),
            "delay_min": self.delay_min.value(),
            "delay_max": self.delay_max.value(),
            "max_detail_per_keyword": self.max_detail.value(),
            "enable_price_sort": self.chk_price_sort.isChecked(),
            "enable_sales_sort": self.chk_sales_sort.isChecked(),
            "retry_times": self.retry_times.value(),
            "list_scroll_times": self.scroll_times.value(),
            "price_min": self.price_min.value(),
            "price_max": self.price_max.value(),
            "sales_min": self.sales_min.value(),
            "filter_black_words": words,
            "filter_skip_shop": self.skip_shop.isChecked(),
        }
        self.config.update(data)
        self.runner.config = self.config
        return data

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", str(ROOT))
        if path:
            self.output_dir.setText(path)

    def append_log(self, msg: str) -> None:
        # 可能从工作线程回调，用 QueuedConnection 更稳；此处简单直接追加
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}] {msg}")

    def on_save_config(self) -> None:
        data = self._ui_to_config()
        self.config_mgr.save(data)
        self.storage = StorageExporter(output_dir=self.config_mgr.abs_output_dir())
        self.runner.storage = self.storage
        self.append_log("配置已保存")
        QMessageBox.information(self, "提示", "配置已保存")

    def choose_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择靶标 Excel", str(ROOT), "Excel (*.xlsx *.xls)"
        )
        if path:
            self.excel_path.setText(path)

    def make_excel_template(self) -> None:
        from excel_target import create_sample_excel

        out = self.config_mgr.abs_output_dir() / "excel_target_template.xlsx"
        create_sample_excel(out)
        self.excel_path.setText(str(out))
        self.append_log(f"已生成模板: {out}")
        QMessageBox.information(self, "模板已生成", str(out))

    def refresh_resumable(self) -> None:
        self.resume_combo.clear()
        self.resume_combo.addItem("（无）", None)
        try:
            tasks = self.storage.list_resumable_excel_tasks()
        except Exception as exc:
            self.append_log(f"刷新可续跑失败: {exc}")
            return
        self.resume_combo.clear()
        if not tasks:
            self.resume_combo.addItem("（暂无未完成 Excel 任务）", None)
            return
        for t in tasks:
            label = (
                f"#{t.get('task_id')} 剩余{t.get('left_rows')}行 "
                f"{t.get('status')} {Path(str(t.get('excel_path') or '')).name}"
            )
            self.resume_combo.addItem(label, t.get("task_id"))

    def on_start_excel(self) -> None:
        self._ui_to_config()
        self.config_mgr.save(self.config)
        path = self.excel_path.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择 Excel 文件（或生成模板后填写）")
            return
        self.runner.start_excel_task(path)
        self.append_log(f"已提交 Excel 靶标任务: {path}")

    def on_resume_excel(self) -> None:
        self._ui_to_config()
        self.config_mgr.save(self.config)
        task_id = self.resume_combo.currentData()
        if not task_id:
            QMessageBox.warning(self, "提示", "请先刷新并选择可续跑任务")
            return
        meta = self.storage.get_excel_task_meta(int(task_id))
        path = (meta or {}).get("excel_path") or self.excel_path.text().strip()
        self.runner.start_excel_task(path, resume_task_id=int(task_id))
        self.append_log(f"已续跑 Excel 任务 task_id={task_id}")

    def on_start(self) -> None:
        self._ui_to_config()
        self.config_mgr.save(self.config)
        kws = self.keywords.toPlainText().splitlines()
        self.runner.start_task(kws)

    def on_pause(self) -> None:
        if self.runner.state == TaskState.PAUSE:
            self.runner.resume_task()
            self.btn_pause.setText("暂停")
        else:
            self.runner.pause_task()
            self.btn_pause.setText("继续")

    def on_stop(self) -> None:
        self.runner.stop_task()

    def on_export(self) -> None:
        rows = self.task_table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "提示", "请先在历史任务中选中一行")
            return
        task_id = int(self.task_table.item(rows[0].row(), 0).text())
        path = self.storage.export_task(task_id, fmt="xlsx")
        if path:
            QMessageBox.information(self, "导出成功", str(path))
        else:
            QMessageBox.warning(self, "导出失败", "该任务没有可导出数据")

    def refresh_tasks(self) -> None:
        # 刷新前记住选中的 task_id，刷新后还原，避免选中被冲掉
        selected_id = None
        rows = self.task_table.selectionModel().selectedRows() if self.task_table.selectionModel() else []
        if rows:
            item = self.task_table.item(rows[0].row(), 0)
            if item:
                try:
                    selected_id = int(item.text())
                except ValueError:
                    selected_id = None

        tasks = self.storage.list_tasks()
        self.task_table.setRowCount(0)
        restore_row = -1
        for t in tasks:
            r = self.task_table.rowCount()
            self.task_table.insertRow(r)
            vals = [
                t.get("task_id"),
                t.get("task_name"),
                t.get("status"),
                t.get("success_count"),
                t.get("fail_count"),
                t.get("start_time"),
            ]
            for c, v in enumerate(vals):
                self.task_table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
            if selected_id is not None and t.get("task_id") == selected_id:
                restore_row = r
        if restore_row >= 0:
            self.task_table.selectRow(restore_row)

    def _tick_state(self) -> None:
        state = self.runner.state
        self.state_label.setText(f"状态：{state.value}")
        # 仅在「刚结束任务」时刷新一次，避免每秒清空选中
        if state == TaskState.IDLE:
            self.btn_pause.setText("暂停")
            if self._last_runner_state != TaskState.IDLE:
                self.refresh_tasks()
                self.refresh_resumable()
        self._last_runner_state = state
