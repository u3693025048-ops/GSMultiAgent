#!/usr/bin/env python3
"""Package golden run artifacts (report + script + log) for submission."""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GOLDEN_README = """\
GSMultiAgent13 — Golden 结果包（可直接交作业）
=============================================

本包为一次完整达标运行的证据与交付物，五项指标均在 report 中记录。

目录说明
--------
  report/   优化报告（Markdown + JSON）
  script/   达标 MATLAB 制导脚本
  log/      完整运行日志（含 Workflow Complete 与指标达标记录）
  prompt.txt  任务输入（与运行一致）

验收要点
--------
  - report 中五项指标均为 ✅
  - log 末尾 Exit code: 0、Workflow Complete!
  - script 为 report 中引用的 .m 文件

复现（可选）
------------
  需配合代码包解压后：python cli_agent.py --file prompt.txt
"""


def _default_files() -> dict[str, Path]:
    return {
        "report/report_20260617_141747.md": ROOT / "guidance_output" / "report_20260617_141747.md",
        "report/report_latest.md": ROOT / "guidance_output" / "report_latest.md",
        "report/report_20260617_141747.json": ROOT
        / "guidance_output"
        / "reports"
        / "report_20260617_141747.json",
        "script/guidance_T4_APN_tanh_softsat_1781674129.m": ROOT
        / "guidance_output"
        / "scripts"
        / "guidance_T4_APN_tanh_softsat_1781674129.m",
        "log/log06171319.txt": ROOT / "logs" / "log06171319.txt",
        "prompt.txt": ROOT / "prompt.txt",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package golden T4 run artifacts")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output zip (default: dist/GSMultiAgent13-YYYYMMDD-golden.zip)",
    )
    args = parser.parse_args()

    if args.output:
        zip_path = Path(args.output)
        if not zip_path.is_absolute():
            zip_path = ROOT / zip_path
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        zip_path = ROOT / "dist" / f"GSMultiAgent13-{stamp}-golden.zip"

    entries = _default_files()
    missing = [arc for arc, p in entries.items() if not p.is_file()]
    if missing:
        print("Error: missing files:", file=sys.stderr)
        for arc in missing:
            print(f"  {arc} -> {entries[arc]}", file=sys.stderr)
        return 1

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GOLDEN_README.txt", GOLDEN_README.encode("utf-8"))
        for arc, src in entries.items():
            zf.write(src, arc)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Created: {zip_path}")
    print(f"Size:    {size_mb:.2f} MB")
    print(f"Files:   {len(entries)} + GOLDEN_README.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
