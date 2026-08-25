from pathlib import Path

from ptrade_order_tool.data.file_naming import (
    migrate_legacy_json_files,
    order_filename,
    parse_prefixed_date,
    ptrade_filename,
)


def test_prefixed_filenames_and_date_parser_are_strict():
    assert ptrade_filename("20260824") == "ptrade_20260824.json"
    assert order_filename("20260824") == "order_20260824.json"
    assert parse_prefixed_date("ptrade_20260824.json", "ptrade_") == "20260824"
    assert parse_prefixed_date("20260824.json", "ptrade_") is None
    assert parse_prefixed_date("ptrade_2026082.json", "ptrade_") is None


def test_migration_renames_legacy_files_and_keeps_unrelated_files(tmp_path):
    ptrade_dir = tmp_path / "ptrade"
    order_dir = tmp_path / "order"
    ptrade_dir.mkdir()
    order_dir.mkdir()
    old_ptrade = ptrade_dir / "20260824.json"
    old_order = order_dir / "20260824.json"
    old_ptrade.write_text("ptrade", encoding="utf-8")
    old_order.write_text("order", encoding="utf-8")
    (ptrade_dir / "notes.json").write_text("notes", encoding="utf-8")

    result = migrate_legacy_json_files(ptrade_dir, order_dir)

    assert not old_ptrade.exists()
    assert not old_order.exists()
    assert (ptrade_dir / "ptrade_20260824.json").read_text(encoding="utf-8") == "ptrade"
    assert (order_dir / "order_20260824.json").read_text(encoding="utf-8") == "order"
    assert result.conflicts == ()


def test_migration_does_not_overwrite_different_prefixed_target(tmp_path):
    ptrade_dir = tmp_path / "ptrade"
    ptrade_dir.mkdir()
    legacy = ptrade_dir / "20260824.json"
    target = ptrade_dir / "ptrade_20260824.json"
    legacy.write_text("old", encoding="utf-8")
    target.write_text("new", encoding="utf-8")

    result = migrate_legacy_json_files(ptrade_dir, None)

    assert legacy.exists()
    assert target.read_text(encoding="utf-8") == "new"
    assert result.conflicts == ((legacy, target),)


def test_migration_removes_identical_legacy_duplicate(tmp_path):
    order_dir = tmp_path / "order"
    order_dir.mkdir()
    legacy = order_dir / "20260824.json"
    target = order_dir / "order_20260824.json"
    legacy.write_bytes(b"same")
    target.write_bytes(b"same")

    result = migrate_legacy_json_files(None, order_dir)

    assert not legacy.exists()
    assert target.exists()
    assert result.renamed == ((legacy, target),)
