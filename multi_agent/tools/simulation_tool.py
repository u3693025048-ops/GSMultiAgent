#!/usr/bin/env python3
"""
Simulation Tools for Hermes Agent
Provides SysML model and MATLAB script generation for guidance system simulation.

Both GenerateSysMLTool and GenerateMATLABTool auto-retrieve templates from the
RAG knowledge base before generating output.  If a RAG knowledge base is not
injected the tools fall back to the built-in default templates.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Unicode annotation chars that LLMs insert as "verification" lines ─────────
_ANNOTATION_FIRST_CHARS = frozenset((
    '\u2705', '\u274c', '\u26a0', '\u2714', '\u2716',
    '\U0001f50d', '\U0001f4dd',
))

# Default values for guidance parameters that LLMs add to dp struct but may
# forget to initialise in dp=struct(...)
_DP_GUIDANCE_DEFAULTS: Dict[str, float] = {
    "N_guidance":   3.0,
    "R_switch":   300.0,
    "gama_max_deg": 45.0,
}


def _sanitize_matlab_guidance_script(content: str) -> Tuple[str, List[str]]:
    """Post-process a MATLAB guidance simulation script before writing to disk.

    Fixes applied (in order):

    1.  Annotation stripping       – ✅❌⚠️ lines → sidecar
    2.  Markdown fence removal     – stray ```matlab / ``` lines
    3.  Unicode math operators     – × ÷ ≥ ≤ ≠ ± → MATLAB equivalents
    4.  Full-width punctuation     – Chinese ；（）：，" " → ASCII
    5.  Prose line comment-out     – pure Chinese / natural-language lines inside
                                     function bodies → prepend %
    6.  dp struct field injection  – add N_guidance/R_switch/gama_max_deg defaults
                                     to dp=struct(...) if missing
    7.  global dp before struct    – inject ``global dp`` before dp=struct(...)
                                     if missing within 5 preceding lines
    8.  run_single_case_general    – inject ``global dp`` + ``dp=sample.dp``
    9.  dp name collision in       – inside guidance_local: if ``dp = <scalar>;``
        guidance_local               conflicts with ``global dp``, rename to
                                     ``dp_rate``

    Returns (cleaned_content, stripped_annotation_lines).
    """
    notes: List[str] = []

    # ── 1. Strip annotation/verification lines ────────────────────────────────
    clean: List[str] = []
    for ln in content.splitlines():
        s = ln.lstrip()
        if s and s[0] in _ANNOTATION_FIRST_CHARS:
            notes.append(ln)
        else:
            clean.append(ln)
    content = "\n".join(clean)

    # ── 2. Remove stray markdown fences ──────────────────────────────────────
    content = re.sub(r"^```(?:matlab)?\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^```\s*$",            "", content, flags=re.MULTILINE)

    # ── 3. Unicode math operator substitution ────────────────────────────────
    _UNICODE_OPS: List[Tuple[str, str]] = [
        ('\u00d7', '*'),    # ×  multiplication sign
        ('\u00f7', '/'),    # ÷  division sign
        ('\u2265', '>='),   # ≥
        ('\u2264', '<='),   # ≤
        ('\u2260', '~='),   # ≠
        ('\u00b1', ''),     # ±  (context-dependent; remove so parser doesn't choke)
        ('\u2192', '%->'),  # →  (likely prose; comment it out)
        ('\u2190', '%<-'),  # ←
        ('\u03bb', 'lambda'),  # λ
        ('\u03c9', 'omega'),   # ω
        ('\u03b6', 'zeta_'),   # ζ (already named zeta in code)
        ('\u03b1', 'alpha_'),  # α (avoid shadowing MATLAB alpha var)
        ('\u03b2', 'beta_'),   # β
        ('\u0307', ''),        # combining dot above (λ̇ → lambda)
        ('\u00b2', '.^2'),     # ²  superscript 2
        ('\u00b3', '.^3'),     # ³
        ('\u221a', 'sqrt'),    # √  (partial – need to manually wrap argument)
    ]
    for uni, asc in _UNICODE_OPS:
        content = content.replace(uni, asc)

    # ── 4. Full-width Chinese punctuation → ASCII ─────────────────────────────
    _FW_MAP: List[Tuple[str, str]] = [
        ('\uff1b', ';'),   # ；
        ('\uff08', '('),   # （
        ('\uff09', ')'),   # ）
        ('\uff1a', ':'),   # ：
        ('\uff0c', ','),   # ，
        ('\u201c', "'"),   # "
        ('\u201d', "'"),   # "
        ('\u2018', "'"),   # '
        ('\u2019', "'"),   # '
        ('\uff05', '%'),   # ％
        ('\uff3b', '['),   # ［
        ('\uff3d', ']'),   # ］
        ('\uff5b', '{'),   # ｛
        ('\uff5d', '}'),   # ｝
        ('\u3002', '.'),   # 。
        ('\uff01', '!'),   # ！
        ('\uff1d', '='),   # ＝
        ('\uff0b', '+'),   # ＋
        ('\uff0d', '-'),   # －
        ('\uff0a', '*'),   # ＊
        ('\uff0f', '/'),   # ／
    ]
    for fw, asc in _FW_MAP:
        content = content.replace(fw, asc)

    # ── 5. Comment-out pure Chinese prose lines inside function bodies ─────────
    # A line is "Chinese prose" if it contains ≥4 CJK characters, has no
    # MATLAB operator (= ; ( [ %) and does NOT start with % already.
    _CJK = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
    _MATLAB_PUNCT = re.compile(r'[=;()\[\]%]')
    prose_fixed = []
    for ln in content.splitlines():
        stripped = ln.lstrip()
        if (stripped and not stripped.startswith('%')
                and len(_CJK.findall(ln)) >= 4
                and not _MATLAB_PUNCT.search(ln)):
            prose_fixed.append('%% [sanitised] ' + ln)
            notes.append('[prose→comment] ' + ln)
        else:
            prose_fixed.append(ln)
    content = "\n".join(prose_fixed)

    # ── 6. dp struct field injection ─────────────────────────────────────────
    def _fix_dp_struct(m: re.Match) -> str:
        struct_line = m.group(0)
        missing = {
            k: v for k, v in _DP_GUIDANCE_DEFAULTS.items()
            if k not in struct_line
        }
        if missing:
            new_fields = ",".join(f"'{k}',{v}" for k, v in missing.items())
            # Check whether the struct already has fields (non-empty interior)
            inner = re.search(r"struct\s*\(([^)]*)\)", struct_line)
            has_existing = inner and inner.group(1).strip()
            sep = "," if has_existing else ""
            struct_line = re.sub(r"\)\s*;", sep + new_fields + ");", struct_line, count=1)
        return struct_line

    content = re.sub(
        r"dp\s*=\s*struct\s*\([^)]*\)\s*;",
        _fix_dp_struct,
        content,
    )

    # ── 7. Inject ``global dp`` before dp=struct(...) if missing ─────────────
    lines = content.splitlines()
    out: List[str] = []
    for i, ln in enumerate(lines):
        if re.match(r"\s*dp\s*=\s*struct\s*\(", ln):
            preceding = "\n".join(lines[max(0, i - 5):i])
            if "global dp" not in preceding:
                out.append("global dp")
        out.append(ln)
    content = "\n".join(out)

    # ── 8. global dp + dp=sample.dp in run_single_case_general ───────────────
    if "function res=run_single_case_general" in content:
        pat = re.compile(
            r"(function\s+res\s*=\s*run_single_case_general\s*\(sample\)[^\n]*\n)"
            r"((?:global\s+\w[^\n]*\n)*)",
            re.DOTALL,
        )
        def _inject_global_dp(m: re.Match) -> str:
            sig, globs = m.group(1), m.group(2)
            if "global dp" not in globs and "global dp" not in sig:
                globs += "global dp\n"
                globs += "if isfield(sample,'dp') && isstruct(sample.dp), dp=sample.dp; end\n"
            return sig + globs
        content = pat.sub(_inject_global_dp, content, count=1)

    # ── 9. dp name collision in guidance_local ────────────────────────────────
    # If guidance_local uses "global dp" AND also assigns dp = <scalar_expr>;
    # the scalar assignment shadows the struct.  Rename scalar uses to dp_rate.
    if "function" in content and "global dp" in content:
        # Find each function body that has BOTH "global dp" AND a bare scalar
        # assignment "dp = <expr>;" where expr does not look like struct().
        def _fix_dp_collision(func_body: str) -> str:
            if "global dp" not in func_body:
                return func_body
            # scalar assignment: dp = <something that is NOT struct(...)>
            scalar_pat = re.compile(
                r"\bdp\s*=\s*(?!struct\s*\()([^;]{1,120});",
            )
            # check if any scalar assignment exists
            if not scalar_pat.search(func_body):
                return func_body
            # rename all bare dp assignments and uses that are NOT dp.field
            # Replace "dp = expr;" → "dp_rate = expr;"
            func_body = scalar_pat.sub(lambda m: m.group(0).replace("dp =", "dp_rate =", 1), func_body)
            # Replace standalone dp in expressions (not dp. or dp_)
            func_body = re.sub(r"\bdp\b(?![._])", "dp_rate", func_body)
            # Restore "global dp" (we just renamed it to global dp_rate)
            func_body = func_body.replace("global dp_rate", "global dp")
            # Restore dp.field references
            func_body = re.sub(r"dp_rate\.([\w]+)", r"dp.\1", func_body)
            return func_body

        # Apply per function body (split on "^function " boundaries)
        func_split = re.split(r"(?=\nfunction\s)", content)
        content = "".join(_fix_dp_collision(fb) for fb in func_split)

    return content, notes


@dataclass
class SimulationToolConfig:
    """仿真工具配置"""

    name: str
    description: str
    input_schema: Dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge-base paths (resolved relative to this file's package root)
# ─────────────────────────────────────────────────────────────────────────────
_PKG_ROOT = Path(__file__).resolve().parent.parent.parent
_KB_SYSML  = _PKG_ROOT / "knowledge_base" / "sysml"
_KB_MATLAB = _PKG_ROOT / "knowledge_base" / "matlab"


def _read_kb_file(path: Path) -> str:
    """Read a knowledge-base file, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        logger.warning(f"Could not read KB file {path}: {exc}")
        return ""


