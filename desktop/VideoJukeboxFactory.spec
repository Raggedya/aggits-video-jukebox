# -*- mode: python ; coding: utf-8 -*-
import os
import runpy
from pathlib import Path

root = Path(SPECPATH).parent
version = runpy.run_path(str(root / "src" / "aggits_video_factory" / "version.py"))
version_resource = os.environ.get("CRISPY_BITS_VERSION_FILE")
if not version_resource or not Path(version_resource).is_file():
    raise RuntimeError("CRISPY_BITS_VERSION_FILE must identify the generated Windows version resource.")

a = Analysis(
    [str(root / "desktop" / "video_jukebox_factory.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=version["EXE_STEM"],
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_resource,
)
