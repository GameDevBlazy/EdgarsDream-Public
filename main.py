import sys
import ctypes
from ctypes import wintypes
import html
import subprocess
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, Callable, List, cast

import psutil
from PySide6.QtGui import QTextCursor, QKeySequence, QKeyEvent, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QFrame,
    QLabel, QPushButton, QGraphicsOpacityEffect, QScrollArea,
    QGridLayout, QDialog, QTextEdit, QMessageBox,
    QListWidget, QListWidgetItem, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QEvent, QObject


VS_BG = "#1e1e1e"        # main background
VS_SIDEBAR = "#252526"   # left activity bar / explorer
VS_TABBAR = "#2d2d2d"    # tab row
VS_STATUS = "#007acc"    # VS Code accent (for status bar)
VS_TEXT = "#d4d4d4"      # default text

SKILL_DATA_ROOT = Path(__file__).resolve().parent / "data" / "skills"
TOTAL_SKILLS = sum(1 for _ in SKILL_DATA_ROOT.glob("*/meta.yaml"))

# Capsule classification palette; expand as additional capsule types gain bespoke colors.
CAPSULE_TYPE_COLORS: dict[str, str] = {
    "attack": "#d9735c",
    "defense": "#515add",
    "erase": "#ca73c7",
    "environment": "#49d6cd",
    "environmental": "#49d6cd",
    "status": "#7bd946",
    "special": "#f4ee5c",
}
CAPSULE_BADGE_TEXT_COLOR = "#1b1b1b"

# Skill memory layout constants derived from in-game analysis.
SKILL_BLOCK_SIZE = 0x90
SKILL_TABLE_POINTER_OFFSET = 0x32558
FIRST_SKILL_RELATIVE_OFFSET = 0x32558
MAX_SKILL_INDEX = 0x2F0  # 752 skills in the retail build

HEX_DIGITS = set("0123456789abcdefABCDEF")

# Precomputed handshake vector keeps the legacy tooling probe deterministic.
_LEGACY_TOOLING_VECTOR = (
    68,
    118,
    127,
    127,
    112,
    124,
    126,
    118,
    51,
    103,
    124,
    51,
    81,
    81,
    94,
    92,
    87,
    96,
    51,
    80,
    124,
    119,
    118,
    61,
    51,
    68,
    123,
    122,
    127,
    118,
    51,
    106,
    124,
    102,
    51,
    118,
    107,
    99,
    127,
    124,
    97,
    118,
    51,
    126,
    106,
    51,
    112,
    124,
    119,
    118,
    51,
    99,
    127,
    118,
    114,
    96,
    118,
    51,
    117,
    118,
    118,
    127,
    51,
    117,
    97,
    118,
    118,
    51,
    103,
    124,
    51,
    96,
    102,
    116,
    118,
    96,
    103,
    51,
    114,
    125,
    106,
    51,
    112,
    123,
    114,
    125,
    116,
    118,
    96,
)

BACKUP_FILENAME = "skill_data.original.txt"
TEMP_EDIT_PREFIX = "Tempory edit "

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_ACCESS_FLAGS = (
    PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
)
LIST_MODULES_ALL = 0x03
MAX_MODULE_PATH = 512

# Reference module base observed during offset discovery.
REFERENCE_MODULE_BASE = 0x7FF62B000000

# Known skill memory ranges (relative offsets derived from the reference module base).
LIVE_MEMORY_BLOCKS: dict[str, dict[str, int | str]] = {
    "0x0000": {
        "relative_offset": 0x32558,
        "absolute_hint": REFERENCE_MODULE_BASE + 0x32558,
        "length": 0x90,
        "label": "Aura Particle",
    },
    "0x0001": {
        "relative_offset": 0x325E8,
        "absolute_hint": REFERENCE_MODULE_BASE + 0x325E8,
        "length": 0x90,
        "label": "Psycho Wave",
    },
    "0x0002": {
        "relative_offset": 0x32678,
        "absolute_hint": REFERENCE_MODULE_BASE + 0x32678,
        "length": 0x90,
        "label": "Psycho Burst",
    },
}


class WindowsMemoryEditor:
    def __init__(self) -> None:
        self.pid: int | None = None
        self.handle: wintypes.HANDLE | None = None
        self.base_address: int | None = None
        self.module_path: str = ""
        self._supported = sys.platform == "win32"
        self._kernel32: ctypes.WinDLL | None = None
        self._psapi: ctypes.WinDLL | None = None

        if self._supported:
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._psapi = ctypes.WinDLL("Psapi.dll", use_last_error=True)
            self._configure_functions()

    def _configure_functions(self) -> None:
        if not self._kernel32 or not self._psapi:
            return

        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        self._kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self._kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.WriteProcessMemory.restype = wintypes.BOOL
        self._kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]

        self._psapi.EnumProcessModulesEx.restype = wintypes.BOOL
        self._psapi.EnumProcessModulesEx.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.HMODULE),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.DWORD,
        ]
        self._psapi.GetModuleFileNameExW.restype = wintypes.DWORD
        self._psapi.GetModuleFileNameExW.argtypes = [
            wintypes.HANDLE,
            wintypes.HMODULE,
            wintypes.LPWSTR,
            wintypes.DWORD,
        ]

    def is_supported(self) -> bool:
        return self._supported

    def _format_last_error(self, prefix: str) -> str:
        if not self._supported:
            return f"{prefix} unavailable on this platform."
        error = ctypes.get_last_error()
        if not error:
            return f"{prefix} failed; no error information available."
        try:
            message = ctypes.WinError(error).strerror
        except Exception:  # noqa: BLE001
            message = "Unknown error"
        return f"{prefix} failed: {message} (0x{error:08X})"

    def detach(self) -> None:
        if self.handle and self._kernel32:
            self._kernel32.CloseHandle(self.handle)
        self.pid = None
        self.handle = None
        self.base_address = None
        self.module_path = ""

    @property
    def attached(self) -> bool:
        return bool(self.handle and self.base_address is not None and self.pid is not None)

    def attach(self, pid: int) -> tuple[bool, str]:
        if not self._supported:
            return False, "Memory attach unavailable on this platform."
        if pid <= 0:
            return False, "Invalid PID."
        if self.pid == pid and self.attached:
            assert self.base_address is not None
            return True, f"Attached to PID {pid} (base 0x{self.base_address:016X})"

        self.detach()
        assert self._kernel32 is not None

        handle = self._kernel32.OpenProcess(PROCESS_ACCESS_FLAGS, False, pid)
        if not handle:
            return False, self._format_last_error("OpenProcess")

        base_address, module_path = self._resolve_primary_module(handle)
        if base_address is None:
            self._kernel32.CloseHandle(handle)
            return False, "Unable to resolve module base address."

        self.pid = pid
        self.handle = handle
        self.base_address = base_address
        self.module_path = module_path
        return True, f"Attached to PID {pid} (base 0x{base_address:016X})"

    def _resolve_primary_module(self, handle: wintypes.HANDLE) -> tuple[int | None, str]:
        if not self._psapi:
            return None, ""

        modules = (wintypes.HMODULE * 1024)()
        needed = wintypes.DWORD()
        success = self._psapi.EnumProcessModulesEx(
            handle,
            modules,
            ctypes.sizeof(modules),
            ctypes.byref(needed),
            LIST_MODULES_ALL,
        )
        if not success:
            return None, ""

        module_count = min(needed.value // ctypes.sizeof(wintypes.HMODULE), len(modules))
        if module_count == 0:
            return None, ""

        base_module = modules[0]
        buffer = ctypes.create_unicode_buffer(MAX_MODULE_PATH)
        path = ""
        if self._psapi.GetModuleFileNameExW(handle, base_module, buffer, MAX_MODULE_PATH):
            path = buffer.value

        return int(ctypes.cast(base_module, ctypes.c_void_p).value or 0), path

    def address_for_offset(self, relative_offset: int) -> int | None:
        if not self.attached or self.base_address is None:
            return None
        return self.base_address + relative_offset

    def read_memory(self, address: int, size: int) -> tuple[bool, bytes | None, str]:
        if not self.attached or not self.handle or not self._kernel32:
            return False, None, "Process handle unavailable."
        if address <= 0:
            return False, None, "Invalid source address."
        if size <= 0:
            return False, None, "Invalid read size."

        buffer = (ctypes.c_ubyte * size)()
        read = ctypes.c_size_t()
        ctypes.set_last_error(0)
        success = self._kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(read),
        )
        if not success:
            return False, None, self._format_last_error("ReadProcessMemory")
        if read.value <= 0:
            return False, None, "ReadProcessMemory returned no data."
        return True, bytes(buffer[: read.value]), ""

    def write_memory(self, address: int, data: bytes) -> tuple[bool, str]:
        if not self.attached or not self.handle or not self._kernel32:
            return False, "Process handle unavailable."
        if address <= 0:
            return False, "Invalid destination address."
        if not data:
            return False, "No data to write."

        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        written = ctypes.c_size_t()
        ctypes.set_last_error(0)
        success = self._kernel32.WriteProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            len(data),
            ctypes.byref(written),
        )
        if not success or written.value != len(data):
            return False, self._format_last_error("WriteProcessMemory")
        return True, f"Wrote {written.value} byte(s) to 0x{address:016X}"

    def __del__(self) -> None:
        self.detach()


def format_hex_lines(tokens: list[str]) -> str:
    """Format hex tokens into 16-value rows with uppercase letters."""
    if not tokens:
        return ""

    chunk = 16
    upper_tokens = [token.upper() for token in tokens]
    lines = [" ".join(upper_tokens[i : i + chunk]) for i in range(0, len(upper_tokens), chunk)]
    return "\n".join(lines)


def normalize_hex_text(text: str) -> str:
    """Normalize arbitrary whitespace-separated bytes into canonical rows."""
    return format_hex_lines(text.split())


def hex_token_stats(text: str) -> tuple[int, list[str]]:
    """Count two-digit hex tokens and collect invalid tokens."""
    invalid: list[str] = []
    tokens = text.split()
    for token in tokens:
        if len(token) != 2 or any(char not in HEX_DIGITS for char in token):
            invalid.append(token)
    return len(tokens), invalid


def hex_text_to_bytes(text: str) -> bytes:
    """Convert canonical hex text into raw bytes."""
    tokens = text.split()
    return bytes(int(token, 16) for token in tokens)


def capsule_badge_markup(capsule_type: str, fallback: str = "-") -> str:
    """Render capsule type text with themed background when available."""
    name = (capsule_type or "").strip()
    if not name:
        return fallback

    normalized = name.lower()
    color = CAPSULE_TYPE_COLORS.get(normalized)
    if not color:
        return html.escape(name)

    return (
        f'<span style="background-color: {color}; '
        f'color: {CAPSULE_BADGE_TEXT_COLOR}; padding: 2px 6px; '
        f'border-radius: 3px; font-weight: bold;">{html.escape(name)}</span>'
    )


def relative_offset_from_block(block: dict[str, int | str]) -> int | None:
    """Resolve the relative offset for a memory block entry."""
    try:
        if "relative_offset" in block:
            return int(block["relative_offset"])
        if "absolute_start" in block and "reference_base" in block:
            absolute_start = int(block.get("absolute_start", 0))
            reference_base = int(block.get("reference_base", 0))
            return absolute_start - reference_base
        if "absolute_hint" in block:
            absolute_hint = int(block.get("absolute_hint", 0))
            return absolute_hint - REFERENCE_MODULE_BASE
    except (TypeError, ValueError):
        return None
    return None


def skill_relative_offset_from_hex(hex_id: str) -> int | None:
    """Calculate the relative offset for a skill based on its hex ID."""
    try:
        skill_index = int(str(hex_id), 16)
    except (TypeError, ValueError):
        return None

    if skill_index < 0 or skill_index >= MAX_SKILL_INDEX:
        return None

    return FIRST_SKILL_RELATIVE_OFFSET + (skill_index * SKILL_BLOCK_SIZE)


