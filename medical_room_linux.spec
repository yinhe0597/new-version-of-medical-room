# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Medical Room Management System (Linux)
# 用于在 Linux 上编译打包

import sys
import os

block_cipher = None

# 自动检测项目根目录（spec 文件所在目录）
SPEC_DIR = os.path.abspath(SPECPATH)

a = Analysis(
    ['run_prod.py'],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SPEC_DIR, 'frontend', 'dist'), 'frontend/dist'),
        (os.path.join(SPEC_DIR, 'backend', 'migrations'), 'backend/migrations'),
    ],
    hiddenimports=[
        # Backend modules
        'backend.config',
        'backend.migrate_to_mysql',
        'backend.migration_app',
        'backend.production_cli',
        'backend.app',
        'backend.app.api',
        'backend.app.api.routes',
        'backend.app.api.auth',
        'backend.app.api.doctor',
        'backend.app.api.nurse',
        'backend.app.api.admin',
        'backend.app.api.finance',
        'backend.app.models',
        'backend.app.utils',
        'backend.app.utils.decorators',
        'backend.app.services',
        'backend.app.services.drug_stock',
        'backend.migrations.migration_helpers',
        'scripts.check_production_database',
        # SQLAlchemy dialects (dynamically loaded)
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.mysql',
        'sqlalchemy.dialects.mysql.pymysql',
        'pymysql',
        'pymysql.connections',
        'pymysql.cursors',
        # Flask extensions
        'flask_cors',
        'flask_jwt_extended',
        'flask_sqlalchemy',
        'flask_migrate',
        'alembic',
        'alembic.runtime.migration',
        'alembic.config',
        'alembic.script',
        'alembic.autogenerate',
        # Data processing
        'pypinyin',
        'pypinyin.style',
        'pypinyin.style._utils',
        'pypinyin.contrib',
        'openpyxl',
        'openpyxl.writer.excel',
        'openpyxl.cell._writer',
        'openpyxl.reader.excel',
        'pandas',
        'numpy',
        'xlrd',
        # Other
        'werkzeug',
        'werkzeug.security',
        'jinja2',
        'markupsafe',
        'click',
        'itsdangerous',
        'dotenv',
        'dateutil',
        'sqlalchemy.sql.default_comparator',
        'waitress',
        'waitress.server',
        'waitress.task',
        'waitress.channel',
        'waitress.parser',
        'waitress.adjustments',
        'waitress.receiver',
        'waitress.buffers',
        'waitress.utilities',
        'waitress.proxy_headers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'matplotlib',
        'scipy',
        'PIL',
        'cv2',
        'setuptools',
        'pip',
    ],
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
    name='medical_room',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
)
