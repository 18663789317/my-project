# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


PROJECT_ROOT = Path(SPECPATH).resolve()


def _unique_toc(entries):
    seen = set()
    result = []
    for src, dest in entries:
        key = (src, dest)
        if key in seen:
            continue
        seen.add(key)
        result.append((src, dest))
    return result


def _unique_strings(entries):
    seen = set()
    result = []
    for item in entries:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


datas = [
    (str(PROJECT_ROOT / "app.py"), "."),
]

for optional_name in ("otc_gui.db", "manifest.json"):
    optional_path = PROJECT_ROOT / optional_name
    if optional_path.exists():
        datas.append((str(optional_path), "."))

datas += collect_data_files(
    "streamlit",
    excludes=["hello/**/*", "testing/**/*"],
)
datas += collect_data_files("akshare")
datas += copy_metadata("streamlit")
datas += copy_metadata("pandas")
datas += copy_metadata("matplotlib")
datas += copy_metadata("numpy")
datas += copy_metadata("pyarrow")
datas += copy_metadata("akshare")
datas += copy_metadata("chinese_calendar")

binaries = []
binaries += collect_dynamic_libs("pyarrow")

hiddenimports = [
    "numpy",
    "pandas",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.font_manager",
    "matplotlib.patheffects",
    "matplotlib.patches",
    "matplotlib.ticker",
    "matplotlib.backends.backend_agg",
    "streamlit",
    "streamlit.components.v1",
    "streamlit.hello",
    "streamlit.hello.streamlit_app",
    "streamlit.web.cli",
    "chinese_calendar",
    "pyarrow",
    "pyarrow.lib",
    "akshare",
    "akshare.futures.futures_zh_sina",
    "akshare.futures_derivative.futures_index_sina",
]
hiddenimports += collect_submodules("streamlit.runtime")
hiddenimports += collect_submodules("streamlit.web")
hiddenimports += collect_submodules("streamlit.proto")
hiddenimports += collect_submodules("streamlit.components")

datas = _unique_toc(datas)
binaries = _unique_toc(binaries)
hiddenimports = _unique_strings(hiddenimports)

excludes = [
    "pandas.tests",
    "matplotlib.tests",
    "matplotlib.testing",
    "pytest",
    "streamlit.testing",
    "IPython",
    "jupyter",
    "notebook",
    "tensorflow",
]


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OTC-Risk-App',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OTC-Risk-App',
)