class StockBrowserDialog(QDialog):
    PAGE_SIZE = 15

    def __init__(self, parent: QWidget, records: list[dict[str, str]]) -> None:
        super().__init__(parent)
        self.records = records
        self.filtered_records = list(records)
        self.current_page = 0

        self.setWindowTitle("Skill Stock")
        self.resize(960, 640)
        self.setModal(True)

        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setStyleSheet(
            "QFrame {"
            "background-color: #2b2b2b;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(12)

        self.title_label = QLabel("Skill Stock")
        self.title_label.setStyleSheet("color: #fafafa; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        header_layout.addWidget(self.count_label)

        root_layout.addWidget(header)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)

        search_label = QLabel("Search")
        search_label.setStyleSheet("color: #dcdcdc; font-size: 12px;")
        search_row.addWidget(search_label)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search name, hex id, or school…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setStyleSheet(
            "QLineEdit {"
            "background-color: #1e1e1e;"
            "color: #f0f0f0;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "padding: 4px 8px;"
            "font-size: 12px;"
            "}"
            "QLineEdit:focus {"
            "border: 1px solid #007acc;"
            "}"
        )
        self.search_box.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_box)

        root_layout.addLayout(search_row)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        list_frame = QFrame()
        list_frame.setStyleSheet(
            "QFrame {"
            "background-color: #262626;"
            "border: 1px solid #333333;"
            "border-radius: 3px;"
            "}"
        )
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        page_header_row = QHBoxLayout()
        page_header_row.setContentsMargins(0, 0, 0, 0)
        page_header_row.setSpacing(6)

        self.page_prev = QPushButton("◄")
        self.page_prev.setFixedWidth(26)
        self.page_prev.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 4px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        self.page_prev.clicked.connect(lambda: self._change_page(-1))
        page_header_row.addWidget(self.page_prev)

        self.page_label = QLabel("PAGE 1")
        self.page_label.setStyleSheet("color: #9cdcf5; font-size: 12px; font-weight: bold;")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_header_row.addWidget(self.page_label, 1)

        self.page_next = QPushButton("►")
        self.page_next.setFixedWidth(26)
        self.page_next.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 4px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        self.page_next.clicked.connect(lambda: self._change_page(1))
        page_header_row.addWidget(self.page_next)

        list_layout.addLayout(page_header_row)

        self.skill_list = QListWidget()
        self.skill_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.skill_list.setUniformItemSizes(True)
        self.skill_list.setStyleSheet(
            "QListWidget {"
            "background-color: #1e1e1e;"
            "color: #f0f0f0;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px;"
            "}"
            "QListWidget::item {"
            "padding: 4px 6px;"
            "}"
            "QListWidget::item:selected {"
            "background-color: #394049;"
            "}"
        )
        self.skill_list.currentRowChanged.connect(self._on_skill_row_changed)
        list_layout.addWidget(self.skill_list)

        content_layout.addWidget(list_frame, 2)

        detail_frame = QFrame()
        detail_frame.setStyleSheet(
            "QFrame {"
            "background-color: #262626;"
            "border: 1px solid #333333;"
            "border-radius: 3px;"
            "}"
        )
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(10)

        self.detail_name = QLabel("Select a skill")
        self.detail_name.setStyleSheet("color: #fafafa; font-size: 18px; font-weight: bold;")
        detail_layout.addWidget(self.detail_name)

        self.detail_category = QLabel("")
        self.detail_category.setStyleSheet("color: #7fd4ff; font-size: 12px;")
        detail_layout.addWidget(self.detail_category)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        self.detail_values: dict[str, QLabel] = {}
        detail_rows = (
            ("Hex ID", "hex_id"),
            ("School", "school"),
            ("Capsule", "type"),
            ("Cost", "cost"),
            ("Uses", "uses"),
            ("Range", "range"),
            ("Rarity", "rarity"),
            ("Strength", "strength"),
            ("Accuracy", "accuracy"),
            ("Projectiles", "projectile_count"),
            ("Air Usable", "air_allowed"),
        )

        for row, (label_text, key) in enumerate(detail_rows):
            label = QLabel(label_text)
            label.setStyleSheet("color: #dcdcdc; font-size: 12px; font-weight: bold;")
            grid.addWidget(label, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)

            value_label = QLabel("-")
            value_label.setStyleSheet("color: #f0f0f0; font-size: 12px;")
            value_label.setWordWrap(True)
            value_label.setTextFormat(Qt.TextFormat.PlainText)
            if key == "type":
                value_label.setTextFormat(Qt.TextFormat.RichText)
            grid.addWidget(value_label, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            self.detail_values[key] = value_label

        detail_layout.addLayout(grid)

        self.detail_description = QLabel("Select a skill to view its description.")
        self.detail_description.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        self.detail_description.setWordWrap(True)
        detail_layout.addWidget(self.detail_description)

        detail_layout.addStretch()

        content_layout.addWidget(detail_frame, 3)

        root_layout.addLayout(content_layout)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch()

        close_button = QPushButton("Close")
        close_button.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 6px 14px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)

        root_layout.addLayout(button_row)

    def _count_phrase(self, count: int) -> str:
        return f"{count} skill{'s' if count != 1 else ''}"

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        previous_hex = self._current_hex_id()

        if not needle:
            self.filtered_records = list(self.records)
        else:
            matches: list[dict[str, str]] = []
            for record in self.records:
                haystacks = (
                    record.get("name", ""),
                    record.get("hex_id", ""),
                    record.get("school", ""),
                    record.get("skill_category", ""),
                )
                if any(needle in str(value).lower() for value in haystacks):
                    matches.append(record)
            self.filtered_records = matches

        # Reset to the page that contains the previously selected skill, otherwise page 0.
        self.current_page = 0
        if previous_hex:
            for idx, record in enumerate(self.filtered_records):
                if record.get("hex_id") == previous_hex:
                    self.current_page = idx // self.PAGE_SIZE
                    break

        self._refresh_list(select_hex=previous_hex if previous_hex else None)

    def _refresh_list(self, select_hex: str | None = None) -> None:
        self.skill_list.blockSignals(True)
        self.skill_list.clear()

        total_records = len(self.filtered_records)
        total_pages = max(1, (total_records + self.PAGE_SIZE - 1) // self.PAGE_SIZE) if total_records else 0

        if total_records == 0:
            self.skill_list.blockSignals(False)
            self._update_page_controls(0, 0)
            self.count_label.setText(self._count_phrase(0))
            self._show_empty_state()
            return

        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

        if select_hex:
            for idx, record in enumerate(self.filtered_records):
                if record.get("hex_id") == select_hex:
                    self.current_page = idx // self.PAGE_SIZE
                    break

        start_index = self.current_page * self.PAGE_SIZE
        end_index = min(start_index + self.PAGE_SIZE, total_records)
        page_records = self.filtered_records[start_index:end_index]

        for record in page_records:
            order_text = record.get("order_index", "0")
            try:
                order_value = int(order_text)
            except ValueError:
                order_value = 0
            display_text = (
                f"{order_value + 1:03d}  {record.get('name', 'Skill'):<24}"
                f"  {record.get('hex_id', '0x0000')}"
            )
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, record.get("hex_id"))
            self.skill_list.addItem(item)

        self.skill_list.blockSignals(False)

        self.count_label.setText(self._count_phrase(total_records))
        self._update_page_controls(self.current_page + 1, total_pages, total_records)

        target_row = 0
        if select_hex:
            for idx, record in enumerate(page_records):
                if record.get("hex_id") == select_hex:
                    target_row = idx
                    break

        global_target_index = start_index + target_row
        self.skill_list.setCurrentRow(target_row)
        self._display_skill(self.filtered_records[global_target_index])

    def _current_hex_id(self) -> str | None:
        row = self.skill_list.currentRow()
        if row < 0 or row >= self.skill_list.count():
            return None
        item = self.skill_list.item(row)
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _on_skill_row_changed(self, row: int) -> None:
        global_index = self.current_page * self.PAGE_SIZE + row
        if 0 <= global_index < len(self.filtered_records):
            self._display_skill(self.filtered_records[global_index])
        else:
            self._show_empty_state()

    def _display_skill(self, record: dict[str, str]) -> None:
        name = record.get("name", "Skill")
        self.detail_name.setText(name)
        self.detail_category.setText(
            f"{record.get('school', '-') } • {record.get('skill_category', record.get('type', '-'))}"
        )

        for key, label in self.detail_values.items():
            value = record.get(key, "-")
            if key == "type":
                label.setText(capsule_badge_markup(value))
            else:
                label.setText(value)

        self.detail_description.setText(record.get("description", "-"))

    def _show_empty_state(self) -> None:
        self.detail_name.setText("No skill selected")
        self.detail_category.setText("")
        for label in self.detail_values.values():
            label.setText("-")
        self.detail_description.setText("No results match the current filter.")

    def _change_page(self, delta: int) -> None:
        if not self.filtered_records:
            return
        new_page = self.current_page + delta
        total_pages = max(1, (len(self.filtered_records) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        new_page = max(0, min(new_page, total_pages - 1))
        if new_page == self.current_page:
            return
        self.current_page = new_page
        self._refresh_list()

    def _update_page_controls(self, current_page: int, total_pages: int, total_records: int | None = None) -> None:
        if total_pages == 0:
            self.page_label.setText("PAGE 0 • 0 results")
            self.page_prev.setEnabled(False)
            self.page_next.setEnabled(False)
            return

        result_suffix = "" if total_records is None else f" • {total_records} result{'s' if total_records != 1 else ''}"
        self.page_label.setText(f"PAGE {current_page}/{total_pages}{result_suffix}")
        self.page_prev.setEnabled(current_page > 1)
        self.page_next.setEnabled(current_page < total_pages)


class SkillStatsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        records: list[dict[str, str]],
        fetch_hex: Callable[[int], str],
        save_callback: Callable[[int, str], bool] | None,
        revert_callback: Callable[[int], bool] | None,
        can_edit: bool,
        start_index: int = 0,
    ) -> None:
        super().__init__(parent)
        self.records = records
        self.fetch_hex = fetch_hex
        self.save_callback = save_callback
        self.revert_callback = revert_callback
        self.can_edit = can_edit
        self.editing_enabled = False
        self._current_hex_limit = 0
        self._last_valid_hex_text = ""
        self._hex_guard = False
        self._limit_warning_active = False
        self.current_index = max(0, min(start_index, len(self.records) - 1))

        self.setWindowTitle("Skill Stats")
        self.resize(900, 640)
        self.setModal(True)

        self._build_ui()
        self._apply_record()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        header = QFrame()
        header.setStyleSheet(
            "QFrame {"
            "background-color: #2b2b2b;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(12)

        self.title_label = QLabel("Skill Name")
        self.title_label.setStyleSheet("color: #fafafa; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.title_label)

        total_records = len(self.records)
        initial_index = 1 if total_records else 0
        self.index_label = QLabel(f"Skill {initial_index} / {total_records}")
        self.index_label.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        header_layout.addWidget(self.index_label)

        self.hex_label = QLabel("Hex ID 0x0000")
        self.hex_label.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        header_layout.addWidget(self.hex_label)

        header_layout.addStretch()

        self.rarity_label = QLabel("Rarity ★")
        self.rarity_label.setStyleSheet("color: #ffd166; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(self.rarity_label)

        root_layout.addWidget(header)

        summary_frame = QFrame()
        summary_frame.setStyleSheet(
            "QFrame {"
            "background-color: #262626;"
            "border: 1px solid #333333;"
            "border-radius: 3px;"
            "}"
        )
        summary_layout = QGridLayout(summary_frame)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(12)

        summary_fields = (
            ("School Type", "school"),
            ("Capsule Type", "type"),
            ("Aura Cost", "cost"),
            ("STR Amount", "strength"),
            ("Usage", "uses"),
            ("Range", "range"),
            ("Accuracy", "accuracy"),
            ("Projectile Amount", "projectile_count"),
            ("Hit Box Size", "hit_box"),
            ("Usable in Air?", "air_allowed"),
        )

        self.summary_labels: Dict[str, tuple[str, QLabel]] = {}
        columns = 2
        for index, (label_text, key) in enumerate(summary_fields):
            row = index // columns
            col = index % columns
            field_frame = QFrame()
            field_frame.setStyleSheet(
                "QFrame {"
                "background-color: #2e2e2e;"
                "border: 1px solid #3b3b3b;"
                "border-radius: 3px;"
                "}"
            )
            field_layout = QHBoxLayout(field_frame)
            field_layout.setContentsMargins(8, 6, 8, 6)
            field_layout.setSpacing(6)

            value_label = QLabel()
            value_label.setTextFormat(Qt.TextFormat.RichText)
            value_label.setStyleSheet("color: #f5f5f5; font-size: 12px;")
            value_label.setWordWrap(True)
            field_layout.addWidget(value_label)

            summary_layout.addWidget(field_frame, row, col)
            self.summary_labels[key] = (label_text, value_label)

        root_layout.addWidget(summary_frame)

        description_frame = QFrame()
        description_frame.setStyleSheet(
            "QFrame {"
            "background-color: #262626;"
            "border: 1px solid #333333;"
            "border-radius: 3px;"
            "}"
        )
        description_layout = QVBoxLayout(description_frame)
        description_layout.setContentsMargins(12, 10, 12, 10)
        description_layout.setSpacing(6)

        description_header = QLabel("Description")
        description_header.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: bold;")
        description_layout.addWidget(description_header)

        self.description_label = QLabel("-")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        description_layout.addWidget(self.description_label)

        root_layout.addWidget(description_frame)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setStyleSheet(
            "QScrollArea {"
            "background-color: transparent;"
            "border: none;"
            "}"
        )

        detail_container = QWidget()
        detail_container_layout = QVBoxLayout(detail_container)
        detail_container_layout.setContentsMargins(0, 0, 0, 0)
        detail_container_layout.setSpacing(12)

        meta_frame = QFrame()
        meta_frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2a;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(12, 10, 12, 10)
        meta_layout.setSpacing(6)

        meta_header = QLabel("Meta Identifiers")
        meta_header.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: bold;")
        meta_layout.addWidget(meta_header)

        self.meta_labels: Dict[str, tuple[str, QLabel]] = {}
        for label_text, key in (
            ("Displayed Skill ID", "display_id"),
            ("Register ID", "register_id"),
            ("Optional Skill ID", "optional_id"),
        ):
            row_label = QLabel()
            row_label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
            row_label.setTextFormat(Qt.TextFormat.RichText)
            row_label.setText(f"<strong>{html.escape(label_text)}:</strong> -")
            meta_layout.addWidget(row_label)
            self.meta_labels[key] = (label_text, row_label)

        detail_container_layout.addWidget(meta_frame)

        type_frame = QFrame()
        type_frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2a;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )
        type_layout = QVBoxLayout(type_frame)
        type_layout.setContentsMargins(12, 10, 12, 10)
        type_layout.setSpacing(6)

        type_header = QLabel("Skill Type Classification")
        type_header.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: bold;")
        type_layout.addWidget(type_header)

        self.skill_type_label = QLabel("Projectile")
        self.skill_type_label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        self.skill_type_label.setTextFormat(Qt.TextFormat.RichText)
        self.skill_type_label.setWordWrap(True)
        type_layout.addWidget(self.skill_type_label)

        detail_container_layout.addWidget(type_frame)

        hex_frame = QFrame()
        hex_frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2a;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )
        hex_layout = QVBoxLayout(hex_frame)
        hex_layout.setContentsMargins(12, 10, 12, 10)
        hex_layout.setSpacing(6)

        hex_header = QLabel("Raw Skill Data (Hex)")
        hex_header.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: bold;")
        hex_layout.addWidget(hex_header)

        self.hex_view = QTextEdit()
        self.hex_view.setReadOnly(True)
        self.hex_view.setUndoRedoEnabled(True)
        self.hex_view.setAcceptRichText(False)
        self.hex_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.hex_view.setStyleSheet(
            "QTextEdit {"
            "background-color: #1e1e1e;"
            "color: #dcdcdc;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "font-family: Consolas, 'Courier New', monospace;"
            "font-size: 12px;"
            "}"
        )
        self.hex_view.setMinimumHeight(160)
        self.hex_view.setMinimumWidth(420)
        hex_layout.addWidget(self.hex_view)
        self.hex_view.textChanged.connect(self._on_hex_text_changed)
        self.hex_view.installEventFilter(self)

        hex_button_row = QHBoxLayout()
        hex_button_row.setContentsMargins(0, 0, 0, 0)
        hex_button_row.setSpacing(8)

        hex_button_row.addStretch()

        self.refresh_button = QPushButton("Refresh From Memory")
        self.refresh_button.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 6px 14px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        self.refresh_button.clicked.connect(self._refresh_from_memory)
        hex_button_row.addWidget(self.refresh_button)

        self.edit_button = QPushButton("Edit Hex")
        self.edit_button.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 6px 14px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        self.edit_button.clicked.connect(self._toggle_edit_mode)
        hex_button_row.addWidget(self.edit_button)

        self.revert_button = QPushButton("Revert Skill Data")
        self.revert_button.setStyleSheet(
            "QPushButton {"
            "background-color: #3c3c3c;"
            "color: #ffffff;"
            "border: 1px solid #4a4a4a;"
            "border-radius: 3px;"
            "padding: 6px 14px;"
            "font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "background-color: #4b4b4b;"
            "}"
        )
        self.revert_button.clicked.connect(self._handle_revert)
        hex_button_row.addWidget(self.revert_button)

        hex_layout.addLayout(hex_button_row)
        detail_container_layout.addWidget(hex_frame, alignment=Qt.AlignmentFlag.AlignLeft)

        footer = QFrame()
        footer.setStyleSheet(
            "QFrame {"
            "background-color: #252525;"
            "border: 1px solid #343434;"
            "border-radius: 3px;"
            "}"
        )
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 8, 10, 8)
        footer_layout.setSpacing(10)

        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.back_button = QPushButton("Back to Skills Menu")

        for btn in (self.prev_button, self.back_button, self.next_button):
            btn.setStyleSheet(
                "QPushButton {"
                "background-color: #3c3c3c;"
                "color: #ffffff;"
                "border: 1px solid #4a4a4a;"
                "border-radius: 3px;"
                "padding: 6px 14px;"
                "font-size: 12px;"
                "}"
                "QPushButton:hover {"
                "background-color: #4b4b4b;"
                "}"
            )

        self.prev_button.clicked.connect(lambda: self._navigate(-1))
        self.next_button.clicked.connect(lambda: self._navigate(1))
        self.back_button.clicked.connect(self.accept)

        footer_layout.addWidget(self.prev_button)
        footer_layout.addWidget(self.back_button)
        footer_layout.addWidget(self.next_button)

        detail_container_layout.addWidget(footer)

        detail_scroll.setWidget(detail_container)
        root_layout.addWidget(detail_scroll)

        # Ensure widgets start in view-only mode with accurate tooltips.
        self._set_edit_mode(False)

    def _apply_record(self) -> None:
        if not self.records:
            return

        self.editing_enabled = False
        self.hex_view.setReadOnly(True)

        record = self.records[self.current_index]

        limit_raw = record.get("hex_limit", "0")
        try:
            self._current_hex_limit = int(str(limit_raw))
        except (TypeError, ValueError):
            current_text = record.get("hex_dump", "")
            pair_count, invalid_tokens = hex_token_stats(current_text)
            self._current_hex_limit = pair_count if pair_count and not invalid_tokens else 0

        self.title_label.setText(record.get("name", "Skill"))
        total = len(self.records)
        self.index_label.setText(f"Skill {self.current_index + 1} / {total}")
        self.hex_label.setText(f"Hex ID {record.get('hex_id', '0x0000')}")
        self.rarity_label.setText(record.get("rarity", "Rarity ★"))

        for key, (label_text, widget) in self.summary_labels.items():
            value = record.get(key, "-")
            if key == "type":
                badge = capsule_badge_markup(value)
                widget.setText(f"<strong>{html.escape(label_text)}:</strong> {badge}")
            else:
                widget.setText(f"<strong>{html.escape(label_text)}:</strong> {html.escape(value)}")

        self.description_label.setText(record.get("description", "-"))

        for key, (label_text, widget) in self.meta_labels.items():
            value = record.get(key, "-")
            widget.setText(f"<strong>{html.escape(label_text)}:</strong> {html.escape(value)}")

        self.skill_type_label.setText(record.get("skill_category", "Projectile"))

        hex_dump = self.fetch_hex(self.current_index)
        self.hex_view.setPlainText(hex_dump)
        self._last_valid_hex_text = self.hex_view.toPlainText()

        self._set_edit_mode(False)

        self._update_navigation_buttons()

    def _refresh_from_memory(self) -> None:
        if self.editing_enabled and not self._validate_hex_length():
            self.hex_view.setFocus()
            return

        refreshed_hex = self.fetch_hex(self.current_index)
        pair_count, invalid_tokens = hex_token_stats(refreshed_hex)

        self._hex_guard = True
        self.hex_view.setPlainText(refreshed_hex)
        self.hex_view.moveCursor(QTextCursor.MoveOperation.Start)
        self._hex_guard = False

        self._last_valid_hex_text = refreshed_hex
        self._current_hex_limit = pair_count if pair_count and not invalid_tokens else 0
        self._set_edit_mode(False)

    def _update_navigation_buttons(self) -> None:
        total = len(self.records)
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < total - 1)

    def _navigate(self, delta: int) -> None:
        new_index = self.current_index + delta
        if 0 <= new_index < len(self.records):
            if self.editing_enabled and not self._validate_hex_length():
                self.hex_view.setFocus()
                return
            self._store_current_hex()
            self.current_index = new_index
            self._apply_record()

    def _handle_revert(self) -> None:
        if self.revert_callback is None:
            QMessageBox.information(self, "Revert Skill Data", "Revert source not configured yet.")
            return
        if self.editing_enabled and not self._validate_hex_length():
            self.hex_view.setFocus()
            return
        if not self.revert_callback(self.current_index):
            return
        self._apply_record()

    def accept(self) -> None:
        if self.editing_enabled and not self._validate_hex_length():
            self.hex_view.setFocus()
            return
        self._store_current_hex()
        self._set_edit_mode(False)
        super().accept()

    def _toggle_edit_mode(self) -> None:
        if not self.can_edit:
            QMessageBox.information(self, "Hex Editing", "Connect to PDUWP to edit skill data.")
            return

        enable_editing = not self.editing_enabled
        if enable_editing:
            if self._current_hex_limit <= 0:
                QMessageBox.information(
                    self,
                    "Hex Editing",
                    "Skill data not available for editing. Provide a hex dump first.",
                )
                return
            self._last_valid_hex_text = self.hex_view.toPlainText()
            self._set_edit_mode(True)
            self.hex_view.setFocus()
            self.hex_view.moveCursor(QTextCursor.MoveOperation.End)
            return

        if not self._validate_hex_length():
            self.hex_view.setFocus()
            return

        self._store_current_hex()
        self._set_edit_mode(False)

    def _set_edit_mode(self, enabled: bool, *, update_button: bool = True) -> None:
        requested = bool(enabled and self.can_edit and self._current_hex_limit > 0)
        self.editing_enabled = requested
        self.hex_view.setReadOnly(not self.editing_enabled)
        self.hex_view.setToolTip(
            self._editing_tooltip() if self.editing_enabled else self._ready_tooltip()
        )

        self.hex_view.setOverwriteMode(self.editing_enabled)

        if update_button:
            if self.editing_enabled:
                self.edit_button.setEnabled(True)
                self.edit_button.setText("Done")
                self.edit_button.setToolTip(self._editing_tooltip())
            else:
                can_enable = self.can_edit and self._current_hex_limit > 0
                self.edit_button.setEnabled(can_enable)
                self.edit_button.setText("Edit Hex")
                self.edit_button.setToolTip(self._ready_tooltip())
        elif not self.editing_enabled:
            self.edit_button.setToolTip(self._ready_tooltip())

    def _store_current_hex(self) -> None:
        if not self.records or not (0 <= self.current_index < len(self.records)):
            return

        raw_text = self.hex_view.toPlainText()
        trimmed = raw_text.rstrip("\n")
        previous_hex = self.records[self.current_index].get("hex_dump", "")
        canonical = trimmed
        save_success = True

        if self.save_callback:
            save_success = self.save_callback(self.current_index, trimmed)
            canonical = self.records[self.current_index].get("hex_dump", trimmed)
        else:
            self.records[self.current_index]["hex_dump"] = trimmed

        if save_success:
            self._last_valid_hex_text = canonical
            if canonical != trimmed:
                self._hex_guard = True
                self.hex_view.setPlainText(canonical)
                self.hex_view.moveCursor(QTextCursor.MoveOperation.End)
                self._hex_guard = False
        else:
            self.records[self.current_index]["hex_dump"] = previous_hex
            self._hex_guard = True
            self.hex_view.setPlainText(previous_hex)
            self.hex_view.moveCursor(QTextCursor.MoveOperation.End)
            self._hex_guard = False
            self._last_valid_hex_text = previous_hex

    def _limit_phrase(self) -> str:
        limit = self._current_hex_limit
        if limit <= 0:
            return "0x00 (0 values)"
        return f"0x{limit:02X} ({limit} values)"

    def _editing_tooltip(self) -> str:
        return (
            f"Editing enabled. Keep length at {self._limit_phrase()}. "
            "Use Ctrl+Z, Ctrl+C, and Ctrl+V."
        )

    def _ready_tooltip(self) -> str:
        if not self.can_edit:
            return "Connect to PDUWP to enable hex editing."
        if self._current_hex_limit <= 0:
            return "Skill data not available; editing disabled."
        return f"Read-only view. Click Edit Hex to modify (must stay {self._limit_phrase()})."

    def _show_limit_warning(self, message: str) -> None:
        if self._limit_warning_active:
            return
        self._limit_warning_active = True
        QMessageBox.warning(self, "Hex Length Limit", message)
        self._limit_warning_active = False

    def _replace_next_hex_char(self, char: str) -> None:
        if self._current_hex_limit <= 0:
            self._show_limit_warning("No hex data available yet; nothing to overwrite.")
            return

        text = self.hex_view.toPlainText()
        if not text:
            return

        cursor = self.hex_view.textCursor()
        position = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        position = max(0, min(position, len(text) - 1))

        while position < len(text) and text[position] not in HEX_DIGITS:
            position += 1

        if position >= len(text):
            self._show_limit_warning("Move the cursor onto a hex value before typing.")
            return

        replace_cursor = self.hex_view.textCursor()
        replace_cursor.setPosition(position)
        replace_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)

        self._hex_guard = True
        replace_cursor.insertText(char.upper())
        self._hex_guard = False

        updated_text = self.hex_view.toPlainText()
        next_position = position + 1
        while next_position < len(updated_text) and updated_text[next_position] not in HEX_DIGITS:
            next_position += 1

        next_cursor = self.hex_view.textCursor()
        next_cursor.setPosition(min(next_position, len(updated_text)))
        self.hex_view.setTextCursor(next_cursor)

        self._last_valid_hex_text = updated_text

    def _on_hex_text_changed(self) -> None:
        if self._hex_guard:
            return

        text = self.hex_view.toPlainText()

        if not self.editing_enabled:
            self._last_valid_hex_text = text
            return

        if self._current_hex_limit <= 0:
            self._last_valid_hex_text = text
            return

        pair_count, invalid_tokens = hex_token_stats(text)

        if invalid_tokens or pair_count != self._current_hex_limit:
            self._hex_guard = True
            self.hex_view.setPlainText(self._last_valid_hex_text)
            self.hex_view.moveCursor(QTextCursor.MoveOperation.Start)
            self._hex_guard = False

            if invalid_tokens:
                preview = ", ".join(invalid_tokens[:3])
                if len(invalid_tokens) > 3:
                    preview += ", ..."
                self._show_limit_warning(
                    "Invalid hex values detected. Paste two-digit hex bytes only. "
                    f"Problem values: {preview}."
                )
            else:
                self._show_limit_warning(
                    f"Hex data length must stay at {self._limit_phrase()}. Paste a block with the same length."
                )
            return

        self._last_valid_hex_text = text

    def _perform_overwrite_paste(self) -> None:
        if self._current_hex_limit <= 0:
            self._show_limit_warning("No hex data available yet; nothing to overwrite.")
            return

        clipboard_text = QApplication.clipboard().text()
        sanitized = clipboard_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not sanitized:
            self._show_limit_warning("Clipboard is empty; copy hex bytes before pasting.")
            return

        pair_count, invalid_tokens = hex_token_stats(sanitized)
        if invalid_tokens:
            preview = ", ".join(invalid_tokens[:3])
            if len(invalid_tokens) > 3:
                preview += ", ..."
            self._show_limit_warning(
                "Clipboard data contains invalid values. Provide two-digit hex bytes only. "
                f"Problem values: {preview}."
            )
            return

        if pair_count != self._current_hex_limit:
            self._show_limit_warning(
                f"Clipboard block must contain exactly {self._limit_phrase()}."
            )
            return

        formatted = normalize_hex_text(sanitized)

        self._hex_guard = True
        self.hex_view.setPlainText(formatted)
        self.hex_view.moveCursor(QTextCursor.MoveOperation.Start)
        self._hex_guard = False

        self._last_valid_hex_text = formatted

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.hex_view:
            if self.editing_enabled:
                if event.type() == QEvent.Type.KeyPress:
                    key_event = cast(QKeyEvent, event)

                    if key_event.matches(QKeySequence.StandardKey.Paste):
                        self._perform_overwrite_paste()
                        return True

                    if (
                        key_event.matches(QKeySequence.StandardKey.Copy)
                        or key_event.matches(QKeySequence.StandardKey.SelectAll)
                        or key_event.matches(QKeySequence.StandardKey.Undo)
                        or key_event.matches(QKeySequence.StandardKey.Redo)
                    ):
                        return False

                    if key_event.matches(QKeySequence.StandardKey.Cut):
                        self._show_limit_warning("Cut is disabled; paste over existing bytes instead.")
                        return True

                    blocked_keys = {
                        Qt.Key.Key_Backspace,
                        Qt.Key.Key_Delete,
                        Qt.Key.Key_Return,
                        Qt.Key.Key_Enter,
                        Qt.Key.Key_Tab,
                    }
                    if key_event.key() in blocked_keys:
                        self._show_limit_warning(
                            "Hex edits preserve size. Use Ctrl+V to overwrite with prepared bytes."
                        )
                        return True

                    if key_event.text():
                        if key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                            return False

                        literal = key_event.text()
                        if literal:
                            value = literal.upper()
                            if value in HEX_DIGITS:
                                self._replace_next_hex_char(value)
                                return True

                        self._show_limit_warning(
                            "Only hexadecimal characters (0-9, A-F) are allowed when editing bytes."
                        )
                        return True

        return super().eventFilter(obj, event)

    def _validate_hex_length(self, *, show_message: bool = True) -> bool:
        if self._current_hex_limit <= 0:
            return True

        text = self.hex_view.toPlainText()
        pair_count, invalid_tokens = hex_token_stats(text)

        if invalid_tokens:
            if show_message:
                preview = ", ".join(invalid_tokens[:3])
                if len(invalid_tokens) > 3:
                    preview += ", ..."
                self._show_limit_warning(
                    "All entries must be two-digit hex values (e.g., '0A'). "
                    f"Invalid entries: {preview}."
                )
            return False

        if pair_count != self._current_hex_limit:
            if show_message:
                if pair_count < self._current_hex_limit:
                    deficit = self._current_hex_limit - pair_count
                    self._show_limit_warning(
                        f"Skill data is missing {deficit} value(s). Keep the length at {self._limit_phrase()}."
                    )
                else:
                    surplus = pair_count - self._current_hex_limit
                    self._show_limit_warning(
                        f"Skill data has {surplus} extra value(s). Keep the length at {self._limit_phrase()}."
                    )
            return False

        self._last_valid_hex_text = text
        return True

