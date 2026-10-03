# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build recipe for the released NetWatch.exe.

Build it with:

    pyinstaller --noconfirm --clean NetWatch.spec

A .spec file is just Python that PyInstaller execs, so everything below is
ordinary code. It is kept in the repo (rather than a long one-off command
line) because every setting here exists to fix a specific, reproducible way
the build breaks — and those reasons belong in version control, not in
someone's shell history.

This file and .github/workflows/release.yml are the *entire* packaging
setup: no application source file is modified or added for the release, so
the released binary runs exactly the code that is in the repository.

Note: PyInstaller does NOT cross-compile. Running this on Linux produces a
Linux binary, not an .exe. The Windows build happens on the windows-latest
runner in .github/workflows/release.yml.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# --------------------------------------------------------------------------- #
# Extra files and modules PyInstaller's static analysis cannot find on its own
# --------------------------------------------------------------------------- #

datas = []
hiddenimports = []

# customtkinter ships its widget themes as JSON (blue.json, dark-blue.json, …)
# and bundles font files. These are opened by *filename at runtime*, so nothing
# in the source code imports them and PyInstaller's import scanner never sees
# them. Without this the frozen app dies on the first ctk widget with a
# FileNotFoundError on blue.json.
datas += collect_data_files("customtkinter")

# scapy builds its protocol layers by importing modules dynamically from
# scapy.layers at runtime (scapy.layers.all walks the package). Static analysis
# only sees `from scapy.all import ARP, Ether, conf, srp`, so every protocol
# module would be left out and the ARP scan in core/wireless_scanner.py would
# fail with a missing-layer error. collect_submodules pulls the whole package.
hiddenimports += collect_submodules("scapy")

# desktop_notifier.common does `files("desktop_notifier.resources") / "python.png"`
# at *import time* — a default notification icon loaded through
# importlib.resources rather than a normal import. PyInstaller sees neither the
# subpackage nor the PNG, so the frozen app aborts on startup with
# "ModuleNotFoundError: No module named 'desktop_notifier.resources'" the moment
# UI/notifier.py is imported. (Verified: this is what the first test build did.)
datas += collect_data_files("desktop_notifier")
hiddenimports += ["desktop_notifier.resources"]

# desktop-notifier talks to the Windows toast API through the winrt-* packages
# (see its sys_platform == "win32" dependencies). They are PEP 420 namespace
# packages imported lazily inside desktop_notifier's Windows backend, and
# PyInstaller misses them, so UI/notifier.py's "scan finished" toast would
# raise ImportError on every scan.
hiddenimports += [
    "winrt.windows.applicationmodel.core",
    "winrt.windows.data.xml.dom",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.ui.notifications",
]

# UI/pages/health_page.py draws the trend chart with FigureCanvasTkAgg, which
# matplotlib resolves by name at import time.
hiddenimports += ["matplotlib.backends.backend_tkagg"]

# --------------------------------------------------------------------------- #
# Things to leave OUT — each one is dead weight in a Tk-only desktop app
# --------------------------------------------------------------------------- #
excludes = [
    # matplotlib supports a dozen GUI toolkits; we only ever use TkAgg, and
    # bundling the Qt backends alone would add well over 100 MB.
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "gi", "gtk",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_webagg",
    # The test suite and its dependencies are not part of a user-facing build.
    "pytest", "_pytest", "pluggy", "tests",
    # Jupyter/IPython are pulled in transitively by some matplotlib paths.
    "IPython", "jupyter", "notebook",
]


a = Analysis(
    # UI/app.py is the real application, frozen as-is. PyInstaller has no
    # equivalent of `python -m UI.app`; it needs a script file. Normally
    # running UI/app.py directly breaks its `from core...` /
    # `from database...` imports, because Python would treat UI/ as the
    # top-level folder — pathex below is what prevents that here: SPECPATH
    # is the repo root (where this .spec lives), and PyInstaller puts it on
    # the import search path, so the absolute imports resolve exactly as
    # they do under `python -m UI.app`.
    ["UI/app.py"],
    pathex=[SPECPATH],  # noqa: F821 — SPECPATH is injected by PyInstaller
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="NetWatch",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # UPX-packed binaries trip antivirus heuristics far
                           # more often than plain ones; not worth the MB here.
    runtime_tmpdir=None,
    # console=False hides the black terminal window behind the GUI.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Embeds a manifest asking Windows to run the app elevated (a UAC prompt on
    # launch). Raw ARP packets require administrator rights — without this the
    # scan always ends in core/wireless_scanner.py's InsufficientPrivilegesError.
    uac_admin=True,
)
