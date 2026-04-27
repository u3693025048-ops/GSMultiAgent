import asyncio
import json
import logging
from typing import Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from multi_agent.config_loader import get_config

logger = logging.getLogger(__name__)


def extract_reasoning_content(response_msg: Any) -> Optional[str]:
    """
    Extract chain-of-thought / reasoning content from a LangChain response.

    Different providers return reasoning in different fields:
      • DeepSeek-R1                 → ``additional_kwargs.reasoning_content``
      • OpenRouter (Claude/DS-R1)   → ``additional_kwargs.reasoning``
      • OpenAI o1/o3                → embedded in ``response_metadata``
      • Anthropic w/ thinking       → ``additional_kwargs.thinking`` blocks

    Returns the reasoning string if found, else None.
    """
    if response_msg is None:
        return None

    addl = getattr(response_msg, "additional_kwargs", {}) or {}
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = addl.get(key)
        if val:
            if isinstance(val, list):
                # Anthropic thinking blocks: [{"type":"thinking","thinking":"..."}]
                parts = [b.get("thinking", "") if isinstance(b, dict) else str(b) for b in val]
                joined = "\n".join(p for p in parts if p)
                if joined:
                    return joined
            elif isinstance(val, str) and val.strip():
                return val

    meta = getattr(response_msg, "response_metadata", {}) or {}
    for key in ("reasoning_content", "reasoning"):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val

    # Some providers stash it under model_extra / extra
    for nest_key in ("model_extra", "extra", "raw"):
        nested = meta.get(nest_key)
        if isinstance(nested, dict):
            for key in ("reasoning_content", "reasoning"):
                val = nested.get(key)
                if isinstance(val, str) and val.strip():
                    return val

    return None


class ReflectionOutput(BaseModel):
    needs_optimization: bool = Field(description="是否需要进一步优化参数")
    suggestion: str = Field(description="给出的优化建议，如果不需要优化可以为空")

class ReflectionAgent:
    """
    结果反思智能体，基于 LangChain 实现。
    用于判别仿真结果，并给出优化建议。
    """
    
    def __init__(self):
        cfg = get_config().llm
        # Enable reasoning capture for providers that need an explicit flag.
        # OpenRouter requires `include_reasoning: true`; OpenAI/Anthropic ignore unknown keys.
        # DeepSeek returns reasoning by default; passing it is harmless.
        extra_body = {"include_reasoning": True}
        self.llm = ChatOpenAI(
            model=cfg.model,
            openai_api_key=cfg.api_key or "sk-dummy",
            openai_api_base=cfg.base_url,
            temperature=0.2,
            extra_body=extra_body,
        )
        self.parser = JsonOutputParser(pydantic_object=ReflectionOutput)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个制导系统仿真结果反思与判别专家。请根据用户任务描述中的具体要求，逐项对照以下指标判断是否全部满足。

【仿真结果字段说明】
输入 JSON 中 "metrics" 字段包含当前轮仿真指标：
  hit_rate          : 命中率 (%)，通常要求 ≥ 90% 或 100%
  miss_distance     : 脱靶量 (m)，越小越好；典型要求 ≤ 5m / ≤ 2m / ≤ 1m
  control_energy    : 控制能量 (J 或归一化)，越小越好
  pitch_PM          : 俯仰通道相位裕度 (°)，通常要求 ≥ 30°（优秀 ≥ 45°）
  pitch_GM          : 俯仰通道增益裕度 (dB)，通常要求 ≥ 6dB（优秀 ≥ 12dB）
  pitch_BW          : 俯仰通道带宽 (rad/s)，通常要求 10~40 rad/s
  yaw_PM / yaw_GM   : 偏航通道相位/增益裕度，要求同俯仰
  alpha_max_deg     : 最大攻角 (°)，通常要求 ≤ 20°
  beta_max_deg      : 最大侧滑角 (°)，通常要求 ≤ 10°
  delta_max_deg     : 最大舵偏 (°)
  delta_sat_ratio   : 舵面饱和比例，越低越好（≤ 0.1 为优秀）
  term_angle_err    : 末端落角误差 (°)，越小越好
  peak_n            : 峰值法向过载 (g)，典型要求 ≤ 15g 或 ≤ 20g；
                      **若值为 0.0 表示本次仿真无法输出该指标（Python fallback），
                      此时视为"数据不可用"，不应因此阻塞退出。**
  best_miss_ever    : 全历史最低脱靶量 (m)，跨所有 RL episode 的参考值
  best_peak_n_ever  : 全历史最低峰值过载 (g)；若为 inf 表示从未获取到有效数据
  best_reward_metrics: 综合奖励最高 episode 的各项指标（供对比参考）

【判断原则】
1. 以任务描述中明确提出的要求为准，未提及的指标可宽松判断。
2. 对照每项要求判断是否满足，全部满足才返回 needs_optimization=false。
3. suggestion 中需逐项说明哪些指标已达标、哪些未达标及建议调整方向。
4. **peak_n=0.0 且 best_peak_n_ever=inf 时**，表示本次及历史均无法获取过载数据。
   此时若任务要求 PeakN 约束，在 suggestion 中注明"过载数据不可用，无法验证"，
   但**不得仅因此一项缺失就将 needs_optimization 设为 true**（其他指标全部达标时可退出）。

请只返回以下 JSON 格式，不要包含任何其他说明文字：
{format_instructions}
"""),
            ("user", """
当前的提示词/任务描述：
{prompt}

本轮仿真结果：
{best_result}

请进行反思与判别。
""")
        ])
        
        self.chain = self.prompt | self.llm
        
    async def reflect(self, current_prompt: str, best_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        对仿真结果进行反思，返回判别结果 JSON 结构。
        """
        try:
            logger.info("正在调用 Reflection Agent 进行结果反思...")
            response_msg = await self.chain.ainvoke({
                "prompt": current_prompt,
                "best_result": json.dumps(best_result, ensure_ascii=False, indent=2),
                "format_instructions": self.parser.get_format_instructions()
            })

            # Surface reasoning content (chain-of-thought) for reasoning models
            # such as Claude-thinking, DeepSeek-R1, OpenAI o1/o3.
            reasoning = extract_reasoning_content(response_msg)
            if reasoning:
                # Limit log to avoid flooding; full reasoning still printed at INFO
                preview = reasoning[:1500] + ("…" if len(reasoning) > 1500 else "")
                logger.info(f"[Reasoning] (model chain-of-thought, {len(reasoning)} chars):\n{preview}")
            else:
                logger.debug(
                    "[Reasoning] No chain-of-thought found in response. "
                    "additional_kwargs keys: %s, response_metadata keys: %s",
                    list(getattr(response_msg, 'additional_kwargs', {}) or {}),
                    list(getattr(response_msg, 'response_metadata', {}) or {}),
                )

            content = response_msg.content

            # Remove <think>...</think> blocks often generated by reasoning models
            # (some return them inline in `content` instead of as a separate field)
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            try:
                parsed_response = json.loads(content)
                return parsed_response
            except json.JSONDecodeError:
                # Fallback if json parsing fails but string looks somewhat like dict
                logger.warning(f"Failed to parse JSON natively, trying Langchain Parser. Raw: {content}")
                return self.parser.parse(response_msg.content)
                
        except KeyboardInterrupt:
            raise  # always let the user interrupt
        except (Exception, asyncio.CancelledError) as e:
            logger.error(f"Reflection Agent 运行出错: {e}")
            # 如果出错，默认不需要进一步优化，避免死循环
            return {"needs_optimization": False, "suggestion": f"反思阶段出错: {e}"}
