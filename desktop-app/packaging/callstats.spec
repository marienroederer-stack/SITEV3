# PyInstaller spec — génère un .exe Windows autonome.
# Build : pyinstaller packaging/callstats.spec   (depuis le dossier desktop-app)

block_cipher = None

a = Analysis(
    ["../main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DoctelStatsAppels",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    onefile=True,
)
