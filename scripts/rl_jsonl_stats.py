#!/usr/bin/env python3
"""Offline rolling-mean report from ``logs/rl_episodes_*.jsonl``.

Usage:
  python scripts/rl_jsonl_stats.py logs/rl_episodes_20260608_120000.jsonl
  python scripts/rl_jsonl_stats.py logs/rl_episodes_20260608_120000.jsonl --window 50 --out logs/stats_summary.txt
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from multi_agent.rl.rolling_stats import analyze_jsonl_episodes  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="RL JSONL rolling statistics")
    parser.add_argument("jsonl_path", help="Path to rl_episodes_*.jsonl")
    parser.add_argument("--window", type=int, default=20, help="Rolling window size")
    parser.add_argument(
        "--diverge-threshold",
        type=float,
        default=-9.5,
        help="Reward at or below this counts as diverge",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional output file (default: stdout only)",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=1,
        help="Print one line every N episodes (default: 1)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.jsonl_path):
        print(f"File not found: {args.jsonl_path}", file=sys.stderr)
        return 1

    rows = analyze_jsonl_episodes(
        args.jsonl_path,
        window=args.window,
        diverge_reward_threshold=args.diverge_threshold,
    )
    if not rows:
        print("No episode records found in JSONL.", file=sys.stderr)
        return 1

    lines = [
        f"# RL rolling stats | file={args.jsonl_path} | window={args.window} | episodes={len(rows)}",
        "# ep | mean_reward | mean_SEP(m) | mean_PeakN_max(g) | mean_hit(%) | diverge(%)",
    ]
    for i, row in enumerate(rows):
        ep = int(row.get("episode", i + 1))
        if ep % max(1, args.every) != 0 and i != len(rows) - 1:
            continue
        lines.append(
            f"{ep:5d} | {row['mean_reward']:11.3f} | {row['mean_sep_m']:11.2f} | "
            f"{row['mean_peak_ny_max_g']:17.2f} | {row['mean_hit_rate_pct']:10.1f} | "
            f"{row['diverge_pct']:9.0f}"
        )

    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