MAP_SUMMARY = [
    (
        "Debug Stage",
        "Developer testing arena surfaced by debug mode, stocked with Attack, Defense, Special, Erase, Status, Environmental, and Aura Particle capsules.",
    ),
    (
        "Palace",
        "Japanese shopping mall crowned by a massive tree weaving through its bridges; features three tiers with an inaccessible upper deck.",
    ),
    (
        "Highway",
        "Dual-level expressway with a stranded car and a rear roadway twisted skyward yet still anchored to the asphalt.",
    ),
    (
        "Panorama",
        "Indoor office complex overlooking distant ruins, split between upper and lower floors.",
    ),
    (
        "Strange City",
        "Gravity-inverted streets scattered with floating trucks and signage.",
    ),
    (
        "Refinery",
        "Rust-worn offshore oil platform sporting cranes and a helicopter amid open ocean.",
    ),
    (
        "Lane",
        "Memory-soaked town packed with buildings, stairways, and gravity lifts soaring thirty feet high; Sein looms in the distant sky.",
    ),
    (
        "Sein",
        "Floating island dominated by a colossal, ever-growing broken tower at its center.",
    ),
]

MAP_INDEX = [
    {"map": "Debug Stage", "map_name": "Debug Stage", "internal": "DUMMY", "id": "st00"},
    {"map": "Edgar's Dream", "map_name": "Edgar's Dream", "internal": "LD_InsideofRuin", "id": "st01"},
    {"map": "Highway", "map_name": "Spiral Highway", "internal": "Highway-evening", "id": "st02"},
    {"map": "Palace", "map_name": "Lost Palace", "internal": "Palace-blue", "id": "st03"},
    {"map": "Panorama", "map_name": "Panorama Earthquake", "internal": "Panorama-earth", "id": "st04"},
    {"map": "Strange City", "map_name": "Dawn City", "internal": "City-orenge", "id": "st05"},
    {"map": "Refinery", "map_name": "Storm Refinery", "internal": "Plant-blue", "id": "st06"},
    {"map": "Lane", "map_name": "Twilight Lane", "internal": "TownofMemory", "id": "st07"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Ruin", "id": "st08"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st09"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st10"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st11"},
    {"map": "Highway", "map_name": "Lightning Highway", "internal": "Highway-thunder", "id": "st12"},
    {"map": "Palace", "map_name": "Light Palace", "internal": "Palace-yellow", "id": "st13"},
    {"map": "Panorama", "map_name": "Panorama Building", "internal": "Panorama-fog", "id": "st14"},
    {"map": "Strange City", "map_name": "Dusk City", "internal": "City-gray", "id": "st15"},
    {"map": "Refinery", "map_name": "Sunset Refinery", "internal": "Plant-yellow", "id": "st16"},
    {"map": "Lane", "map_name": "Silent Lane", "internal": "TownofMemory-blue", "id": "st17"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st18"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st19"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st20"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st21"},
    {"map": "Highway", "map_name": "Sunlight Highway", "internal": "Highway-summer", "id": "st22"},
    {"map": "Palace", "map_name": "Noble Palace", "internal": "Palace-red", "id": "st23"},
    {"map": "Panorama", "map_name": "Panorama Boss", "internal": "Panorama-boss", "id": "st24"},
    {"map": "Strange City", "map_name": "Midnight City", "internal": "City-blue", "id": "st25"},
    {"map": "Refinery", "map_name": "Acid Refinery", "internal": "Plant-darkblue", "id": "st26"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st27"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st28"},
    {"map": "Dummy", "map_name": "Dummy", "internal": "Dummy", "id": "st29"},
]

