from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from storm_app import APP_NAME, APP_VERSION
from storm_app.llm_manager import check_llm_status, ensure_model
from storm_app.paths import CONFIG_DIR, ROOT
from storm_app.update_manager import check_for_updates, load_app_settings, start_self_update
from storm_app.workflow import (
    BuildRequest,
    add_brand_rule,
    add_category_rule,
    collect_build_warnings,
    default_output_path,
    discover_links,
    known_category_names,
    load_build_summary,
    load_parser_rules,
    normalize_links,
    run_build,
)


APP_SETTINGS_PATH = CONFIG_DIR / "app_settings.json"
APP_LOG_PATH = ROOT / "storm_comp_analysis.log"


class TaskThread(QThread):
    message = Signal(str)
    progress = Signal(int)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def run(self) -> None:
        try:
            result = self.task(*self.args, **self.kwargs)
            self.result.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Login")
        self.setModal(True)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.status = QLabel("")
        login_button = QPushButton("Login")
        login_button.clicked.connect(self.try_login)

        layout = QFormLayout()
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        layout.addRow("", login_button)
        layout.addRow("", self.status)
        self.setLayout(layout)
        self.username.setText("admin")

    def try_login(self) -> None:
        settings = load_app_settings(APP_SETTINGS_PATH)
        login = settings.get("login", {})
        if self.username.text() == login.get("username") and self.password.text() == login.get("password"):
            self.accept()
            return
        self.status.setText("Invalid username or password.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1180, 760)
        self.discovery = None
        self.current_thread: TaskThread | None = None

        self.mode_fresh = QRadioButton("Start from blank template")
        self.mode_append = QRadioButton("Append to existing workbook")
        self.mode_fresh.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_fresh)
        self.mode_group.addButton(self.mode_append)
        self.mode_fresh.toggled.connect(self.update_workbook_mode_controls)
        self.mode_append.toggled.connect(self.update_workbook_mode_controls)

        self.existing_path = QLineEdit()
        self.existing_path.setPlaceholderText("Existing competitor analysis workbook")
        self.existing_browse = QPushButton("Browse")
        self.existing_browse.clicked.connect(self.pick_existing)

        self.output_path = QLineEdit(str(default_output_path()))
        self.output_browse = QPushButton("Save As")
        self.output_browse.clicked.connect(self.pick_output)

        self.links_edit = QPlainTextEdit()
        self.links_edit.setPlaceholderText(
            "Step 1: paste product/category listing URLs here.\n"
            "Use one URL per line. Then click '1. Discover Products'."
        )
        links_path = ROOT / "links.txt"
        if links_path.exists():
            self.links_edit.setPlainText(links_path.read_text(encoding="utf-8"))

        self.discover_button = QPushButton("1. Discover Products")
        self.discover_button.clicked.connect(self.start_discovery)
        self.apply_rules_button = QPushButton("2. Apply Brand/Category Changes")
        self.apply_rules_button.clicked.connect(self.apply_rule_changes)
        self.build_button = QPushButton("3. Build Workbook")
        self.build_button.clicked.connect(self.start_build)

        self.llm_status = QLabel("LLM status: not checked")
        self.check_llm_button = QPushButton("Check LLM")
        self.check_llm_button.clicked.connect(self.refresh_llm_status)
        self.setup_llm_button = QPushButton("Set Up LLM")
        self.setup_llm_button.clicked.connect(self.start_llm_setup)

        self.update_status = QLabel("Updates: not checked")
        self.check_updates_button = QPushButton("Check Updates")
        self.check_updates_button.clicked.connect(self.refresh_update_status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMinimumHeight(140)
        self.brand_table = QTableWidget(0, 3)
        self.brand_table.setHorizontalHeaderLabels(["Brand", "Count", "Classify as"])
        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(["Product needing category", "Category to create/use", "Match terms"])

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.copy_log_button = QPushButton("Copy Log")
        self.copy_log_button.clicked.connect(self.copy_log_to_clipboard)

        self.setCentralWidget(self.build_layout())
        self.update_workbook_mode_controls()
        self.log_message(f"Log file: {APP_LOG_PATH}")
        self.refresh_llm_status()
        self.refresh_update_status()

    def build_layout(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        top.addWidget(self.llm_status, 2)
        top.addWidget(self.check_llm_button)
        top.addWidget(self.setup_llm_button)
        top.addWidget(self.update_status, 2)
        top.addWidget(self.check_updates_button)
        layout.addLayout(top)

        workbook_box = QGroupBox("Workbook")
        grid = QGridLayout(workbook_box)
        grid.addWidget(self.mode_fresh, 0, 0)
        grid.addWidget(self.mode_append, 0, 1)
        grid.addWidget(QLabel("Existing"), 1, 0)
        grid.addWidget(self.existing_path, 1, 1)
        grid.addWidget(self.existing_browse, 1, 2)
        grid.addWidget(QLabel("Output"), 2, 0)
        grid.addWidget(self.output_path, 2, 1)
        grid.addWidget(self.output_browse, 2, 2)
        layout.addWidget(workbook_box)

        tabs = QTabWidget()
        tabs.addTab(self.build_input_tab(), "Input")
        tabs.addTab(self.build_review_tab(), "Review")
        tabs.addTab(self.log, "Log")
        layout.addWidget(tabs, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.discover_button)
        actions.addWidget(self.apply_rules_button)
        actions.addWidget(self.build_button)
        actions.addWidget(self.copy_log_button)
        actions.addWidget(self.progress)
        layout.addLayout(actions)
        return root

    def build_input_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Step 1: paste product/category listing URLs below, one per line."))
        layout.addWidget(QLabel("Step 2: click Discover Products. Step 3: review brands/categories. Step 4: build workbook."))
        layout.addWidget(self.links_edit, 1)
        return tab

    def update_workbook_mode_controls(self) -> None:
        append_mode = self.mode_append.isChecked()
        self.existing_path.setEnabled(append_mode)
        self.existing_browse.setEnabled(append_mode)
        if append_mode:
            self.existing_path.setPlaceholderText("Choose the existing competitor analysis workbook to append to")
        else:
            self.existing_path.clear()
            self.existing_path.setPlaceholderText("Disabled when starting from blank template")

    def build_review_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Discovery Summary"))
        layout.addWidget(self.summary_text)
        layout.addWidget(QLabel("Unknown Brands"))
        layout.addWidget(self.brand_table)
        layout.addWidget(QLabel("Uncategorized Products"))
        layout.addWidget(self.category_table)
        self.brand_table.horizontalHeader().setStretchLastSection(True)
        self.category_table.horizontalHeader().setStretchLastSection(True)
        self.brand_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.category_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return tab

    def pick_existing(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select existing workbook", str(ROOT), "Excel workbooks (*.xlsx)")
        if path:
            self.existing_path.setText(path)
            if not self.output_path.text().strip():
                self.output_path.setText(path)

    def pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save workbook as", self.output_path.text(), "Excel workbooks (*.xlsx)")
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self.output_path.setText(path)

    def links(self) -> list[str]:
        return normalize_links(self.links_edit.toPlainText())

    def start_discovery(self) -> None:
        links = self.links()
        if not links:
            QMessageBox.warning(self, "Missing URLs", "Add at least one URL to scrape.")
            return
        self.run_task("Discovering products...", lambda: discover_links(links), self.on_discovery)

    def on_discovery(self, discovery) -> None:
        self.discovery = discovery
        self.summary_text.setPlainText(self.discovery_summary(discovery))
        self.populate_brand_table(discovery.unknown_brand_counts)
        self.populate_category_table(discovery.uncategorized_products)
        self.log_message("Discovery complete.")

    def discovery_summary(self, discovery) -> str:
        lines = [
            f"Products found: {len(discovery.products)}",
            "",
            "Brands:",
            *[f"  {brand}: {count}" for brand, count in discovery.brand_counts.items()],
            "",
            "Categories:",
            *[f"  {category}: {count}" for category, count in discovery.category_counts.items()],
        ]
        if not discovery.unknown_brand_counts:
            lines.extend(["", "No unknown brands found."])
        if not discovery.uncategorized_products:
            lines.extend(["No uncategorized products found."])
        return "\n".join(lines)

    def populate_brand_table(self, unknown_brands: dict[str, int]) -> None:
        self.brand_table.setRowCount(len(unknown_brands))
        for row, (brand, count) in enumerate(unknown_brands.items()):
            self.brand_table.setItem(row, 0, QTableWidgetItem(brand))
            self.brand_table.setItem(row, 1, QTableWidgetItem(str(count)))
            combo = QComboBox()
            combo.addItems(["competitor", "owned"])
            self.brand_table.setCellWidget(row, 2, combo)

    def populate_category_table(self, products) -> None:
        self.category_table.setRowCount(len(products))
        categories = sorted(known_category_names(load_parser_rules()))
        for row, product in enumerate(products):
            self.category_table.setItem(row, 0, QTableWidgetItem(product.name))
            category_combo = QComboBox()
            category_combo.addItems([category.title() for category in categories])
            category_combo.setEditable(True)
            self.category_table.setCellWidget(row, 1, category_combo)
            terms = QLineEdit(default_match_terms(product.name))
            self.category_table.setCellWidget(row, 2, terms)

    def apply_rule_changes(self) -> None:
        for row in range(self.brand_table.rowCount()):
            brand_item = self.brand_table.item(row, 0)
            combo = self.brand_table.cellWidget(row, 2)
            if brand_item and isinstance(combo, QComboBox):
                add_brand_rule(brand_item.text(), combo.currentText())

        for row in range(self.category_table.rowCount()):
            combo = self.category_table.cellWidget(row, 1)
            terms = self.category_table.cellWidget(row, 2)
            if isinstance(combo, QComboBox) and isinstance(terms, QLineEdit):
                add_category_rule(combo.currentText(), terms.text())
        self.log_message("Rule changes saved to config/parser_rules.json.")

    def start_build(self) -> None:
        links = self.links()
        if not links:
            QMessageBox.warning(self, "Missing URLs", "Add at least one URL to scrape.")
            return
        output = Path(self.output_path.text().strip())
        if not output:
            QMessageBox.warning(self, "Missing output", "Choose where to save the output workbook.")
            return
        append_to = None
        if self.mode_append.isChecked():
            append_to = Path(self.existing_path.text().strip())
            if not append_to.exists():
                QMessageBox.warning(self, "Missing existing workbook", "Choose an existing workbook to append to.")
                return
        request = BuildRequest(links=links, output_path=output, append_to=append_to)
        self.run_task("Building workbook...", lambda: run_build(request), self.on_build_complete)

    def on_build_complete(self, output_path: Path) -> None:
        self.log_message(f"Workbook written: {output_path}")
        summary = load_build_summary()
        for warning in collect_build_warnings(summary):
            self.log_message(f"Build warning: {warning}")
        QMessageBox.information(self, "Workbook complete", f"Workbook written:\n{output_path}")

    def refresh_llm_status(self) -> None:
        self.log_message("Checking LLM status...")
        try:
            status = check_llm_status()
            self.llm_status.setText(f"LLM: {status.message}")
            if status.service_available and status.model_available:
                self.log_message(f"LLM status: {status.message}")
            else:
                self.log_message(f"LLM check failed: {status.message}")
        except Exception as exc:
            details = traceback.format_exc()
            self.llm_status.setText("LLM: LLM error.")
            self.log_message(f"LLM check failed: {exc}\n{details}")

    def start_llm_setup(self) -> None:
        def task():
            def progress(message: str) -> None:
                self.current_thread.message.emit(message)
                self.current_thread.message.emit("")
                match = re.search(r"(\d{1,3})%", message)
                if match:
                    self.current_thread.progress.emit(min(100, int(match.group(1))))

            return ensure_model(progress)

        self.llm_status.setText("LLM: setting up...")
        self.run_task(
            "Setting up LLM...",
            task,
            self.on_llm_setup_complete,
            progress_mode="percent",
        )

    def on_llm_setup_complete(self, status) -> None:
        self.llm_status.setText(f"LLM: {status.message}")
        self.log_message(f"LLM setup complete: {status.message}")

    def refresh_update_status(self) -> None:
        self.log_message("Checking for updates...")
        try:
            status = check_for_updates()
            self.update_status.setText(f"Updates: {status.message}")
            self.log_message(f"Update status: {status.message}")
            if status.update_available:
                answer = QMessageBox.question(
                    self,
                    "Update available",
                    f"{status.message}\n\n{status.release_url}\n\nUpdate now? The app will close, rebuild, and reopen.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    log_path = start_self_update(status)
                    self.log_message(f"Updater started. Update log: {log_path}")
                    QMessageBox.information(
                        self,
                        "Update started",
                        f"The app will close now. It will reopen after the update finishes.\n\nUpdate log:\n{log_path}",
                    )
                    QApplication.quit()
        except Exception as exc:
            details = traceback.format_exc()
            self.update_status.setText("Updates: check failed.")
            self.log_message(f"Update check failed: {exc}\n{details}")

    def run_task(self, start_message: str, task: Callable[[], Any], on_result: Callable[[Any], None], progress_mode: str = "busy") -> None:
        if self.current_thread and self.current_thread.isRunning():
            QMessageBox.warning(self, "Busy", "A task is already running.")
            return
        self.log_message(start_message)
        self.progress.setVisible(True)
        if progress_mode == "percent":
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
        else:
            self.progress.setRange(0, 0)
        self.current_thread = TaskThread(task)
        self.current_thread.message.connect(self.log_message)
        self.current_thread.progress.connect(self.progress.setValue)
        self.current_thread.result.connect(lambda result: self.finish_task(result, on_result))
        self.current_thread.failed.connect(self.fail_task)
        self.current_thread.start()

    def finish_task(self, result: Any, on_result: Callable[[Any], None]) -> None:
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        on_result(result)

    def fail_task(self, message: str) -> None:
        self.progress.setVisible(False)
        self.log_message(f"Error:\n{message}")
        QMessageBox.critical(self, "Task failed", message)

    def log_message(self, message: str) -> None:
        timestamped = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        self.log.append(timestamped)
        try:
            APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with APP_LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write(timestamped + "\n")
        except Exception:
            pass

    def copy_log_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self.log.toPlainText())
        self.log_message("Log copied to clipboard.")


def default_match_terms(product_name: str) -> str:
    words = [word.strip(" -_/").casefold() for word in product_name.split()]
    useful = [word for word in words if len(word) >= 4 and not word.isdigit()]
    return ", ".join(useful[:3])


def main() -> int:
    app = QApplication(sys.argv)
    login = LoginDialog()
    if login.exec() != QDialog.Accepted:
        return 0
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
