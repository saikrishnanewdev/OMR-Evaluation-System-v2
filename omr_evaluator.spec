# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import site
import sys

block_cipher = None

# Locate rapidocr_onnxruntime package to bundle local models
import rapidocr_onnxruntime
rapidocr_dir = str(Path(rapidocr_onnxruntime.__file__).parent)

datas = [
    ('app/database/schema.sql', 'app/database'),
    ('models/template_digits.npz', 'models'),
    ('resources/app_icon.png', 'resources'),
    ('resources/app_icon.ico', 'resources'),
    ('resources/spin_up.png', 'resources'),
    ('resources/spin_down.png', 'resources'),
]

if rapidocr_dir:
    datas.append((rapidocr_dir, 'rapidocr_onnxruntime'))

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'app.ui.client_window',
        'app.ui.license_dialog',
        'app.security.license_manager',
        'extract_identities_to_excel',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'cv2',
        'pymupdf',
        'rapidocr_onnxruntime',
        'onnxruntime',
        'pytesseract',
        # 'six' is imported by rapidocr_onnxruntime/ch_ppocr_v3_det/utils.py,
        # loaded dynamically via importlib, so PyInstaller's static scan
        # misses it — same crash class as pytesseract before it. The three
        # subpackages are also loaded dynamically (Det/Rec/Cls), so list
        # them explicitly too.
        'six',
        'rapidocr_onnxruntime.ch_ppocr_v3_det',
        'rapidocr_onnxruntime.ch_ppocr_v3_rec',
        'rapidocr_onnxruntime.ch_ppocr_v2_cls',
        'openpyxl',
        'openpyxl.styles',
        'pandas',
        'sqlite3',
        'pyclipper',
        'shapely',
        'yaml',
        'PIL',
        'PIL.Image'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'torchaudio', 'transformers', 'huggingface_hub',
        'scipy', 'matplotlib', 'gradio', 'gradio_client', 'boto3', 'botocore',
        'playwright', 'fastapi', 'flask', 'sqlalchemy', 'fsspec', 'alembic',
        'gevent', 'yfinance', 'sympy', 'peewee', 'darkdetect', 'customtkinter'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OMREvaluationSystem',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OMREvaluationSystem',
)
