"""
Claude AI Prospectus Analysis Service

On-demand analysis of SEC filings using the Anthropic Claude API.
Supports multiple analysis types: summary, competitive intel, change detection, risk review.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_INPUT_TOKENS = 25000  # Truncate filing text beyond this (rough char estimate)

ANALYSIS_TYPES = {
    "summary": {
        "label": "Summary",
        "description": "High-level summary of the prospectus filing",
        "prompt": (
            "You are an SEC filing analyst. Analyze this prospectus filing and provide:\n"
            "1. **Overview**: What type of fund(s) are described and their investment objectives\n"
            "2. **Key Terms**: Fee structure, expense ratios, minimum investments\n"
            "3. **Strategy**: Investment strategy and principal risks\n"
            "4. **Timeline**: Any effective dates, amendment dates, or status changes\n"
            "5. **Notable Items**: Anything unusual or noteworthy\n\n"
            "Be concise and use bullet points. Focus on facts from the filing."
        ),
    },
    "competitive": {
        "label": "Competitive Intel",
        "description": "Compare against the competitive ETP landscape",
        "prompt": (
            "You are a competitive intelligence analyst for an ETP (Exchange-Traded Product) company. "
            "Analyze this prospectus filing and extract:\n"
            "1. **Product Positioning**: What market segment does this fund target?\n"
            "2. **Fee Comparison**: How do the fees compare to typical ETFs in this category?\n"
            "3. **Differentiation**: What makes this fund unique vs existing products?\n"
            "4. **Market Implications**: What does this filing signal about market trends?\n"
            "5. **Competitive Threat Level**: Low/Medium/High and why\n\n"
            "Be specific and actionable. This analysis will be read by product development leadership."
        ),
    },
    "changes": {
        "label": "Change Detection",
        "description": "Identify what changed in this amendment",
        "prompt": (
            "You are a legal analyst reviewing an SEC filing amendment. Identify:\n"
            "1. **Type of Change**: Is this a new filing, amendment, or supplement?\n"
            "2. **Key Changes**: What specific changes were made (fees, strategy, names, etc.)?\n"
            "3. **Effective Date**: When do changes take effect?\n"
            "4. **Regulatory Status**: Any delaying amendments or conditions?\n"
            "5. **Impact Assessment**: What's the practical impact of these changes?\n\n"
            "Focus on what changed, not general fund description."
        ),
    },
    "risk": {
        "label": "Risk Review",
        "description": "Analyze risk factors and regulatory concerns",
        "prompt": (
            "You are a risk analyst reviewing an SEC prospectus filing. Analyze:\n"
            "1. **Principal Risks**: List and categorize the main risk factors\n"
            "2. **Leverage/Derivatives**: Any use of leverage, derivatives, or complex instruments?\n"
            "3. **Regulatory Risks**: Any regulatory concerns or compliance issues noted?\n"
            "4. **Liquidity Risks**: Any liquidity concerns or redemption restrictions?\n"
            "5. **Risk Rating**: Overall risk level (Conservative/Moderate/Aggressive/Speculative)\n\n"
            "Be thorough but concise."
        ),
    },
}


def _load_api_key() -> str:
    """Load Anthropic API key from .env or environment."""
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("ANTHROPIC_API_KEY", "")


def is_configured() -> bool:
    """Check if Claude API key is available."""
    key = _load_api_key()
    return bool(key and key.startswith("sk-ant-"))


def analyze_filing(
    filing_text: str,
    analysis_type: str,
    fund_name: str = "",
    trust_name: str = "",
) -> dict[str, Any]:
    """Analyze a filing using Claude API.

    Args:
        filing_text: The raw text content of the filing
        analysis_type: One of: summary, competitive, changes, risk
        fund_name: Optional fund name for context
        trust_name: Optional trust name for context

    Returns:
        Dict with: result_text, model_used, input_tokens, output_tokens, analysis_type
    """
    api_key = _load_api_key()
    if not api_key:
        return {"error": "Anthropic API key not configured"}

    if analysis_type not in ANALYSIS_TYPES:
        return {"error": f"Unknown analysis type: {analysis_type}"}

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed. Run: pip install anthropic"}

    type_config = ANALYSIS_TYPES[analysis_type]

    # Build context prefix
    context = ""
    if trust_name:
        context += f"Trust: {trust_name}\n"
    if fund_name:
        context += f"Fund: {fund_name}\n"

    # Truncate filing text if too long
    if len(filing_text) > MAX_INPUT_TOKENS * 4:
        filing_text = filing_text[: MAX_INPUT_TOKENS * 4] + "\n\n[... truncated for length ...]"

    user_message = f"{context}\n--- FILING TEXT ---\n{filing_text}"

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=type_config["prompt"],
            messages=[{"role": "user", "content": user_message}],
        )

        result_text = response.content[0].text if response.content else ""

        return {
            "result_text": result_text,
            "model_used": MODEL,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "analysis_type": analysis_type,
        }

    except anthropic.APIError as e:
        log.error("Claude API error: %s", e)
        return {"error": f"Claude API error: {e}"}


def estimate_cost(text_length: int) -> dict[str, float]:
    """Estimate the cost of analyzing a filing.

    Returns dict with input_tokens_est, output_tokens_est, cost_est_usd.
    """
    # Rough estimate: 1 token ~= 4 characters
    input_tokens = min(text_length // 4, MAX_INPUT_TOKENS) + 500  # prompt overhead
    output_tokens = 4000  # max output

    # Sonnet pricing (as of 2025): $3/M input, $15/M output
    cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

    return {
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
        "cost_est_usd": round(cost, 4),
    }
