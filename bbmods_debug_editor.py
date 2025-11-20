"""BBMODS Debug Editor for Phantom Dust stage and mission data."""
from __future__ import annotations

import csv
import string
import struct
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

BACKGROUND = "#1e1e1e"
PANEL = "#252526"
ACCENT = "#094771"
FOREGROUND = "#d4d4d4"
INPUT_BG = "#2d2d30"
INPUT_FG = "#e7e7e7"
BUTTON_BG = "#3c3c3c"
BUTTON_FG = "#f3f3f3"

DEFAULT_GAME_ROOT = Path(__file__).resolve().parent.parent
_game_root = DEFAULT_GAME_ROOT


def get_game_root() -> Path:
    return _game_root


def set_game_root(path: Path) -> None:
    global _game_root
    _game_root = path


def core_file_path(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "Assets" / "Data" / "setup" / "stageset" / "stageset.dat"


def display_file_path(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "Assets" / "Data" / "setup" / "stageset" / "stageset_en.dat"


def single2_file_path(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "Assets" / "Data" / "com" / "single2.csv"


def deck_directory(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "Assets" / "Data" / "com" / "deck"


def tool_single2_path(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "tool" / "single2.csv"


def ai_directory(root: Optional[Path] = None) -> Path:
    base = root or get_game_root()
    return base / "Assets" / "Data" / "com" / "ai"

CATEGORY_LABELS = {
    0: "Unused",
    1: "Special",
    2: "Standard",
    3: "Boss",
}

ACTOR_TYPES = [
    "PLAYER",
    "ENEMY",
    "BOSS00",
    "BOSS01",
    "BOSS02",
    "BOSS03",
    "BOSS04",
]

ACTOR_TYPE_TOKENS = {token.upper() for token in ACTOR_TYPES}

SINGLE2_HEADER = [
    "actor_type",
    "spawn_slot",
    "alias",
    "deck",
    "ai_script",
    "character_id",
    "spawn_index",
    "hp",
    "flag_a",
    "flag_b",
]

MAX_CHARACTER_ID = 0x2F


def parse_character_number(value: str) -> Optional[int]:
    text = value.strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        pass
    if all(char in string.hexdigits for char in text):
        try:
            return int(text, 16)
        except ValueError:
            return None
    return None


def coerce_character_id(value: str) -> str:
    number = parse_character_number(value)
    if number is None:
        number = 0
    number = max(0, min(MAX_CHARACTER_ID, number))
    return f"{number:02X}"


def normalize_character_key(value: str) -> Optional[str]:
    number = parse_character_number(value)
    if number is None:
        return None
    if 0 <= number <= MAX_CHARACTER_ID:
        return f"{number:02X}"
    return None


def character_display_value(value: str) -> str:
    number = parse_character_number(value)
    if number is None:
        return value.strip()
    return str(number)


def character_display_label(code: str, name: str) -> str:
    return f"{character_display_value(code)} - {name}"

DEBUG_TEST_PRESETS: list[dict[str, Any]] = [
    {
        "label": "Basic",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Basic"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Enemy",
                "deck": "DECK000",
                "ai_script": "chkprog000.ssb",
                "character_id": "5",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Decoy",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Decoy"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Decoy",
                "deck": "DECK000",
                "ai_script": "chkprog000.ssb",
                "character_id": "5",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Edgar-Dodge-Bot",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Edgar-Dodge-Bot"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Edgar",
                "deck": "DECK000",
                "ai_script": "eneprog_freya.ssb",
                "character_id": "1",
                "spawn_index": 1,
                "hp": 9999,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Freya-Jump-Bot",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Freya-Jump-Bot"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Freya",
                "deck": "DECK000",
                "ai_script": "eneprog_freya.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 9999,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-0",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-0"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-0",
                "deck": "DECK068_2",
                "ai_script": "eneprog000.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-0-nodef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-0-nodef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-0-nodef",
                "deck": "DECK068_2",
                "ai_script": "eneprog000_nodef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-0-noNdef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-0-noNdef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-0-noNdef",
                "deck": "DECK066_2",
                "ai_script": "eneprog000_noNdef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-1",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-1"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-1",
                "deck": "DECK069_0",
                "ai_script": "eneprog001.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-1-nodef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-1-nodef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-1-nodef",
                "deck": "DECK074_0",
                "ai_script": "eneprog001_nodef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-1-noNdef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-1-noNdef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-1-noNdef",
                "deck": "DECK078_2",
                "ai_script": "eneprog001_noNdef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-2-nodef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-2-nodef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-2-nodef",
                "deck": "DECK081_1",
                "ai_script": "eneprog002_nodef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-2-noNdef",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-2-noNdef"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-2-noNdef",
                "deck": "DECK086_3",
                "ai_script": "eneprog002_noNdef.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-3",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-3"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-3",
                "deck": "DECK091_P",
                "ai_script": "eneprog003.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-4",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-4"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-4",
                "deck": "DECK099_1",
                "ai_script": "eneprog004.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-5",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-5"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-5",
                "deck": "DECK117_3",
                "ai_script": "eneprog005.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-6",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-6"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-6",
                "deck": "DECK123_1",
                "ai_script": "eneprog006.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "Program-3 (alt)",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "Program-3"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "Program-3",
                "deck": "DECK127_3",
                "ai_script": "eneprog003.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "motchk",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "motchk"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "motchk",
                "deck": "DECK132_2",
                "ai_script": "motchk.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "rootchk",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "rootchk"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": -1,
                "alias": "rootchk",
                "deck": "DECK138_1",
                "ai_script": "rootchk.ssb",
                "character_id": "2",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "4-FFA-Characters",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "4-FFA-Characters"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Edgar",
                "deck": "DECK_EDGAR_1",
                "ai_script": "eneprog004.ssb",
                "character_id": "1",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
            {
                "actor_type": "ENEMY",
                "spawn_slot": 2,
                "alias": "Freya",
                "deck": "DECK_FREIA_1",
                "ai_script": "eneprog005.ssb",
                "character_id": "2",
                "spawn_index": 2,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
            {
                "actor_type": "ENEMY",
                "spawn_slot": 3,
                "alias": "Meister",
                "deck": "DECK_MEISTER_1",
                "ai_script": "eneprog006.ssb",
                "character_id": "3",
                "spawn_index": 3,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "4-FFA-Monsters",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": -1, "alias": "4-FFA-Monsters"},
            {
                "actor_type": "ENEMY",
                "spawn_slot": 1,
                "alias": "Ceno",
                "deck": "DECK_EDGAR_1",
                "ai_script": "eneprog000.ssb",
                "character_id": "24",
                "spawn_index": 1,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
            {
                "actor_type": "ENEMY",
                "spawn_slot": 2,
                "alias": "Germano",
                "deck": "DECK_FREIA_1",
                "ai_script": "eneprog001.ssb",
                "character_id": "25",
                "spawn_index": 2,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
            {
                "actor_type": "ENEMY",
                "spawn_slot": 3,
                "alias": "Belono",
                "deck": "DECK_MEISTER_1",
                "ai_script": "eneprog003.ssb",
                "character_id": "26",
                "spawn_index": 3,
                "hp": 20,
                "flag_a": 0,
                "flag_b": 0,
            },
        ],
    },
    {
        "label": "BOSS0-Peccato",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS0-Peccato"},
            {
                "actor_type": "BOSS00",
                "spawn_slot": -1,
                "alias": "BOSS0-Peccato",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS0-Peccato-Test",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS0-Peccato-Test"},
            {
                "actor_type": "BOSS00",
                "spawn_slot": -1,
                "alias": "BOSS0-Peccato-Test",
                "ai_script": "bossprogtest.ssb",
            },
        ],
    },
    {
        "label": "BOSS1-Thalasso",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS1-Thalasso"},
            {
                "actor_type": "BOSS01",
                "spawn_slot": -1,
                "alias": "BOSS1-Thalasso",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS1-Thalasso-Test",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS1-Thalasso-Test"},
            {
                "actor_type": "BOSS01",
                "spawn_slot": -1,
                "alias": "BOSS1-Thalasso-Test",
                "ai_script": "bossprogtest.ssb",
            },
        ],
    },
    {
        "label": "BOSS2-Carcino",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS2-Carcino"},
            {
                "actor_type": "BOSS02",
                "spawn_slot": -1,
                "alias": "BOSS2-Carcino",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS2-Carcino-Test",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS2-Carcino-Test"},
            {
                "actor_type": "BOSS02",
                "spawn_slot": -1,
                "alias": "BOSS2-Carcino-Test",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS3-DFreia-Phase1",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS3-DFreia-Phase1"},
            {
                "actor_type": "BOSS03",
                "spawn_slot": 0,
                "alias": "BOSS3-DFreia-Phase1",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS3b-DFreia-Phase2",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS3b-DFreia-Phase2"},
            {
                "actor_type": "BOSS04",
                "spawn_slot": 0,
                "alias": "BOSS3b-DFreia-Phase2",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
    {
        "label": "BOSS3b-DFreia-Phase2 (Copy)",
        "entries": [
            {"actor_type": "PLAYER", "spawn_slot": 2, "alias": "BOSS3b-DFreia-Phase2"},
            {
                "actor_type": "BOSS04",
                "spawn_slot": 0,
                "alias": "BOSS3b-DFreia-Phase2",
                "ai_script": "bossprog00.ssb",
            },
        ],
    },
]

DEBUG_TEST_PRESET_LOOKUP = {preset["label"]: preset for preset in DEBUG_TEST_PRESETS}


def preset_entry_to_row(entry: dict[str, Any]) -> list[str]:
    row: list[str] = []
    for field in SINGLE2_HEADER:
        value = entry.get(field, "")
        if value in (None, ""):
            text = ""
        elif isinstance(value, str):
            text = value.strip()
        else:
            text = str(value)
        if field == "actor_type":
            text = text.upper()
        if field == "character_id":
            text = coerce_character_id(text)
        row.append(text)
    return row


def preset_to_rows(preset: dict[str, Any]) -> list[list[str]]:
    return [preset_entry_to_row(entry) for entry in preset.get("entries", [])]


def ensure_single2_seed(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SINGLE2_HEADER)
        for index, preset in enumerate(DEBUG_TEST_PRESETS):
            for row in preset_to_rows(preset):
                writer.writerow(row)
            if index != len(DEBUG_TEST_PRESETS) - 1:
                writer.writerow([])


CHARACTER_ID_PRESETS: List[Tuple[str, str]] = [
    ("00", "NANASHI"),
    ("01", "EDGAR"),
    ("02", "FREIA"),
    ("03", "MEISTER"),
    ("04", "CHUNKY"),
    ("05", "CUFF BUTTON"),
    ("06", "PH"),
    ("07", "KNOW"),
    ("08", "TSUBUTAKI"),
    ("09", "JD"),
    ("10", "SAMMAH"),
    
]


def first_selection(selection: Any) -> Optional[int]:
    if not selection:
        return None
    try:
        return int(selection[0])
    except (TypeError, ValueError, IndexError):
        return None


@dataclass
class RawRecord:
    unk_flag: int
    name_off: int
    label_off: int
    internal_off: int
    id_flags: int


@dataclass
class StageEntry:
    index: int
    unk_flag: int
    category: int
    stage_id: int
    map_name: str
    map_label: str
    internal_name: str
    core_map_name: str
    core_map_label: str
    core_internal_name: str


@dataclass
class Single2Entry:
    index: int
    actor_type: str
    spawn_slot: int
    alias: str
    deck: str
    ai_script: str
    character_id: str
    spawn_index: int
    hp: int
    flag_a: int
    flag_b: int

    def as_row(self) -> List[str]:
        return [
            self.actor_type,
            str(self.spawn_slot),
            self.alias,
            self.deck,
            self.ai_script,
            self.character_id,
            str(self.spawn_index),
            str(self.hp),
            str(self.flag_a),
            str(self.flag_b),
        ]


@dataclass
class MissionGroup:
    index: int
    entries: List[Single2Entry]

    @property
    def leader(self) -> Single2Entry:
        for entry in self.entries:
            if entry.actor_type.strip().upper() == "PLAYER":
                return entry
        return self.entries[0]

    @property
    def mission_name(self) -> str:
        leader = self.leader
        return leader.alias or leader.ai_script or leader.actor_type or f"Mission {self.index}"

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def participant_count(self) -> int:
        return sum(1 for entry in self.entries if entry.actor_type.strip())

    @property
    def non_player_count(self) -> int:
        return sum(1 for entry in self.entries if entry.actor_type.strip().upper() != "PLAYER")

    @property
    def has_deck_gap(self) -> bool:
        return any(
            entry.actor_type.strip().upper() != "PLAYER" and not entry.deck.strip()
            for entry in self.entries
        )

    @property
    def within_limits(self) -> bool:
        return 1 <= self.entry_count <= 4

    def summary_label(self) -> str:
        warning_flags: List[str] = []
        if not self.within_limits:
            warning_flags.append("count")
        if self.has_deck_gap:
            warning_flags.append("deck")
        warning = f" !{'/'.join(warning_flags).upper()}" if warning_flags else ""
        return f"{self.index:03d} - {self.mission_name} [{self.entry_count}]" + warning


class BinaryStageSet:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.total_size, self.count, self.strings_offset = struct.unpack_from("<III", self.data, 0)
        self.records = [RawRecord(*struct.unpack_from("<5I", self.data, 12 + i * 20)) for i in range(self.count)]
        self.padding = self.data[12 + self.count * 20 : self.strings_offset]
        self.string_blob = self.data[self.strings_offset :]
        self.encoding = self._detect_encoding()
        self.strings = dict(self._iter_strings(self.encoding))

    def _detect_encoding(self) -> str:
        for encoding in ("utf-8", "cp932", "shift_jis"):
            try:
                list(self._iter_strings(encoding))
                return encoding
            except UnicodeDecodeError:
                continue
        return "utf-8"

    def _iter_strings(self, encoding: str) -> Iterable[Tuple[int, str]]:
        blob = self.string_blob
        pos = 0
        while pos < len(blob):
            end = blob.find(b"\0", pos)
            if end == -1:
                break
            text = blob[pos:end].decode(encoding)
            yield pos, text
            pos = end + 1

    def string_at(self, offset: int) -> str:
        return self.strings.get(offset, f"<@{offset}>")


class StageSetModel:
    def __init__(self, core_path: Path, display_path: Optional[Path]) -> None:
        self.core_path = core_path
        self.display_path = display_path if display_path and display_path.exists() else None
        self.core: Optional[BinaryStageSet] = None
        self.display: Optional[BinaryStageSet] = None
        self.entries: List[StageEntry] = []
        self._load()

    @staticmethod
    def _compose_id(category: int, stage_id: int) -> int:
        return ((category & 0xFFFF) << 16) | (stage_id & 0xFFFF)

    def _load(self) -> None:
        self.core = BinaryStageSet(self.core_path)
        display_set = None
        if self.display_path and self.display_path != self.core_path:
            display_set = BinaryStageSet(self.display_path)
        self.display = display_set
        display_source = display_set or self.core
        if display_source.count != self.core.count:
            raise ValueError("Entry count mismatch between core and display files.")

        entries: List[StageEntry] = []
        for idx in range(self.core.count):
            core_record = self.core.records[idx]
            display_record = display_source.records[idx]
            stage_id = core_record.id_flags & 0xFFFF
            category = (core_record.id_flags >> 16) & 0xFFFF
            map_name = display_source.string_at(display_record.name_off)
            map_label = display_source.string_at(display_record.label_off)
            internal_name = display_source.string_at(display_record.internal_off)
            core_map_name = self.core.string_at(core_record.name_off)
            core_map_label = self.core.string_at(core_record.label_off)
            core_internal_name = self.core.string_at(core_record.internal_off)
            entries.append(
                StageEntry(
                    index=idx,
                    unk_flag=core_record.unk_flag,
                    category=category,
                    stage_id=stage_id,
                    map_name=map_name,
                    map_label=map_label,
                    internal_name=internal_name,
                    core_map_name=core_map_name,
                    core_map_label=core_map_label,
                    core_internal_name=core_internal_name,
                )
            )

        self.entries = entries

    def reload(self) -> None:
        self._load()

    def save(self, overwrite_core_strings: bool) -> None:
        if not self.entries:
            raise ValueError("No stages to save.")
        if self.core is None:
            raise RuntimeError("Core file is not loaded.")

        if self.display_path and self.display is not None:
            display_payload = self._build_with_strings(
                self.display,
                self.entries,
                lambda stage: (stage.map_name, stage.map_label, stage.internal_name),
                self.display.encoding,
            )
            self._write_file(self.display_path, display_payload)
            if overwrite_core_strings:
                core_payload = self._build_with_strings(
                    self.core,
                    self.entries,
                    lambda stage: (stage.map_name, stage.map_label, stage.internal_name),
                    self.core.encoding,
                )
            else:
                core_payload = self._build_with_existing_strings(self.core, self.entries)
            self._write_file(self.core_path, core_payload)
        else:
            payload = self._build_with_strings(
                self.core,
                self.entries,
                lambda stage: (stage.map_name, stage.map_label, stage.internal_name),
                self.core.encoding,
            )
            self._write_file(self.core_path, payload)

        self._load()

    def _build_with_existing_strings(self, template: BinaryStageSet, entries: List[StageEntry]) -> bytes:
        record_bytes = bytearray()
        for stage, raw in zip(entries, template.records):
            id_flags = self._compose_id(stage.category, stage.stage_id)
            record_bytes.extend(
                struct.pack(
                    "<5I",
                    stage.unk_flag & 0xFFFFFFFF,
                    raw.name_off,
                    raw.label_off,
                    raw.internal_off,
                    id_flags,
                )
            )
        string_offset = 12 + len(record_bytes) + len(template.padding)
        total_size = string_offset + len(template.string_blob)
        header = struct.pack("<III", total_size - 4, len(entries), string_offset)
        return header + record_bytes + template.padding + template.string_blob

    def _build_with_strings(
        self,
        template: BinaryStageSet,
        entries: List[StageEntry],
        string_getter: Callable[[StageEntry], Tuple[str, str, str]],
        encoding: str,
    ) -> bytes:
        string_map: Dict[str, int] = {}
        string_blob = bytearray()

        def add_string(value: str) -> int:
            value = value or ""
            if value not in string_map:
                try:
                    encoded = value.encode(encoding)
                except UnicodeEncodeError as exc:
                    raise ValueError(f"String cannot be encoded as {encoding}: {value!r}") from exc
                string_map[value] = len(string_blob)
                string_blob.extend(encoded + b"\x00")
            return string_map[value]

        record_bytes = bytearray()
        for stage in entries:
            map_name, map_label, internal_name = string_getter(stage)
            name_off = add_string(map_name)
            label_off = add_string(map_label)
            internal_off = add_string(internal_name)
            id_flags = self._compose_id(stage.category, stage.stage_id)
            record_bytes.extend(
                struct.pack(
                    "<5I",
                    stage.unk_flag & 0xFFFFFFFF,
                    name_off,
                    label_off,
                    internal_off,
                    id_flags,
                )
            )

        string_offset = 12 + len(record_bytes) + len(template.padding)
        total_size = string_offset + len(string_blob)
        header = struct.pack("<III", total_size - 4, len(entries), string_offset)
        return header + record_bytes + template.padding + string_blob

    def _write_file(self, path: Path, payload: bytes) -> None:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists() and path.exists():
            backup.write_bytes(path.read_bytes())
        path.write_bytes(payload)


class Single2Model:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.header: List[str] = []
        self.entries: List[Single2Entry] = []
        self.groups: List[MissionGroup] = []
        self.character_map: Dict[str, str] = {}
        self._load()

    @staticmethod
    def _parse_int(value: str, default: int = 0) -> int:
        value = value.strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default
    def _load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            rows = [row for row in reader if row]
        if not rows:
            raise ValueError("single2.csv is empty")
        self.header = rows[0]
        entries: List[Single2Entry] = []
        for idx, row in enumerate(rows[1:]):
            entries.append(self._row_to_entry(idx, list(row)))
        self.entries = entries
        self._build_groups()

    def reload(self) -> None:
        self._load()

    def save(self, allow_violations: bool = False) -> None:
        if not self.entries:
            raise ValueError("No mission rows to save.")
        violations = self.rule_violations()
        if violations and not allow_violations:
            raise ValueError("Rule violations detected:\n" + "\n".join(violations))
        flat_entries: List[Single2Entry] = []
        for group in self.groups:
            flat_entries.extend(group.entries)
        for idx, entry in enumerate(flat_entries):
            entry.index = idx
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        if not backup.exists() and self.path.exists():
            backup.write_bytes(self.path.read_bytes())
        with self.path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.header)
            for entry in flat_entries:
                writer.writerow(entry.as_row())
        self._load()

    def _build_groups(self) -> None:
        groups: List[MissionGroup] = []
        current: List[Single2Entry] = []
        for entry in self.entries:
            actor_type = entry.actor_type.strip().upper()
            if actor_type == "PLAYER" and current:
                groups.append(MissionGroup(index=len(groups), entries=current))
                current = [entry]
            else:
                if not current:
                    current = [entry]
                else:
                    current.append(entry)
        if current:
            groups.append(MissionGroup(index=len(groups), entries=current))
        if not groups and self.entries:
            groups = [MissionGroup(index=0, entries=self.entries[:])]
        self.groups = groups
        self._reindex_entries()
        self._build_character_map()

    def _reindex_entries(self) -> None:
        flat: List[Single2Entry] = []
        for group_index, group in enumerate(self.groups):
            group.index = group_index
            for entry in group.entries:
                entry.index = len(flat)
                flat.append(entry)
        self.entries = flat

    def rule_violations(self) -> List[str]:
        violations: List[str] = []
        for group in self.groups:
            if group.entry_count < 1:
                violations.append(f"Mission {group.index:03d} has no characters.")
            if group.entry_count > 4:
                violations.append(
                    f"Mission {group.index:03d} exceeds 4 characters ({group.entry_count})."
                )
            for entry in group.entries:
                actor_type = entry.actor_type.strip().upper()
                if actor_type and actor_type != "PLAYER" and not entry.deck.strip():
                    violations.append(
                        f"Mission {group.index:03d} entry {entry.index:03d} ({entry.alias or actor_type}) is missing a deck."
                    )
                char_key = normalize_character_key(entry.character_id)
                if char_key is None:
                    violations.append(
                        f"Mission {group.index:03d} entry {entry.index:03d} has invalid character ID '{character_display_value(entry.character_id)}'."
                    )
        return violations

    def _build_character_map(self) -> None:
        mapping: Dict[str, str] = {code: name for code, name in CHARACTER_ID_PRESETS}
        for entry in self.entries:
            key = normalize_character_key(entry.character_id or "")
            if key is None:
                continue
            alias = entry.alias.strip()
            if alias:
                mapping.setdefault(key, alias)
        extra_path = tool_single2_path()
        if extra_path.exists():
            with extra_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                next(reader, None)
                for row in reader:
                    if not row:
                        continue
                    key_raw = row[5].strip() if len(row) > 5 else ""
                    key = normalize_character_key(key_raw)
                    alias = row[2].strip() if len(row) > 2 else ""
                    if key and alias:
                        mapping.setdefault(key, alias)
        self.character_map = mapping

    def refresh_character_map(self) -> None:
        self._build_character_map()

    def character_options(self) -> List[str]:
        ordered: List[Tuple[int, str, str]] = []
        for code, name in self.character_map.items():
            normalized = normalize_character_key(code)
            if normalized is None:
                continue
            number = parse_character_number(normalized)
            if number is None:
                continue
            ordered.append((number, normalized, name))
        ordered.sort(key=lambda item: item[0])
        return [character_display_label(code, name) for _, code, name in ordered]

    def _row_to_entry(self, idx: int, row: List[str]) -> Single2Entry:
        normalized = (row + [""] * 10)[:10]
        return Single2Entry(
            index=idx,
            actor_type=normalized[0].strip(),
            spawn_slot=self._parse_int(normalized[1], -1),
            alias=normalized[2].strip(),
            deck=normalized[3].strip(),
            ai_script=normalized[4].strip(),
            character_id=coerce_character_id(normalized[5]),
            spawn_index=self._parse_int(normalized[6]),
            hp=self._parse_int(normalized[7], 20),
            flag_a=self._parse_int(normalized[8]),
            flag_b=self._parse_int(normalized[9]),
        )

    def add_preset_group(self, preset: dict[str, Any]) -> MissionGroup:
        rows = preset_to_rows(preset)
        if not rows:
            raise ValueError("Preset contains no entries.")
        entries = [self._row_to_entry(0, row) for row in rows]
        group = MissionGroup(index=len(self.groups), entries=entries)
        self.groups.append(group)
        self._reindex_entries()
        self._build_character_map()
        return group

    def add_entry(self, group_index: int, actor_type: str) -> MissionGroup:
        if group_index < 0 or group_index >= len(self.groups):
            raise IndexError("Invalid mission index")
        group = self.groups[group_index]
        if group.entry_count >= 4:
            raise ValueError("Mission already has 4 characters.")
        actor_code = actor_type.strip().upper() or "ENEMY"
        default_deck = "" if actor_code == "PLAYER" else "DECK000"
        new_entry = Single2Entry(
            index=0,
            actor_type=actor_code,
            spawn_slot=-1,
            alias=(actor_code.title() if actor_code else "NewActor"),
            deck=default_deck,
            ai_script="",
            character_id="00",
            spawn_index=0,
            hp=20,
            flag_a=0,
            flag_b=0,
        )
        group.entries.append(new_entry)
        self._reindex_entries()
        self._build_character_map()
        return group

    def remove_entry(self, group_index: int, entry_index: int) -> MissionGroup:
        if group_index < 0 or group_index >= len(self.groups):
            raise IndexError("Invalid mission index")
        group = self.groups[group_index]
        if entry_index < 0 or entry_index >= len(group.entries):
            raise IndexError("Invalid entry index")
        if group.entry_count <= 1:
            raise ValueError("Mission must keep at least one character.")
        del group.entries[entry_index]
        self._reindex_entries()
        self._build_character_map()
        return group


class StageTab:
    def __init__(
        self,
        master: ttk.Notebook,
        status_var: tk.StringVar,
        on_root_changed: Callable[[Path], None] | None = None,
    ) -> None:
        self.status_var = status_var
        self.frame = tk.Frame(master, bg=BACKGROUND)
        self.model: Optional[StageSetModel] = None
        self.current_index: Optional[int] = None
        self.on_root_changed = on_root_changed

        self.root_dir_var = tk.StringVar(value=str(get_game_root()))
        self.core_file_var = tk.StringVar(value=str(core_file_path()))
        self.display_file_var = tk.StringVar(value=str(display_file_path()))
        self.name_var = tk.StringVar()
        self.label_var = tk.StringVar()
        self.internal_var = tk.StringVar()
        self.core_name_var = tk.StringVar()
        self.core_label_var = tk.StringVar()
        self.core_internal_var = tk.StringVar()
        self.id_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.flag_var = tk.IntVar(value=0)
        self.sync_names_var = tk.BooleanVar(value=False)

        self.stage_list: Optional[tk.Listbox] = None

        self._build_ui(self.frame)

        self._apply_root(get_game_root(), notify=False)
        default_core = core_file_path()
        if default_core.exists():
            default_display = display_file_path()
            display = default_display if default_display.exists() else None
            self._load_files(default_core, display)

    def _build_file_row(self, parent: tk.Widget, label: str, var: tk.StringVar, row: int, callback: Callable[[], None]) -> None:
        tk.Label(parent, text=label, bg=BACKGROUND, fg=FOREGROUND).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = tk.Entry(parent, textvariable=var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        browse = tk.Button(parent, text="Browse", command=callback, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        browse.grid(row=row, column=2, padx=(8, 0), pady=4, sticky="ew")

    def _build_root_row(self, parent: tk.Widget, row: int) -> None:
        tk.Label(parent, text="Game folder", bg=BACKGROUND, fg=FOREGROUND).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = tk.Entry(parent, textvariable=self.root_dir_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        browse = tk.Button(parent, text="Browse", command=self._browse_root, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        browse.grid(row=row, column=2, padx=(8, 0), pady=4, sticky="ew")

    def _browse_root(self) -> None:
        initial_text = self.root_dir_var.get().strip()
        initial_dir = Path(initial_text).expanduser() if initial_text else get_game_root()
        directory = filedialog.askdirectory(initialdir=str(initial_dir))
        if directory:
            self._apply_root(Path(directory))

    def _sync_root_from_entry(self) -> bool:
        text = self.root_dir_var.get().strip()
        if not text:
            return True
        candidate = Path(text).expanduser()
        if not candidate.exists():
            messagebox.showerror("Game Folder", f"Folder not found: {candidate}")
            return False
        self._apply_root(candidate)
        return True

    def _apply_root(self, root_path: Path, *, notify: bool = True) -> None:
        resolved = root_path.expanduser()
        if not resolved.exists():
            messagebox.showerror("Game Folder", f"Folder not found: {resolved}")
            return
        resolved = resolved.resolve()
        current_root = Path(get_game_root()).resolve()
        changed = resolved != current_root
        self.root_dir_var.set(str(resolved))
        set_game_root(resolved)
        self.core_file_var.set(str(core_file_path(resolved)))
        self.display_file_var.set(str(display_file_path(resolved)))
        if notify and not (resolved / "PDUWP.exe").exists():
            messagebox.showwarning(
                "Game Folder",
                f"PDUWP.exe not found in {resolved}. Continue if this is intentional.",
            )
        if notify and self.on_root_changed and changed:
            self.on_root_changed(resolved)

    def _build_ui(self, container: tk.Frame) -> None:
        container.grid_columnconfigure(0, weight=1)

        top_frame = tk.Frame(container, bg=BACKGROUND)
        top_frame.pack(fill=tk.X, padx=12, pady=(12, 6))
        top_frame.grid_columnconfigure(1, weight=1)

        self._build_root_row(top_frame, 0)
        self._build_file_row(top_frame, "Core file", self.core_file_var, 1, self._browse_core)
        self._build_file_row(top_frame, "Display file", self.display_file_var, 2, self._browse_display)

        load_btn = tk.Button(top_frame, text="Load", command=self._load_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        load_btn.grid(row=0, column=3, rowspan=3, padx=(8, 0), pady=0, sticky="nsw")

        main_frame = tk.Frame(container, bg=BACKGROUND)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        list_frame = tk.Frame(main_frame, bg=BACKGROUND)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        self.stage_list = tk.Listbox(
            list_frame,
            bg=PANEL,
            fg=FOREGROUND,
            selectbackground=ACCENT,
            selectforeground=FOREGROUND,
            activestyle="none",
            highlightthickness=0,
            width=34,
        )
        self.stage_list.pack(side=tk.LEFT, fill=tk.Y)
        self.stage_list.bind("<<ListboxSelect>>", self._on_select)

        def _on_scroll(*args: Any) -> None:
            if self.stage_list is not None:
                self.stage_list.yview(*args)  # type: ignore[arg-type]

        list_scroll = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=_on_scroll)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.stage_list.configure(yscrollcommand=list_scroll.set)

        form_frame = tk.Frame(main_frame, bg=BACKGROUND)
        form_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        form_frame.grid_columnconfigure(1, weight=1)

        self._add_label(form_frame, "Stage ID", 0, 0)
        id_entry = tk.Entry(form_frame, textvariable=self.id_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        id_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Display name", 1, 0)
        name_entry = tk.Entry(form_frame, textvariable=self.name_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        name_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Core name", 2, 0)
        name_core = tk.Label(form_frame, textvariable=self.core_name_var, bg=BACKGROUND, fg=FOREGROUND, anchor="w")
        name_core.grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Map label", 3, 0)
        label_entry = tk.Entry(form_frame, textvariable=self.label_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        label_entry.grid(row=3, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Core label", 4, 0)
        label_core = tk.Label(form_frame, textvariable=self.core_label_var, bg=BACKGROUND, fg=FOREGROUND, anchor="w")
        label_core.grid(row=4, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Internal name", 5, 0)
        internal_entry = tk.Entry(form_frame, textvariable=self.internal_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        internal_entry.grid(row=5, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Core internal", 6, 0)
        internal_core = tk.Label(form_frame, textvariable=self.core_internal_var, bg=BACKGROUND, fg=FOREGROUND, anchor="w")
        internal_core.grid(row=6, column=1, sticky="ew", padx=6, pady=4)

        self._add_label(form_frame, "Category", 7, 0)
        self.category_box = tk.OptionMenu(form_frame, self.category_var, *self._category_options())
        self.category_box.configure(bg=BUTTON_BG, fg=BUTTON_FG, highlightthickness=0, activebackground=ACCENT, activeforeground=FOREGROUND)
        self.category_box.grid(row=7, column=1, sticky="ew", padx=6, pady=4)

        flag_frame = tk.Frame(form_frame, bg=BACKGROUND)
        flag_frame.grid(row=8, column=1, sticky="w", padx=6, pady=4)
        flag_check = tk.Checkbutton(
            flag_frame,
            text="Flag (0/1)",
            variable=self.flag_var,
            bg=BACKGROUND,
            fg=FOREGROUND,
            selectcolor=BACKGROUND,
            activebackground=BACKGROUND,
            activeforeground=FOREGROUND,
        )
        flag_check.pack(anchor="w")

        sync_check = tk.Checkbutton(
            form_frame,
            text="Overwrite core strings with display values when saving",
            variable=self.sync_names_var,
            bg=BACKGROUND,
            fg=FOREGROUND,
            selectcolor=BACKGROUND,
            activebackground=BACKGROUND,
            activeforeground=FOREGROUND,
        )
        sync_check.grid(row=9, column=0, columnspan=2, sticky="w", padx=6, pady=(12, 4))

        button_frame = tk.Frame(form_frame, bg=BACKGROUND)
        button_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        save_btn = tk.Button(button_frame, text="Save", command=self._save_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        save_btn.pack(side=tk.RIGHT, padx=(6, 0))
        reload_btn = tk.Button(button_frame, text="Revert", command=self._reload_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        reload_btn.pack(side=tk.RIGHT)

    def _add_label(self, parent: tk.Widget, text: str, row: int, column: int) -> None:
        label = tk.Label(parent, text=text, bg=BACKGROUND, fg=FOREGROUND)
        label.grid(row=row, column=column, sticky="w", padx=6, pady=4)

    def _category_options(self) -> List[str]:
        return [f"{key}:{value}" for key, value in CATEGORY_LABELS.items()]

    def _set_file_var(self, var: tk.StringVar) -> None:
        file_path = filedialog.askopenfilename(
            initialdir=core_file_path().parent,
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")],
        )
        if file_path:
            var.set(file_path)

    def _browse_core(self) -> None:
        self._set_file_var(self.core_file_var)

    def _browse_display(self) -> None:
        self._set_file_var(self.display_file_var)

    def _load_clicked(self) -> None:
        if not self._sync_root_from_entry():
            return
        core_path = Path(self.core_file_var.get()).expanduser()
        if not core_path.exists():
            messagebox.showerror("Load failed", f"Core file not found: {core_path}")
            return
        display_text = self.display_file_var.get().strip()
        display_path = Path(display_text).expanduser() if display_text else None
        if display_path and not display_path.exists():
            messagebox.showerror("Load failed", f"Display file not found: {display_path}")
            return
        self._load_files(core_path, display_path)

    def _load_files(self, core_path: Path, display_path: Optional[Path]) -> None:
        try:
            self.model = StageSetModel(core_path, display_path)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.current_index = None
        self._refresh_list()
        self._clear_form()
        if display_path:
            self.status_var.set(f"Loaded stage sets | core: {core_path} | display: {display_path}")
        else:
            self.status_var.set(f"Loaded stage sets | core: {core_path}")

    def _refresh_list(self) -> None:
        if self.stage_list is None:
            return
        self.stage_list.delete(0, tk.END)
        if not self.model:
            return
        for entry in self.model.entries:
            label = f"{entry.stage_id:02d} • {entry.map_name}"
            self.stage_list.insert(tk.END, label)

    def _clear_form(self) -> None:
        self.name_var.set("")
        self.label_var.set("")
        self.internal_var.set("")
        self.core_name_var.set("")
        self.core_label_var.set("")
        self.core_internal_var.set("")
        self.id_var.set("")
        self.category_var.set(self._category_options()[0])
        self.flag_var.set(0)

    def _on_select(self, event: tk.Event[tk.Widget]) -> None:
        if not self.model or self.stage_list is None:
            return
        index = first_selection(self.stage_list.curselection())  # type: ignore[call-arg]
        if index is None:
            return
        self.current_index = index
        stage = self.model.entries[index]
        self.name_var.set(stage.map_name)
        self.label_var.set(stage.map_label)
        self.internal_var.set(stage.internal_name)
        self.core_name_var.set(stage.core_map_name)
        self.core_label_var.set(stage.core_map_label)
        self.core_internal_var.set(stage.core_internal_name)
        self.id_var.set(str(stage.stage_id))
        category_label = CATEGORY_LABELS.get(stage.category, f"{stage.category}")
        if stage.category in CATEGORY_LABELS:
            self.category_var.set(f"{stage.category}:{category_label}")
        else:
            self.category_var.set(str(stage.category))
        self.flag_var.set(stage.unk_flag)

    def _apply_form(self) -> bool:
        if self.model is None or self.current_index is None:
            return False
        stage = self.model.entries[self.current_index]
        stage.map_name = self.name_var.get().strip()
        stage.map_label = self.label_var.get().strip()
        stage.internal_name = self.internal_var.get().strip()
        try:
            stage.stage_id = int(self.id_var.get().strip(), 0)
        except ValueError:
            messagebox.showerror("Invalid value", "Stage ID must be an integer.")
            return False
        cat_value = self.category_var.get().split(":", 1)[0]
        try:
            stage.category = int(cat_value, 0)
        except ValueError:
            messagebox.showerror("Invalid value", "Category must be an integer.")
            return False
        stage.unk_flag = 1 if self.flag_var.get() else 0
        return True

    def _save_clicked(self) -> None:
        if self.model is None:
            messagebox.showinfo("No file", "Load stageset files first.")
            return
        if self.current_index is not None and not self._apply_form():
            return
        try:
            self.model.save(self.sync_names_var.get())
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._refresh_list()
        self.status_var.set("Stage sets saved.")

    def _reload_clicked(self) -> None:
        if not self.model:
            return
        try:
            self.model.reload()
        except Exception as exc:
            messagebox.showerror("Reload failed", str(exc))
            return
        self._refresh_list()
        self._clear_form()
        self.status_var.set("Stage sets reloaded from disk.")


class Single2Tab:
    def __init__(self, master: ttk.Notebook, status_var: tk.StringVar) -> None:
        self.status_var = status_var
        self.frame = tk.Frame(master, bg=BACKGROUND)
        self.model: Optional[Single2Model] = None
        self.current_group: Optional[int] = None
        self.current_entry: Optional[int] = None

        self.file_var = tk.StringVar(value=str(single2_file_path()))
        self.preset_var = tk.StringVar()
        self.actor_type_var = tk.StringVar()
        self.spawn_slot_var = tk.StringVar()
        self._alias_trace_suspended = False
        self._alias_was_auto = True
        self._last_auto_alias = ""
        self._character_trace_suspended = False
        self.alias_var = tk.StringVar()
        self.alias_var.trace_add("write", self._on_alias_changed)
        self.deck_var = tk.StringVar()
        self.ai_var = tk.StringVar()
        self.character_id_var = tk.StringVar(value="00")
        self.character_id_var.trace_add("write", self._on_character_id_change)
        self.spawn_index_var = tk.StringVar()
        self.hp_var = tk.StringVar()
        self.flag_a_var = tk.StringVar()
        self.flag_b_var = tk.StringVar()
        self._last_auto_alias = self._character_default_alias("00") or ""

        self.deck_options = self._discover_decks()
        self.ai_options = self._discover_ai_scripts()

        self.mission_list: Optional[tk.Listbox] = None
        self.entry_list: Optional[tk.Listbox] = None
        self.deck_combo: Optional[ttk.Combobox] = None
        self.ai_combo: Optional[ttk.Combobox] = None
        self.preset_combo: Optional[ttk.Combobox] = None
        self.character_combo_var = tk.StringVar()
        self.character_combo: Optional[ttk.Combobox] = None

        self._build_ui(self.frame)
        self._set_character_id("00", suppress=True)

    def _set_alias(self, value: str, *, auto: bool = False) -> None:
        self._alias_trace_suspended = True
        try:
            self.alias_var.set(value)
        finally:
            self._alias_trace_suspended = False
        if auto:
            self._alias_was_auto = True
            self._last_auto_alias = value
        else:
            self._alias_was_auto = False

    def _on_alias_changed(self, *_: str) -> None:
        if self._alias_trace_suspended:
            return
        self._alias_was_auto = False

    def _set_character_id(self, value: str, *, suppress: bool = False) -> None:
        text = value.strip()
        normalized = normalize_character_key(text)
        if normalized is not None:
            text = character_display_value(normalized)
        else:
            number = parse_character_number(text)
            if number is not None:
                text = str(number)
        if suppress:
            previous = self._character_trace_suspended
            self._character_trace_suspended = True
            try:
                self.character_id_var.set(text)
            finally:
                self._character_trace_suspended = previous
        else:
            self.character_id_var.set(text)

    def _on_character_id_change(self, *_: str) -> None:
        if self._character_trace_suspended:
            return
        self._handle_character_alias_update()

    def _handle_character_alias_update(self) -> None:
        """Auto-sync alias with the chosen character ID unless the user overrode it."""
        raw_value = self.character_id_var.get().strip()
        if not raw_value:
            return
        if " - " in raw_value:
            raw_value = raw_value.split(" - ", 1)[0].strip()
        normalized = normalize_character_key(raw_value)
        if normalized is None:
            return
        display_value = character_display_value(normalized)
        if raw_value != display_value:
            self._set_character_id(normalized, suppress=True)
        previous_auto = self._last_auto_alias
        default_alias = self._character_default_alias(normalized)
        if default_alias:
            self._last_auto_alias = default_alias
        current_alias = self.alias_var.get().strip()
        should_auto = False
        if not current_alias:
            should_auto = True
        elif self._alias_was_auto:
            should_auto = True
        elif previous_auto and current_alias.lower() == previous_auto.lower():
            should_auto = True
        elif default_alias and current_alias.lower() == default_alias.lower():
            should_auto = True
        if should_auto and default_alias:
            self._set_alias(default_alias, auto=True)
        formatted = self._format_character_option(normalized)
        if formatted:
            self.character_combo_var.set(formatted)
        elif default_alias:
            self.character_combo_var.set(character_display_label(normalized, default_alias))

    def _character_default_alias(self, char_id: str) -> Optional[str]:
        normalized = normalize_character_key(char_id)
        if normalized is None:
            return None
        if self.model:
            alias = self.model.character_map.get(normalized)
            if alias:
                return alias
        for code, name in CHARACTER_ID_PRESETS:
            if code == normalized:
                return name
        return normalized

    def _infer_alias_auto_state(self, entry: Single2Entry) -> None:
        """Determine whether the current alias should auto-follow the character."""
        current_alias = self.alias_var.get().strip()
        default_alias = self._character_default_alias(entry.character_id)
        actor_label = entry.actor_type.strip()
        actor_title = actor_label.title()
        if not current_alias:
            self._alias_was_auto = True
            self._last_auto_alias = default_alias or ""
            return
        if default_alias and current_alias.lower() == default_alias.lower():
            self._alias_was_auto = True
            self._last_auto_alias = default_alias
            return
        if current_alias.lower() in {actor_label.lower(), actor_title.lower()}:
            self._alias_was_auto = True
            self._last_auto_alias = default_alias or current_alias
            return
        self._alias_was_auto = False
        self._last_auto_alias = default_alias or current_alias

    def _discover_decks(self) -> List[str]:
        deck_dir = deck_directory()
        if not deck_dir.exists():
            return []
        names = [item.name for item in deck_dir.iterdir() if not item.name.startswith(".")]
        return sorted(names, key=lambda name: name.lower())

    def _discover_ai_scripts(self) -> List[str]:
        scripts: set[str] = set()
        for folder in (ai_directory(), get_game_root() / "tool" / "ai"):
            if not folder.exists():
                continue
            for path in folder.rglob("*.ssb"):
                if path.is_file():
                    scripts.add(path.name)
        return sorted(scripts, key=lambda name: name.lower())

    def _build_ui(self, container: tk.Frame) -> None:
        top_frame = tk.Frame(container, bg=BACKGROUND)
        top_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

        path_entry = tk.Entry(top_frame, textvariable=self.file_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        browse_btn = tk.Button(top_frame, text="Browse", command=self._browse_file, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        browse_btn.pack(side=tk.LEFT, padx=(8, 0))

        load_btn = tk.Button(top_frame, text="Load", command=self._load_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        load_btn.pack(side=tk.LEFT, padx=(8, 0))

        preset_frame = tk.Frame(container, bg=BACKGROUND)
        preset_frame.pack(fill=tk.X, padx=12, pady=(0, 6))

        tk.Label(preset_frame, text="Debug presets", bg=BACKGROUND, fg=FOREGROUND).pack(side=tk.LEFT)
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, state="readonly", values=self._preset_names(), width=28)
        if self.preset_combo["values"]:
            self.preset_var.set(self.preset_combo["values"][0])
        self.preset_combo.pack(side=tk.LEFT, padx=(8, 0))
        preset_btn = tk.Button(preset_frame, text="Insert", command=self._add_preset_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        preset_btn.pack(side=tk.LEFT, padx=(8, 0))

        main_frame = tk.Frame(container, bg=BACKGROUND)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        mission_frame = tk.Frame(main_frame, bg=BACKGROUND)
        mission_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        tk.Label(mission_frame, text="Debug Test", bg=BACKGROUND, fg=FOREGROUND).pack(anchor="w", pady=(0, 4))
        self.mission_list = tk.Listbox(
            mission_frame,
            bg=PANEL,
            fg=FOREGROUND,
            selectbackground=ACCENT,
            selectforeground=FOREGROUND,
            activestyle="none",
            highlightthickness=0,
            width=32,
        )
        self.mission_list.pack(side=tk.LEFT, fill=tk.Y)
        def _on_mission_scroll(*args: Any) -> None:
            if self.mission_list is not None:
                self.mission_list.yview(*args)  # type: ignore[arg-type]

        mission_scroll = tk.Scrollbar(mission_frame, orient=tk.VERTICAL, command=_on_mission_scroll)
        mission_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.mission_list.configure(yscrollcommand=mission_scroll.set)
        self.mission_list.bind("<<ListboxSelect>>", self._on_mission_select)

        entry_frame = tk.Frame(main_frame, bg=BACKGROUND)
        entry_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))

        tk.Label(entry_frame, text="Entries", bg=BACKGROUND, fg=FOREGROUND).pack(anchor="w", pady=(0, 4))
        self.entry_list = tk.Listbox(
            entry_frame,
            bg=PANEL,
            fg=FOREGROUND,
            selectbackground=ACCENT,
            selectforeground=FOREGROUND,
            activestyle="none",
            highlightthickness=0,
            width=40,
        )
        self.entry_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        def _on_entry_scroll(*args: Any) -> None:
            if self.entry_list is not None:
                self.entry_list.yview(*args)  # type: ignore[arg-type]

        entry_scroll = tk.Scrollbar(entry_frame, orient=tk.VERTICAL, command=_on_entry_scroll)
        entry_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_list.configure(yscrollcommand=entry_scroll.set)
        self.entry_list.bind("<<ListboxSelect>>", self._on_entry_select)

        entry_button_frame = tk.Frame(entry_frame, bg=BACKGROUND)
        entry_button_frame.pack(fill=tk.X, pady=(6, 0))
        add_btn = tk.Button(
            entry_button_frame,
            text="Add Actor",
            command=self._add_actor_clicked,
            bg=BUTTON_BG,
            fg=BUTTON_FG,
            activebackground=ACCENT,
            activeforeground=FOREGROUND,
        )
        add_btn.pack(side=tk.LEFT, padx=(0, 6))
        remove_btn = tk.Button(
            entry_button_frame,
            text="Remove Actor",
            command=self._remove_actor_clicked,
            bg=BUTTON_BG,
            fg=BUTTON_FG,
            activebackground=ACCENT,
            activeforeground=FOREGROUND,
        )
        remove_btn.pack(side=tk.LEFT)

        form_frame = tk.Frame(main_frame, bg=BACKGROUND)
        form_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        form_frame.grid_columnconfigure(1, weight=1)

        self._add_label(form_frame, "Actor type", 0)
        self.actor_menu = tk.OptionMenu(form_frame, self.actor_type_var, *ACTOR_TYPES)
        self.actor_menu.configure(bg=BUTTON_BG, fg=BUTTON_FG, highlightthickness=0, activebackground=ACCENT, activeforeground=FOREGROUND)
        self.actor_menu.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        self._add_entry(form_frame, "Spawn slot", 1, self.spawn_slot_var)
        self._add_entry(form_frame, "Alias", 2, self.alias_var)
        self._add_label(form_frame, "Deck", 3)
        self.deck_combo = ttk.Combobox(form_frame, textvariable=self.deck_var, values=self.deck_options, state="normal")
        self.deck_combo.grid(row=3, column=1, sticky="ew", padx=6, pady=4)
        self._add_label(form_frame, "AI script", 4)
        self.ai_combo = ttk.Combobox(form_frame, textvariable=self.ai_var, values=self.ai_options, state="normal")
        self.ai_combo.grid(row=4, column=1, sticky="ew", padx=6, pady=4)
        self._add_label(form_frame, "Character ID", 5)
        id_frame = tk.Frame(form_frame, bg=BACKGROUND)
        id_frame.grid(row=5, column=1, sticky="ew", padx=6, pady=4)
        id_frame.grid_columnconfigure(1, weight=1)
        id_entry = tk.Entry(id_frame, textvariable=self.character_id_var, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND, width=8)
        id_entry.grid(row=0, column=0, sticky="w")
        self.character_combo = ttk.Combobox(id_frame, textvariable=self.character_combo_var, state="readonly")
        self.character_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.character_combo.bind("<<ComboboxSelected>>", self._on_character_choice)
        self._add_entry(form_frame, "Spawn index", 6, self.spawn_index_var)
        self._add_entry(form_frame, "HP", 7, self.hp_var)
        self._add_entry(form_frame, "Flag A", 8, self.flag_a_var)
        self._add_entry(form_frame, "Flag B", 9, self.flag_b_var)

        button_frame = tk.Frame(form_frame, bg=BACKGROUND)
        button_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        save_btn = tk.Button(button_frame, text="Save", command=self._save_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        save_btn.pack(side=tk.RIGHT, padx=(6, 0))
        apply_btn = tk.Button(button_frame, text="Apply", command=self._apply_clicked, bg=BUTTON_BG, fg=BUTTON_FG, activebackground=ACCENT, activeforeground=FOREGROUND)
        apply_btn.pack(side=tk.RIGHT)

        self._update_character_choices()

    def _preset_names(self) -> List[str]:
        return sorted(DEBUG_TEST_PRESET_LOOKUP.keys(), key=lambda value: value.lower())

    def update_root(self, root: Path) -> None:
        target = single2_file_path(root)
        ensure_single2_seed(target)
        self.file_var.set(str(target))
        self.deck_options = self._discover_decks()
        if self.deck_combo is not None:
            self.deck_combo.configure(values=self.deck_options)
        self.ai_options = self._discover_ai_scripts()
        if self.ai_combo is not None:
            self.ai_combo.configure(values=self.ai_options)
        self._ensure_ai_choice(self.ai_var.get())
        if not target.exists():
            return
        if self.model and self.model.path.resolve() == target.resolve():
            try:
                self.model.reload()
            except Exception as exc:
                messagebox.showerror("Load failed", str(exc))
                return
            self._refresh_group_list(reset_selection=False)
            self.status_var.set(f"Reloaded Debug Test actors: {target}")
        else:
            self._load_file(target)

    def _add_preset_clicked(self) -> None:
        if self.model is None:
            messagebox.showinfo("No file", "Load a single2.csv file first.")
            return
        if self.current_group is not None and self.current_entry is not None:
            if not self._apply_form():
                return
        selection = self.preset_var.get().strip()
        if not selection:
            messagebox.showinfo("Preset", "Choose a preset to insert.")
            return
        self._add_preset_by_name(selection)

    def _unique_preset_label(self, base_label: str) -> str:
        if self.model is None:
            return base_label
        existing = {group.mission_name.lower() for group in self.model.groups}
        if base_label.lower() not in existing:
            return base_label
        suffix = 2
        while True:
            candidate = f"{base_label} ({suffix})"
            if candidate.lower() not in existing:
                return candidate
            suffix += 1

    def _add_preset_by_name(self, name: str) -> None:
        if self.model is None:
            return
        preset = DEBUG_TEST_PRESET_LOOKUP.get(name)
        if not preset:
            messagebox.showerror("Preset", f"Preset not found: {name}")
            return
        preset_entries: List[Dict[str, Any]] = [dict(entry) for entry in preset.get("entries", [])]
        preset_copy: Dict[str, Any] = {
            "label": preset.get("label", name),
            "entries": preset_entries,
        }
        if not preset_entries:
            messagebox.showerror("Preset", "Preset has no entries to insert.")
            return
        unique_label = self._unique_preset_label(preset_copy["label"])
        if unique_label != preset_copy["label"]:
            preset_copy["label"] = unique_label
        player_updated = False
        for entry in preset_entries:
            actor_type = entry.get("actor_type", "").strip().upper()
            if actor_type == "PLAYER":
                entry["alias"] = unique_label
                player_updated = True
        if not player_updated and preset_entries:
            preset_entries[0]["alias"] = unique_label
        try:
            group = self.model.add_preset_group(preset_copy)
        except Exception as exc:
            messagebox.showerror("Preset", str(exc))
            return
        self.current_group = group.index
        self.current_entry = None
        self._refresh_group_list(reset_selection=False)
        self.status_var.set(f"Preset '{unique_label}' inserted (not saved).")

    def _add_label(self, parent: tk.Widget, text: str, row: int) -> None:
        tk.Label(parent, text=text, bg=BACKGROUND, fg=FOREGROUND).grid(row=row, column=0, sticky="w", padx=6, pady=4)

    def _add_entry(self, parent: tk.Widget, label: str, row: int, variable: tk.StringVar) -> None:
        self._add_label(parent, label, row)
        entry = tk.Entry(parent, textvariable=variable, bg=INPUT_BG, fg=INPUT_FG, insertbackground=FOREGROUND)
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)

    def _ensure_deck_choice(self, deck: str) -> None:
        deck = deck.strip()
        if not deck or deck in self.deck_options:
            return
        self.deck_options.append(deck)
        self.deck_options.sort(key=lambda value: value.lower())
        if self.deck_combo is not None:
            self.deck_combo.configure(values=self.deck_options)

    def _ensure_ai_choice(self, script: str) -> None:
        script = script.strip()
        if not script or script in self.ai_options:
            return
        self.ai_options.append(script)
        self.ai_options.sort(key=lambda value: value.lower())
        if self.ai_combo is not None:
            self.ai_combo.configure(values=self.ai_options)

    def _update_character_choices(self) -> None:
        if self.character_combo is None:
            return
        options = self.model.character_options() if self.model else []
        self.character_combo.configure(values=options)
        formatted = None
        raw_value = self.character_id_var.get().strip()
        if raw_value:
            formatted = self._format_character_option(raw_value)
            if not formatted:
                normalized = normalize_character_key(raw_value)
                if normalized:
                    alias = self._character_default_alias(normalized)
                    if alias:
                        formatted = character_display_label(normalized, alias)
        if formatted:
            self.character_combo_var.set(formatted)
        else:
            self.character_combo_var.set("")

    def _format_character_option(self, value: str) -> Optional[str]:
        if not self.model:
            return None
        key = value.strip()
        if not key:
            return None
        if " - " in key:
            key = key.split(" - ", 1)[0].strip()
        normalized = normalize_character_key(key)
        if normalized:
            name = self.model.character_map.get(normalized)
            if name:
                return character_display_label(normalized, name)
        number = parse_character_number(key)
        if number is None:
            return None
        normalized = f"{number:02X}"
        name = self.model.character_map.get(normalized)
        if name:
            return character_display_label(normalized, name)
        return None

    def _on_character_choice(self, event: tk.Event[Any]) -> None:
        selection = self.character_combo_var.get().strip()
        if not selection:
            return
        char_id = selection.split(" - ", 1)[0].strip()
        self._set_character_id(char_id)

    def _resolve_character_id(self) -> str:
        raw_value = self.character_id_var.get().strip()
        if not raw_value:
            selection = self.character_combo_var.get().strip()
            if selection:
                raw_value = selection.split(" - ", 1)[0].strip()
        if not raw_value:
            return "00"
        if " - " in raw_value:
            raw_value = raw_value.split(" - ", 1)[0].strip()
        normalized = normalize_character_key(raw_value)
        if normalized:
            return normalized
        number = parse_character_number(raw_value)
        if number is None:
            return "00"
        return coerce_character_id(f"{number:02X}")

    def _prompt_actor_type(self) -> Optional[str]:
        prompt = simpledialog.askstring(
            "Actor Type",
            "Enter actor type (e.g. PLAYER, ENEMY, BOSS00...)",
            initialvalue="ENEMY",
            parent=self.frame,
        )
        if prompt is None:
            return None
        prompt = prompt.strip().upper()
        return prompt or "ENEMY"

    def _add_actor_clicked(self) -> None:
        if self.model is None or self.current_group is None:
            return
        if self.current_entry is not None and not self._apply_form():
            return
        actor_type = self._prompt_actor_type()
        if not actor_type:
            return
        try:
            group = self.model.add_entry(self.current_group, actor_type)
        except Exception as exc:  # pragma: no cover - tkinter callback
            messagebox.showerror("Add actor failed", str(exc))
            return
        self.current_entry = len(group.entries) - 1
        self._refresh_group_list(reset_selection=False)
        self.status_var.set("Actor added (not saved).")

    def _remove_actor_clicked(self) -> None:
        if self.model is None or self.current_group is None or self.current_entry is None:
            return
        group = self.model.groups[self.current_group]
        if group.entry_count <= 1:
            messagebox.showerror("Remove actor failed", "Mission must keep at least one character.")
            return
        if not messagebox.askyesno("Remove actor", "Remove the selected actor?", parent=self.frame):
            return
        try:
            self.model.remove_entry(self.current_group, self.current_entry)
        except Exception as exc:  # pragma: no cover - tkinter callback
            messagebox.showerror("Remove actor failed", str(exc))
            return
        entries = self.model.groups[self.current_group].entries
        self.current_entry = min(self.current_entry, len(entries) - 1) if entries else None
        self._refresh_group_list(reset_selection=False)
        self.status_var.set("Actor removed (not saved).")

    def _browse_file(self) -> None:
        file_path = filedialog.askopenfilename(
            initialdir=single2_file_path().parent,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if file_path:
            self.file_var.set(file_path)

    def _load_clicked(self) -> None:
        target = Path(self.file_var.get()).expanduser()
        self._load_file(target)

    def _load_file(self, target: Path) -> None:
        try:
            self.model = Single2Model(target)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.ai_options = self._discover_ai_scripts()
        if self.ai_combo is not None:
            self.ai_combo.configure(values=self.ai_options)
        self.current_group = None
        self.current_entry = None
        self._refresh_group_list(reset_selection=True)
        if self.model:
            for entry in self.model.entries:
                self._ensure_ai_choice(entry.ai_script)
            if self.ai_combo is not None:
                self.ai_combo.configure(values=self.ai_options)
        message = f"Loaded Debug Test actors: {target}"
        violations = self.model.rule_violations()
        if violations:
            message += f" | First issue: {violations[0]}"
        self.status_var.set(message)
        self._update_character_choices()

    def _refresh_group_list(self, reset_selection: bool = False) -> None:
        if self.mission_list is None:
            return
        previous_group = None if reset_selection else self.current_group
        self.mission_list.delete(0, tk.END)
        if not self.model or not self.model.groups:
            self.current_group = None
            self._refresh_entries(reset_entry=True)
            return
        for group in self.model.groups:
            self.mission_list.insert(tk.END, group.summary_label())
        target = previous_group if previous_group is not None else 0
        target = max(0, min(target, len(self.model.groups) - 1))
        if previous_group is None:
            self.current_entry = None
        self.current_group = target
        self.mission_list.selection_clear(0, tk.END)
        self.mission_list.selection_set(target)
        self.mission_list.see(target)
        self._refresh_entries(reset_entry=previous_group is None)
        self._update_character_choices()

    def _refresh_entries(self, reset_entry: bool = False) -> None:
        if self.entry_list is None:
            return
        self.entry_list.delete(0, tk.END)
        if not self.model or self.current_group is None:
            self.current_entry = None
            self._clear_form()
            return
        group = self.model.groups[self.current_group]
        for idx, entry in enumerate(group.entries):
            deck_display = entry.deck or "(no deck)"
            alias_display = entry.alias or "(blank)"
            actor_display = entry.actor_type or "?"
            self.entry_list.insert(tk.END, f"{idx:02d} - {actor_display} - {alias_display} - {deck_display}")
        if not group.entries:
            self.current_entry = None
            self._clear_form()
            self._update_character_choices()
            return
        if reset_entry or self.current_entry is None or self.current_entry >= len(group.entries):
            self.current_entry = 0
        self.entry_list.selection_clear(0, tk.END)
        self.entry_list.selection_set(self.current_entry)
        self.entry_list.see(self.current_entry)
        self._load_entry(group.entries[self.current_entry])
        self._update_character_choices()

    def _clear_form(self) -> None:
        self.actor_type_var.set(ACTOR_TYPES[0])
        self.spawn_slot_var.set("-1")
        self._set_alias("", auto=True)
        self.deck_var.set("")
        self.ai_var.set("")
        self._set_character_id("00", suppress=True)
        self.spawn_index_var.set("0")
        self.hp_var.set("20")
        self.flag_a_var.set("0")
        self.flag_b_var.set("0")
        self.character_combo_var.set("")
        self._last_auto_alias = self._character_default_alias("00") or ""
        self._update_character_choices()

    def _load_entry(self, entry: Single2Entry) -> None:
        actor_type = entry.actor_type or ACTOR_TYPES[0]
        self.actor_type_var.set(actor_type)
        self.spawn_slot_var.set(str(entry.spawn_slot))
        self._set_alias(entry.alias, auto=False)
        self._ensure_deck_choice(entry.deck)
        self.deck_var.set(entry.deck)
        self._ensure_ai_choice(entry.ai_script)
        self.ai_var.set(entry.ai_script)
        self._set_character_id(entry.character_id, suppress=True)
        self.spawn_index_var.set(str(entry.spawn_index))
        self.hp_var.set(str(entry.hp))
        self.flag_a_var.set(str(entry.flag_a))
        self.flag_b_var.set(str(entry.flag_b))
        formatted = self._format_character_option(entry.character_id)
        self.character_combo_var.set(formatted or "")
        self._infer_alias_auto_state(entry)
        self._update_character_choices()

    def _on_mission_select(self, event: tk.Event[tk.Widget]) -> None:
        if self.mission_list is None:
            return
        index = first_selection(self.mission_list.curselection())  # type: ignore[call-arg]
        if index is None:
            return
        if self.current_group == index:
            return
        self.current_group = index
        self.current_entry = None
        self._refresh_entries(reset_entry=True)

    def _on_entry_select(self, event: tk.Event[tk.Widget]) -> None:
        if not self.model or self.entry_list is None or self.current_group is None:
            return
        index = first_selection(self.entry_list.curselection())  # type: ignore[call-arg]
        if index is None:
            return
        self.current_entry = index
        entry = self.model.groups[self.current_group].entries[index]
        self._load_entry(entry)

    def _apply_clicked(self) -> None:
        if self.current_group is None or self.current_entry is None:
            return
        if self._apply_form():
            self._refresh_group_list(reset_selection=False)
            self.status_var.set("Entry updated (not saved).")

    def _apply_form(self) -> bool:
        if self.model is None or self.current_group is None or self.current_entry is None:
            return False
        group = self.model.groups[self.current_group]
        entry = group.entries[self.current_entry]
        actor_type = self.actor_type_var.get().strip()
        if not actor_type:
            messagebox.showerror("Invalid value", "Actor type cannot be blank.")
            return False
        entry.actor_type = actor_type
        try:
            entry.spawn_slot = int(self.spawn_slot_var.get().strip() or -1)
            entry.spawn_index = int(self.spawn_index_var.get().strip() or 0)
            entry.hp = int(self.hp_var.get().strip() or 20)
            entry.flag_a = int(self.flag_a_var.get().strip() or 0)
            entry.flag_b = int(self.flag_b_var.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Invalid value", "Numeric fields must contain integers.")
            return False
        char_id = self._resolve_character_id()
        number = parse_character_number(char_id)
        upper_dec = character_display_value(f"{MAX_CHARACTER_ID:02X}")
        if number is None:
            messagebox.showerror(
                "Invalid value",
                f"Character ID must be a number between 0 and {upper_dec}.",
            )
            return False
        if not 0 <= number <= MAX_CHARACTER_ID:
            messagebox.showerror(
                "Invalid value",
                f"Character ID must be between 0 and {upper_dec}.",
            )
            return False
        char_id_str = f"{number:02X}"
        entry.character_id = char_id_str
        self._set_character_id(char_id_str)
        entry.alias = self.alias_var.get().strip()
        deck_value = self.deck_var.get().strip()
        if entry.actor_type.upper() != "PLAYER" and not deck_value:
            messagebox.showerror("Invalid value", "Deck is required for non-player actors.")
            return False
        entry.deck = deck_value
        self._ensure_deck_choice(deck_value)
        entry.ai_script = self.ai_var.get().strip()
        self._ensure_ai_choice(entry.ai_script)
        if self.model:
            self.model.refresh_character_map()
        self._handle_character_alias_update()
        self._update_character_choices()
        return True

    def _save_clicked(self) -> None:
        if self.model is None:
            messagebox.showinfo("No file", "Load a single2.csv file first.")
            return
        if self.current_group is not None and self.current_entry is not None:
            if not self._apply_form():
                return
        allow_violations = False
        violations = self.model.rule_violations()
        if violations:
            preview_lines = [f"- {issue}" for issue in violations[:5]]
            if len(violations) > 5:
                preview_lines.append(f"...and {len(violations) - 5} more issue(s).")
            warning_text = (
                "Rule violations detected:\n"
                + "\n".join(preview_lines)
                + "\n\nSaving with these issues may cause the game to crash. Continue anyway?"
            )
            allow_violations = messagebox.askyesno("Rule Violations", warning_text)
            if not allow_violations:
                self.status_var.set("Save canceled. Resolve rule violations first.")
                return
        try:
            self.model.save(allow_violations=allow_violations)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self._refresh_group_list(reset_selection=False)
        if violations and allow_violations:
            self.status_var.set("Debug Test actors saved with rule violations.")
        else:
            self.status_var.set("Debug Test actors saved.")


class BBMODSDebugEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BBMODS Debug Editor")
        self.configure(bg=BACKGROUND)
        self.geometry("1120x620")
        self.resizable(True, True)

        self.status_var = tk.StringVar(value="")

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.stage_tab = StageTab(notebook, self.status_var, on_root_changed=self._on_root_changed)
        self.single_tab = Single2Tab(notebook, self.status_var)

        notebook.add(self.stage_tab.frame, text="Stage Sets")
        notebook.add(self.single_tab.frame, text="Debug Test Actors")

        status_label = tk.Label(self, textvariable=self.status_var, bg=BACKGROUND, fg=FOREGROUND, anchor="w")
        status_label.pack(fill=tk.X, padx=12, pady=(0, 8))

        self._on_root_changed(get_game_root())

    def _on_root_changed(self, root: Path) -> None:
        ensure_single2_seed(single2_file_path(root))
        self.single_tab.update_root(root)


def main() -> None:
    editor = BBMODSDebugEditor()
    editor.mainloop()


if __name__ == "__main__":
    main()
