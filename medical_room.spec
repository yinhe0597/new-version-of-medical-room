# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Medical Room Management System

import sys
import os

block_cipher = None

a = Analysis(
    ['run_prod.py'],
    pathex=['D:\\yiwushi\\new-version-of-medical-room'],
    binaries=[],
    datas=[
        ('frontend/dist', 'frontend/dist'),
    ],
    hiddenimports=[
        # Backend modules
        'backend.config',
        'backend.app',
        'backend.app.api',
        'backend.app.api.routes',
        'backend.app.api.auth',
        'backend.app.api.doctor',
        'backend.app.api.nurse',
        'backend.app.api.admin',
        'backend.app.models',
        'backend.app.utils',
        'backend.app.utils.decorators',
        'backend.app.services',
        'backend.app.services.drug_stock',
        # SQLAlchemy dialects (dynamically loaded)
        'sqlalchemy.dialects.sqlite',
        # Flask extensions
        'flask_cors',
        'flask_jwt_extended',
        'flask_sqlalchemy',
        'flask_migrate',
        # Data processing
        'pypinyin',
        'pypinyin.style',
        'pypinyin.style._utils',
        'pypinyin.contrib',
        'openpyxl',
        'pandas',
        'numpy',
        'xlrd',
        # Other
        'werkzeug',
        'jinja2',
        'markupsafe',
        'click',
        'itsdangerous',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'pymysql',
        'matplotlib',
        'scipy',
        'PIL',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='医务室管理系统',
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
