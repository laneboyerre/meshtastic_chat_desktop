# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['meshtastic_chat_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('Class\\\\meshtastic_chat_app.py', 'Class'), ('datafile.txt', '.')],
    hiddenimports=['webview', 'timeago', 'timeago.locales.en'],
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
    name='meshtastic_chat_desktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
