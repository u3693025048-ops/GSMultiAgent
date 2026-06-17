#!/usr/bin/env python3
"""Full Hermes smoke test (RUNBOOK §2.2).

Uses config.smoke.yaml (generated from config.yaml) without mutating the main config.
Logs to logs/smoke_YYYYMMDD_HHMMSS.txt

Usage (repo root, Python 3.10+ recommended):
    python scripts/smoke_hermes_full.py
    python scripts/smoke_hermes_full.py --python C:/path/to/python310/python.exe
"""

from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PROMPT = (
    "T4高频大幅度机动：RUN_CASE='T'; SUB_IDX=4; 命中率>=92%; SEP<=7m; "
    "PeakNy<=20g; PM在45-70度; BW在20-85rad/s"
)


def _deep_set(d: dict, path: str, value) -> None:
    cur = d
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def build_smoke_config() -> Path:
    src = ROOT / "config.yaml"
    dst = ROOT / "config.smoke.yaml"
    with open(src, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    patched = copy.deepcopy(data)
    _deep_set(patched, "workflow.max_iterations", 1)
    _deep_set(patched, "matlab_rl_optimizer.max_episodes", 10)
    _deep_set(patched, "matlab_rl_optimizer.nmc_per_eval", 5)
    _deep_set(patched, "matlab_rl_optimizer.constraint_local_search.enabled", False)
    with open(dst, "w", encoding="utf-8") as f:
        yaml.dump(patched, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return dst


def run_preflight(python: str, smoke_cfg: Path) -> int:
    code = (
        "from multi_agent.config_loader import reload_config; "
        "from multi_agent.preflight import ensure_preflight_or_exit; "
        f"reload_config({str(smoke_cfg)!r}); "
        "ensure_preflight_or_exit(strict=False, preflight_only=True)"
    )
    return subprocess.call([python, "-c", code], cwd=str(ROOT))


def run_smoke_cli(python: str, smoke_cfg: Path, log_path: Path) -> int:
    launcher = ROOT / "scripts" / "_smoke_cli_launcher.py"
    launcher.write_text(
        f"""#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

ROOT = Path({str(ROOT)!r})
sys.path.insert(0, str(ROOT))

from multi_agent.config_loader import reload_config
reload_config({str(smoke_cfg)!r})

import cli_agent

class Args:
    skip_preflight = True
    preflight_only = False
    preflight_strict = False
    verbose = False
    quiet = False
    resume_checkpoint = None
    prompt = {SMOKE_PROMPT!r}
    file = None

asyncio.run(cli_agent.main(Args()))
""",
        encoding="utf-8",
    )
    with open(log_path, "w", encoding="utf-8") as logf:
        logf.write(f"# smoke_hermes_full started {datetime.now().isoformat()}\n")
        logf.write(f"# prompt: {SMOKE_PROMPT}\n")
        logf.write(f"# config: {smoke_cfg}\n\n")
        logf.flush()
        proc = subprocess.Popen(
            [python, str(launcher)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            logf.write(line)
        return proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Full Hermes smoke test")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter (default: current)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight-only gate",
    )
    args = parser.parse_args()

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"smoke_{stamp}.txt"

    smoke_cfg = build_smoke_config()
    print(f"[smoke] config → {smoke_cfg}")
    print(f"[smoke] log    → {log_path}")

    if not args.skip_preflight:
        print("[smoke] preflight …")
        pf = run_preflight(args.python, smoke_cfg)
        if pf != 0:
            print(f"[smoke] preflight failed (exit {pf}) — fix environment first")
            return pf

    print("[smoke] starting cli_agent (max_iterations=1, max_episodes=10) …")
    rc = run_smoke_cli(args.python, smoke_cfg, log_path)
    print(f"\n[smoke] finished exit={rc}  log={log_path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
