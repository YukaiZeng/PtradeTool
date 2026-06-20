from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_scripts_use_project_spec_and_platform_python_defaults():
    macos_script = (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")
    windows_script = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")

    assert "ptrade-order-tool.spec --clean --noconfirm" in macos_script
    assert "ptrade-order-tool.spec --clean --noconfirm" in windows_script
    assert '.venv/bin/python' in macos_script
    assert r".venv\Scripts\python.exe" in windows_script


def test_pyinstaller_spec_only_builds_macos_bundle_on_darwin():
    spec = (ROOT / "ptrade-order-tool.spec").read_text(encoding="utf-8")

    assert '["src/ptrade_order_tool/main.py"]' in spec
    assert 'name="PtradeOrderTool"' in spec
    assert 'if sys.platform == "darwin":' in spec
    assert spec.index('if sys.platform == "darwin":') < spec.index("BUNDLE(")
    assert "COLLECT(" in spec
    assert "hiddenimports=[]" in spec