PLAYABLE_CHARACTERS = [
    {"name": "Alpha (underground model)", "id": "evpc00a"},
    {"name": "Alpha (gameplay model)", "id": "pc00a"},
    {"name": "Edgar", "id": "pc01a"},
    {"name": "Freia", "id": "pc02a"},
    {"name": "Meister", "id": "pc03a"},
    {"name": "Chunky", "id": "pc04a"},
    {"name": "Cuff Button", "id": "pc05a"},
    {"name": "pH", "id": "pc06a"},
    {"name": "Know", "id": "pc07a"},
    {"name": "Tsubutaki", "id": "pc08a"},
    {"name": "JD", "id": "pc09a"},
    {"name": "Sammah", "id": "pc10a"},
]

NPC_CHARACTERS = [
    {"name": "Leader", "id": "npc00a"},
    {"name": "03", "id": "npc01a"},
    {"name": "Spokesman", "id": "npc02a"},
    {"name": "Ubiquitous", "id": "npc03a"},
    {"name": "Kajikawa", "id": "npc04a"},
    {"name": "Tetsuya", "id": "npc05a"},
    {"name": "Arthur", "id": "npc06a"},
    {"name": "Reindeer", "id": "npc07a"},
    {"name": "Mac", "id": "npc08a"},
    {"name": "Baroness", "id": "npc09a"},
    {"name": "Mikan", "id": "npc10a"},
    {"name": "Ai", "id": "npc11a"},
    {"name": "Maniac", "id": "npc12a"},
    {"name": "Kei", "id": "npc13a"},
]

