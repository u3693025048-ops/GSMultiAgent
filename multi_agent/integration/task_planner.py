#!/usr/bin/env python3
"""
Intelligent Task Planner
使用LLM决策是否拆分任务、拆分数目、执行策略
"""

import ast
import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """执行策略"""

    SINGLE = "single"  # 单Agent直接执行
    SEQUENTIAL = "sequential"  # 顺序拆分执行
    PARALLEL = "parallel"  # 并行拆分执行


@dataclass
class TaskPlan:
    """任务规划"""

    original_task: str
    strategy: ExecutionStrategy
    should_split: bool
    subagent_count: int
    subtasks: List[str]
    reason: str
    mode: str = "TUNE_PARAMS"        # REUSE_HISTORY | MODIFY_LAW | TUNE_PARAMS
    retrieval_context: str = ""      # RAG + PE context injected into prompt
    # ── Mission-condition analysis (Step 0A, performed BEFORE mode selection) ──
    # Free-form LLM analysis of which 工况 (categories A-F + subcases) the user's
    # task implies, derived from the MC_gongkuang_simulation_robust_all reference.
    mission_analysis: str = ""
    # Parsed mapping {category_letter: [subcase_indices]} produced by the LLM
    # 工况 analysis.  Empty dict if analysis was unavailable / unparseable; the
    # caller (cli_agent) can fall back to the regex-based parse_mission_conditions.
    mission_conditions: Dict[str, List[int]] = None
    # Raw conditions.md snippet retrieved during Step 0A — forwarded to Hermes
    # Step 0A system prompt so the agent has the same reference the planner used.
    conditions_md_ref: str = ""
    # Per-subtask mission condition strings (parallel to subtasks list).
    # Each element is a MATLAB-style condition string like "RUN_CASE='T';SUB_IDX=1;"
    # derived by the LLM during planning.  Empty list = fall back to regex parse.
    subtask_conditions: List[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Keyword heuristics for task-mode inference
# ─────────────────────────────────────────────────────────────────────────────

_MODIFY_LAW_KEYWORDS = [
    # Strong signals that the user wants a NEW guidance law algorithm
    "新设计制导律", "重新设计制导律", "设计新的制导律", "替换制导律",
    "全新制导律", "新的制导算法", "新制导算法", "重构制导律",
    "滑模变结构", "sliding mode", "redesign guidance", "new guidance law",
    "design new guidance", "改进制导律算法",
]

_TUNE_PARAMS_KEYWORDS = [
    "调参", "调整参数", "优化参数", "参数优化", "参数调优",
    "优化自动驾驶仪", "调整自动驾驶仪", "调整 w1", "优化 w1",
    "tune param", "parameter tuning", "rl 优化", "rl optimization",
    "调整 zeta", "优化 zeta", "调整 tao", "优化 tao",
    "调整制导律", "优化制导律", "调整导引系数", "优化导引系数",
    "调整导航系数", "tune guidance", "optimize guidance",
]

_REUSE_KEYWORDS = [
    "参考知识库", "参考模板", "使用模板", "利用模板", "基于模板",
    "基于知识库", "复用", "重用", "reuse", "use existing",
    "跑仿真", "直接使用",
    "使用已有", "基于已有", "use template",
]


def _heuristic_mode(task: str) -> Optional[str]:
    """
    Keyword-based mode inference — used **only** as a last-resort fallback
    when the LLM is completely unavailable (no response / unparseable JSON).
    It is intentionally NOT injected into the LLM prompt so that the mode
    decision is made purely by Hermes Agent's task-decomposition analysis.
    """
    if not task:
        return None
    t = task.lower()

    has_modify = any(k.lower() in t for k in _MODIFY_LAW_KEYWORDS)
    has_tune   = any(k.lower() in t for k in _TUNE_PARAMS_KEYWORDS)
    has_reuse  = any(k.lower() in t for k in _REUSE_KEYWORDS)

    if has_modify:
        return "MODIFY_LAW"
    if has_tune:
        return "TUNE_PARAMS"
    if has_reuse:
        return "REUSE_HISTORY"
    return None


class IntelligentTaskPlanner:
    """
    智能任务规划器

    使用LLM决策：
    1. 是否拆分任务
    2. 拆分成几个子任务
    3. 使用什么执行策略
    """

    def __init__(
        self,
        hermes: Any = None,
        llm_client: Any = None,
        rag_kb: Any = None,
        parameter_experience: Any = None,
    ):
        if llm_client is None and hermes is not None:
            llm_client = hermes.agent if hasattr(hermes, "agent") else None

        self.hermes = hermes
        self.llm_client = llm_client
        self.rag_kb = rag_kb
        self.parameter_experience = parameter_experience

    async def build_retrieval_context(self, task: str) -> str:
        """
        Retrieve relevant content from knowledge_base (RAG) and best historical
        parameters (ParameterExperience) to enrich the task prompt.

        Returns a formatted multi-line context string, or empty string on failure.
        """
        import json as _json
        parts: List[str] = []

        # 1. RAG retrieval — knowledge_base docs only
        if self.rag_kb:
            try:
                rag_results = await self.rag_kb.retrieve(query=task, top_k=5)
                # Python-side filter: keep only knowledge_base documents.
                # Old PE JSON files may be in Chroma from previous runs (indexed
                # before the source_tag fix); this filter removes them regardless
                # of whether Chroma's where-filter syntax works on this version.
                rag_results = [
                    r for r in rag_results
                    if r.get("metadata", {}).get("source_tag") == "knowledge_base"
                ][:3]
                if rag_results:
                    parts.append("[知识库检索结果]")
                    for r in rag_results:
                        score = r.get("score", 0.0)
                        src   = r.get("metadata", {}).get("filename", "")
                        snip  = r.get("content", "")[:400].replace("\n", " ")
                        parts.append(f"  [score={score:.2f}, src={src}] {snip}")
            except Exception as exc:
                logger.debug(f"RAG retrieval in planner failed: {exc}")

        # 2. ParameterExperience best history
        if self.parameter_experience:
            try:
                pe_results = await self.parameter_experience.retrieve_best(
                    task_context={"task": "guidance_rl_optimization"}, top_k=3
                )
                if pe_results:
                    parts.append("[历史最优参数记录]")
                    for r in pe_results:
                        fitness = r.get("fitness", 0.0)
                        params  = r.get("parameters", {})
                        obj     = r.get("objectives", {})
                        parts.append(
                            f"  fitness={fitness:.4f}  params={_json.dumps(params, ensure_ascii=False)}"
                            f"  objectives={_json.dumps(obj, ensure_ascii=False)}"
                        )
            except Exception as exc:
                logger.debug(f"PE retrieval in planner failed: {exc}")

        return "\n".join(parts)

    async def analyze_mission_conditions(
        self, task: str
    ) -> Dict[str, Any]:
        """
        Step 0A — 任务工况分析 (performed BEFORE mode selection).

        Retrieves the authoritative MC_gongkuang_simulation_robust_all reference
        from the RAG knowledge base, then asks the LLM to map the user's task
        description onto the 6 categories (A-F) and their subcases defined in
        that file.  The result is later injected into the mode-selection prompt
        so that the design path (REUSE_HISTORY / TUNE_PARAMS / MODIFY_LAW) is
        chosen with full awareness of the working conditions the task implies.

        Returns
        -------
        Dict with keys:
            "analysis"   : free-form LLM prose explaining the 工况 reasoning
            "conditions" : {category_letter: [subcase_indices]} dict (may be {})
            "reference"  : truncated MC_gongkuang_* RAG snippet used as context
        """
        import json as _json
        import re as _re

        # 1a. Retrieve MC_gongkuang_simulation_robust_all from RAG.
        ref_snippet = ""
        if self.rag_kb:
            try:
                rag_results = await self.rag_kb.retrieve(
                    query=(
                        "MC_gongkuang_simulation_robust_all mission conditions "
                        "categories A B C D E F subcases run_A sub_A definition "
                        "target maneuver initial geometry aerodynamic perturbation"
                    ),
                    top_k=5,
                )
                preferred = [
                    r for r in rag_results
                    if "MC_gongkuang" in r.get("metadata", {}).get("filename", "")
                ]
                pool = preferred or [
                    r for r in rag_results
                    if r.get("metadata", {}).get("source_tag") == "knowledge_base"
                ]
                if pool:
                    pieces = []
                    for r in pool[:3]:
                        src = r.get("metadata", {}).get("filename", "")
                        snip = r.get("content", "")[:1200]
                        pieces.append(f"[src={src}]\n{snip}")
                    ref_snippet = "\n\n".join(pieces)
            except Exception as exc:
                logger.debug(f"[Planner] MC_gongkuang RAG retrieval failed: {exc}")

        # 1b. Retrieve conditions.md from RAG; fall back to direct file read.
        conditions_md_snippet = ""
        if self.rag_kb:
            try:
                cond_results = await self.rag_kb.retrieve(
                    query=(
                        "conditions 工况分类 A B C D E F 子工况定义 "
                        "目标机动 初始交战几何 气动参数不确定 质量推力 "
                        "初始速度姿态 驾驶仪带宽阻尼"
                    ),
                    top_k=5,
                )
                cond_preferred = [
                    r for r in cond_results
                    if "conditions" in r.get("metadata", {}).get("filename", "").lower()
                ]
                cond_pool = cond_preferred or [
                    r for r in cond_results
                    if r.get("metadata", {}).get("source_tag") == "knowledge_base"
                ]
                if cond_pool:
                    pieces = []
                    for r in cond_pool[:3]:
                        src = r.get("metadata", {}).get("filename", "")
                        snip = r.get("content", "")[:1500]
                        pieces.append(f"[src={src}]\n{snip}")
                    conditions_md_snippet = "\n\n".join(pieces)
            except Exception as exc:
                logger.debug(f"[Planner] conditions.md RAG retrieval failed: {exc}")

        if not conditions_md_snippet:
            import pathlib
            _candidates = [
                pathlib.Path("knowledge_base/conditions.md"),
                pathlib.Path("../knowledge_base/conditions.md"),
                pathlib.Path(__file__).parent.parent.parent / "knowledge_base" / "conditions.md",
            ]
            for _p in _candidates:
                try:
                    if _p.exists():
                        conditions_md_snippet = (
                            f"[src=conditions.md (direct read)]\n"
                            + _p.read_text(encoding="utf-8")[:3000]
                        )
                        logger.info(f"[Planner] conditions.md read directly from {_p}")
                        break
                except Exception:
                    pass

        # 2. Ask the LLM to analyse 工况, grounding it in conditions.md content.
        mc_block = (
            f"\n\n[MC_gongkuang_simulation_robust_all.m 参考片段]\n{ref_snippet}\n"
            if ref_snippet else
            "\n\n(注: RAG 未返回 MC_gongkuang 片段，请以 conditions.md 为准)\n"
        )
        cond_block = (
            f"\n\n[conditions.md — 工况权威定义文档]\n{conditions_md_snippet}\n"
            if conditions_md_snippet else
            "\n\n(注: conditions.md 未检索到，请基于通用定义分析)\n"
        )

        gk_prompt = (
            "你是制导系统任务工况分析专家。请执行以下两步分析:\n\n"
            "【第一步】阅读下方 conditions.md 工况权威定义文档，提取四类工况(T/G/AP/R)的\n"
            "  控制变量、物理含义及子工况参数范围。\n\n"
            "【第二步】对照用户任务描述，判断任务涉及哪类工况及子工况：\n"
            "  • T：目标机动强度扫描(T1 匹速直飞/T2 低频小幅/T3 中频中等/T4 高频大幅)\n"
            "  • G：交战几何(G1 标称/G2 近距小偏/G3 近距大偏/G4 远距小偏/G5 远距大偏)\n"
            "  • AP：驾驶仪退化(AP1 全标称/AP2 时间常数退化/AP3 轻度退化/AP4 中度退化/AP5 重度退化)\n"
            "  • R：综合鲁棒(R1 全标称/R2 多参数摄动/R3 大姿态偏差)\n"
            "  • 任务未指明任何工况 → 仅 T 类(T1 匹速直飞，默认基本工况)\n"
            "  • 关键词 '鲁棒性/全工况' → T/G/AP/R 全部启用\n"
            "  • 子工况编号(SUB_IDX): T类 T1-T4(索引 1-4), G类 G1-G5(索引 1-5), AP类 AP1-AP5(索引 1-5), R类 R1-R3(索引 1-3); 0=全部子工况\n\n"
            f"用户任务描述:\n{task}\n"
            f"{cond_block}"
            f"{mc_block}\n"
            "请返回严格 JSON (不要其他文字):\n"
            "{\n"
            "  \"analysis\": \"基于 conditions.md 检索内容的工况分析：逐类说明任务是否触发该类别及依据\",\n"
            "  \"conditions\": {\"T\": [0,1], \"G\": [], ...}  // 仅列出需运行的类别，键为 T/G/AP/R\n"
            "}"
        )

        response_text = ""
        try:
            if hasattr(self.hermes, "run_with_tools"):
                response_text = await self.hermes.run_with_tools(
                    "System: 你是制导系统任务工况分析专家，输出严格 JSON。\n\n"
                    f"User: {gk_prompt}",
                    tools=[],
                )
            elif hasattr(self.llm_client, "generate"):
                response_text = await self.llm_client.generate(
                    prompt=gk_prompt,
                    system_prompt="你是制导系统任务工况分析专家，输出严格 JSON。",
                )
            elif hasattr(self.llm_client, "run_conversation"):
                import inspect
                msg = (
                    "System: 你是制导系统任务工况分析专家，输出严格 JSON。\n\n"
                    f"User: {gk_prompt}"
                )
                if inspect.iscoroutinefunction(self.llm_client.run_conversation):
                    response_text = await self.llm_client.run_conversation(msg)
                else:
                    response_text = self.llm_client.run_conversation(msg)
                if isinstance(response_text, dict):
                    response_text = response_text.get("final_response", "")
        except Exception as exc:
            logger.warning(f"[Planner] 工况 analysis LLM call failed: {exc}")
            response_text = ""

        analysis_text = ""
        conditions: Dict[str, List[int]] = {}
        if response_text:
            text = str(response_text).strip()
            # Strip markdown fences
            for fence in ("```json", "```"):
                if text.startswith(fence):
                    text = text[len(fence):]
                    break
            if text.endswith("```"):
                text = text[:-3]
            m = _re.search(r"\{[\s\S]*\}", text)
            blob = m.group(0) if m else text
            # Normalise common LLM quirks before parsing
            blob = _re.sub(r",\s*([}\]])", r"\1", blob)   # trailing commas
            blob = blob.replace("\u2022", "")               # bullet U+2022
            blob = blob.replace("\u2018", '"').replace("\u2019", '"')  # curly quotes
            blob = blob.replace("\u201c", '"').replace("\u201d", '"')
            data = None
            try:
                data = _json.loads(blob)
            except Exception:
                pass
            if data is None:
                # Fallback: replace Python-style single-quoted keys/values
                blob2 = _re.sub(r"(?<![\w])'", '"', blob)
                try:
                    data = _json.loads(blob2)
                except Exception:
                    pass
            if data is None:
                try:
                    data = ast.literal_eval(blob)
                except Exception as exc:
                    _safe = ascii(str(response_text)[:200])
                    logger.warning(
                        f"[Planner] 工况 JSON parse failed ({exc}); raw={_safe}"
                    )
            if data is not None:
                analysis_text = str(data.get("analysis", "")).strip()
                raw_cond = data.get("conditions", {}) or {}
                for cat, subs in raw_cond.items():
                    cat_u = str(cat).strip().upper()
                    if cat_u in {"T", "G", "AP", "R", "ALL"}:
                        if isinstance(subs, list):
                            try:
                                conditions[cat_u] = [int(x) for x in subs]
                            except (TypeError, ValueError):
                                conditions[cat_u] = []
                        else:
                            conditions[cat_u] = []
            else:
                analysis_text = str(response_text)[:800]

        return {
            "analysis": analysis_text,
            "conditions": conditions,
            "reference": ref_snippet[:600],
            "conditions_md_ref": conditions_md_snippet[:1200],
        }

    async def select_best_model(
        self,
        candidates: List[Dict],
        mission_conditions: Dict[str, List[int]],
        conditions_md_ref: str = "",
    ) -> Optional[Dict]:
        """
        LLM-driven model selection for REUSE_HISTORY mode.

        Parameters
        ----------
        candidates : list of dicts, each with keys:
            path          - absolute file path
            filename      - basename
            fitness       - float [0,1] from PE memory
            objectives    - dict {hit_rate, miss_distance, pitch_PM, ...}
            file_conds    - {cat: [subcases]} extracted from filename
            mtime_str     - human-readable modification time
        mission_conditions : {cat: [subcases]} from Planner Step 0A
        conditions_md_ref  : conditions.md snippet for physical context

        Returns
        -------
        The selected candidate dict, or None if LLM is unavailable / fails.
        """
        import json as _json
        import re as _re

        if not candidates:
            return None

        # Build a concise summary table for the LLM
        rows = []
        for i, c in enumerate(candidates):
            obj = c.get("objectives", {})
            dp  = c.get("dp_params", {})
            dp_str = "  ".join(f"{k}={v:.3g}" for k, v in dp.items()) if dp else "N/A"
            rows.append(
                f"  [{i}] {c['filename']}\n"
                f"      脚本内工况: run_flags+sub_flags={c.get('file_conds',{})}  fitness={c.get('fitness',0):.3f}\n"
                f"      仿真指标: hit={obj.get('hit_rate','-')}%  miss={obj.get('miss_distance','-')}m  "
                f"PM={obj.get('pitch_PM','-')}°\n"
                f"      关键参数: {dp_str}  mtime={c.get('mtime_str','')}"
            )
        candidates_block = "\n".join(rows)

        cond_section = (
            f"\n[conditions.md — 工况物理含义参考]\n{conditions_md_ref[:1200]}\n"
            if conditions_md_ref else
            "(conditions.md 未检索到，请基于通用工况定义分析)\n"
        )

        prompt = (
            "你是制导系统仿真专家，负责为当前任务选择最合适的历史仿真模型。\n\n"
            f"当前任务工况: {mission_conditions}\n"
            f"{cond_section}\n"
            f"候选模型列表:\n{candidates_block}\n\n"
            "选择标准（按优先级）:\n"
            "  1. 工况物理含义匹配：结合 conditions.md 判断哪个模型的训练工况与当前任务的\n"
            "     物理场景（目标机动/交战几何/气动不确定/质量推力/姿态/驾驶仪带宽）最相近\n"
            "  2. 性能指标：fitness 高、hit_rate 高、miss 小\n"
            "  3. 新鲜度：mtime 较新的模型参数更新\n\n"
            "请返回严格 JSON（不要其他文字）:\n"
            "{\n"
            "  \"selected_index\": <候选列表中的序号>,\n"
            "  \"reason\": \"选择理由：从工况物理含义角度说明为何该模型最适合当前任务\"\n"
            "}"
        )

        response_text = ""
        try:
            if hasattr(self.hermes, "run_with_tools"):
                response_text = await self.hermes.run_with_tools(
                    "System: 你是制导系统仿真专家，输出严格 JSON。\n\nUser: " + prompt,
                    tools=[],
                )
            elif hasattr(self.llm_client, "generate"):
                response_text = await self.llm_client.generate(
                    prompt=prompt,
                    system_prompt="你是制导系统仿真专家，输出严格 JSON。",
                )
            elif hasattr(self.llm_client, "run_conversation"):
                import inspect as _ins
                msg = "System: 你是制导系统仿真专家，输出严格 JSON。\n\nUser: " + prompt
                if _ins.iscoroutinefunction(self.llm_client.run_conversation):
                    response_text = await self.llm_client.run_conversation(msg)
                else:
                    response_text = self.llm_client.run_conversation(msg)
                if isinstance(response_text, dict):
                    response_text = response_text.get("final_response", "")
        except Exception as exc:
            logger.warning(f"[Planner] select_best_model LLM call failed: {exc}")
            return None

        if not response_text:
            return None

        # Parse JSON
        text = str(response_text).strip()
        for fence in ("```json", "```"):
            if text.startswith(fence):
                text = text[len(fence):]
                break
        if text.endswith("```"):
            text = text[:-3]
        m = _re.search(r"\{[\s\S]*\}", text)
        blob = m.group(0) if m else text
        blob = _re.sub(r",\s*([}\]])", r"\1", blob)
        try:
            data = _json.loads(blob)
        except Exception:
            logger.warning(f"[Planner] select_best_model JSON parse failed: {blob[:200]}")
            return None

        idx = data.get("selected_index")
        reason = data.get("reason", "")
        if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            logger.warning(f"[Planner] select_best_model invalid index {idx}")
            return None

        selected = candidates[idx]
        logger.info(
            f"[Planner] LLM selected model [{idx}] '{selected['filename']}': {reason[:200]}"
        )
        selected["llm_reason"] = reason
        return selected

    async def analyze_and_plan(self, task: str, reflection_feedback: str = "") -> TaskPlan:
        """
        使用LLM分析任务并制定执行计划

        Parameters
        ----------
        task               : 用户任务描述
        reflection_feedback: 上轮设计失败后反思智能体给出的优化建议 (空串=首轮)。
                             非空时优先级高于 expert_design_path.md；
                             首轮时 expert_design_path.md 优先级高于智能体独立分析。
        """
        if not self.llm_client and not self.hermes:
            raise RuntimeError(
                "LLM client not configured. Please provide llm_client or hermes with agent."
            )

        logger.info(f"[Planner] Analyzing task with LLM: {task[:50]}...")

        # ── Step 0A: 任务工况分析 (BEFORE mode selection) ──
        # The 工况 result is fed into the mode-selection prompt so the design
        # path is chosen with explicit awareness of which categories/subcases
        # the task requires.
        logger.info("[Planner] Step 0A: 任务工况分析 (MC_gongkuang reference)…")
        gk_result = await self.analyze_mission_conditions(task)
        mission_analysis_text = gk_result.get("analysis", "")
        mission_conditions_dict = gk_result.get("conditions", {}) or {}
        if mission_analysis_text:
            logger.info(
                f"[Planner] 工况 analysis: {mission_analysis_text[:200]}"
            )
        if mission_conditions_dict:
            logger.info(
                f"[Planner] 工况 conditions: {mission_conditions_dict}"
            )

        # Build retrieval context from RAG + ParameterExperience
        retrieval_ctx = await self.build_retrieval_context(task)
        ctx_block = f"\n\n[参考上下文]\n{retrieval_ctx}\n" if retrieval_ctx else ""

        conditions_md_ref = gk_result.get("conditions_md_ref", "")

        # 工况 analysis block — injected into the mode-selection prompt so that
        # the LLM's mode decision is conditioned on the retrieved working conditions.
        _cond_md_section = (
            f"\n  [conditions.md 检索内容]:\n{conditions_md_ref[:800]}\n"
            if conditions_md_ref else ""
        )
        if mission_analysis_text or mission_conditions_dict or conditions_md_ref:
            gk_block = (
                "\n\n[任务工况分析 — 已检索 conditions.md + MC_gongkuang_simulation_robust_all]\n"
                f"{_cond_md_section}"
                + (f"  工况分析结论: {mission_analysis_text}\n" if mission_analysis_text else "")
                + (f"  启用类别映射: {mission_conditions_dict}\n" if mission_conditions_dict else "")
                + "\n  ⚑ 请根据以上检索到的 conditions.md 工况物理含义和任务需求，\n"
                "    自行推导本轮最合适的 mode，不得套用固定'类别→mode'对照表。\n"
                "    判断依据应来自 conditions.md 中各类别的控制变量和物理效应描述。\n"
            )
        else:
            gk_block = ""

        # ── Step 0C: Load expert_design_path.md as authoritative path reference ──
        # Priority (enforced via prompt rules):
        #   Tier 1 (highest, when iteration failed): reflection_feedback > expert path
        #   Tier 2 (normal): expert path > agent's own analysis  (on divergence)
        #   Tier 3: agent's own analysis (combined with expert path)
        #
        # NOTE: Direct file read is preferred over RAG retrieval because
        # _MAX_EMBED_CHARS=6000 at index time truncates expert_design_path.md
        # (7949 chars) — RAG returns at most 6000 chars, losing F-class and
        # the summary table.  Direct read always provides the full document.
        expert_path_snippet = ""
        import pathlib as _pl
        _edp_candidates = [
            _pl.Path("knowledge_base/expert design path.md"),
            _pl.Path("../knowledge_base/expert design path.md"),
            _pl.Path(__file__).parent.parent.parent / "knowledge_base" / "expert design path.md",
            _pl.Path("knowledge_base/expert_design_path.md"),
            _pl.Path("../knowledge_base/expert_design_path.md"),
            _pl.Path(__file__).parent.parent.parent / "knowledge_base" / "expert_design_path.md",
        ]
        for _p in _edp_candidates:
            try:
                if _p.exists():
                    expert_path_snippet = _p.read_text(encoding="utf-8")
                    logger.info(
                        f"[Planner] expert_design_path.md read directly from {_p} "
                        f"({len(expert_path_snippet)} chars, full document)"
                    )
                    break
            except Exception:
                pass

        if not expert_path_snippet and self.rag_kb:
            try:
                edp_results = await self.rag_kb.retrieve(
                    query=(
                        "expert_design_path 工况路径选择建议 调参 改制导律 重用模板 "
                        "路径判断原则 A类 B类 C类 D类 E类 F类 HitRate MissMean 超标升级"
                    ),
                    top_k=5,
                )
                edp_preferred = [
                    r for r in edp_results
                    if "expert_design_path" in r.get("metadata", {}).get("filename", "").lower()
                ]
                edp_pool = edp_preferred or [
                    r for r in edp_results
                    if r.get("metadata", {}).get("source_tag") == "knowledge_base"
                ]
                if edp_pool:
                    expert_path_snippet = edp_pool[0].get("content", "")[:8000]
                    logger.info(
                        f"[Planner] expert_design_path.md fallback via RAG "
                        f"({len(expert_path_snippet)} chars, may be truncated at index)"
                    )
            except Exception as exc:
                logger.debug(f"[Planner] expert_design_path RAG retrieval failed: {exc}")

        # ── Step 0D: Load monte_mean_2.md (real simulation data, highest factual priority) ──
        # Direct file read preferred; RAG fallback for completeness.
        monte_mean_snippet = ""
        _mm2_candidates = [
            _pl.Path("knowledge_base/monte mean results.md"),
            _pl.Path("../knowledge_base/monte mean results.md"),
            _pl.Path(__file__).parent.parent.parent / "knowledge_base" / "monte mean results.md",
            _pl.Path("knowledge_base/monte_mean_2.md"),
            _pl.Path("../knowledge_base/monte_mean_2.md"),
            _pl.Path(__file__).parent.parent.parent / "knowledge_base" / "monte_mean_2.md",
        ]
        for _p in _mm2_candidates:
            try:
                if _p.exists():
                    monte_mean_snippet = _p.read_text(encoding="utf-8")
                    logger.info(
                        f"[Planner] monte_mean_2.md read directly from {_p} "
                        f"({len(monte_mean_snippet)} chars)"
                    )
                    break
            except Exception:
                pass

        if not monte_mean_snippet and self.rag_kb:
            try:
                mm2_results = await self.rag_kb.retrieve(
                    query="monte_mean_2 HitRate MissMean MissStd PeakN PM GM BW Category A B C D E F",
                    top_k=3,
                )
                mm2_preferred = [
                    r for r in mm2_results
                    if "monte_mean" in r.get("metadata", {}).get("filename", "").lower()
                ]
                mm2_pool = mm2_preferred or [
                    r for r in mm2_results
                    if r.get("metadata", {}).get("source_tag") == "knowledge_base"
                ]
                if mm2_pool:
                    monte_mean_snippet = mm2_pool[0].get("content", "")[:4000]
                    logger.info(
                        f"[Planner] monte_mean_2 fallback via RAG ({len(monte_mean_snippet)} chars)"
                    )
            except Exception as exc:
                logger.debug(f"[Planner] monte_mean_2 RAG retrieval failed: {exc}")

        # ── Build combined reference block (monte_mean_2 + expert_design_path) ──
        # Priority order enforced in the prompt:
        #   Tier 0 (override): reflection_feedback  — present only on re-plan
        #   Tier 1 (factual):  monte_mean_2          — actual simulation numbers
        #   Tier 2 (expert):   expert_design_path.md — interpretation & decision rules
        #   Tier 3 (fallback): agent's own analysis
        _mm2_section = (
            "\n[仿真数据参考 — monte_mean_2.md (实测，最高事实优先级)]\n"
            f"{monte_mean_snippet}\n"
        ) if monte_mean_snippet else ""

        _edp_section = (
            "\n[专家路径参考 — expert_design_path.md (结合仿真数据做决策)]\n"
            f"{expert_path_snippet}\n"
        ) if expert_path_snippet else ""

        if monte_mean_snippet or expert_path_snippet:
            if reflection_feedback:
                expert_path_block = (
                    f"{_mm2_section}"
                    f"{_edp_section}"
                    "\n[上轮设计失败 — 反馈优化建议 (最高优先级)]\n"
                    f"{reflection_feedback}\n\n"
                    "⚠ 优先级规则 (严格遵守):\n"
                    "  1. 本轮为上轮设计失败后的重新规划，反馈优化建议具有最高优先级。\n"
                    "  2. 首先查阅 monte_mean_2.md 中该子工况的实测指标，以数据事实为分析基础。\n"
                    "  3. 再参考 expert_design_path.md 的专家解读和路径规则，印证数据结论。\n"
                    "  4. 若反馈建议与专家路径有分歧，以反馈建议为准。\n"
                )
            else:
                expert_path_block = (
                    f"{_mm2_section}"
                    f"{_edp_section}"
                    "\n⚠ 优先级规则 (严格遵守):\n"
                    "  1. 首先查阅 monte_mean_2.md 中该子工况的实测指标（HitRate/MissMean/PeakN/PM 等），\n"
                    "     以仿真数据事实作为分析基础。\n"
                    "  2. 再用 expert_design_path.md 的专家路径规则印证结论。\n"
                    "  3. 若 monte_mean_2 数据与 expert_design_path.md 路径规则有分歧，\n"
                    "     以 expert_design_path.md 为准。\n"
                    "  4. 当你的分析与专家路径有分歧时，以专家路径为准。\n"
                )
        elif reflection_feedback:
            expert_path_block = (
                "\n\n[上轮设计失败 — 反馈优化建议 (最高优先级)]\n"
                f"{reflection_feedback}\n\n"
                "⚠ 本轮为上轮设计失败后的重新规划，请以反馈建议为主要依据确定 mode。\n"
            )
        else:
            expert_path_block = ""

        # Keyword heuristic is computed ONLY for: (a) _default_plan fallback,
        # (b) a log note if LLM chose differently.  It is NOT put in the prompt.
        heuristic_mode = _heuristic_mode(task)

        prompt = f"""分析以下制导系统任务，制定最优执行计划：

任务：{task}{ctx_block}{gk_block}{expert_path_block}

三种执行模式 (必须从中选一个)：

⚠️ **模式由任务本身需求决定，与用户提示词关键字无关**。请根据任务实际内容分析应该做什么。

【REUSE_HISTORY】—— 默认模式，当任务满足以下**任意一条**时选择：
  • 任务的核心是"仿真/验证/查看结果"，且未要求改变参数或算法
  • 现有知识库模板和历史参数已能满足任务需求
  • ParameterExperience 中已有相似场景的高质量参数记录
  • 任务未明确说明需要优化或重新设计
  执行方式：**直接调用知识库模板文件仿真，不生成新脚本**
  ⚠️ "运行工况"(run_A/sub_A) 只表示选择哪些工况，不影响模式选择。

【TUNE_PARAMS】—— 参数调优模式，当任务满足以下条件时选择：
  • 任务明确需要改善仿真性能（命中率、脱靶量、稳定裕度等）
  • 任务要求调整 **制导律参数** (N_guidance、R_switch、gama_max_deg) 或 **驾驶仪参数** (w1/ζ1/τ1/w2/w3等)
  • 任务要求运行 RL 优化 / 参数扫描
  执行方式：用模板生成新脚本，运行 PPO-RL 同时调优制导律+驾驶仪参数（11维）

【MODIFY_LAW】—— 新算法设计模式，**仅在**以下情况选择：
  • 任务要求设计/实现一种不同于现有比例导引的**新**制导算法
  • 任务要求改变制导律数学结构（如改用滑模、预测等）
  • 现有模板的算法结构无法满足任务需求
  执行方式：修改制导律算法本身，生成新 MATLAB 文件
  ⚠️ 只是调整参数值或工况开关，不属于 MODIFY_LAW。

默认偏好：**除非任务内容明确要求调参或改算法，否则选 REUSE_HISTORY**。

拆分决策原则（先读完再填 JSON）：
- **子任务 = 工具调用步骤**：拆分粒度为工具调用级别，例如 [检索, 生成脚本, 语法检测, 运行仿真]。
- **sequential**：步骤之间有前后依赖（前步输出是后步输入），如检索结果→生成脚本→检测→运行。大多数 TUNE_PARAMS / MODIFY_LAW 任务均为 sequential。
- **parallel**：步骤之间完全独立、可同时执行，如同时检索多个不相关子库。
- **single**：任务足够简单，由单个 Agent 一步完成，无需拆分。
- subagent_count 与 subtasks 数组长度相等（1-5）。

请返回 JSON（subtask_conditions 为可选，能填尽量填）：
{{
    "should_split": true/false,
    "strategy": "single/sequential/parallel",
    "subagent_count": 数字,
    "subtasks": ["子任务1描述", ...],
    "subtask_conditions": ["RUN_CASE='T';SUB_IDX=1;", ...],
    "reason": "拆分决策依据 + mode 选择依据",
    "mode": "REUSE_HISTORY/MODIFY_LAW/TUNE_PARAMS"
}}

subtask_conditions 填写规则（简单映射，照抄即可）：
- 每个元素 = "RUN_CASE='X';SUB_IDX=N;"，X∈T/G/AP/R/ALL，N=子工况编号（0=全部）
- T1→"RUN_CASE='T';SUB_IDX=1;"，T2→"...SUB_IDX=2;"，以此类推；G1→"RUN_CASE='G';SUB_IDX=1;"
- 不拆分时 subtask_conditions = [单个全局条件字符串]；长度必须等于 subtasks 数组长度

请直接返回 JSON，不要其他内容："""

        import json
        import re

        def _default_plan(reason: str = "fallback") -> TaskPlan:
            """Return a safe single-agent plan.  Always defaults to REUSE_HISTORY:
            direct KB template execution is the safest no-side-effect fallback."""
            default_mode = "REUSE_HISTORY"
            return TaskPlan(
                original_task=task,
                strategy=ExecutionStrategy.SINGLE,
                should_split=False,
                subagent_count=1,
                subtasks=[task],
                reason=reason,
                mode=default_mode,
                retrieval_context=retrieval_ctx,
                mission_analysis=mission_analysis_text,
                mission_conditions=dict(mission_conditions_dict),
            )

        def _parse_json(text: str) -> Optional[Dict]:
            """
            Try several strategies to extract a JSON object from *text*.

            1. Direct parse of the whole text (or after stripping markdown fences).
            2. Regex extraction of the first ``{...}`` block.
            3. Remove trailing commas and retry.
            Returns None if all strategies fail.
            """
            if not text or not text.strip():
                return None

            candidates = []

            # Strip markdown fences
            stripped = text.strip()
            for fence in ("```json", "```"):
                if stripped.startswith(fence):
                    stripped = stripped[len(fence):]
                    break
            if stripped.endswith("```"):
                stripped = stripped[:-3]
            candidates.append(stripped.strip())

            # Regex: first { ... } block (greedy, handles nested braces)
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                candidates.append(m.group(0))

            for candidate in candidates:
                if not candidate:
                    continue
                # Direct parse
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
                # Remove trailing commas
                try:
                    fixed = re.sub(r',\s*([}\]])', r'\1', candidate)
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

            return None

        response = ""
        try:
            if hasattr(self.hermes, "run_with_tools"):
                response = await self.hermes.run_with_tools(
                    f"System: 你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。\n\nUser: {prompt}",
                    tools=[]
                )
            elif hasattr(self.llm_client, "generate"):
                response = await self.llm_client.generate(
                    prompt=prompt,
                    system_prompt="你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。",
                )
            elif hasattr(self.llm_client, "run_conversation"):
                import inspect
                msg = f"System: 你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。\n\nUser: {prompt}"
                if inspect.iscoroutinefunction(self.llm_client.run_conversation):
                    response = await self.llm_client.run_conversation(msg)
                else:
                    response = self.llm_client.run_conversation(msg)
                if isinstance(response, dict):
                    response = response.get("final_response", str(response))
            else:
                logger.warning("[Planner] No LLM method available; using default plan.")
                return _default_plan("no LLM client")

            if not response:
                logger.warning("[Planner] LLM returned empty response; using default plan.")
                return _default_plan("empty LLM response")

            data = _parse_json(str(response))

            if data is None:
                logger.warning(
                    "[Planner] Could not extract JSON from LLM response "
                    f"(first 200 chars): {str(response)[:200]!r} — using default plan."
                )
                return _default_plan("unparseable LLM response")

            try:
                strategy = ExecutionStrategy(data.get("strategy", "single"))
            except ValueError:
                strategy = ExecutionStrategy.SINGLE

            llm_mode = data.get("mode", "REUSE_HISTORY")
            final_mode = llm_mode
            final_reason = data.get("reason", "")

            # LLM task analysis is authoritative — mode is determined by what
            # the task REQUIRES, not by user-prompt keywords.  The keyword
            # heuristic above is only a prompt hint; never override LLM here.
            if heuristic_mode and heuristic_mode != llm_mode:
                logger.info(
                    f"[Planner] LLM chose {llm_mode} (keyword hint was {heuristic_mode}). "
                    f"Trusting LLM task analysis."
                )

            _subtasks = data.get("subtasks", [task])
            _raw_st_conds = data.get("subtask_conditions") or []
            # Validate: must be a list of strings same length as subtasks
            if (
                isinstance(_raw_st_conds, list)
                and len(_raw_st_conds) == len(_subtasks)
                and all(isinstance(s, str) for s in _raw_st_conds)
            ):
                _subtask_conditions = _raw_st_conds
            else:
                _subtask_conditions = None  # caller falls back to regex
                if _raw_st_conds:
                    logger.warning(
                        f"[Planner] subtask_conditions length mismatch or wrong type "
                        f"(got {_raw_st_conds!r}), ignoring."
                    )

            return TaskPlan(
                original_task=task,
                strategy=strategy,
                should_split=data.get("should_split", False),
                subagent_count=data.get("subagent_count", 1),
                subtasks=_subtasks,
                reason=final_reason,
                mode=final_mode,
                retrieval_context=retrieval_ctx,
                mission_analysis=mission_analysis_text,
                mission_conditions=dict(mission_conditions_dict),
                conditions_md_ref=conditions_md_ref,
                subtask_conditions=_subtask_conditions,
            )

        except Exception as exc:
            logger.error(f"[Planner] LLM planning error: {exc}")
            return _default_plan(f"exception: {exc}")

    async def execute(self, task: str) -> Dict[str, Any]:
        """
        智能执行任务：规划 -> 决策 -> 执行
        """
        plan = await self.analyze_and_plan(task)
        logger.info(
            f"[Planner] Plan: {plan.strategy.value}, split={plan.should_split}, count={plan.subagent_count}"
        )

        if not plan.should_split or plan.subagent_count == 1:
            return await self._execute_single(task, plan)

        elif plan.strategy == ExecutionStrategy.PARALLEL:
            return await self._execute_parallel(task, plan)

        else:
            return await self._execute_sequential(task, plan)

    async def _execute_single(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """单Agent执行"""
        if not self.hermes:
            return {
                "status": "completed",
                "strategy": "single",
                "result": f"任务已完成: {task[:50]}...",
                "subagent_count": 1,
            }

        result = await self.hermes.run_with_tools(task, tools=[])
        return {
            "status": "completed",
            "strategy": "single",
            "result": result,
            "subagent_count": 1,
            "plan_reason": plan.reason,
        }

    async def _execute_parallel(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """并行执行多个子任务"""
        from .subagent import SubagentManager, SubagentConfig

        manager = SubagentManager(self.hermes)

        results = await manager.delegate_parallel(
            tasks=plan.subtasks,
            configs=[
                SubagentConfig(name=f"parallel_{i}", max_iterations=30)
                for i in range(len(plan.subtasks))
            ],
        )

        aggregated = await manager.aggregate_results(results, strategy="all")

        return {
            "status": "completed",
            "strategy": "parallel",
            "original_task": task,
            "subtasks": plan.subtasks,
            "results": [r.result for r in results if r.status == "completed"],
            "aggregated_result": aggregated,
            "subagent_count": len(plan.subtasks),
            "plan_reason": plan.reason,
        }

    async def _execute_sequential(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """顺序执行多个子任务"""
        from .subagent import SubagentManager, SubagentConfig

        manager = SubagentManager(self.hermes)
        all_results = []

        for i, subtask in enumerate(plan.subtasks):
            logger.info(f"[Planner] Sequential step {i + 1}/{len(plan.subtasks)}")
            result = await manager.delegate(
                task=subtask,
                config=SubagentConfig(name=f"seq_{i}", max_iterations=30),
            )
            all_results.append(result)

        return {
            "status": "completed",
            "strategy": "sequential",
            "original_task": task,
            "subtasks": plan.subtasks,
            "results": [r.result for r in all_results if r.status == "completed"],
            "subagent_count": len(plan.subtasks),
            "plan_reason": plan.reason,
        }


async def smart_execute(
    task: str,
    hermes: Any = None,
    llm_client: Any = None,
) -> Dict[str, Any]:
    """
    智能任务执行

    使用LLM自动决策：
    - 任务复杂度分析
    - 是否需要拆分
    - 执行策略选择
    - 子Agent调度
    """
    planner = IntelligentTaskPlanner(hermes=hermes, llm_client=llm_client)
    return await planner.execute(task)
