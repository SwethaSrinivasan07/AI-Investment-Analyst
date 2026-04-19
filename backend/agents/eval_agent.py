"""
Eval Agent — LLM-as-judge that scores every memo on 5 quality dimensions.

Runs asynchronously after memo generation (non-blocking via asyncio.create_task).
A failing eval never affects the user-facing pipeline.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Structured quality scores for a generated memo."""

    memo_id: str
    data_grounding: float       # 1-5: are claims backed by data?
    thesis_clarity: float       # 1-5: is thesis specific and falsifiable?
    risk_depth: float           # 1-5: are risks quantified?
    valuation_rigor: float      # 1-5: is valuation methodology sound?
    actionability: float        # 1-5: can investor make a decision?
    overall: float              # arithmetic average of the 5 dimensions
    rationale: dict = field(default_factory=dict)  # {dimension: one-sentence explanation}


class EvalAgent:
    """
    Scores investment memos on 5 analytical quality dimensions using Claude
    as an LLM-as-judge.
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        # Haiku is 10x cheaper than Sonnet and perfectly capable for structured JSON scoring.
        self.model = "claude-haiku-4-5"
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = (
            Path(__file__).parent.parent / "prompts" / "system" / "eval_agent.txt"
        )
        try:
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.error(f"Eval agent system prompt not found at {prompt_path}")
            raise

    async def evaluate(self, memo_id: str, memo_text: str) -> EvalResult:
        """
        Score a memo on 5 quality dimensions.

        Returns a structured EvalResult. On any failure, returns a default
        3.0 score across all dimensions so the pipeline is never blocked.
        """
        # Truncate memo to avoid excessive input tokens
        truncated = memo_text[:6000]
        if len(memo_text) > 6000:
            truncated += "\n... [memo truncated for evaluation]"

        user_msg = (
            f"Evaluate this investment memo:\n\n"
            f"---\n{truncated}\n---\n\n"
            "Return ONLY a JSON object with this exact structure:\n"
            "{\n"
            '  "data_grounding": <1-5 float>,\n'
            '  "thesis_clarity": <1-5 float>,\n'
            '  "risk_depth": <1-5 float>,\n'
            '  "valuation_rigor": <1-5 float>,\n'
            '  "actionability": <1-5 float>,\n'
            '  "rationale": {\n'
            '    "data_grounding": "<one sentence>",\n'
            '    "thesis_clarity": "<one sentence>",\n'
            '    "risk_depth": "<one sentence>",\n'
            '    "valuation_rigor": "<one sentence>",\n'
            '    "actionability": "<one sentence>"\n'
            "  }\n"
            "}"
        )

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )

            text = response.content[0].text.strip()

            # Strip markdown code fences if Claude wraps the JSON
            if text.startswith("```"):
                parts = text.split("```")
                # parts[1] is the fenced content
                fenced = parts[1] if len(parts) > 1 else text
                if fenced.startswith("json"):
                    fenced = fenced[4:]
                text = fenced.strip()

            scores = json.loads(text)

            # Validate and clamp each score to [1, 5]
            def clamp(val: Optional[float]) -> float:
                try:
                    return max(1.0, min(5.0, float(val)))
                except (TypeError, ValueError):
                    return 3.0

            data_grounding = clamp(scores.get("data_grounding"))
            thesis_clarity = clamp(scores.get("thesis_clarity"))
            risk_depth = clamp(scores.get("risk_depth"))
            valuation_rigor = clamp(scores.get("valuation_rigor"))
            actionability = clamp(scores.get("actionability"))
            overall = round(
                (data_grounding + thesis_clarity + risk_depth + valuation_rigor + actionability) / 5,
                2,
            )
            rationale = scores.get("rationale", {})

            logger.info(
                f"EvalAgent scored memo {memo_id}: overall={overall} "
                f"(dg={data_grounding}, tc={thesis_clarity}, rd={risk_depth}, "
                f"vr={valuation_rigor}, ac={actionability})"
            )

            return EvalResult(
                memo_id=memo_id,
                data_grounding=data_grounding,
                thesis_clarity=thesis_clarity,
                risk_depth=risk_depth,
                valuation_rigor=valuation_rigor,
                actionability=actionability,
                overall=overall,
                rationale=rationale,
            )

        except Exception as e:
            logger.error(f"EvalAgent failed for memo {memo_id}: {e}", exc_info=True)
            # Return neutral defaults — never block the pipeline
            return EvalResult(
                memo_id=memo_id,
                data_grounding=3.0,
                thesis_clarity=3.0,
                risk_depth=3.0,
                valuation_rigor=3.0,
                actionability=3.0,
                overall=3.0,
                rationale={},
            )
