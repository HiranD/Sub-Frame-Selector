# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for SubFrame Selector.

Build commands:
  macOS:   pyinstaller subframe-selector.spec
  Windows: pyinstaller subframe-selector.spec

Output: dist/SubFrame Selector/
"""

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Determine platform
is_macos = sys.platform == 'darwin'
is_windows = sys.platform == 'win32'

# App metadata
APP_NAME = 'SubFrame Selector'
APP_VERSION = '1.0.0'

# Paths
block_cipher = None
spec_dir = os.path.dirname(os.path.abspath(SPEC))

# Icon paths (will be created later)
icon_file = None
if is_macos and os.path.exists(os.path.join(spec_dir, 'assets', 'icon.icns')):
    icon_file = os.path.join(spec_dir, 'assets', 'icon.icns')
elif is_windows and os.path.exists(os.path.join(spec_dir, 'assets', 'icon.ico')):
    icon_file = os.path.join(spec_dir, 'assets', 'icon.ico')

# Collect all data for scientific packages
matplotlib_datas, matplotlib_binaries, matplotlib_hiddenimports = collect_all('matplotlib')
astropy_datas, astropy_binaries, astropy_hiddenimports = collect_all('astropy')
photutils_datas, photutils_binaries, photutils_hiddenimports = collect_all('photutils')

# Additional hidden imports for multiprocessing and tkinter
hidden_imports = [
    'multiprocessing',
    'multiprocessing.pool',
    'multiprocessing.process',
    'multiprocessing.spawn',
    'multiprocessing.popen_spawn_win32' if is_windows else 'multiprocessing.popen_spawn_posix',
    'multiprocessing.popen_fork',
    'multiprocessing.popen_forkserver',
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'customtkinter',
    'PIL',
    'PIL._tkinter_finder',
    'scipy.special._cdflib',
    'scipy.special._ufuncs',
    'scipy.linalg',
    'scipy.ndimage',
    'scipy.optimize',
    'scipy.stats',
    'numpy',
    'astropy.io.fits',
    'astropy.wcs',
    'photutils.detection',
    'photutils.background',
    'photutils.psf',
]

# Combine all hidden imports
all_hidden_imports = (
    hidden_imports +
    matplotlib_hiddenimports +
    astropy_hiddenimports +
    photutils_hiddenimports
)

# Combine all datas
all_datas = matplotlib_datas + astropy_datas + photutils_datas

# Combine all binaries
all_binaries = matplotlib_binaries + astropy_binaries + photutils_binaries

# Analysis
a = Analysis(
    ['run.py'],
    pathex=[os.path.join(spec_dir, 'src')],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'sphinx',
        'docutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove unnecessary files to reduce size
a.datas = [d for d in a.datas if not d[0].startswith('share/doc')]
a.datas = [d for d in a.datas if not d[0].endswith('.pyx')]
a.datas = [d for d in a.datas if not d[0].endswith('.pxd')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (windowed mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS: Create .app bundle
if is_macos:
    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=icon_file,
        bundle_identifier='com.subframeselector.app',
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleVersion': APP_VERSION,
            'CFBundleShortVersionString': APP_VERSION,
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,  # Support dark mode
        },
    )