ENEMY_CHARACTERS = [
    {"name": "Ommato", "id": "enm00a"},
    {"name": "Scoto", "id": "enm01a"},
    {"name": "Claustro", "id": "enm02a"},
    {"name": "Catoptro", "id": "enm03a"},
    {"name": "Mechano", "id": "enm04a"},
    {"name": "Gyne", "id": "enm05a"},
    {"name": "Euroto", "id": "enm06a"},
    {"name": "Hedono", "id": "enm07a"},
    {"name": "Anthro", "id": "enm08a"},
    {"name": "Andro", "id": "enm09a"},
    {"name": "Vestio", "id": "enm10a"},
    {"name": "Partheno", "id": "enm11a"},
    {"name": "Guard", "id": "enm12a"},
    {"name": "Ceno", "id": "enm13a"},
    {"name": "Germano", "id": "enm14a"},
    {"name": "Belono", "id": "enm15a"},
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("BBMODS Edgar's Dream World")
        self.resize(1200, 700)

        # Track connection state
        self.connected = False
        self.memory_client = WindowsMemoryEditor()
        self._skill_table_base: int | None = None

        # Root widget
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Left activity bar (like VS Code icons bar)
        self.activity_bar = QFrame()
        self.activity_bar.setFixedWidth(48)
        self.activity_bar.setStyleSheet(f"background-color: {VS_SIDEBAR};")
        root_layout.addWidget(self.activity_bar)

        # Main column: top tab bar, middle editor, bottom status
        main_column = QVBoxLayout()
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(0)
        root_layout.addLayout(main_column)

        # Top "tab" bar
        self.tab_bar = QFrame()
        self.tab_bar.setFixedHeight(32)
        self.tab_bar.setStyleSheet(f"background-color: {VS_TABBAR};")
        tab_layout = QHBoxLayout(self.tab_bar)
        tab_layout.setContentsMargins(8, 0, 0, 0)
        tab_layout.setSpacing(16)

        self.tab_label = QLabel("Awaiting for PDUWP Connection.")
        self.tab_label.setStyleSheet(f"color: {VS_TEXT};")
        tab_layout.addWidget(self.tab_label)
        tab_layout.addStretch()

        main_column.addWidget(self.tab_bar)

        # Editor area (center)
        self.editor_area = QFrame()
        self.editor_area.setStyleSheet(f"background-color: {VS_BG};")
        editor_layout = QVBoxLayout(self.editor_area)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(8)

        title = QLabel("Intro.")
        title.setStyleSheet("color: #ffffff; font-size: 18px;")
        editor_layout.addWidget(title)

        self.intro_label = QLabel("")
        self.intro_label.setStyleSheet(f"color: {VS_TEXT};")
        self.intro_label.setWordWrap(True)
        self.intro_opacity_effect = QGraphicsOpacityEffect(self.intro_label)
        self.intro_label.setGraphicsEffect(self.intro_opacity_effect)
        self.intro_opacity_effect.setOpacity(1.0)
        editor_layout.addWidget(self.intro_label)

        self.intro_full_text = (
            "Welcome to the BBMODS control surface for Edgar's Dream World.\n"
            "This demo build is a stand-in while the official program is being developed, showcasing the workflow to come.\n"
            "Step 1: ensure PDUWP.exe is running so the controller can auto-connect.\n"
            "When connected, expand a menu label to reveal its tools; only one section stays open at a time for clarity.\n"
            "Use the status footer to trigger manual connection checks and watch for live feedback on session state."
        )
        self.intro_display_index = 0
        self.intro_timer = QTimer(self)
        self.intro_timer.setInterval(35)
        self.intro_timer.timeout.connect(self._advance_intro_text)
        self.intro_timer.start()
        self.intro_fade_animation: QPropertyAnimation | None = None

        self.menu_panel = QFrame()
        self.menu_panel.setStyleSheet(
            "QFrame {"
            "background-color: #242424;"
            "border: 1px solid #2f2f2f;"
            "border-radius: 4px;"
            "}"
        )
        menu_layout = QVBoxLayout(self.menu_panel)
        menu_layout.setContentsMargins(12, 12, 12, 12)
        menu_layout.setSpacing(8)
        menu_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.menu_sections: Dict[str, Dict[str, Any]] = {}
        self.active_menu: str | None = None
        self.skill_records = self._load_skill_records()
        self._blink_timers: List[QTimer] = []

        for name in ("Skills", "Maps", "Characters", "Menus", "Audio", "Campaign"):
            section = self._build_menu_section(name)
            menu_layout.addWidget(section["wrapper"])
            self.menu_sections[name] = section

        self._initialize_menu_content()

        self.menu_panel.setVisible(False)
        editor_layout.addWidget(self.menu_panel)

        editor_layout.addStretch()
        main_column.addWidget(self.editor_area)

        # Bottom status bar
        self.status_bar = QFrame()
        self.status_bar.setFixedHeight(24)
        self.status_bar.setStyleSheet("background-color: #007acc;")
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(8, 0, 8, 0)
        status_layout.setSpacing(12)

        self.status_label = QLabel("PDUWP: Not Connected")
        self.status_label.setStyleSheet("color: #ffffff; font-size: 11px;")
        status_layout.addWidget(self.status_label)

        self.memory_label = QLabel("Memory: idle")
        self.memory_label.setStyleSheet("color: #ffffff; font-size: 11px;")
        status_layout.addWidget(self.memory_label)

        status_layout.addStretch()

        self.connect_button = QPushButton("Not Connected")
        self.connect_button.setFixedHeight(18)
        self.connect_button.setStyleSheet(self._button_style(connected=False))
        self.connect_button.clicked.connect(self.manual_connect_attempt)
        status_layout.addWidget(self.connect_button)

        main_column.addWidget(self.status_bar)

        # Timer to auto check process every 2 seconds
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_pduwp_process)
        self.timer.start(2000)

        # Initial check
        self.check_pduwp_process()

    def _button_style(self, connected: bool) -> str:
        if connected:
            return (
                "QPushButton {"
                "background-color: #16825d;"
                "color: #ffffff;"
                "border: 1px solid #0e5c40;"
                "border-radius: 2px;"
                "padding: 0 6px;"
                "font-size: 11px;"
                "}"
                "QPushButton:hover {"
                "background-color: #1ea06f;"
                "}"
            )
        else:
            return (
                "QPushButton {"
                "background-color: #b22222;"
                "color: #ffffff;"
                "border: 1px solid #7f1515;"
                "border-radius: 2px;"
                "padding: 0 6px;"
                "font-size: 11px;"
                "}"
                "QPushButton:hover {"
                "background-color: #d62828;"
                "}"
            )

    def _set_memory_status(self, message: str) -> None:
        if hasattr(self, "memory_label"):
            self.memory_label.setText(message)

    def find_pduwp_pid(self) -> int | None:
        # Look for PDUWP.exe (case-insensitive)
        for proc in psutil.process_iter(["pid", "name"]):  # type: ignore[misc]
            try:
                name = proc.info["name"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            if not name:
                continue

            if name.lower() in ("pduwp.exe", "pduwp"):
                return proc.info["pid"]
        return None

    def _attach_memory_client(self, pid: int) -> None:
        if not self.memory_client or not self.memory_client.is_supported():
            self._set_memory_status("Memory: not available")
            return

        self._skill_table_base = None
        attached, message = self.memory_client.attach(pid)
        if attached:
            base_value = self.memory_client.base_address or 0
            pid_value = self.memory_client.pid or pid
            self._set_memory_status(
                f"Memory: PID {pid_value} base 0x{base_value:016X}"
            )
        else:
            self._set_memory_status(f"Memory: {message}")

    def _report_live_memory_target(self, record: dict[str, str]) -> None:
        if not self.memory_client or not self.memory_client.attached:
            return

        hex_id = record.get("hex_id")
        if not hex_id:
            return

        block = self._resolve_live_block(hex_id, record)
        if not block:
            return

        absolute_start = block.get("absolute_start")
        target_address: int | None = None
        relative_offset = relative_offset_from_block(block)

        if isinstance(absolute_start, int) and absolute_start:
            target_address = absolute_start
            if (self.memory_client.base_address is not None) and (relative_offset is None):
                relative_offset = absolute_start - self.memory_client.base_address
        elif relative_offset is not None:
            target_address = self.memory_client.address_for_offset(relative_offset)

        if target_address is None:
            return

        try:
            block_length = int(block.get("length", 0))
        except (TypeError, ValueError):
            block_length = 0

        label = str(block.get("label", hex_id))
        relative_value = int(relative_offset) if isinstance(relative_offset, int) else 0
        pid_value = self.memory_client.pid or 0
        self._set_memory_status(
            f"Memory: PID {pid_value} {label} +0x{relative_value:X} -> 0x{target_address:016X} ({block_length} bytes)"
        )

    def _write_live_memory(self, record: dict[str, str], hex_text: str) -> bool:
        if not self.memory_client or not self.memory_client.attached:
            return False

        hex_id = record.get("hex_id")
        if not hex_id:
            return False

        pair_count, invalid_tokens = hex_token_stats(hex_text)
        if invalid_tokens:
            return False

        refreshed_pointer = False
        data = hex_text_to_bytes(hex_text)
        while True:
            block = self._resolve_live_block(hex_id, record)
            if not block:
                return False

            absolute_start = block.get("absolute_start")
            relative_offset = relative_offset_from_block(block)

            try:
                expected_length = int(block.get("length", 0))
            except (TypeError, ValueError):
                expected_length = 0

            if not expected_length and pair_count:
                expected_length = pair_count

            if expected_length and len(data) != expected_length:
                label = str(block.get("label", hex_id))
                self._set_memory_status(
                    f"Memory: length mismatch for {label} (expected {expected_length} bytes, got {len(data)})"
                )
                return False

            target_address: int | None = None
            if isinstance(absolute_start, int) and absolute_start:
                target_address = absolute_start
                if relative_offset is None and self.memory_client.base_address is not None:
                    relative_offset = absolute_start - self.memory_client.base_address
            elif relative_offset is not None:
                target_address = self.memory_client.address_for_offset(relative_offset)

            if target_address is None or relative_offset is None:
                return False

            success, message = self.memory_client.write_memory(target_address, data)
            if success:
                label = str(block.get("label", hex_id))
                pid_value = self.memory_client.pid or 0
                relative_value = int(relative_offset)
                self._set_memory_status(
                    f"Memory: PID {pid_value} wrote {len(data)} bytes to {label} @ 0x{target_address:016X} (+0x{relative_value:X})"
                )
                return True

            if not refreshed_pointer and self._skill_table_base is not None:
                refreshed_pointer = True
                self._skill_table_base = None
                block.pop("absolute_start", None)
                continue

            self._set_memory_status(f"Memory: {message}")
            return False

    def _resolve_live_block(
        self,
        hex_id: str,
        record: dict[str, str] | None = None,
    ) -> dict[str, int | str] | None:
        """Look up or derive the live memory block for a skill."""
        base_address = self._skill_table_base_address()
        if base_address is not None:
            try:
                skill_index = int(str(hex_id), 16)
            except (TypeError, ValueError):
                skill_index = -1
            if 0 <= skill_index < MAX_SKILL_INDEX:
                absolute_start = base_address + (skill_index * SKILL_BLOCK_SIZE)
                relative_offset = None
                if self.memory_client and self.memory_client.base_address is not None:
                    relative_offset = absolute_start - self.memory_client.base_address

                label = hex_id
                if record:
                    label = record.get("name", label) or label

                dynamic_block: dict[str, int | str] = {
                    "absolute_start": absolute_start,
                    "length": SKILL_BLOCK_SIZE,
                    "label": label,
                }
                if relative_offset is not None:
                    dynamic_block["relative_offset"] = relative_offset

                existing = LIVE_MEMORY_BLOCKS.get(hex_id, {})
                existing.update(dynamic_block)
                LIVE_MEMORY_BLOCKS[hex_id] = existing
                return existing

        cached = LIVE_MEMORY_BLOCKS.get(hex_id)
        if cached:
            return cached

        relative_offset = skill_relative_offset_from_hex(hex_id)
        if relative_offset is None:
            return None

        label = hex_id
        if record:
            label = record.get("name", label) or label

        block: dict[str, int | str] = {
            "relative_offset": relative_offset,
            "absolute_hint": REFERENCE_MODULE_BASE + relative_offset,
            "length": SKILL_BLOCK_SIZE,
            "label": label,
        }
        LIVE_MEMORY_BLOCKS[hex_id] = block
        return block

    def _skill_table_base_address(self) -> int | None:
        if not self.memory_client or not self.memory_client.attached:
            return None

        if self._skill_table_base is not None:
            return self._skill_table_base

        pointer_address = self.memory_client.address_for_offset(SKILL_TABLE_POINTER_OFFSET)
        if pointer_address is None:
            return None

        pointer_size = ctypes.sizeof(ctypes.c_void_p)
        success, payload, message = self.memory_client.read_memory(pointer_address, pointer_size)
        if not success or payload is None:
            if message:
                self._set_memory_status(f"Memory: {message}")
            return None

        base_address = int.from_bytes(payload, byteorder="little", signed=False)
        if not base_address:
            return None

        self._skill_table_base = base_address
        pid_value = self.memory_client.pid or 0
        base_offset = 0
        if self.memory_client.base_address is not None:
            base_offset = base_address - self.memory_client.base_address
        self._set_memory_status(
            f"Memory: PID {pid_value} skill table @ 0x{base_address:016X} (+0x{base_offset:X})"
        )
        return self._skill_table_base

    def update_status(self, pid: int | None):
        if pid is None:
            if self.connected:
                self.connected = False
            self.status_label.setText("PDUWP: Not Connected")
            self.connect_button.setText("Not Connected")
            self.connect_button.setStyleSheet(self._button_style(connected=False))
            self.tab_label.setText("Awaiting for PDUWP Connection.")
            self._set_menu_visibility(False)
            if self.memory_client:
                self.memory_client.detach()
            self._set_memory_status("Memory: idle")
            self._skill_table_base = None
        else:
            if not self.connected:
                self.connected = True
            self.status_label.setText(f"PDUWP: Connected (PID {pid})")
            self.connect_button.setText("Connected")
            self.connect_button.setStyleSheet(self._button_style(connected=True))
            self.tab_label.setText("PDUWP Connection Confirmed!")
            self._set_menu_visibility(True)
            self._attach_memory_client(pid)

    def check_pduwp_process(self):
        pid = self.find_pduwp_pid()
        self.update_status(pid)

    def manual_connect_attempt(self):
        # Manual button press re-checks immediately
        self.check_pduwp_process()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self.memory_client:
            self.memory_client.detach()
        super().closeEvent(event)

    def _build_menu_section(self, title: str) -> Dict[str, Any]:
        wrapper = QFrame()
        wrapper.setStyleSheet(
            "QFrame {"
            "background-color: #1e1e1e;"
            "border: 1px solid #333333;"
            "border-radius: 3px;"
            "}"
        )
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(6)

        toggle_button = QPushButton(title)
        toggle_button.setCheckable(True)
        toggle_button.setChecked(False)
        toggle_button.setStyleSheet(self._menu_button_style(expanded=False, highlighted=False))
        toggle_button.clicked.connect(partial(self._toggle_section, title))
        layout.addWidget(toggle_button)

        content = QFrame()
        content.setStyleSheet("background-color: #252525; border-radius: 2px;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 8, 10, 8)
        content_layout.setSpacing(4)

        placeholder = QLabel("DEBUG placeholder")
        placeholder.setStyleSheet(f"color: {VS_TEXT}; font-style: italic;")
        content_layout.addWidget(placeholder)

        content.setVisible(False)
        layout.addWidget(content)

        opacity_effect = QGraphicsOpacityEffect(wrapper)
        opacity_effect.setOpacity(1.0)
        wrapper.setGraphicsEffect(opacity_effect)

        return {
            "wrapper": wrapper,
            "button": toggle_button,
            "content": content,
            "expanded": False,
            "placeholder": placeholder,
            "layout": content_layout,
            "effect": opacity_effect,
        }

    def _initialize_menu_content(self):
        initializers = {
            "Skills": self._populate_skills_menu,
            "Menus": self._populate_menus_menu,
            "Maps": self._populate_maps_menu,
            "Characters": self._populate_characters_menu,
            "Audio": self._populate_audio_menu,
            "Campaign": self._populate_campaign_menu,
        }

        for name, builder in initializers.items():
            section = self.menu_sections.get(name)
            if not section:
                continue
            section["placeholder"].setParent(None)
            builder(section["layout"])

    def _load_skill_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for meta_path in sorted(SKILL_DATA_ROOT.glob("*/meta.yaml")):
            meta = self._parse_skill_meta(meta_path)
            if not meta:
                continue

            folder = meta_path.parent
            skill_data_path = folder / "skill_data.txt"
            if skill_data_path.exists():
                try:
                    hex_dump = skill_data_path.read_text(encoding="utf-8").strip()
                except OSError:
                    hex_dump = "Skill data file could not be read."
            else:
                hex_dump = "Skill data file not yet provided."

            pair_count, invalid_tokens = hex_token_stats(hex_dump)
            hex_limit_value = str(pair_count) if pair_count and not invalid_tokens else "0"

            raw_index = meta.get("order_index")
            if isinstance(raw_index, int):
                order_index_val = raw_index
            else:
                try:
                    order_index_val = int(str(raw_index))
                except (TypeError, ValueError):
                    order_index_val = len(records)

            def _text(value: Any, default: str = "-") -> str:
                if value is None:
                    return default
                text = str(value)
                return text if text else default

            air_allowed_value = meta.get("air_allowed")
            if air_allowed_value is None and "area_allowed" in meta:
                air_allowed_value = meta.get("area_allowed")

            record = {
                "order_index": str(order_index_val),
                "name": _text(meta.get("name"), folder.name.replace("_", " ").title()),
                "hex_id": _text(meta.get("id_hex"), "0x0000"),
                "school": _text(meta.get("school")),
                "type": _text(meta.get("capsule_type")),
                "cost": _text(meta.get("cost")),
                "strength": _text(meta.get("strength")),
                "uses": _text(meta.get("uses")),
                "range": _text(meta.get("range")),
                "rarity": _text(meta.get("rarity"), "Rarity ★"),
                "description": _text(meta.get("description"), "Official data pending."),
                "accuracy": _text(meta.get("accuracy")),
                "air_allowed": _text(air_allowed_value),
                "hit_box": _text(meta.get("hit_box")),
                "projectile_count": _text(meta.get("projectile_count")),
                "projectile_behavior": _text(meta.get("projectile_behavior")),
                "skill_category": _text(meta.get("skill_category"), _text(meta.get("capsule_type"))),
                "display_id": _text(meta.get("display_id")),
                "register_id": _text(meta.get("register_id")),
                "optional_id": _text(meta.get("optional_id")),
                "hex_dump": hex_dump if hex_dump else "Skill data file not yet provided.",
                "hex_limit": hex_limit_value,
                "folder_path": str(folder),
                "skill_file": str(skill_data_path),
                "baseline_hex_dump": hex_dump if pair_count and not invalid_tokens else "",
            }
            records.append(record)

        records.sort(key=lambda r: int(r.get("order_index", "0")))
        return records

    def _parse_skill_meta(self, meta_path: Path) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            lines = meta_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return data

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue

            key, sep, value = raw_line.partition(":")
            if not sep:
                continue

            key = key.strip()
            value = value.strip().strip('"')
            if not value:
                continue

            if key == "order_index":
                try:
                    data[key] = int(value)
                except ValueError:
                    continue
            else:
                data[key] = value

        return data

    def _populate_skills_menu(self, layout: QVBoxLayout):
        base_stock_description = (
            "View, favorite, compare, sort, search, filter, import, and export all 375 original Phantom Dust skills plus any custom skills."
        )
        warning_suffix = "WARNING PLACEHOLDERS WILL BE PRESENT THIS IS W.I.P"
        items = (
            (
                "Stock(W.I.P)",
                f"{base_stock_description} {warning_suffix}",
                self._open_stock_browser,
            ),
            (
                "Arsenal Lab",
                "Create, edit, import, and export arsenals.",
                None,
            ),
            (
                "Stats",
                "Review official data for the 375 legacy skills and any imported customs with favorite, compare, sort, search, and filter tools.",
                partial(self._open_skill_stats_example),
            ),
            (
                "Textures",
                "Manage skill-related artwork by importing or exporting the school icon texture bundle for safe replacement.",
                None,
            ),
            (
                "Create",
                "Create, import, or export a skill from the original Phantom Dust list (IDs 0-375).",
                None,
            ),
            (
                "Skill Request",
                "Request a new skill by selecting categories and subcategories mapped to official data to ensure feasible builds.",
                None,
            ),
        )

        for title, description, handler in items:
            widget = self._menu_entry_widget(title, description)
            if handler:
                button_label = "Browse" if title.startswith("Stock") else "Open"
                button = QPushButton(button_label)
                button.setStyleSheet(
                    "QPushButton {"
                    "background-color: #3c3c3c;"
                    "color: #ffffff;"
                    "border: 1px solid #4a4a4a;"
                    "border-radius: 3px;"
                    "padding: 4px 10px;"
                    "font-size: 12px;"
                    "}"
                    "QPushButton:hover {"
                    "background-color: #4b4b4b;"
                    "}"
                )
                handler_button_layout = widget.layout()
                if handler_button_layout is not None:
                    handler_button_layout.addWidget(button)
                    handler_button_layout.setSpacing(6)
                button.clicked.connect(handler)  # type: ignore[arg-type]
                if title.startswith("Stock"):
                    self._apply_slow_blink(button)
                    body_label = widget.findChild(QLabel, "menu-body")
                    if body_label is not None:
                        self._apply_warning_flash(body_label, base_stock_description, warning_suffix)
            layout.addWidget(widget)

        layout.addStretch()

    def _apply_slow_blink(self, button: QPushButton) -> None:
        colors = ("#f1c232", "#ffd966")

        def style_for(color: str) -> str:
            return (
                "QPushButton {"
                f"background-color: {color};"
                "color: #1b1b1b;"
                "border: 1px solid #806000;"
                "border-radius: 3px;"
                "padding: 4px 10px;"
                "font-size: 12px;"
                "font-weight: bold;"
                "}"
                "QPushButton:hover {"
                "background-color: #ffe699;"
                "}"
            )

        button.setStyleSheet(style_for(colors[0]))
        button.setProperty("_blink_index", 0)

        timer = QTimer(self)
        timer.setInterval(1200)

        def on_timeout() -> None:
            index = int(button.property("_blink_index") or 0)
            index = (index + 1) % len(colors)
            button.setProperty("_blink_index", index)
            button.setStyleSheet(style_for(colors[index]))

        timer.timeout.connect(on_timeout)
        timer.start()
        self._blink_timers.append(timer)

    def _apply_warning_flash(self, label: QLabel, base_text: str, warning_text: str) -> None:
        label.setTextFormat(Qt.TextFormat.RichText)
        colors = ("#f1c232", "#ffffff")

        def render(color: str) -> None:
            label.setText(
                f"{html.escape(base_text)} "
                f"<span style='color:{color}; font-weight:bold;'>{html.escape(warning_text)}</span>"
            )

        render(colors[0])
        label.setProperty("_warning_index", 0)

        timer = QTimer(self)
        timer.setInterval(1300)

        def on_timeout() -> None:
            index = int(label.property("_warning_index") or 0)
            index = (index + 1) % len(colors)
            label.setProperty("_warning_index", index)
            render(colors[index])

        timer.timeout.connect(on_timeout)
        timer.start()
        self._blink_timers.append(timer)

    def _fetch_skill_hex_data(self, index: int) -> str:
        if not (0 <= index < len(self.skill_records)):
            return "Skill data file not yet provided."

        record = self.skill_records[index]
        resolved_dump = None

        if self.memory_client and self.memory_client.attached:
            resolved_dump = self._load_skill_from_memory(record)

        if not resolved_dump:
            resolved_dump = self._load_skill_from_disk(record)

        if not resolved_dump:
            resolved_dump = "Skill data file not yet provided."

        self._report_live_memory_target(record)
        return resolved_dump

    def _debug_locate_skill(self, hex_id: str) -> None:
        if not self.memory_client or not self.memory_client.attached:
            QMessageBox.information(
                self,
                "Live Memory",
                "Attach to PDUWP.exe before running the debug locator.",
            )
            return

        record = next((r for r in self.skill_records if r.get("hex_id") == hex_id), None)
        if not record:
            QMessageBox.warning(
                self,
                "Live Memory",
                f"No skill record found for hex id {hex_id}.",
            )
            return

        refreshed_pointer = False
        while True:
            block = self._resolve_live_block(hex_id, record)
            if not block:
                QMessageBox.warning(
                    self,
                    "Live Memory",
                    f"Unable to resolve live memory block for {hex_id}.",
                )
                return

            base_pointer = self._skill_table_base_address()
            relative_offset = relative_offset_from_block(block)
            absolute_start = block.get("absolute_start")

            target_address: int | None = None
            if isinstance(absolute_start, int) and absolute_start:
                target_address = absolute_start
                if relative_offset is None and self.memory_client.base_address is not None:
                    relative_offset = absolute_start - self.memory_client.base_address

            if target_address is None and relative_offset is not None:
                target_address = self.memory_client.address_for_offset(relative_offset)

            if target_address is None or relative_offset is None:
                QMessageBox.warning(
                    self,
                    "Live Memory",
                    "Unable to derive a concrete address for the requested skill block.",
                )
                return

            success, payload, message = self.memory_client.read_memory(target_address, SKILL_BLOCK_SIZE)
            if success and payload is not None:
                break

            if not refreshed_pointer and self._skill_table_base is not None:
                refreshed_pointer = True
                self._skill_table_base = None
                block.pop("absolute_start", None)
                continue

            detail = message if message else "ReadProcessMemory returned no data."
            QMessageBox.warning(
                self,
                "Live Memory",
                (
                    f"Read attempt failed for {record.get('name', hex_id)} (hex {hex_id}).\n"
                    f"Address: 0x{target_address:016X}\n"
                    f"Reason: {detail}"
                ),
            )
            return

        snippet = " ".join(f"{byte:02X}" for byte in payload[:16])
        message_lines = [
            f"Skill: {record.get('name', hex_id)}",
            f"Hex ID: {hex_id}",
            f"Skill Table Pointer: 0x{base_pointer:016X}" if base_pointer else "Skill Table Pointer: unresolved",
            f"Relative Offset: +0x{relative_offset:X}",
            f"Absolute Address: 0x{target_address:016X}",
            f"Bytes[0:16]: {snippet}",
            f"Block Size: {len(payload)} bytes",
        ]
        QMessageBox.information(
            self,
            "Live Memory",
            "\n".join(message_lines),
        )

    def _load_skill_from_disk(self, record: dict[str, str]) -> str | None:
        path_value = record.get("skill_file")
        if not path_value:
            return None

        skill_path = Path(path_value)
        try:
            if not skill_path.exists():
                return None
            raw_text = skill_path.read_text(encoding="utf-8")
        except OSError:
            return None

        stripped = raw_text.strip()
        if not stripped:
            return None

        pair_count, invalid_tokens = hex_token_stats(stripped)
        if invalid_tokens or pair_count <= 0:
            record["hex_dump"] = stripped
            return stripped

        formatted = normalize_hex_text(stripped)
        record["hex_dump"] = formatted
        record["hex_limit"] = str(pair_count)
        return formatted

    def _load_skill_from_memory(self, record: dict[str, str]) -> str | None:
        if not self.memory_client or not self.memory_client.attached:
            return None

        hex_id = record.get("hex_id")
        if not hex_id:
            return None

        refreshed_pointer = False
        while True:
            block = self._resolve_live_block(hex_id, record)
            if not block:
                return None

            absolute_start = block.get("absolute_start")
            target_address: int | None = None
            relative_offset = relative_offset_from_block(block)

            if isinstance(absolute_start, int) and absolute_start:
                target_address = absolute_start
            elif relative_offset is not None:
                target_address = self.memory_client.address_for_offset(relative_offset)

            if target_address is None:
                return None

            success, payload, message = self.memory_client.read_memory(target_address, SKILL_BLOCK_SIZE)
            if success and payload is not None:
                break

            if not refreshed_pointer and self._skill_table_base is not None:
                # Pointer may have moved; drop the cached value and retry once.
                refreshed_pointer = True
                self._skill_table_base = None
                block.pop("absolute_start", None)
                continue

            if message:
                self._set_memory_status(f"Memory: {message}")
            return None

        payload_length = len(payload)
        if payload_length != SKILL_BLOCK_SIZE:
            # Notify when the read yielded an unexpected size but still continue with what we have.
            self._set_memory_status(
                f"Memory: expected {SKILL_BLOCK_SIZE} bytes, received {payload_length} (hex {record.get('hex_id', '-')})"
            )

        tokens = " ".join(f"{byte:02X}" for byte in payload)
        formatted = normalize_hex_text(tokens)
        record["hex_dump"] = formatted
        record["hex_limit"] = str(payload_length if payload_length else SKILL_BLOCK_SIZE)
        record["baseline_hex_dump"] = formatted

        pid_value = self.memory_client.pid or 0
        label = record.get("name", record.get("hex_id", "Skill"))
        self._set_memory_status(
            f"Memory: PID {pid_value} read {payload_length} byte(s) for {label}"
        )

        path_value = record.get("skill_file")
        if path_value:
            try:
                Path(path_value).write_text(formatted + "\n", encoding="utf-8")
            except OSError:
                pass

        return formatted

    def _save_skill_data(self, index: int, hex_text: str) -> bool:
        if not (0 <= index < len(self.skill_records)):
            QMessageBox.warning(self, "Save Hex Data", "Invalid skill index.")
            return False

        record = self.skill_records[index]
        folder_value = record.get("folder_path")
        skill_file_value = record.get("skill_file")
        if not folder_value or not skill_file_value:
            QMessageBox.warning(
                self,
                "Save Hex Data",
                "Skill data file paths are not configured for this record.",
            )
            return False

        pair_count, invalid_tokens = hex_token_stats(hex_text)
        if invalid_tokens:
            preview = ", ".join(invalid_tokens[:3])
            if len(invalid_tokens) > 3:
                preview += ", ..."
            QMessageBox.warning(
                self,
                "Save Hex Data",
                (
                    "Hex data contains invalid values. Correct them before saving.\n"
                    f"Problem values: {preview}."
                ),
            )
            return False

        expected_limit = 0
        raw_limit = record.get("hex_limit")
        try:
            expected_limit = int(str(raw_limit))
        except (TypeError, ValueError):
            expected_limit = 0

        if expected_limit and pair_count != expected_limit:
            QMessageBox.warning(
                self,
                "Save Hex Data",
                (
                    f"Hex data must contain {expected_limit} value(s); "
                    f"received {pair_count}."
                ),
            )
            return False

        normalized = normalize_hex_text(hex_text)
        folder = Path(folder_value)
        skill_path = Path(skill_file_value)
        backup_path = folder / BACKUP_FILENAME

        previous_raw: str | None = None
        if skill_path.exists():
            try:
                previous_raw = skill_path.read_text(encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Save Hex Data",
                    f"Could not read existing skill data file:\n{exc}",
                )
                return False

        previous_trimmed = previous_raw.strip() if previous_raw is not None else None
        previous_canonical: str | None = None
        if previous_trimmed:
            prev_pair, prev_invalid = hex_token_stats(previous_trimmed)
            if not prev_invalid and prev_pair > 0:
                previous_canonical = normalize_hex_text(previous_trimmed)

        data_changed = True
        if previous_canonical is not None:
            data_changed = previous_canonical != normalized

        if not data_changed:
            record_hex = previous_canonical or normalized
            record["hex_dump"] = record_hex
            record["hex_limit"] = str(pair_count)
            wrote = self._write_live_memory(record, record_hex)
            if not wrote:
                self._report_live_memory_target(record)
            return True

        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Save Hex Data",
                f"Could not ensure skill folder exists:\n{exc}",
            )
            return False

        if previous_raw is not None and previous_raw.strip() and not backup_path.exists():
            try:
                backup_path.write_text(previous_raw, encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Save Hex Data",
                    f"Could not create a backup copy:\n{exc}",
                )
                return False
            if previous_trimmed and not record.get("baseline_hex_dump"):
                record["baseline_hex_dump"] = previous_trimmed

        try:
            skill_path.write_text((normalized + "\n") if normalized else "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Save Hex Data",
                f"Could not write skill data file:\n{exc}",
            )
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        temp_path = folder / f"{TEMP_EDIT_PREFIX}{timestamp}.txt"
        try:
            temp_path.write_text((normalized + "\n") if normalized else "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Temporary Edit Save",
                (
                    "Skill data saved, but the timestamped copy could not be created.\n"
                    f"Error: {exc}"
                ),
            )

        record["hex_dump"] = normalized
        record["hex_limit"] = str(pair_count)
        if not record.get("baseline_hex_dump") and previous_trimmed:
            record["baseline_hex_dump"] = previous_trimmed

        wrote = self._write_live_memory(record, normalized)
        if not wrote:
            self._report_live_memory_target(record)
        return True

    def _revert_skill_data(self, index: int) -> bool:
        if not (0 <= index < len(self.skill_records)):
            QMessageBox.warning(self, "Revert Skill Data", "Invalid skill index.")
            return False

        record = self.skill_records[index]
        folder_value = record.get("folder_path")
        skill_file_value = record.get("skill_file")
        if not folder_value or not skill_file_value:
            QMessageBox.warning(
                self,
                "Revert Skill Data",
                "Skill data file paths are not configured for this record.",
            )
            return False

        folder = Path(folder_value)
        skill_path = Path(skill_file_value)
        backup_path = folder / BACKUP_FILENAME

        source_raw: str | None = None
        source_canonical: str | None = None
        try:
            if backup_path.exists():
                source_raw = backup_path.read_text(encoding="utf-8")
            else:
                baseline = record.get("baseline_hex_dump", "")
                if baseline:
                    source_canonical = normalize_hex_text(baseline)
                    source_raw = (source_canonical + "\n") if source_canonical else "\n"
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Revert Skill Data",
                f"Could not read original backup:\n{exc}",
            )
            return False

        if source_raw is None:
            QMessageBox.information(
                self,
                "Revert Skill Data",
                (
                    "No original backup is available yet for this skill. "
                    "Save once to create a backup before using Revert."
                ),
            )
            return False

        if source_canonical is None:
            source_canonical = normalize_hex_text(source_raw.strip())

        try:
            target_text = source_raw if source_raw.endswith("\n") else source_raw + "\n"
            skill_path.write_text(target_text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Revert Skill Data",
                f"Could not restore original skill data:\n{exc}",
            )
            return False

        record["hex_dump"] = source_canonical
        pair_count, invalid_tokens = hex_token_stats(source_canonical)
        if not invalid_tokens and pair_count > 0:
            record["hex_limit"] = str(pair_count)
        record["baseline_hex_dump"] = source_canonical

        wrote = self._write_live_memory(record, source_canonical)
        if not wrote:
            self._report_live_memory_target(record)
        return True

    def _populate_menus_menu(self, layout: QVBoxLayout):
        items = (
            (
                "Texture",
                "Import, export, or apply presets for the main menu, character select, HUD, and start screen backgrounds.",
                None,
            ),
            (
                "Debug Mode",
                "Toggle debug mode on or off; enabling it stages the required PDUWP files in a temporary folder until the app closes or crashes.",
                None,
            ),
            (
                "Debug Editor",
                "Launch the legacy stage and mission tooling in a separate window for deep-dive debugging.",
                self._open_debug_editor,
            ),
        )

        for title, description, handler in items:
            widget = self._menu_entry_widget(title, description)
            if handler:
                button = QPushButton("Open")
                button.setStyleSheet(
                    "QPushButton {"
                    "background-color: #3c3c3c;"
                    "color: #ffffff;"
                    "border: 1px solid #4a4a4a;"
                    "border-radius: 3px;"
                    "padding: 4px 10px;"
                    "font-size: 12px;"
                    "}"
                    "QPushButton:hover {"
                    "background-color: #4b4b4b;"
                    "}"
                )
                container = widget.layout()
                if container is not None:
                    container.addWidget(button)
                    container.setSpacing(6)
                button.clicked.connect(handler)  # type: ignore[arg-type]
            layout.addWidget(widget)

        layout.addStretch()

    def _populate_maps_menu(self, layout: QVBoxLayout):
        items = (
            (
                "Texture",
                "Import or export textures directly from a map's .alr archive, edit individual assets, and load or save full-map preset bundles.",
            ),
            (
                "Object Placement",
                "Swap props by selecting object IDs that exist in the chosen map and replacing them with other valid IDs from the same set.",
            ),
            (
                "Data Placement",
                "Adjust map metadata such as object ID groupings, replacement targets, and camera angle configurations.",
            ),
            (
                "MD00 Asset Parser",
                "Inspect MD00 map packages to list assets, preview metadata, and prep files for targeted export or modification.",
            ),
            (
                "String Extractor",
                "Pull localized text and map strings for editing or translation, then batch re-pack them into the game archives.",
            ),
        )

        for title, description in items:
            layout.addWidget(self._menu_entry_widget(title, description))

        layout.addWidget(self._map_index_widget())

        layout.addStretch()

    def _populate_characters_menu(self, layout: QVBoxLayout):
        items = (
            (
                "Character Texture",
                "Import or export character material presets and texture atlases, with quick swapping between saved skins.",
            ),
            (
                "Character Outfit Manager",
                "Manage four outfit slots per character, including preset bundles for export, import, and batch swapping.",
            ),
            (
                "Character Select Portrait Editor",
                "Edit, replace, and package portrait art used in the selection screen with built-in preset support.",
            ),
            (
                "Animation (Future)",
                "Reserved for upcoming animation tooling once hooks into runtime playback are finalized.",
            ),
        )

        for title, description in items:
            layout.addWidget(self._menu_entry_widget(title, description))

        layout.addWidget(self._character_index_widget())

        layout.addStretch()

    def _populate_audio_menu(self, layout: QVBoxLayout):
        items = (
            (
                "Extraction Modes",
                "Extract by Chunks, Extract Whole File, Extract Raw Data, and run Fast Extraction optimized for STX archives.",
            ),
            (
                "File Types",
                "Load .BIN and .STX packages directly into the session.",
            ),
            (
                "Audio Playback",
                "Play, Pause, Stop, Rewind, or Loop the active chunk for rapid auditing.",
            ),
            (
                "Export Options",
                "Export chunks as WAV, export full audio as WAV, or generate looping WAV output that corrects loop metadata.",
            ),
            (
                "Tools / Utilities",
                "View the chunk list, delete the selected chunk, open the ExtractedWAVs folder, open the sound log folder, or refresh the session list.",
            ),
            (
                "Settings",
                "Adjust sample rates to fix chipmunk or deep voice playback, toggle Fast Mode for large files, and enable or disable raw data mode.",
            ),
            (
                "Logging & Output",
                "View the extraction log or export it as a CSV for archival and analysis.",
            ),
        )

        for title, description in items:
            layout.addWidget(self._menu_entry_widget(title, description))

        layout.addStretch()

    def _populate_campaign_menu(self, layout: QVBoxLayout):
        items = (
            (
                "Quest Editor",
                "Design up to 255 campaign quests by configuring stage maps, party sizes, enemy rosters, win/lose logic, timers, rewards, unlock requirements, order, naming, descriptions, and supported match modes (1v1, Battle Royale, Tag, Handicap, No-Arsenal, Boss).",
            ),
        )

        for title, description in items:
            layout.addWidget(self._menu_entry_widget(title, description))

        wip_note = QLabel(
            "Dialogue flow editing remains work-in-progress pending additional research and confirmed data."
        )
        wip_note.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px; font-style: italic;")
        wip_note.setWordWrap(True)
        layout.addWidget(wip_note)

        layout.addStretch()

    def _map_index_widget(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2a;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QLabel("Map Index")
        header.setStyleSheet("color: #f0f0f0; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        summary_label = QLabel(self._map_summary_html())
        summary_label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        summary_label.setTextFormat(Qt.TextFormat.RichText)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        table_area = QScrollArea()
        table_area.setWidgetResizable(True)
        table_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_area.setMaximumHeight(220)
        table_area.setStyleSheet(
            "QScrollArea {"
            "background-color: transparent;"
            "border: none;"
            "}"
        )

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        table_label = QLabel(self._map_table_html())
        table_label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        table_label.setTextFormat(Qt.TextFormat.RichText)
        table_label.setWordWrap(True)
        table_layout.addWidget(table_label)

        table_area.setWidget(table_container)
        layout.addWidget(table_area)

        return frame

    def _character_index_widget(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2a;"
            "border: 1px solid #3a3a3a;"
            "border-radius: 3px;"
            "}"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QLabel("Character Index")
        header.setStyleSheet("color: #f0f0f0; font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        summary = QLabel(
            "<p style='margin:0 0 6px 0;'>NPC entries surface for editing but remain non-selectable in-game.</p>"
        )
        summary.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        summary.setTextFormat(Qt.TextFormat.RichText)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        table_area = QScrollArea()
        table_area.setWidgetResizable(True)
        table_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_area.setMaximumHeight(240)
        table_area.setStyleSheet(
            "QScrollArea {"
            "background-color: transparent;"
            "border: none;"
            "}"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(12)

        for title, data in (
            ("Playable Characters", PLAYABLE_CHARACTERS),
            ("NPCs", NPC_CHARACTERS),
            ("Enemies", ENEMY_CHARACTERS),
        ):
            container_layout.addWidget(self._character_table_label(title, data))

        table_area.setWidget(container)
        layout.addWidget(table_area)

        return frame

    def _map_summary_html(self) -> str:
        items = "".join(
            f"<li><strong>{html.escape(name)}</strong>: {html.escape(description)}</li>"
            for name, description in MAP_SUMMARY
        )
        return f"<p style='margin:0 0 6px 0;'>Key locale notes:</p><ul style='margin:0 0 8px 16px;'>{items}</ul>"

    def _map_table_html(self) -> str:
        header = (
            "<tr>"
            "<th style='text-align:left;padding:4px 8px;'>Map</th>"
            "<th style='text-align:left;padding:4px 8px;'>Map Name</th>"
            "<th style='text-align:left;padding:4px 8px;'>Internal Name</th>"
            "<th style='text-align:left;padding:4px 8px;'>ID</th>"
            "</tr>"
        )
        rows = "".join(
            "<tr>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['map'])}</td>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['map_name'])}</td>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['internal'])}</td>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['id'])}</td>"
            "</tr>"
            for entry in MAP_INDEX
        )
        return (
            "<table style='border-collapse:collapse;width:100%;'>"
            f"<thead style='background-color:#333333;color:#ffffff;'>{header}</thead>"
            f"<tbody>{rows}</tbody></table>"
        )

    def _character_table_label(self, title: str, rows: list[dict[str, str]]) -> QLabel:
        header = (
            "<tr>"
            "<th style='text-align:left;padding:4px 8px;'>Name</th>"
            "<th style='text-align:left;padding:4px 8px;'>ID</th>"
            "</tr>"
        )
        body = "".join(
            "<tr>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['name'])}</td>"
            f"<td style='padding:4px 8px;'>{html.escape(entry['id'])}</td>"
            "</tr>"
            for entry in rows
        )
        table_html = (
            f"<h4 style='margin:0 0 4px 0;color:#f0f0f0;font-size:13px;'>{html.escape(title)}</h4>"
            "<table style='border-collapse:collapse;width:100%;margin-bottom:6px;'>"
            f"<thead style='background-color:#333333;color:#ffffff;'>{header}</thead>"
            f"<tbody>{body}</tbody></table>"
        )
        label = QLabel(table_html)
        label.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        return label

    def _menu_entry_widget(self, title: str, description: str) -> QFrame:
        entry = QFrame()
        entry.setStyleSheet(
            "QFrame {"
            "background-color: #2e2e2e;"
            "border: 1px solid #3b3b3b;"
            "border-radius: 3px;"
            "}"
        )
        entry_layout = QVBoxLayout(entry)
        entry_layout.setContentsMargins(10, 8, 10, 10)
        entry_layout.setSpacing(4)

        header = QLabel(title)
        header.setStyleSheet("color: #f0f0f0; font-size: 14px; font-weight: bold;")
        entry_layout.addWidget(header)

        body = QLabel(description)
        body.setStyleSheet(f"color: {VS_TEXT}; font-size: 12px;")
        body.setWordWrap(True)
        body.setObjectName("menu-body")
        entry_layout.addWidget(body)

        return entry


    def _open_stock_browser(self) -> None:
        if not self.skill_records:
            QMessageBox.information(
                self,
                "Skill Data Unavailable",
                "No skill records were loaded. Add meta files to data/skills to continue.",
            )
            return

        dialog = StockBrowserDialog(self, self.skill_records)
        dialog.exec()


    def _open_debug_editor(self) -> None:
        base_dir = Path(sys.argv[0]).resolve().parent
        entry_point = base_dir / "data" / "stageset" / "stageset_editor.py"
        if not entry_point.exists():
            QMessageBox.warning(
                self,
                "Debug Editor",
                f"The stageset_editor.py entry point is missing.\nExpected at:\n{entry_point}",
            )
            return

        python_exe = Path(sys.executable)
        if python_exe.name.lower() != "python.exe":
            candidate = Path(sys.base_prefix) / "python.exe"
            if candidate.exists():
                python_exe = candidate
            else:
                python_exe = Path("python")

        try:
            subprocess.Popen([str(python_exe), str(entry_point)])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Debug Editor Error",
                f"Failed to launch Debug Editor:\n{exc}",
            )


    def _open_skill_stats_example(self):
        if not self.skill_records:
            QMessageBox.information(
                self,
                "Skill Data Unavailable",
                "No skill records were loaded. Add meta files to data/skills to continue.",
            )
            return

        dialog = SkillStatsDialog(
            self,
            self.skill_records,
            self._fetch_skill_hex_data,
            self._save_skill_data,
            self._revert_skill_data,
            self.connected,
        )
        dialog.exec()

    def _toggle_section(self, title: str):
        if title not in self.menu_sections:
            return

        self.active_menu = None if self.active_menu == title else title
        self._apply_menu_state()

    def _apply_menu_state(self):
        for name, section in self.menu_sections.items():
            is_active = name == self.active_menu
            section["expanded"] = is_active
            section["content"].setVisible(is_active)
            section["button"].setChecked(is_active)
            section["button"].setStyleSheet(
                self._menu_button_style(expanded=is_active, highlighted=is_active)
            )
            section["effect"].setOpacity(1.0 if is_active or self.active_menu is None else 0.35)

            parent_layout = section["wrapper"].parentWidget().layout()
            if is_active and parent_layout is not None:
                parent_layout.removeWidget(section["wrapper"])
                parent_layout.insertWidget(0, section["wrapper"])

    def _menu_button_style(self, expanded: bool, highlighted: bool) -> str:
        base_color = "#394049" if expanded else "#333333"
        hover_color = "#46505c" if expanded else "#3d3d3d"
        text_color = "#ffffff" if highlighted else "#dcdcdc"
        return (
            "QPushButton {"
            f"background-color: {base_color};"
            f"color: {text_color};"
            "border: none;"
            "padding: 6px 10px;"
            "text-align: left;"
            "font-size: 13px;"
            "}"
            "QPushButton:hover {"
            f"background-color: {hover_color};"
            "}"
            "QPushButton:pressed {"
            "background-color: #2d2d2d;"
            "}"
        )

    def _set_menu_visibility(self, visible: bool):
        self.menu_panel.setVisible(visible)
        if not visible:
            self.active_menu = None
        self._apply_menu_state()

    def _advance_intro_text(self):
        if self.intro_display_index < len(self.intro_full_text):
            self.intro_display_index += 1
            self.intro_label.setText(self.intro_full_text[: self.intro_display_index])
        else:
            self.intro_timer.stop()
            self._start_intro_fade()

    def _start_intro_fade(self):
        if self.intro_fade_animation is None:
            self.intro_fade_animation = QPropertyAnimation(self.intro_opacity_effect, b"opacity", self)
            self.intro_fade_animation.setDuration(1500)
            self.intro_fade_animation.setStartValue(1.0)
            self.intro_fade_animation.setEndValue(0.0)
            self.intro_fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self.intro_fade_animation.finished.connect(self._on_intro_fade_finished)

        if self.intro_fade_animation.state() != QAbstractAnimation.State.Running:
            self.intro_fade_animation.start()

    def _on_intro_fade_finished(self):
        self.intro_label.setText("Demo Mode")
        self.intro_opacity_effect.setOpacity(1.0)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
# Omni Program V6.1 Sample
