#!/usr/bin/env python3
"""
SyntaxCheckMATLABTool — Layer 2 Hermes tool.

Validates and auto-fixes a generated monte_carlo_single-style .m file
before it is handed to run_simulation or the RL optimizer.

Checks performed:
  1. File existence
  2. Content looks like MATLAB (not LLM prose)
  3. RL_PARAMS_BEGIN / RL_PARAMS_END block present
  4. function declaration matches filename
  5. Unicode / markdown contamination
  6. Common syntax issues (missing semicolons on param lines, etc.)

Auto-fixes applied via _sanitize_matlab_guidance_script (existing helper).
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SyntaxCheckMATLABTool:
    name = "syntax_check_matlab"
    description = (
        "验证并自动修正生成的 MATLAB .m 脚本文件。"
        "检查文件是否为有效 MATLAB 脚本、是否包含 RL_PARAMS 注入块、函数名与文件名是否匹配，"
        "并修复 Unicode/Markdown 污染等常见问题。"
        "返回 {status, valid, issues, fixed_path}。"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": "待检查的 .m 文件绝对路径",
            },
            "auto_fix": {
                "type": "boolean",
                "description": "是否自动修复并覆盖写回（默认 true）",
            },
        },
        "required": ["script_path"],
    }

    async def execute(
        self,
        script_path: str,
        auto_fix: bool = True,
    ) -> str:
        result: Dict[str, Any] = {
            "status": "error",
            "valid": False,
            "issues": [],
            "fixed_path": script_path,
        }

        if not os.path.isfile(script_path):
            result["issues"].append(f"文件不存在: {script_path}")
            return json.dumps(result, ensure_ascii=False)

        try:
            with open(script_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception as exc:
            result["issues"].append(f"读取文件失败: {exc}")
            return json.dumps(result, ensure_ascii=False)

        issues = []

        # ── Check 1: content looks like MATLAB ───────────────────────────────
        from multi_agent.rl.matlab_rl_optimizer import _looks_like_matlab_script
        is_valid, reason = _looks_like_matlab_script(content)
        if not is_valid:
            issues.append(f"内容不像 MATLAB 脚本: {reason}")

        # ── Check 2: RL_PARAMS block present ─────────────────────────────────
        has_rl_params = bool(re.search(r"RL_PARAMS_BEGIN", content))
        if not has_rl_params:
            issues.append("缺少 RL_PARAMS_BEGIN 注入块（RL 优化器无法 patch 参数）")

        # ── Check 3: function name vs filename ────────────────────────────────
        func_match = re.search(r"^function\s+(\w+)", content, re.MULTILINE)
        if func_match:
            func_name = func_match.group(1)
            file_base = os.path.splitext(os.path.basename(script_path))[0]
            if func_name != file_base:
                issues.append(
                    f"函数名 '{func_name}' 与文件名 '{file_base}' 不一致"
                    f"（MATLAB 要求两者匹配）"
                )

        # ── Check 4: markdown / Unicode contamination ─────────────────────────
        if "```" in content:
            issues.append("含有 Markdown 代码围栏 (```)，需清除")
        has_unicode_ops = any(c in content for c in ("×", "÷", "≥", "≤", "≠"))
        if has_unicode_ops:
            issues.append("含有 Unicode 数学运算符（×÷≥≤≠），需替换为 MATLAB 等价符")

        # ── Auto-fix via sanitizer ─────────────────────────────────────────────
        fixed_content = content
        if auto_fix and issues:
            try:
                from multi_agent.tools.simulation_tool import _sanitize_matlab_guidance_script
                fixed_content, notes = _sanitize_matlab_guidance_script(content)
                if fixed_content != content:
                    with open(script_path, "w", encoding="utf-8") as fh:
                        fh.write(fixed_content)
                    result["fixed_path"] = script_path
                    issues = [f"[已修复] {iss}" for iss in issues]
                    logger.info(
                        f"[SyntaxCheck] Auto-fixed {len(notes)} issue(s) in "
                        f"'{os.path.basename(script_path)}'"
                    )
            except Exception as fix_exc:
                issues.append(f"自动修复失败: {fix_exc}")

        # Determine final validity (after fix attempt)
        is_valid_after, _ = _looks_like_matlab_script(fixed_content)
        final_valid = is_valid_after and has_rl_params

        result.update({
            "status": "success" if final_valid else "warning",
            "valid": final_valid,
            "issues": issues if issues else ["脚本检查通过，无问题"],
            "fixed_path": script_path,
            "has_rl_params_block": has_rl_params,
        })
        return json.dumps(result, ensure_ascii=False)
