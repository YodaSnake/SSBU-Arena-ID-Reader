from pathlib import Path


repo_root = Path(SPEC).resolve().parent.parent
source_root = repo_root / "src"
template_directory = (
    source_root
    / "ssbu_arena_id_reader"
    / "assets"
    / "arena_id_templates"
)
launcher = repo_root / "installer" / "launcher.py"

analysis = Analysis(
    [str(launcher)],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (
            str(template_directory),
            "ssbu_arena_id_reader/assets/arena_id_templates",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SSBU Arena ID Reader",
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
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SSBU Arena ID Reader",
)

app = BUNDLE(
    collection,
    name="SSBU Arena ID Reader.app",
    icon=None,
    bundle_identifier="com.yodasnake.ssbu-arena-id-reader",
)
