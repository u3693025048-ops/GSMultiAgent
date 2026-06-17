#!/usr/bin/env python3
"""Create a release zip for hand-off to a teammate with shared API keys.

Usage (from repo root):

    python scripts/package_release.py
    python scripts/package_release.py --output dist/MyRelease.zip
    python scripts/package_release.py --dry-run

The archive includes ``config.yaml`` with shared llm/rag keys intact.
Only ``simulation.matlab_path`` / ``octave_path`` are reset to generic
``matlab`` / ``octave`` so the recipient can unzip-overwrite and run;
they edit matlab_path only if MATLAB is not on PATH.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "chroma_db",
    ".pytest_cache",
    "dist",
    "node_modules",
}

EXCLUDE_DIR_GLOBS = [
    "logs",
    "guidance_output/results",
    "guidance_output/reports",
    "guidance_output/scripts",
    "guidance_output/matlab_scripts",
    "parameter_experience/models",
    "parameter_experience/params",
]

# config.yaml is included (prepared on write); backups/smoke copies excluded.
EXCLUDE_FILE_NAMES = {
    "config.yaml.backup",
    "config.copy.yaml",
    "config.smoke.yaml",
    "config.smoke_ppo.yaml",
    "parameter_experience_memory.json",
    "hermes_agent_memory.json",
    ".DS_Store",
}

EXCLUDE_FILE_GLOBS = [
    "*.pyc",
    "*.pyo",
    "*.rar",
    "*.zip",
    "log*.txt",
    "_check_pe*.py",
    "_local_run_check.py",
    "_matlab_smoke_run.py",
    "GSMultiAgent*.rar",
]

FORCE_INCLUDE: set[str] = set()

RECEIVER_SETUP = """\
GSMultiAgent13 — 接收方快速上手（与发件方共用 API Key）
======================================================

1. 解压到工作目录，直接覆盖同名文件即可（含 config.yaml）。

2. 安装依赖
   pip install -r requirements.txt

3. MATLAB 路径（通常唯一需要改的地方）
   config.yaml 中默认为:
     simulation:
       matlab_path: matlab
   若 MATLAB 已加入系统 PATH → 无需修改。
   若 python run_preflight.py 报找不到 matlab → 改为本机绝对路径，例如:
     matlab_path: "D:/Program Files/MATLAB/R2025a/bin/matlab.exe"

4. 预检与运行
   python run_preflight.py
   python cli_agent.py --file prompt.txt

