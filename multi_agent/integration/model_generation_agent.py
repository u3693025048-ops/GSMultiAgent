#!/usr/bin/env python3
"""
Model Generation Agent
LLM-powered dynamic generation of MATLAB and SysML guidance-system models.

Routing logic
-------------
TUNE_PARAMS / REUSE_HISTORY
    Pure template-patching: no LLM call needed, fast and deterministic.
MODIFY_LAW
    LLM extracts the guidance-law function body from the template, rewrites
    it according to the task description, then patches it back.  Parameter
    values are patched afterwards with the normal regex-based logic.
Non-standard working conditions (no A-F mapping)
    LLM receives the task description and maps the physical scenario to the
    closest A-F category flags, enabling the standard template to execute.
SysML customisation
    LLM adapts the retrieved XML template to task-specific architecture
    requirements (parameter values, component descriptions, etc.).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Unicode characters that mark LLM verification/annotation lines
_VERIFY_PREFIXES: tuple = (
    '\u2705',  # ✅
    '\u274c',  # ❌
    '\u26a0',  # ⚠
    '\u2714',  # ✔
    '\u2716',  # ✖
    '\U0001f50d',  # 🔍
    '\U0001f4dd',  # 📝
)


def _strip_verification_lines(text: str) -> Tuple[str, str]:
    """Separate pure MATLAB lines from LLM annotation lines (✅ / ❌ …).

    Returns
    -------
    (clean_code, notes)
      clean_code : lines that belong in the .m file
      notes      : annotation lines to write to the sidecar file
    """
    code, notes = [], []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped and stripped[0] in _VERIFY_PREFIXES:
            notes.append(line)
        else:
            code.append(line)
    return '\n'.join(code), '\n'.join(notes)


class ModelGenerationAgent:
    """
    LLM-powered model generation agent.

    Uses the same LLM backend as ReflectionAgent (configured via config.yaml).
    Call ``generate_matlab()`` or ``generate_sysml()`` from the corresponding
    Hermes tools.
    """

    def __init__(self):
        from ..config_loader import get_config
        from langchain_openai import ChatOpenAI

        cfg = get_config().llm
        extra_body = {"include_reasoning": True}
        self.llm = ChatOpenAI(
            model=cfg.model,
            openai_api_key=cfg.api_key or "sk-dummy",
            openai_api_base=cfg.base_url,
            temperature=0.1,
            extra_body=extra_body,
        )

    # ── public API ────────────────────────────────────────────────────────────

    async def generate_matlab(
        self,
        task_description: str,
        template_content: str,
        mode: str = "TUNE_PARAMS",
        autopilot_params: Optional[Dict[str, float]] = None,
        mission_conditions: Optional[str] = None,
        nmc: int = 100,
        non_standard_task: str = "",
    ) -> str:
        """
        Generate / modify a MATLAB simulation script.

        Parameters
        ----------
        task_description : natural-language task (used by LLM in MODIFY_LAW)
        template_content : raw MATLAB template string (already retrieved from KB)
        mode             : "TUNE_PARAMS" | "REUSE_HISTORY" | "MODIFY_LAW"
        autopilot_params : {param_name: value} overrides for dp.* fields
        mission_conditions : pre-built conditions string (run_X=…;sub_X=…;)
        nmc              : Monte Carlo run count
        non_standard_task: free-text description of non-standard working
                           conditions (used when mission_conditions is None)

        Returns
        -------
        Modified MATLAB script as a string (not written to disk here).
        """
        script = template_content

        # Always update the Monte Carlo count
        script = re.sub(r"Nmc\s*=\s*\d+;", f"Nmc = {nmc};", script)

        if mode == "MODIFY_LAW":
            script = await self._rewrite_guidance_law(
                script, task_description, autopilot_params, mission_conditions
            )
        else:
            # TUNE_PARAMS / REUSE_HISTORY — deterministic patching only
            if autopilot_params:
                script = self._patch_autopilot_params(script, autopilot_params)
            if mission_conditions:
                script = self._patch_mission_conditions(script, mission_conditions)

        # Non-standard working conditions: LLM generates parameter values directly
        # (does NOT map to A-F flags — caller controls run_X via mission_conditions)
        if non_standard_task:
            script = await self._generate_custom_conditions(script, non_standard_task)

        return script

    async def generate_sysml(
        self,
        task_description: str,
        template: str,
        diagram_type: str,
        substitutions: Dict[str, str],
    ) -> str:
        """
        Generate a SysML XML diagram.

        For simple tasks: fills ``{placeholder}`` slots in the template.
        For tasks with specific architectural requirements: LLM customises the
        XML to match the task description before returning.

        Parameters
        ----------
        task_description : natural-language task description
        template         : raw XML template string
        diagram_type     : "bdd" | "parametric" | "ibd"
        substitutions    : {placeholder_key: value} for basic fill

        Returns
        -------
        Customised XML string.
        """
        result = template
        for key, val in substitutions.items():
            result = result.replace(f"{{{key}}}", str(val))

        if task_description and len(task_description) > 30:
            adapted = await self._customize_sysml(result, task_description, diagram_type)
            if adapted and len(adapted) > 100:
                result = adapted

        return result

    # ── MODIFY_LAW helpers ────────────────────────────────────────────────────

    async def _rewrite_guidance_law(
        self,
        script: str,
        task_description: str,
        autopilot_params: Optional[Dict],
        mission_conditions: Optional[str],
    ) -> str:
        """
        LLM rewrites the guidance-law function body, then patches params.

        Extraction strategy (first match wins):
        1. Named ``guidance_local`` (original template)
        2. Any function whose name contains "guidance" or "nav"
        3. Any function body that references ``N_guidance`` or LOS-rate terms
        4. Fallback: ask LLM to rewrite the full script (guidance section only)
        """
        guidance_section, func_name = self._extract_guidance_section_robust(script)

        if guidance_section and func_name:
            # ── targeted function rewrite ──────────────────────────────────
            prompt = (
                "你是MATLAB制导律设计专家。根据任务需求修改以下制导律函数代码。\n\n"
                f"任务需求: {task_description}\n\n"
                f"当前制导律函数名: {func_name}\n"
                f"当前制导律代码:\n```matlab\n{guidance_section[:2500]}\n```\n\n"
                "要求:\n"
                "1. 只修改制导律算法逻辑，不修改自动驾驶仪传递函数结构\n"
                "2. 保持函数名和接口（输入/输出参数）完全不变\n"
                "3. 保留 dp.N_guidance、dp.R_switch、dp.gama_max_deg 参数引用\n"
                "4. 直接返回修改后的完整制导律函数代码，不加任何说明文字或 markdown 格式\n"
            )
            new_section = await self._llm_call(prompt)
            new_section = re.sub(r"^```(?:matlab)?\s*\n?", "", new_section.strip(), flags=re.IGNORECASE)
            new_section = re.sub(r"\n?```\s*$", "", new_section.strip())
            new_section, _sec_notes = _strip_verification_lines(new_section)
            if _sec_notes:
                logger.debug(
                    "[ModelGen] Stripped %d verification line(s) from LLM guidance section.",
                    len(_sec_notes.splitlines()),
                )

            if new_section and self._is_valid_matlab(new_section):
                script = self._replace_guidance_section_by_name(script, func_name, new_section)
                logger.info(
                    f"[ModelGen] MODIFY_LAW: guidance-law function '{func_name}' "
                    "successfully rewritten and embedded."
                )
            else:
                logger.error(
                    f"[ModelGen] MODIFY_LAW: LLM output for '{func_name}' failed MATLAB "
                    "validation — falling back to full-script rewrite."
                )
                script = await self._full_script_rewrite(
                    script, task_description, func_name
                )
        else:
            # ── no extractable function found: full-script rewrite ─────────
            logger.warning(
                "[ModelGen] MODIFY_LAW: could not locate guidance-law function; "
                "requesting full-script rewrite from LLM."
            )
            script = await self._full_script_rewrite(script, task_description, "")

        # Always patch params after guidance rewrite
        if autopilot_params:
            script = self._patch_autopilot_params(script, autopilot_params)
        if mission_conditions:
            script = self._patch_mission_conditions(script, mission_conditions)
        return script

    async def _full_script_rewrite(
        self, script: str, task_description: str, hint_func: str
    ) -> str:
        """
        Ask the LLM to identify and rewrite the guidance section in the full
        script.  Used when targeted extraction fails.
        """
        hint = f"函数名参考: {hint_func}" if hint_func else "请自行定位制导律计算部分"
        prompt = (
            "你是MATLAB制导律设计专家。以下是一个完整的制导系统仿真脚本。\n"
            "请根据任务需求，定位并修改其中的制导律计算部分，其余代码保持不变。\n\n"
            f"任务需求: {task_description}\n"
            f"{hint}\n\n"
            f"完整脚本（前3500字符）:\n```matlab\n{script[:3500]}\n```\n\n"
            "要求:\n"
            "1. 只修改制导律算法逻辑，保持蒙特卡洛循环、自动驾驶仪等结构不变\n"
            "2. 返回修改后的完整MATLAB脚本，不加说明或 markdown 格式\n"
        )
        result = await self._llm_call(prompt)
        result = re.sub(r"^```(?:matlab)?\s*\n?", "", result.strip(), flags=re.IGNORECASE)
        result = re.sub(r"\n?```\s*$", "", result.strip())
        result, _res_notes = _strip_verification_lines(result)
        if _res_notes:
            logger.debug(
                "[ModelGen] Stripped %d verification line(s) from full-script rewrite.",
                len(_res_notes.splitlines()),
            )
        if result and self._is_valid_matlab(result) and len(result) > 500:
            logger.info("[ModelGen] MODIFY_LAW: full-script rewrite applied.")
            return result
        logger.error(
            "[ModelGen] MODIFY_LAW: full-script rewrite also failed validation; "
            "script is unchanged — check LLM output."
        )
        return script

    # ── non-standard condition: direct free-text → parameter generation ────────

    async def _generate_custom_conditions(
        self, script: str, non_standard_task: str
    ) -> str:
        """
        Generate MATLAB parameter values directly from a free-text working-condition
        description.  Does NOT map to A-F category flags.

        1. Extracts the parameter/initialisation block from the template.
        2. LLM outputs only the assignment lines that need to change
           (format: ``var = value;``).
        3. Each assignment is patched into the script with a targeted regex;
           only variables that already exist in the template are touched.
        4. A-F ``run_X`` / ``sub_X`` flags are intentionally NOT modified here.
        """
        param_section = self._extract_param_section(script)

        prompt = (
            "你是MATLAB仿真专家。根据以下自由文本工况描述，确定需要修改的仿真参数值。\n\n"
            f"任务工况（自由文本，无需映射到A-F类别）: {non_standard_task}\n\n"
            f"当前参数初始化代码块:\n{param_section[:2500]}\n\n"
            "要求:\n"
            "1. 只输出需要修改的参数赋值语句，每行一条，格式严格为: 变量名 = 值;\n"
            "   例如: dp.H0 = 5000;  或  dp.V0 = 300;\n"
            "2. 不要修改 run_A/run_B/sub_A 等工况开关\n"
            "3. 只修改与任务描述直接相关的参数，不相关参数不输出\n"
            "4. 不加任何说明文字或 markdown 格式\n"
        )

        assignments_text = await self._llm_call(prompt)
        if not assignments_text:
            return script

        applied = 0
        for raw_line in assignments_text.strip().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("%") or line.startswith("#") or line.startswith("```"):
                continue
            m = re.match(r"^([\w.]+)\s*=\s*(.+?)\s*;?\s*$", line)
            if not m:
                continue
            var, val = m.group(1), m.group(2).rstrip(";")
            # Only patch variables that already exist in the script
            if re.search(rf"{re.escape(var)}\s*=", script):
                script = re.sub(
                    rf"({re.escape(var)}\s*=\s*)[^;\n]+;",
                    f"{var} = {val};",
                    script,
                    count=1,
                )
                applied += 1

        logger.info(
            f"[ModelGen] Non-standard conditions: applied {applied} "
            "parameter override(s) from free-text description."
        )
        return script

    # ── SysML LLM customisation ───────────────────────────────────────────────

    async def _customize_sysml(
        self, xml_content: str, task_description: str, diagram_type: str
    ) -> str:
        """LLM adapts SysML XML to task-specific architecture requirements."""
        prompt = (
            f"你是SysML制导系统建模专家。请根据任务需求调整以下 SysML {diagram_type.upper()} 图。\n\n"
            f"任务需求: {task_description}\n\n"
            f"当前模板（前1500字符）:\n{xml_content[:1500]}\n\n"
            "要求:\n"
            "1. 保持XML结构完全有效\n"
            "2. 调整与任务需求相关的参数值和组件/端口描述\n"
            "3. 直接返回完整XML，不加任何说明文字或 markdown 格式\n"
        )
        result = await self._llm_call(prompt)
        result = re.sub(r"^```(?:xml)?\s*\n?", "", result.strip(), flags=re.IGNORECASE)
        result = re.sub(r"\n?```\s*$", "", result.strip())
        return result

    # ── Syntax-error repair ───────────────────────────────────────────────────

    async def repair_matlab(self, content: str, error_msg: str) -> str:
        """Ask the LLM to fix a MATLAB/Octave syntax error in *content*.

        Parameters
        ----------
        content   : the MATLAB source code that failed to execute
        error_msg : the stderr output from Octave/MATLAB (≤1500 chars)

        Returns the repaired source, or *content* unchanged if LLM fails.
        """
        prompt = (
            "你是MATLAB语法修复专家。以下MATLAB脚本在Octave中运行时出现了语法错误，"
            "请修复脚本中的语法问题。\n\n"
            f"错误信息:\n{error_msg}\n\n"
            f"需要修复的脚本（前4000字符）:\n```matlab\n{content[:4000]}\n```\n\n"
            "修复要求:\n"
            "1. 只修复导致错误的语法问题，不改变算法逻辑\n"
            "2. 常见问题: struct(, 多余逗号、全角标点符号、Unicode数学符号、"
               "dp变量命名冲突、缺少global声明\n"
            "3. 直接返回完整的修复后MATLAB脚本，不加任何说明或markdown格式\n"
        )
        try:
            result = await self._llm_call(prompt)
            result = re.sub(r"^```(?:matlab)?\s*\n?", "", result.strip(), flags=re.IGNORECASE)
            result = re.sub(r"\n?```\s*$", "", result.strip())
            result, _notes = _strip_verification_lines(result)
            if result and self._is_valid_matlab(result) and len(result) > 200:
                logger.info("[ModelGen] repair_matlab: repaired script accepted.")
                return result
            logger.warning("[ModelGen] repair_matlab: LLM output failed validation; returning original.")
        except Exception as exc:
            logger.warning(f"[ModelGen] repair_matlab error: {exc}")
        return content

    # ── LLM call helper ───────────────────────────────────────────────────────

    async def _llm_call(self, prompt: str) -> str:
        """Invoke LLM and return the text response."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content="你是制导系统工程专家，擅长MATLAB编程和SysML建模。"),
                HumanMessage(content=prompt),
            ]
            response = await self.llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip()
        except Exception as exc:
            logger.warning(f"[ModelGen] LLM call failed: {exc}")
            return ""

    # ── static patching helpers (mirrors GenerateMATLABTool) ─────────────────

    @staticmethod
    def _extract_guidance_section_robust(script: str):
        """
        Return ``(section_text, function_name)`` for the guidance-law function.
        Tries four patterns in order; returns ``("", "")`` if none match.
        """
        # Pattern 1: exact name guidance_local (original template)
        m = re.search(
            r"(?m)^(function[^\n]*?\b(guidance_local)\b[^\n]*\n[\s\S]*?)(?=^function|\Z)",
            script,
        )
        if m:
            return m.group(1)[:3000], m.group(2)

        # Pattern 2: any function whose name contains "guidance" or ends with "_nav"
        m = re.search(
            r"(?m)^(function[^\n]*?\b([\w]*(?:guidance|_nav)[\w]*)\b[^\n]*\n[\s\S]*?)(?=^function|\Z)",
            script,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)[:3000], m.group(2)

        # Pattern 3: any function body that references dp.N_guidance
        m = re.search(
            r"(?m)^(function[^\n]*?\b([a-zA-Z_]\w*)\b[^\n]*\n[\s\S]{0,2000}?dp\.N_guidance[\s\S]*?)(?=^function|\Z)",
            script,
        )
        if m:
            return m.group(1)[:3000], m.group(2)

        # Pattern 4: any function body containing LOS-rate keywords
        m = re.search(
            r"(?m)^(function[^\n]*?\b([a-zA-Z_]\w*)\b[^\n]*\n[\s\S]{0,2000}?(?:los_rate|dq_|sigma_dot|eta_)[\s\S]*?)(?=^function|\Z)",
            script,
            re.IGNORECASE,
        )
        if m:
            return m.group(1)[:3000], m.group(2)

        return "", ""

    @staticmethod
    def _replace_guidance_section_by_name(script: str, func_name: str, new_section: str) -> str:
        """Replace the named function body with ``new_section``."""
        pattern = re.compile(
            rf"(?m)^(function[^\n]*?\b{re.escape(func_name)}\b[^\n]*\n[\s\S]*?)(?=^function|\Z)"
        )
        replaced = pattern.sub(new_section.rstrip() + "\n", script, count=1)
        if replaced == script:
            # Fallback: append new section at end (last resort)
            logger.warning(
                f"[ModelGen] _replace_guidance_section_by_name: could not find "
                f"'{func_name}' in script; appending new section."
            )
            return script.rstrip() + "\n\n" + new_section
        return replaced

    @staticmethod
    def _patch_autopilot_params(script: str, params: Dict) -> str:
        for key, val in params.items():
            script = re.sub(
                rf"(dp\.{key}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?\s*;",
                f"dp.{key} = {val:.6f};",
                script,
            )
        return script

    @staticmethod
    def _patch_mission_conditions(script: str, conditions_str: str) -> str:
        _ALL_CATS = list("ABCDEF")
        enabled: set = set()
        for m in re.finditer(r"run_([A-F])\s*=\s*(true|false)", conditions_str, re.IGNORECASE):
            cat, val = m.group(1).upper(), m.group(2).lower()
            if val == "true":
                enabled.add(cat)
        for cat in _ALL_CATS:
            val = "true" if cat in enabled else "false"
            script = re.sub(
                rf"run_{cat}\s*=\s*(true|false)\s*;", f"run_{cat} = {val};", script
            )
        for m in re.finditer(r"sub_([A-F])\s*=\s*\[(.*?)\]", conditions_str, re.IGNORECASE):
            cat, content = m.group(1).upper(), m.group(2).strip()
            script = re.sub(
                rf"sub_{cat}\s*=\s*\[.*?\]\s*;", f"sub_{cat} = [{content}];", script
            )
        return script

    @staticmethod
    def _extract_param_section(script: str) -> str:
        """
        Extract the parameter / initialisation block from the script.
        Looks for the dp.* assignment block or a marked initialisation section.
        Falls back to the first 2000 characters if neither is found.
        """
        # Try to find the dp.* parameter block (at least 3 consecutive dp. lines)
        m = re.search(
            r"((?:(?:dp\.[\w]+\s*=\s*[^\n]+;\s*\n){3,}))",
            script,
        )
        if m:
            # Return from the start of that block, up to 2500 chars
            start = max(0, m.start() - 200)
            return script[start : start + 2500]
        # Fallback: first 2000 chars of script (usually contains init params)
        return script[:2000]

    @staticmethod
    def _is_valid_matlab(content: str) -> bool:
        """Lightweight MATLAB content check."""
        if "```" in content:
            return False
        if len(re.findall(r"(?m)^\s{0,3}#{1,6}\s+\S", content)) >= 2:
            return False
        return bool(re.search(r"\w+\s*=\s*.+;", content))