class GenerateSysMLTool:
    """
    Generate SysML models for guidance system architecture.

    Templates are retrieved **automatically** from the RAG knowledge base
    (``knowledge_base/sysml/``).  Three diagram types are produced:
      - BDD  (Block Definition Diagram)  → ``*_bdd.xml``
      - Parametric Diagram               → ``*_parametric.xml``
      - IBD  (Internal Block Diagram)    → ``*_ibd.xml``

    All files are saved to the configured ``sysml_output_dir``.
    """

    name = "generate_sysml"
    description = """
    Generate SysML models (BDD, Parametric, IBD) for the guidance system.
    Automatically retrieves templates from the knowledge base via RAG.
    Saves generated .xml files to the SysML output directory.
    Use this for system architecture design or documentation tasks.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "model_name": {
                "type": "string",
                "description": "Model/project name used in file names and XML",
                "default": "GuidanceSystem",
            },
            "navigation_coefficient": {
                "type": "number",
                "description": "Proportional navigation coefficient N (e.g. 3.5)",
            },
            "damping_ratio": {
                "type": "number",
                "description": "Autopilot damping ratio ζ (e.g. 0.75)",
            },
            "control_gain": {
                "type": "number",
                "description": "Control gain (default 1.0)",
                "default": 1.0,
            },
            "target_position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Target position [x, y, z] in metres (default [20000,2000,5000])",
            },
            "task_description": {
                "type": "string",
                "description": "Free-text description of the task/scenario (used for RAG retrieval and LLM customisation)",
            },
            "mode": {
                "type": "string",
                "description": "Generation mode: REUSE_HISTORY | TUNE_PARAMS | MODIFY_LAW",
                "enum": ["REUSE_HISTORY", "TUNE_PARAMS", "MODIFY_LAW"],
                "default": "TUNE_PARAMS",
            },
        },
        "required": [],
    }

    def __init__(self, *args, **kwargs):
        self.simulator = None
        self.rag_kb = None
        self.parameter_experience = None
        self._model_agent = None
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    def set_rag_kb(self, rag_kb) -> None:
        self.rag_kb = rag_kb

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience

    def _get_model_agent(self):
        """Lazy-instantiate ModelGenerationAgent (avoids import cost on every run)."""
        if self._model_agent is None:
            try:
                from ..integration.model_generation_agent import ModelGenerationAgent
                self._model_agent = ModelGenerationAgent()
            except Exception as exc:
                logger.warning(f"[SysML] Could not create ModelGenerationAgent: {exc}")
        return self._model_agent

    async def _load_pe_sysml(self, diagram_type: str, query_hint: str = "") -> Optional[str]:
        """
        Return the best-matching PE SysML XML for *diagram_type* from
        ``experience_base_dir/models/``, or ``None`` if none found.

        Retrieval priority:
        1. ``ParameterExperience.retrieve_best()`` when PE is injected —
           structural similarity × fitness × reliability (Q-score).
        2. JSON file scan with fitness + keyword scoring (fallback when PE
           is not loaded).
        3. Most-recent file by mtime (last resort).
        """
        import json as _json
        try:
            from ..config_loader import get_config
            pe_base   = Path(get_config().model_output.experience_base_dir)
            pe_models = pe_base / "models"
            pe_params = pe_base / "params"
            if not pe_models.exists():
                return None
            candidates = sorted(
                pe_models.glob(f"*_{diagram_type}_*.xml"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                return None

            # ── Priority 1: ParameterExperience structural retrieval ──────────
            if self.parameter_experience is not None:
                try:
                    task_ctx: Dict[str, Any] = {"task": "guidance_rl_optimization"}
                    if query_hint:
                        task_ctx["prompt"] = query_hint
                    pe_results = await self.parameter_experience.retrieve_best(
                        task_ctx, top_k=3
                    )
                    for pe_rec in pe_results:
                        mem_id = pe_rec.get("memory_id", "")
                        if not mem_id:
                            continue
                        matched = next(
                            (c for c in candidates if c.name.startswith(mem_id)), None
                        )
                        if matched:
                            content = _read_kb_file(matched)
                            if content:
                                logger.info(
                                    f"[SysML] PE structural retrieval: '{matched.name}' "
                                    f"(Q={pe_rec.get('quality_score', 0):.3f}, "
                                    f"fitness={pe_rec.get('fitness', 0):.3f}, "
                                    f"sim={pe_rec.get('similarity', 0):.3f})"
                                )
                                return content
                except Exception as exc:
                    logger.warning(f"[SysML] PE retrieve_best failed: {exc}")

            # ── Priority 2: JSON file scan with fitness + keyword scoring ─────
            best_hash, best_score = None, -1.0
            if query_hint and pe_params.exists():
                kw = [w for w in query_hint.lower().split() if len(w) > 3]
                for jf in pe_params.glob("*.json"):
                    try:
                        rec      = _json.loads(jf.read_text(encoding="utf-8"))
                        fitness  = float(rec.get("fitness", 0.0))
                        kw_bonus = 0.1 if kw and any(
                            w in rec.get("task_context", {}).get("prompt", "").lower()
                            for w in kw
                        ) else 0.0
                        score = fitness + kw_bonus
                        if score > best_score:
                            best_score = score
                            best_hash  = rec.get("memory_id", "")
                    except Exception:
                        pass

            matched = None
            if best_hash:
                matched = next((c for c in candidates if c.name.startswith(best_hash)), None)
            target = matched or candidates[0]

            content = _read_kb_file(target)
            if content:
                logger.info(
                    f"[SysML] Loaded PE {diagram_type} model '{target.name}' "
                    f"(matched={'yes' if matched else 'latest'}, score={best_score:.3f})"
                )
                return content
        except Exception as exc:
            logger.warning(f"[SysML] _load_pe_sysml failed: {exc}")
        return None

    # ── template retrieval ────────────────────────────────────────────────────

    async def _retrieve_template(self, diagram_type: str, query_hint: str) -> str:
        """
        Retrieve a SysML template.  Priority:
        1. RAG knowledge base (full-text search)
        2. Direct file read from ``knowledge_base/sysml/``
        """
        filename_map = {
            "bdd":        "sysml_bdd_reference.xml",
            "parametric": "sysml_parametric_reference.xml",
            "ibd":        "sysml_ibd_reference.xml",
        }
        fname = filename_map.get(diagram_type, "sysml_bdd_reference.xml")

        # Try RAG first
        if self.rag_kb:
            try:
                query = f"SysML {diagram_type.upper()} guidance system {query_hint}"
                results = await self.rag_kb.retrieve(query=query, top_k=3)
                for r in results:
                    content = r.get("content", "")
                    src = r.get("metadata", {}).get("filename", "")
                    # Prefer results that look like XML SysML diagrams
                    if ("<SysML" in content or "SysML" in content) and fname.split(".")[0].split("_")[-1] in src.lower():
                        logger.info(f"[SysML] Retrieved {diagram_type} template via RAG (src={src})")
                        return content
                # Fallback: return best-scored result if it contains XML
                for r in results:
                    if "<SysML" in r.get("content", ""):
                        return r["content"]
            except Exception as exc:
                logger.warning(f"RAG retrieval for SysML {diagram_type} failed: {exc}")

        # Direct KB file read
        content = _read_kb_file(_KB_SYSML / fname)
        if content:
            logger.info(f"[SysML] Using local KB template: {fname}")
        return content

    # ── template parametrization ──────────────────────────────────────────────

    @staticmethod
    def _fill_template(template: str, substitutions: Dict[str, str]) -> str:
        """Replace ``{key}`` placeholders in template with values."""
        result = template
        for key, val in substitutions.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    # ── main execute ──────────────────────────────────────────────────────────

    async def execute(
        self,
        model_name: str = "GuidanceSystem",
        navigation_coefficient: float = 3.5,
        damping_ratio: float = 0.75,
        control_gain: float = 1.0,
        target_position: Optional[List[float]] = None,
        task_description: str = "",
        mode: str = "TUNE_PARAMS",
    ) -> Dict[str, Any]:
        """Retrieve SysML templates from knowledge base, generate via ModelGenerationAgent, and save."""
        try:
            from ..config_loader import get_config
            cfg = get_config()
            out_dir = Path(cfg.model_output.sysml_output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            tpos = target_position or [20000.0, 2000.0, 5000.0]
            subs = {
                "model_name":             model_name,
                "navigation_coefficient": str(navigation_coefficient),
                "damping_ratio":          str(damping_ratio),
                "control_gain":           str(control_gain),
                "target_position_0":      str(tpos[0]),
                "target_position_1":      str(tpos[1]),
                "target_position_2":      str(tpos[2]),
            }

            hint = task_description or f"nav={navigation_coefficient} damping={damping_ratio}"
            ts   = int(time.time())
            saved: Dict[str, str] = {}

            diagram_configs = [
                ("bdd",        f"{model_name}_bdd_{ts}.xml"),
                ("parametric", f"{model_name}_parametric_{ts}.xml"),
                ("ibd",        f"{model_name}_ibd_{ts}.xml"),
            ]

            agent = self._get_model_agent() if mode == "MODIFY_LAW" else None

            for diag_type, fname in diagram_configs:
                if mode == "REUSE_HISTORY":
                    # Prefer best-matching PE XML; fall back to KB template
                    content = await self._load_pe_sysml(diag_type, query_hint=hint)
                    if not content:
                        template = await self._retrieve_template(diag_type, hint)
                        content = self._fill_template(template, subs) if template else ""
                        logger.info(
                            f"[SysML] REUSE_HISTORY: no PE {diag_type} found, "
                            "using KB template."
                        )
                elif mode == "TUNE_PARAMS":
                    # Check PE first (richer starting point); fall back to KB template
                    pe_base_content = await self._load_pe_sysml(diag_type, query_hint=hint)
                    if pe_base_content:
                        template = pe_base_content
                        logger.info(f"[SysML] TUNE_PARAMS: seeding from PE model for {diag_type}")
                    else:
                        template = await self._retrieve_template(diag_type, hint)
                    if not template:
                        logger.warning(f"[SysML] No template for {diag_type}, skipping.")
                        continue
                    content = self._fill_template(template, subs)
                else:  # MODIFY_LAW
                    # Use best-matching PE model as LLM base if available;
                    # fall back to KB template.  PE experience gives the LLM
                    # a better-tuned starting architecture to adapt from.
                    pe_base_content = await self._load_pe_sysml(diag_type, query_hint=hint)
                    kb_template     = await self._retrieve_template(diag_type, hint)
                    template = pe_base_content or kb_template
                    if pe_base_content:
                        logger.info(f"[SysML] MODIFY_LAW: seeding LLM from PE model for {diag_type}")
                    if not template:
                        logger.warning(f"[SysML] No template for {diag_type}, skipping.")
                        continue
                    if agent:
                        content = await agent.generate_sysml(
                            task_description=task_description,
                            template=template,
                            diagram_type=diag_type,
                            substitutions=subs,
                        )
                    else:
                        content = self._fill_template(template, subs)

                if not content:
                    logger.warning(f"[SysML] Empty content for {diag_type}, skipping.")
                    continue
                out_path = out_dir / fname
                out_path.write_text(content, encoding="utf-8")
                saved[diag_type] = str(out_path)
                logger.info(f"[SysML] Saved {diag_type} → {out_path}  (mode={mode})")

            return {
                "status":          "success",
                "model_name":      model_name,
                "output_dir":      str(out_dir),
                "generated_files": saved,
                "mode":            mode,
                "template_source": "pe_model" if mode == "REUSE_HISTORY" else "rag_knowledge_base",
            }
        except Exception as exc:
            logger.error(f"SysML generation failed: {exc}")
            return {"status": "error", "message": str(exc)}


class GenerateMATLABTool:
    """
    Generate MATLAB simulation scripts for the guidance system.

    The template is retrieved **automatically** from the RAG knowledge base
    (``knowledge_base/matlab/``).  The tool then applies the requested
    autopilot design parameters (``dp.*``) and mission condition flags
    (``run_A``, ``sub_A``, etc.) to produce a ready-to-run script.

    The generated script is saved to the configured ``matlab_scripts_dir``.
    """

    name = "generate_matlab"
    description = """
    Generate a MATLAB simulation script from the knowledge-base template.
    Automatically retrieves the best-matching MATLAB template via RAG
    (monte_carlo_single.m — primary template; legacy fallbacks also supported),
    then patches it with the specified autopilot design parameters and
    mission conditions (RUN_CASE / SUB_IDX for T/G/AP/R categories).
    Saves the result to the MATLAB scripts directory.
    Use this when you need to create or refresh the simulation script.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "script_name": {
                "type": "string",
                "description": "Output file name (without .m extension)",
                "default": "guidance_simulation",
            },
            "task_description": {
                "type": "string",
                "description": "Free-text description used for RAG template retrieval and LLM generation",
            },
            "mode": {
                "type": "string",
                "description": (
                    "Generation mode: "
                    "REUSE_HISTORY (minimal patching), "
                    "TUNE_PARAMS (patch dp.* params + conditions), "
                    "MODIFY_LAW (LLM rewrites guidance-law function body)."
                ),
                "enum": ["REUSE_HISTORY", "TUNE_PARAMS", "MODIFY_LAW"],
                "default": "TUNE_PARAMS",
            },
            "autopilot_params": {
                "type": "object",
                "description": (
                    "Autopilot design parameter overrides.  Supported keys: "
                    "w1, zeta1, tao1, w2, zeta2, tao2, w3, zeta3.  "
                    "Missing keys keep the template default."
                ),
                "additionalProperties": {"type": "number"},
            },
            "mission_conditions": {
                "type": "string",
                "description": (
                    "Mission condition overrides, e.g. "
                    "'run_A=true;sub_A=[];run_B=false;'  "
                    "Overwrites the corresponding flags in the template.  "
                    "Leave empty for non-standard conditions and set "
                    "non_standard_task instead."
                ),
            },
            "non_standard_task": {
                "type": "string",
                "description": (
                    "Free-text description of working conditions that do NOT map "
                    "to standard A-F categories.  The ModelGenerationAgent will "
                    "infer the closest A-F flag mapping via LLM."
                ),
            },
            "nmc": {
                "type": "integer",
                "description": "Number of Monte Carlo runs (Nmc in the script)",
                "default": 100,
            },
        },
        "required": [],
    }

    # Priority-ordered list of MATLAB template file names to search for
    _TEMPLATE_PRIORITY = [
        "monte_carlo_single.m",                # current primary template
        "MC_gongkuang_simulation_robust_all.m",  # legacy fallback
        "chengxu_robust_analysis_singlefile.m",  # legacy fallback
    ]

    def __init__(self, *args, **kwargs):
        self.simulator = None
        self.rag_kb = None
        self.parameter_experience = None
        self.last_script_path: str = ""
        self.last_modification_desc: str = ""  # task description for MODIFY_LAW
        self._model_agent = None
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    def set_rag_kb(self, rag_kb) -> None:
        self.rag_kb = rag_kb

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience

    def _get_model_agent(self):
        """Lazy-instantiate ModelGenerationAgent."""
        if self._model_agent is None:
            try:
                from ..integration.model_generation_agent import ModelGenerationAgent
                self._model_agent = ModelGenerationAgent()
            except Exception as exc:
                logger.warning(f"[MATLAB] Could not create ModelGenerationAgent: {exc}")
        return self._model_agent

    async def _load_pe_model(self, query: str = "") -> Optional[tuple]:
        """
        Return ``(content, source_label)`` for the best-matching PE model
        script in ``experience_base_dir/models/``, or ``None`` if none exist.

        Retrieval priority:
        1. ``ParameterExperience.retrieve_best()`` when PE is injected —
           structural similarity × fitness × reliability (Q-score).
        2. JSON file scan with fitness + keyword scoring (fallback when PE
           is not loaded).
        3. Most-recent file by mtime (last resort).
        """
        import json as _json
        try:
            from ..config_loader import get_config
            cfg       = get_config()
            pe_base   = Path(cfg.model_output.experience_base_dir)
            pe_models = pe_base / "models"
            pe_params = pe_base / "params"
            if not pe_models.exists():
                return None
            candidates = sorted(
                pe_models.glob("*.m"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                return None

            # ── Priority 1: ParameterExperience structural retrieval ──────────
            if self.parameter_experience is not None:
                try:
                    task_ctx: Dict[str, Any] = {"task": "guidance_rl_optimization"}
                    if query:
                        task_ctx["prompt"] = query
                    pe_results = await self.parameter_experience.retrieve_best(
                        task_ctx, top_k=3
                    )
                    for pe_rec in pe_results:
                        mem_id = pe_rec.get("memory_id", "")
                        if not mem_id:
                            continue
                        matched = next(
                            (c for c in candidates if c.name.startswith(mem_id)), None
                        )
                        if matched:
                            content = _read_kb_file(matched)
                            if content:
                                logger.info(
                                    f"[MATLAB] PE structural retrieval: '{matched.name}' "
                                    f"(Q={pe_rec.get('quality_score', 0):.3f}, "
                                    f"fitness={pe_rec.get('fitness', 0):.3f}, "
                                    f"sim={pe_rec.get('similarity', 0):.3f})"
                                )
                                return content, (
                                    f"pe_model:{matched.name}"
                                    f"(Q={pe_rec.get('quality_score', 0):.3f})"
                                )
                except Exception as exc:
                    logger.warning(f"[MATLAB] PE retrieve_best failed: {exc}")

            # ── Priority 2: JSON file scan with fitness + keyword scoring ─────
            best_hash, best_score = None, -1.0
            if query and pe_params.exists():
                kw = [w for w in query.lower().split() if len(w) > 3]
                for jf in pe_params.glob("*.json"):
                    try:
                        rec      = _json.loads(jf.read_text(encoding="utf-8"))
                        fitness  = float(rec.get("fitness", 0.0))
                        kw_bonus = 0.1 if kw and any(
                            w in rec.get("task_context", {}).get("prompt", "").lower()
                            for w in kw
                        ) else 0.0
                        score = fitness + kw_bonus
                        if score > best_score:
                            best_score = score
                            best_hash  = rec.get("memory_id", "")
                    except Exception:
                        pass

            matched = None
            if best_hash:
                matched = next((c for c in candidates if c.name.startswith(best_hash)), None)
            target = matched or candidates[0]

            content = _read_kb_file(target)
            if content:
                logger.info(
                    f"[MATLAB] Loaded PE model '{target.name}' "
                    f"(matched={'yes' if matched else 'latest'}, score={best_score:.3f})"
                )
                return content, (
                    f"pe_model:{target.name}(score={best_score:.3f})"
                    if matched else
                    f"pe_model:{target.name}(latest)"
                )
        except Exception as exc:
            logger.warning(f"[MATLAB] _load_pe_model failed: {exc}")
        return None

    # ── template retrieval ────────────────────────────────────────────────────

    async def _retrieve_template(self, query: str) -> tuple:
        """
        Return ``(template_content, source_label)``.

        Priority:
        1. Direct file read from ``knowledge_base/matlab/``
           (preferred: monte_carlo_single.m).
           Local files are the **source of truth** and always up-to-date.
        2. RAG knowledge base — fallback when no local file matches.
           (RAG may contain stale indexed content from before bug fixes.)
        """
        # 1. Direct file read (always prefer the on-disk source of truth)
        for fname in self._TEMPLATE_PRIORITY:
            for subdir in ["guidance", "robust_analysis", ""]:
                candidate = _KB_MATLAB / subdir / fname if subdir else _KB_MATLAB / fname
                content = _read_kb_file(candidate)
                if content:
                    logger.info(f"[MATLAB] Using local KB template: {candidate}")
                    return content, f"local:{fname}"

        # 2. RAG retrieval (fallback only) — strict content gate so a
        #    markdown documentation chunk that mentions "function" and "dp."
        #    can't be mistaken for a real MATLAB template.
        if self.rag_kb:
            try:
                rag_query = f"MATLAB guidance simulation robust {query}"
                results = await self.rag_kb.retrieve(query=rag_query, top_k=5)
                for r in results:
                    content = r.get("content", "")
                    src = r.get("metadata", {}).get("filename", "")
                    if self._is_real_matlab_template(content):
                        logger.info(
                            f"[MATLAB] Retrieved template via RAG "
                            f"(src={src}, score={r.get('score',0):.2f})"
                        )
                        return content, f"rag:{src}"
                    else:
                        logger.debug(
                            f"[MATLAB] RAG result rejected (src={src}): "
                            f"does not look like a real MATLAB template"
                        )
            except Exception as exc:
                logger.warning(f"RAG retrieval for MATLAB template failed: {exc}")

        return "", "not_found"

    @staticmethod
    def _is_real_matlab_template(content: str) -> bool:
        """Strict gate: only accept content that is unambiguously a
        MATLAB template (not a markdown doc, not LLM prose).

        Required positive markers:
          • Source file name suffix `.m` is implied by the text features
            below (markdown docs would not pass them).
          • Multiple ``dp.<name> = <number>;`` numeric assignments
            (the autopilot parameter block — load-bearing for RL patching).
          • A function declaration OR a ``clc;``/``clear`` script header.

        Hard rejections:
          • Markdown fenced code markers (triple-backtick blocks).
          • Two or more markdown-style headings (``# `` at line start).
        """
        if not content or not content.strip():
            return False
        # Hard rejections
        if "```" in content:
            return False
        if len(re.findall(r"(?m)^\s{0,3}#{1,6}\s+\S", content)) >= 2:
            return False
        # Must have at least 3 dp.* numeric assignments (the parameter block
        # the RL optimiser keys off of).
        n_dp_assigns = len(re.findall(
            r"dp\.[a-zA-Z_]\w*\s*=\s*[-+]?\d", content
        ))
        if n_dp_assigns < 3:
            return False
        # Must have either a function header or a clc/clear script header
        has_function = bool(re.search(r"(?m)^\s*function\s+\w", content))
        has_script_header = bool(re.search(r"(?m)^\s*(clc|clear)\b", content))
        if not (has_function or has_script_header):
            return False
        return True

    # ── parameter patching ────────────────────────────────────────────────────

    # RL_PARAMS block variable name mapping (Python key → MATLAB rl_* variable)
    _RL_PARAM_MAP: Dict[str, str] = {
        "w1": "rl_w1", "zeta1": "rl_zeta1",
        "w2": "rl_w2", "zeta2": "rl_zeta2",
        "w3": "rl_w3", "zeta3": "rl_zeta3",
        "N_pn": "rl_N_pn", "sw_dist": "rl_sw_dist",
    }

    @classmethod
    def _patch_autopilot_params(cls, script: str, params: Dict[str, float]) -> str:
        """Patch parameters. Strategy A: RL_PARAMS block (monte_carlo_single).
        Strategy B: dp.key = value (legacy templates)."""
        # Strategy A: RL_PARAMS block (match %% or % prefix, flexible spacing)
        rl_block_pat = re.compile(
            r"(%+.*?RL_PARAMS_BEGIN.*?\n)(.*?)(%+.*?RL_PARAMS_END)",
            re.DOTALL,
        )
        rl_match = rl_block_pat.search(script)
        if rl_match:
            block = rl_match.group(2)
            matched_any = False
            for py_key, ml_var in cls._RL_PARAM_MAP.items():
                val = params.get(py_key)
                if val is None:
                    continue
                new_block, n = re.subn(
                    rf"({re.escape(ml_var)}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?(\s*;)",
                    rf"\g<1>{val:.6f}\2",
                    block,
                )
                if n:
                    block = new_block
                    matched_any = True
            if matched_any:
                script = rl_block_pat.sub(
                    lambda m: m.group(1) + block + m.group(3), script, count=1
                )
                return script
        # Strategy B: bare rl_key = value anywhere in script (outside block or block missing)
        patched_b = False
        for py_key, ml_var in cls._RL_PARAM_MAP.items():
            val = params.get(py_key)
            if val is None:
                continue
            new_script, n = re.subn(
                rf"({re.escape(ml_var)}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?(\s*;)",
                rf"\g<1>{val:.6f}\2",
                script,
            )
            if n:
                script = new_script
                patched_b = True
        if patched_b:
            return script
        # Strategy C: dp.key = value (legacy templates)
        for key, val in params.items():
            script = re.sub(
                rf"(dp\.{key}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?\s*;",
                f"dp.{key} = {val:.6f};",
                script,
            )
        return script

    @staticmethod
    def _patch_mission_conditions(script: str, conditions_str: str) -> str:
        """
        Apply mission conditions to a MATLAB script.

        Supports two formats:
          New: "RUN_CASE='T';SUB_IDX=0;" (monte_carlo_single style)
          Legacy: "run_A=true;sub_A=[1,2];run_B=false;" (old template style)
        """
        # ── New format: RUN_CASE / SUB_IDX ───────────────────────────────────
        rc_m = re.search(r"RUN_CASE\s*=\s*'([A-Za-z]+)'", conditions_str)
        si_m = re.search(r"SUB_IDX\s*=\s*(\d+)", conditions_str)
        if rc_m:
            rc_val = rc_m.group(1)
            si_val = si_m.group(1) if si_m else "0"
            script = re.sub(
                r"RUN_CASE\s*=\s*'[A-Za-z]+'", f"RUN_CASE='{rc_val}'", script
            )
            script = re.sub(r"SUB_IDX\s*=\s*\d+", f"SUB_IDX={si_val}", script)
            return script

        # ── Legacy format: run_X / sub_X ────────────────────────────────────
        _ALL_CATS = list("ABCDEF")
        enabled: set = set()
        for m in re.finditer(r"run_([A-F])\s*=\s*(true|false)", conditions_str, re.IGNORECASE):
            cat, val = m.group(1).upper(), m.group(2).lower()
            if val == "true":
                enabled.add(cat)
        for cat in _ALL_CATS:
            val = "true" if cat in enabled else "false"
            script = re.sub(rf"run_{cat}\s*=\s*(true|false)\s*;", f"run_{cat} = {val};", script)
        for m in re.finditer(r"sub_([A-F])\s*=\s*\[(.*?)\]", conditions_str, re.IGNORECASE):
            cat, content = m.group(1).upper(), m.group(2).strip()
            script = re.sub(rf"sub_{cat}\s*=\s*\[.*?\]\s*;", f"sub_{cat} = [{content}];", script)
        return script

    # ── main execute ──────────────────────────────────────────────────────────

    async def execute(
        self,
        script_name: str = "guidance_simulation",
        task_description: str = "",
        mode: str = "TUNE_PARAMS",
        autopilot_params: Optional[Dict[str, float]] = None,
        mission_conditions: Optional[str] = None,
        non_standard_task: str = "",
        nmc: int = 100,
    ) -> Dict[str, Any]:
        """Retrieve MATLAB template from KB, generate/patch via ModelGenerationAgent, and save."""
        try:
            from ..config_loader import get_config
            cfg = get_config()
            out_dir = Path(cfg.model_output.matlab_scripts_dir)
            out_dir.mkdir(parents=True, exist_ok=True)

            query = task_description or script_name

            # ── Mode-specific template selection ──────────────────────────────
            if mode == "REUSE_HISTORY":
                # Prefer best-matching PE model (fitness + keyword); fall back to KB template
                pe_result = await self._load_pe_model(query=query)
                if pe_result:
                    content, source = pe_result
                else:
                    content, source = await self._retrieve_template(query)
                    logger.info("[MATLAB] REUSE_HISTORY: no PE model found, using KB template")

                if not content:
                    return {
                        "status": "error",
                        "message": "REUSE_HISTORY: no model found in PE base or KB.",
                    }
                # Minimal patching: only Nmc + mission_conditions (no param tuning)
                content = re.sub(r"Nmc\s*=\s*\d+;", f"Nmc = {nmc};", content)
                if mission_conditions:
                    content = self._patch_mission_conditions(content, mission_conditions)
                rewrite_applied = False

            else:
                # TUNE_PARAMS / MODIFY_LAW: seed from best-matching PE model if available;
                # fall back to KB template.  PE experience gives LLM / RL a better-tuned
                # starting point and preserves any prior guidance-law modifications.
                pe_result = await self._load_pe_model(query=query)
                if pe_result:
                    content, source = pe_result
                    logger.info(f"[MATLAB] {mode}: seeding from PE model (src={source})")
                else:
                    content, source = await self._retrieve_template(query)
                if not content:
                    return {
                        "status": "error",
                        "message": "No MATLAB template found in knowledge base or local files.",
                    }

                agent = self._get_model_agent()
                if agent:
                    content = await agent.generate_matlab(
                        task_description=task_description or script_name,
                        template_content=content,
                        mode=mode,
                        autopilot_params=autopilot_params,
                        mission_conditions=mission_conditions,
                        nmc=nmc,
                        non_standard_task=non_standard_task,
                    )
                    rewrite_applied = (mode == "MODIFY_LAW")
                    # Force-patch after LLM generation:
                    # LLM may have reset or omitted these values.
                    if autopilot_params:
                        content = self._patch_autopilot_params(content, autopilot_params)
                    if mission_conditions:
                        content = self._patch_mission_conditions(content, mission_conditions)
                else:
                    # Fallback: original patching logic
                    content = re.sub(r"Nmc\s*=\s*\d+;", f"Nmc = {nmc};", content)
                    if autopilot_params:
                        content = self._patch_autopilot_params(content, autopilot_params)
                    if mission_conditions:
                        content = self._patch_mission_conditions(content, mission_conditions)
                    rewrite_applied = False

            # ── Build a filename that is also a valid MATLAB identifier ──
            # MATLAB requires the function declaration's name to match the
            # file's basename; otherwise it raises a hard parse error on
            # line 1.  We sanitise the user-supplied script_name (so it is
            # a valid identifier prefix) and then rename the function
            # declaration inside the template to match the final basename.
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', script_name or "guidance_simulation")
            if not safe_name or not re.match(r'[a-zA-Z]', safe_name[0]):
                safe_name = f"sim_{safe_name}" if safe_name else "guidance_simulation"
            ts = int(time.time())
            out_basename = f"{safe_name}_{ts}"          # valid identifier
            out_name     = f"{out_basename}.m"
            out_path     = out_dir / out_name

            # Rename the inherited `function <name>` declaration (if any) to
            # match the new file basename.  Robust to optional `[out] = ...`
            # signature prefix (function out = name(args) → keep `out =`).
            func_decl_re = re.compile(
                r"^(\s*function\s+(?:[^=\s]+\s*=\s*)?)([a-zA-Z_]\w*)",
                re.MULTILINE,
            )
            m_decl = func_decl_re.search(content)
            if m_decl and m_decl.group(2) != out_basename:
                old_func = m_decl.group(2)
                content = func_decl_re.sub(
                    rf"\g<1>{out_basename}", content, count=1
                )
                # Also rename any explicit recursive self-calls inside the body
                # (rare, but keeps the script self-consistent).
                content = re.sub(
                    rf"\b{re.escape(old_func)}\s*\(",
                    f"{out_basename}(",
                    content,
                )
                logger.info(
                    f"[MATLAB] Renamed function declaration "
                    f"'{old_func}' → '{out_basename}' to match filename"
                )

            # ── Universal MATLAB script sanitiser ────────────────────────────
            # Handles all known LLM-generated script issues in one pass:
            #   1. Strip ✅/❌/⚠️ annotation lines (write sidecar if any)
            #   2. Inject missing dp guidance fields (N_guidance/R_switch/gama_max_deg)
            #   3. Add "global dp" before dp=struct(...) if missing
            #   4. Add "global dp; dp=sample.dp" to run_single_case_general
            content, _note_lines = _sanitize_matlab_guidance_script(content)
            if _note_lines:
                _sidecar = out_dir / f"{out_basename}_interface_check.txt"
                _sidecar.write_text("\n".join(_note_lines), encoding="utf-8")
                logger.info(
                    f"[MATLAB] Stripped {len(_note_lines)} annotation line(s) from script "
                    f"→ sidecar: {_sidecar.name}"
                )

            out_path.write_text(content, encoding="utf-8")
            try:
                # Also copy to model output dir for traceability.
                # Write to a temp file then rename to avoid WinError 32 when
                # MATLAB has the destination locked.
                model_out = Path(cfg.model_output.generated_dir)
                model_out.mkdir(parents=True, exist_ok=True)
                _dst = model_out / out_name
                _tmp = model_out / f"{out_basename}_tmp_{int(time.time())}.m"
                shutil.copy2(str(out_path), str(_tmp))
                try:
                    _tmp.replace(_dst)
                except OSError:
                    pass  # destination still locked; temp copy remains
            except Exception as exc:
                logger.warning(f"Could not copy script to model output dir: {exc}")

            logger.info(f"[MATLAB] Generated script → {out_path}  (source: {source})")
            self.last_script_path = str(out_path)
            if mode == "MODIFY_LAW":
                self.last_modification_desc = task_description or non_standard_task or ""
            return {
                "status":          "success",
                "script_path":     str(out_path),
                "model_copy_path": str(model_out / out_name),
                "template_source": source,
                "mode":            mode,
                "rewrite_applied": rewrite_applied,
                "nmc":             nmc,
            }
        except Exception as exc:
            logger.error(f"MATLAB generation failed: {exc}")
            return {"status": "error", "message": str(exc)}


class RunSimulationTool:
    name = "run_simulation"
    description = """
    Run guidance system simulation.

    Two modes:
    1. **Direct KB template execution** (REUSE_HISTORY): provide `script_path` pointing
       to an existing knowledge-base MATLAB template (e.g. the absolute path of
       MC_gongkuang_simulation_robust_all.m).  Optionally supply `dp_params` to
       patch dp.* design parameters and `mission_conditions` to select subcases.
       The script is executed directly via Octave/MATLAB — **no new file is generated**.

    2. **Python simulator** (fallback): provide `navigation_coefficient` and
       `damping_ratio` to run the internal Python simulation.
    """

    # Canonical KB template path — monte_carlo_single.m is the primary template
    KB_TEMPLATE_PATH: str = str(
        _KB_MATLAB / "guidance" / "monte_carlo_single.m"
    )
    # Legacy path kept for backward compat
    KB_TEMPLATE_PATH_LEGACY: str = str(
        _KB_MATLAB / "robust_analysis" / "MC_gongkuang_simulation_robust_all.m"
    )

    input_schema = {
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": (
                    "Absolute path to an existing MATLAB script to run directly. "
                    "Default KB template: monte_carlo_single.m "
                    f"({str(_KB_MATLAB / 'guidance' / 'monte_carlo_single.m')})"
                ),
            },
            "dp_params": {
                "type": "object",
                "description": (
                    "Optional parameter overrides applied to the RL_PARAMS block "
                    "before execution. Keys: w1, zeta1, w2, zeta2, w3, zeta3, "
                    "N_pn, sw_dist."
                ),
                "additionalProperties": {"type": "number"},
            },
            "mission_conditions": {
                "type": "string",
                "description": (
                    "Mission conditions for monte_carlo_single.m. "
                    "Format: \"RUN_CASE='T';SUB_IDX=0;\" or \"RUN_CASE='ALL';SUB_IDX=0;\" "
                    "Categories: T=目标机动, G=交战几何, AP=驾驶仪退化, R=综合鲁棒"
                ),
            },
            "nmc": {
                "type": "integer",
                "description": "Number of Monte Carlo runs (Nmc) when running a template script.",
                "default": 20,
            },
            "navigation_coefficient": {"type": "number"},
            "damping_ratio": {"type": "number"},
            "control_gain": {"type": "number"},
            "target_position": {"type": "array"},
            "duration": {"type": "number", "default": 100.0},
            "dt": {"type": "number", "default": 0.01},
        },
        "required": [],
    }

    def __init__(self, *args, **kwargs):
        self.simulator = None
        # Captures the raw MATLAB stdout from the most recent successful simulation
        # so that callers (e.g. cli_agent Step 3.5) can parse metrics without
        # having to re-run the simulation.
        self.last_stdout: str = ""
        # Fallback mission conditions injected from cli_agent each iteration.
        # Used when Hermes omits the mission_conditions argument.
        self._default_mission_conditions: str = ""
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    def set_mission_conditions(self, conditions_str: str) -> None:
        """Inject user-resolved mission conditions as fallback for Hermes tool calls."""
        self._default_mission_conditions = conditions_str or ""

    @staticmethod
    def _find_latest_generated_script() -> Optional[str]:
        """Return the most recently modified .m file from matlab_scripts_dir, or None."""
        try:
            from ..config_loader import get_config
            scripts_dir = Path(get_config().model_output.matlab_scripts_dir)
            candidates = sorted(
                scripts_dir.glob("*.m"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                logger.info(
                    f"[run_simulation] No script_path given; "
                    f"using latest Hermes-generated script: {candidates[0].name}"
                )
                return str(candidates[0])
        except Exception as exc:
            logger.debug(f"[run_simulation] Could not scan matlab_scripts_dir: {exc}")
        return None

    async def execute(
        self,
        script_path: Optional[str] = None,
        dp_params: Optional[Dict[str, float]] = None,
        mission_conditions: Optional[str] = None,
        nmc: int = 20,
        navigation_coefficient: float = 3.5,
        damping_ratio: float = 0.75,
        control_gain: float = 1.0,
        target_position: Optional[List[float]] = None,
        duration: float = 100.0,
        dt: float = 0.01,
    ) -> Dict[str, Any]:
        """Run simulation — directly via Hermes-generated script, KB template, or Python sim.

        Priority when script_path is omitted:
          1. Most recently generated .m from matlab_scripts_dir (Hermes output)
          2. KB template monte_carlo_single.m
          3. Python internal simulator (fallback)
        """

        # ── Resolve script_path: prefer Hermes-generated, then KB template ───
        if not script_path:
            script_path = self._find_latest_generated_script()
            if not script_path and Path(self.KB_TEMPLATE_PATH).exists():
                script_path = self.KB_TEMPLATE_PATH
                logger.info(
                    "[run_simulation] No generated script found; "
                    "falling back to KB template: monte_carlo_single.m"
                )

        # ── Path 1: Direct script execution ──────────────────────────────────
        if script_path:
            _result = await self._run_script_directly(
                script_path, dp_params or {}, mission_conditions, nmc
            )
            # Capture stdout so cli_agent can parse metrics at Step 3.5
            # without needing to re-run the simulation.
            if isinstance(_result, dict) and _result.get("status") == "success":
                self.last_stdout = _result.get("stdout", "")
            return _result

        # ── Path 2: Python internal simulator ────────────────────────────────
        try:
            from ..simulation import GuidanceSimulator, GuidanceParameters

            params = GuidanceParameters(
                navigation_coefficient=navigation_coefficient,
                damping_ratio=damping_ratio,
                control_gain=control_gain,
                target_position=target_position or [20000.0, 2000.0, 5000.0],
            )
            sim = GuidanceSimulator()
            results = await sim.generate_and_simulate(
                params=params, duration=duration, dt=dt,
                generate_sysml=False, generate_matlab=False,
            )
            return {"status": "success", "result": results["simulation_result"]}
        except Exception as e:
            logger.error(f"Python simulation failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _run_script_directly(
        self,
        script_path: str,
        dp_params: Dict[str, float],
        mission_conditions: Optional[str],
        nmc: int,
    ) -> Dict[str, Any]:
        """
        Patch dp.* params + mission flags into *script_path* (in-memory),
        write to a temp file alongside the original, execute via Octave/MATLAB,
        and return parsed metrics.  The original KB template is never modified.
        """
        import subprocess, tempfile, time as _time, re as _re

        path = Path(script_path)
        if not path.exists():
            return {"status": "error", "message": f"Script not found: {script_path}"}

        content = _read_kb_file(path)
        if not content:
            return {"status": "error", "message": f"Could not read script: {script_path}"}

        # Patch N_MC (monte_carlo_single) and Nmc (legacy)
        content = _re.sub(r"\bN_MC\s*=\s*\d+\s*;", f"N_MC = {nmc};", content)
        content = _re.sub(r"\bNmc\s*=\s*\d+\s*;",  f"Nmc = {nmc};",  content)

        # Patch dp.* params
        if dp_params:
            content = GenerateMATLABTool._patch_autopilot_params(content, dp_params)

        # Patch mission conditions (use caller arg; fall back to injected default)
        _cond = mission_conditions or self._default_mission_conditions
        if _cond:
            content = GenerateMATLABTool._patch_mission_conditions(content, _cond)

        # Write temp file (named after the function to satisfy MATLAB/Octave).
        # IMPORTANT: filename basename must be a valid MATLAB identifier when
        # the engine resolves the script as a function.  We append a uuid hex
        # suffix (letter-prefix safe + collision free for parallel callers).
        import uuid as _uuid
        func_match = _re.match(r"^\s*function\s+(?:[^=\s]+\s*=\s*)?([a-zA-Z_]\w*)", content)
        func_name = func_match.group(1) if func_match else None
        tmp_dir = path.parent
        unique_tag = _uuid.uuid4().hex[:8]
        suffix = f"_direct_{unique_tag}"
        if func_name:
            tmp_name = f"{func_name}{suffix}.m"
            content = _re.sub(
                r"^function\s+" + _re.escape(func_name),
                f"function {func_name}{suffix}",
                content, count=1, flags=_re.MULTILINE,
            )
            call_name = f"{func_name}{suffix}"
        else:
            # No leading underscore — keeps basename a valid identifier.
            tmp_name  = f"directrun_{unique_tag}.m"
            call_name = None

        tmp_path = tmp_dir / tmp_name
        try:
            tmp_path.write_text(content, encoding="utf-8")

            # Determine engine from simulator's executor
            executor = getattr(getattr(self.simulator, "executor", None), "__dict__", {})
            engine   = executor.get("engine", "octave")
            oct_path = executor.get("octave_path", "octave")
            mat_path = executor.get("matlab_path", "matlab")
            abs_path = str(tmp_path).replace("\\", "/")
            script_dir = str(tmp_dir).replace("\\", "/")

            # Use shared Octave batch constants: --no-window-system + figure
            # suppression + warning silencing to keep the run_simulation tool
            # call from blowing past the timeout on the KB template's
            # ~30 figure() rendering operations.
            from multi_agent.simulation.guidance_simulator import (
                OCTAVE_BATCH_FLAGS,
                DEFAULT_SUBPROCESS_TIMEOUT_SEC,
                build_octave_eval_string,
            )

            # ── Branch 0: in-process matlab.engine ────────────────────────
            # Skips subprocess startup entirely.  Returns the result early
            # rather than going through subprocess.run() below.  Falls
            # through to the subprocess MATLAB branch on backend errors.
            if engine == "matlab_engine":
                executor_obj = getattr(self.simulator, "executor", None)
                backend = getattr(executor_obj, "matlab_engine_backend", None)
                if backend is not None and backend.started:
                    stdout, stderr, ok = backend.run_script(
                        abs_path,
                        call_name=call_name,
                        timeout_sec=float(DEFAULT_SUBPROCESS_TIMEOUT_SEC),
                    )
                    if ok:
                        logger.info(
                            f"[run_simulation] in-process matlab.engine complete, "
                            f"stdout={len(stdout)} chars"
                        )
                        return {
                            "status":      "success",
                            "script_path": script_path,
                            "stdout":      (stdout or "")[:4000],
                            "stderr":      (stderr or "")[:500],
                            "note":        "KB template executed via matlab.engine (in-process)",
                        }
                    # not ok — distinguish engine crash from script error
                    if not backend.started:
                        # Engine crashed — fall through to subprocess MATLAB
                        logger.warning(
                            f"matlab.engine crashed on '{tmp_name}'; "
                            f"falling back to MATLAB subprocess."
                        )
                        engine = "matlab"
                    else:
                        logger.warning(
                            f"matlab.engine returned error on '{tmp_name}':\n"
                            f"{(stderr or '')[:2000]}"
                        )
                        return {
                            "status":  "error",
                            "message": f"matlab.engine: {(stderr or '')[:200]}",
                            "stderr":  (stderr or "")[:2000],
                        }
                if engine == "matlab_engine":  # backend unavailable from the start
                    logger.info(
                        "matlab.engine backend not started; falling back to "
                        "MATLAB subprocess for this run_simulation call."
                    )
                    engine = "matlab"

            if engine == "octave":
                # source() runs the file in the current scope without trying to
                # resolve its basename as an identifier (avoids parse errors
                # on temp filenames that look like numeric literals).
                eval_str = build_octave_eval_string(abs_path, call_name)
                cmd = [oct_path, *OCTAVE_BATCH_FLAGS, "--eval", eval_str]
            elif engine == "matlab":
                # MATLAB equivalent: -nosplash + -nodesktop + -nodisplay +
                # set DefaultFigureVisible='off' avoids GUI/figure rendering.
                if call_name:
                    eval_str = (
                        f"set(0,'DefaultFigureVisible','off'); "
                        f"addpath('{script_dir}'); {call_name}; exit"
                    )
                else:
                    eval_str = (
                        f"set(0,'DefaultFigureVisible','off'); "
                        f"run('{abs_path}'); exit"
                    )
                cmd = [mat_path, "-nosplash", "-nodesktop", "-nodisplay",
                       "-batch", eval_str]
            else:
                return {"status": "error", "message": f"Unsupported engine: {engine}"}

            _aio_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout_b, _stderr_b = await asyncio.wait_for(
                    _aio_proc.communicate(), timeout=DEFAULT_SUBPROCESS_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                _aio_proc.kill()
                raise subprocess.TimeoutExpired(cmd, DEFAULT_SUBPROCESS_TIMEOUT_SEC)
            stdout = _stdout_b.decode("utf-8", errors="replace")
            stderr = _stderr_b.decode("utf-8", errors="replace")

            if _aio_proc.returncode != 0:
                logger.warning(
                    f"Script returned code {_aio_proc.returncode} on "
                    f"'{tmp_name}'.\n"
                    f"  cmd: {' '.join(cmd)}\n"
                    f"  stderr (up to 2000 chars):\n{(stderr or '').strip()[:2000]}"
                )
                return {
                    "status":  "error",
                    "message": f"returncode={_aio_proc.returncode}",
                    "stderr":  (stderr or "")[:2000],
                }

            logger.info(f"[run_simulation] Direct KB execution complete, stdout={len(stdout)} chars")
            return {
                "status":      "success",
                "script_path": script_path,
                "stdout":      stdout[:4000],
                "stderr":      stderr[:500] if stderr else "",
                "note":        "KB template executed directly — no new script generated",
            }
        except subprocess.TimeoutExpired:
            return {
                "status":  "error",
                "message": (
                    f"Simulation timed out (>{DEFAULT_SUBPROCESS_TIMEOUT_SEC}s); "
                    f"set MATLAB_TIMEOUT_SEC env var to override"
                ),
            }
        except FileNotFoundError as exc:
            return {"status": "error", "message": f"Engine executable not found: {exc}"}
        except Exception as exc:
            logger.error(f"Direct script execution failed: {exc}")
            return {"status": "error", "message": str(exc)}
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


class ParameterStudyTool:
    """参数研究工具"""

    name = "parameter_study"
    description = """
    Perform parameter study by exploring parameter grid.
    Evaluates all parameter combinations and returns metrics for each.
    Used for sensitivity analysis and design space exploration.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "param_grid": {
                "type": "object",
                "description": "Parameter grid, e.g., {'nav': [0.3, 0.5, 0.7], 'damp': [0.2, 0.3]}",
            },
            "duration": {"type": "number", "default": 100.0},
            "dt": {"type": "number", "default": 0.01},
        },
        "required": ["param_grid"],
    }

    def __init__(self, *args, **kwargs):
        self.simulator = None
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    async def execute(
        self,
        param_grid: Dict[str, List[float]],
        duration: float = 100.0,
        dt: float = 0.01,
    ) -> Dict[str, Any]:
        """执行参数研究"""
        try:
            from ..simulation import GuidanceSimulator, GuidanceParameters

            guidance_params = {}
            for key, values in param_grid.items():
                if key == "navigation_coefficient":
                    guidance_params["nav_values"] = values
                elif key == "damping_ratio":
                    guidance_params["damp_values"] = values

            nav_values = guidance_params.get("nav_values", [0.3, 0.5, 0.7])
            damp_values = guidance_params.get("damp_values", [0.2, 0.3, 0.4])

            study_grid = {
                "navigation_coefficient": nav_values,
                "damping_ratio": damp_values,
            }

            simulator = GuidanceSimulator()
            results = await simulator.parameter_study(
                param_grid=study_grid,
                duration=duration,
                dt=dt,
            )

            return {
                "status": "success",
                "total_combinations": len(results),
                "results": results,
            }
        except Exception as e:
            logger.error(f"Parameter study failed: {e}")
            return {"status": "error", "message": str(e)}


class OptimizeParametersTool:
    """参数优化工具"""

    name = "optimize_parameters"
    description = """
    Optimize guidance parameters using simulation results.
    Combines SysML model generation, MATLAB script generation, and iterative simulation.
    Returns optimal parameters that minimize miss distance and control energy.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "objectives": {
                "type": "object",
                "description": "Optimization objectives",
                "example": {
                    "miss_distance": {"type": "minimize", "weight": 1.0},
                    "control_energy": {"type": "minimize", "weight": 0.8},
                },
            },
            "constraints": {
                "type": "object",
                "description": "Parameter constraints",
            },
            "initial_params": {"type": "object"},
            "max_iterations": {"type": "integer", "default": 30},
        },
        "required": ["objectives"],
    }

    def __init__(self, *args, **kwargs):
        self.optimizer = None
        self.parameter_experience = None
        self.rl_learner = None
        super().__init__(*args, **kwargs)

    def set_optimizer(self, optimizer) -> None:
        self.optimizer = optimizer

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience

    def set_rl_learner(self, rl_learner) -> None:
        self.rl_learner = rl_learner

    async def execute(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 30,
    ) -> Dict[str, Any]:
        """执行参数优化"""
        try:
            from ..simulation.guidance_optimization_workflow import GuidanceOptimizationWorkflow, OptimizationObjectives
            from ..simulation import GuidanceParameters

            init_nav = 3.0
            init_damp = 0.3
            if initial_params:
                init_nav = initial_params.get("navigation_coefficient", init_nav)
                init_damp = initial_params.get("damping_ratio", init_damp)

            params = GuidanceParameters(
                navigation_coefficient=init_nav,
                damping_ratio=init_damp,
            )

            # Build objectives
            opt_objs = OptimizationObjectives(
                miss_distance=bool(objectives.get("miss_distance")),
                control_energy=bool(objectives.get("control_energy")),
                overshoot=bool(objectives.get("overshoot", False))
            )

            workflow = GuidanceOptimizationWorkflow()

            result = await workflow.run_optimization(
                initial_params=params,
                objectives=opt_objs,
                max_iterations=max_iterations
            )

            return {
                "status": "success",
                "optimal_parameters": result.get("best_parameters", {}),
                "metrics": result.get("simulation_metrics", {}),
                "optimization_result": result.get("optimization_result", {}),
                "generated_files": result.get("generated_files", {}),
                "report_file": result.get("report_file", "")
            }
        except Exception as e:
            logger.error(f"Parameter optimization failed: {e}")
            return {"status": "error", "message": str(e)}
