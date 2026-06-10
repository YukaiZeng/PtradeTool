from pathlib import Path

from ptrade_order_tool.data.order_exporter import ORDER_TYPES


def test_ptrade_runtime_reads_all_exported_order_types():
    runtime_source = (
        Path(__file__).parents[1] / "src" / "ptrade_order_tool" / "runtime" / "in-app.py"
    ).read_text(encoding="utf-8")

    for order_type in ORDER_TYPES:
        assert f'info_dict.get("{order_type}"' in runtime_source
