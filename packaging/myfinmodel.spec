# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

# __file__ is not defined when PyInstaller executes a .spec file.
# SPECPATH points to the folder containing this spec (packaging/).
BASE_DIR = Path(SPECPATH).resolve().parent


from PyInstaller.utils.hooks import collect_data_files, copy_metadata

def collect_tree(source_dir: str, destination_root: str) -> list[tuple[str, str]]:
    source_path = BASE_DIR / source_dir
    if not source_path.exists():
        return []

    data: list[tuple[str, str]] = []
    for file_path in source_path.rglob("*"):
        if file_path.is_file() and "__pycache__" not in file_path.parts:
            relative_parent = file_path.parent.relative_to(source_path)
            destination = str(Path(destination_root) / relative_parent)
            data.append((str(file_path), destination))
    return data


datas = [
    (str(BASE_DIR / "app.py"), "."),
    *collect_tree("simulation", "simulation"),
    *collect_tree("ui", "ui"),
    *collect_tree("utils", "utils"),
    *collect_data_files("streamlit"),
    *copy_metadata("streamlit"),
]

hiddenimports = [
    "streamlit",
    "streamlit.web.cli",
]


block_cipher = None


a = Analysis(
    [str(BASE_DIR / "packaging/launcher/__main__.py")],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="MyFinModelLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Keep launcher windowless for double-click user flow; failures are logged to launcher.log.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MyFinModelLauncher",
)
