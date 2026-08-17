# PyInstaller spec — génère un .exe Windows autonome.
# Build : pyinstaller packaging/call_analyzer.spec   (depuis le dossier call-analyzer)
#
# L'icône n'est pas dupliquée dans call-analyzer/ : elle est reprise directement du
# dossier voisin ../desktop-app (icône de marque CADUCEA), présent dans le même
# checkout du dépôt au moment du build.

block_cipher = None

ICON = "../../desktop-app/icon.ico"

a = Analysis(
    ["../main.py"],
    pathex=["."],
    binaries=[],
    datas=[(ICON, ".")],
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
    name="CADUCEA - Analyse interne des appels",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    onefile=True,
    icon=ICON,
)