详细说明见 RUNBOOK.md
"""


def _rel_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _should_exclude_dir(rel: Path) -> bool:
    if rel.name in EXCLUDE_DIR_NAMES:
        return True
    rel_s = rel.as_posix()
    for pat in EXCLUDE_DIR_GLOBS:
        if rel_s == pat or rel_s.startswith(pat + "/"):
            return True
    return False


def _should_exclude_file(rel: Path) -> bool:
    rel_s = rel.as_posix()
    if rel_s in FORCE_INCLUDE:
        return False
    if rel.name in EXCLUDE_FILE_NAMES:
        return True
    for pat in EXCLUDE_FILE_GLOBS:
        if fnmatch.fnmatch(rel.name, pat):
            return True
    if rel_s.startswith("dist/"):
        return True
    return False


def iter_release_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            continue
        excluded = False
        for parent in rel.parents:
            if parent == Path("."):
                continue
            if _should_exclude_dir(parent):
                excluded = True
                break
        if excluded:
            continue
        if _should_exclude_file(rel):
            continue
        files.append(path)
    return files


def prepare_config_for_release(
    text: str,
    *,
    matlab_path: str = "matlab",
    octave_path: str = "octave",
) -> str:
    """Keep shared API keys; strip machine-specific MATLAB/Octave paths only."""
    out = text
    # Quoted absolute paths
    out = re.sub(
        r'^(\s*matlab_path:\s*)".*"',
        f'\\1{matlab_path}',
        out,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    out = re.sub(
        r'^(\s*octave_path:\s*)".*"',
        f'\\1{octave_path}',
        out,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Unquoted or bare values
    out = re.sub(
        r"^(\s*matlab_path:\s*)\S+",
        f"\\1{matlab_path}",
        out,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    out = re.sub(
        r"^(\s*octave_path:\s*)\S+",
        f"\\1{octave_path}",
        out,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    note = (
        "# [交付包] API Key 与发件方共用；matlab_path 已重置为通用值，"
        "Preflight 失败时改为本机 matlab.exe 路径。\n"
    )
    if "[交付包]" not in out[:500]:
        out = note + out
    return out


def read_file_bytes(path: Path, *, matlab_path: str, octave_path: str) -> bytes:
    if path.name == "config.yaml":
        src = path.read_text(encoding="utf-8")
        return prepare_config_for_release(
            src, matlab_path=matlab_path, octave_path=octave_path
        ).encode("utf-8")
    return path.read_bytes()


def write_zip(
    zip_path: Path,
    files: list[Path],
    *,
    dry_run: bool,
    matlab_path: str,
    octave_path: str,
) -> None:
    extra = 1  # RECEIVER_SETUP.txt
    if dry_run:
        print(f"[dry-run] would create {zip_path} ({len(files) + extra} entries)")
        return
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc = _rel_posix(f)
            zf.writestr(arc, read_file_bytes(f, matlab_path=matlab_path, octave_path=octave_path))
        zf.writestr("RECEIVER_SETUP.txt", RECEIVER_SETUP.encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Package GSMultiAgent13 for delivery")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output zip path (default: dist/GSMultiAgent13-YYYYMMDD.zip)",
    )
    parser.add_argument(
        "--matlab-path",
        type=str,
        default="matlab",
        help="matlab_path written into shipped config.yaml (default: matlab)",
    )
    parser.add_argument(
        "--octave-path",
        type=str,
        default="octave",
        help="octave_path written into shipped config.yaml (default: octave)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be packed without writing zip",
    )
    args = parser.parse_args()

    if args.output:
        zip_path = Path(args.output)
        if not zip_path.is_absolute():
            zip_path = ROOT / zip_path
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        zip_path = ROOT / "dist" / f"GSMultiAgent13-{stamp}.zip"

    if not (ROOT / "config.yaml").is_file():
        print("Error: config.yaml not found at repo root.", file=sys.stderr)
        return 1

    files = iter_release_files()
    if args.dry_run:
        print(f"Root: {ROOT}")
        print(f"Files to pack: {len(files)} (+ RECEIVER_SETUP.txt)")
        print("Includes: config.yaml (shared keys, matlab_path reset)")
        print(f"Ship matlab_path={args.matlab_path!r} octave_path={args.octave_path!r}")
        print("Excluded: logs/, chroma_db/, guidance_output/scripts/, ...")
        for f in files[:25]:
            mark = " *" if f.name == "config.yaml" else ""
            print(f"  + {_rel_posix(f)}{mark}")
        if len(files) > 25:
            print(f"  ... and {len(files) - 25} more")
        write_zip(
            zip_path,
            files,
            dry_run=True,
            matlab_path=args.matlab_path,
            octave_path=args.octave_path,
        )
        return 0

    write_zip(
        zip_path,
        files,
        dry_run=False,
        matlab_path=args.matlab_path,
        octave_path=args.octave_path,
    )
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Created: {zip_path}")
    print(f"Size:    {size_mb:.2f} MB")
    print(f"Files:   {len(files)} + RECEIVER_SETUP.txt")
    print()
    print("对方收到后：")
    print("  1. 解压并覆盖本地目录（含 config.yaml，API Key 已共用）")
    print(f"  2. 若 MATLAB 不在 PATH，仅改 config.yaml 中 matlab_path")
    print("  3. python run_preflight.py && python cli_agent.py --file prompt.txt")
    print()
    print("你本地 config.yaml 不会被修改（仅 zip 内 matlab_path 重置）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
