from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


PTRADER_PREFIX = "ptrade_"
ORDER_PREFIX = "order_"
_DATE_RE = re.compile(r"^\d{8}$")
_LEGACY_JSON_RE = re.compile(r"^(\d{8})\.json$")


@dataclass(frozen=True, slots=True)
class JsonFilenameMigration:
    renamed: tuple[tuple[Path, Path], ...] = ()
    conflicts: tuple[tuple[Path, Path], ...] = ()


def ptrade_filename(manage_date: str) -> str:
    _validate_date(manage_date)
    return f"{PTRADER_PREFIX}{manage_date}.json"


def order_filename(manage_date: str) -> str:
    _validate_date(manage_date)
    return f"{ORDER_PREFIX}{manage_date}.json"


def parse_prefixed_date(filename: str, prefix: str) -> str | None:
    match = re.fullmatch(rf"{re.escape(prefix)}(\d{{8}})\.json", filename)
    return match.group(1) if match else None


def migrate_legacy_json_files(
    ptrade_data_dir: str | Path | None,
    order_data_dir: str | Path | None,
) -> JsonFilenameMigration:
    renamed: list[tuple[Path, Path]] = []
    conflicts: list[tuple[Path, Path]] = []
    for directory, prefix in (
        (ptrade_data_dir, PTRADER_PREFIX),
        (order_data_dir, ORDER_PREFIX),
    ):
        if not directory:
            continue
        root = Path(directory)
        if not root.is_dir():
            continue
        for legacy_path in sorted(root.iterdir(), key=lambda path: path.name):
            match = _LEGACY_JSON_RE.fullmatch(legacy_path.name)
            if not legacy_path.is_file() or match is None:
                continue
            target = root / f"{prefix}{match.group(1)}.json"
            if target.exists():
                if target.is_file() and target.read_bytes() == legacy_path.read_bytes():
                    legacy_path.unlink()
                    renamed.append((legacy_path, target))
                else:
                    conflicts.append((legacy_path, target))
                continue
            legacy_path.replace(target)
            renamed.append((legacy_path, target))
    return JsonFilenameMigration(tuple(renamed), tuple(conflicts))


def _validate_date(manage_date: str) -> None:
    if not _DATE_RE.fullmatch(manage_date):
        raise ValueError(f"Invalid manage date: {manage_date}")
