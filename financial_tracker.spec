# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Financial Strategy Tracker.

Build with:
    pyinstaller financial_tracker.spec

Output: dist/financial_tracker/  (onedir bundle)
"""

import importlib
import importlib.metadata
import os
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata, collect_all

# ---------------------------------------------------------------------------
# Version (read from VERSION file at project root)
# ---------------------------------------------------------------------------

version = Path("VERSION").read_text(encoding="utf-8").strip()

# ---------------------------------------------------------------------------
# Streamlit static assets path
# ---------------------------------------------------------------------------

streamlit_pkg = Path(importlib.import_module("streamlit").__file__).parent
streamlit_static = str(streamlit_pkg / "static")

# ---------------------------------------------------------------------------
# Package metadata (importlib.metadata needs *.dist-info at runtime)
# ---------------------------------------------------------------------------

metadata_packages = [
    "streamlit",
    "altair",
    "pandas",
    "plotly",
    "pyarrow",
    "numpy",
    "packaging",
    "importlib_metadata",
    "tornado",
    "click",
    "rich",
    "toml",
    "gitpython",
    "pydeck",
]

metadata_datas = []
for pkg in metadata_packages:
    try:
        metadata_datas += copy_metadata(pkg)
    except Exception:
        pass  # skip packages not installed

# ---------------------------------------------------------------------------
# Collect all streamlit submodules, data files, and binaries
# ---------------------------------------------------------------------------

st_datas, st_binaries, st_hiddenimports = collect_all("streamlit")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[] + st_binaries,
    datas=[
        # Include app source files that launcher.py references
        ("app.py", "."),
        ("config.py", "."),
        ("constants.py", "."),
        ("calculations.py", "."),
        ("database.py", "."),
        ("engine.py", "."),
        ("models.py", "."),
        ("repository.py", "."),
        ("VERSION", "."),
        # Package directories
        ("charts", "charts"),
        ("importers", "importers"),
        ("strategies", "strategies"),
        ("views", "views"),
    ] + metadata_datas + st_datas,
    hiddenimports=[
        "plotly",
        "pandas",
        "openpyxl",
        "sqlite3",
    ] + st_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="financial_tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # console visible so Streamlit can log startup info
    icon=None,
    version_info=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="financial_tracker",
)
