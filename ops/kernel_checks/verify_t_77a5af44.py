#!/usr/bin/env python3
"""Kernel proof for t_77a5af44 — NVDA revenue estimate source policy."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "feedback-audits" / "revenue-source-policy.md"
PLAN = Path("/mnt/c/Users/cedon/Desktop/SA/PLAN_conseil_kanban_NVDA_feedback_2026-06-16.md")
REVIEW = Path("/mnt/c/Users/cedon/Desktop/SA/REVUE_ecarts_NVDA_deepdive_2026-06-16.md")
SCREENSHOT = Path("/mnt/c/Users/cedon/Desktop/SA/2026-06-11_061719_Screenshot_2026-06-10_at_10.48.22_PM.png")
CONFIG = ROOT / "backend" / "config" / "consensus_overrides.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(DOC.exists(), f"missing policy doc: {DOC}")
    doc = DOC.read_text(encoding="utf-8")

    required_doc_markers = [
        "Investing.com `79.19B` is allowed",
        "explicitly cited analyst-consensus estimate override",
        "not allowed as",
        "Fallback order",
        "Source: Investing.com analyst consensus, as of 2026-05-20.",
        "This card is spec-only",
        "does not implement, modify, regenerate, or deploy any report",
        "Serena tool access is degraded",
        "codegraph status",
        "_extract_quarterly_comparison",
        "_deep_dive_metrics",
    ]
    for marker in required_doc_markers:
        require(marker in doc, f"doc missing marker: {marker}")

    for source_path in (PLAN, REVIEW, SCREENSHOT):
        require(source_path.exists(), f"missing source evidence: {source_path}")
        require(source_path.stat().st_size > 0, f"empty source evidence: {source_path}")

    plan_text = PLAN.read_text(encoding="utf-8", errors="replace")
    review_text = REVIEW.read_text(encoding="utf-8", errors="replace")
    for text_name, text in (("plan", plan_text), ("review", review_text)):
        require("79.19B" in text, f"{text_name} missing 79.19B evidence")
        require("3.04" in text, f"{text_name} missing 3.04% evidence")
        require("Investing.com" in text, f"{text_name} missing Investing.com evidence")

    # Non-mutating consistency check: the already-present override registry, if used by
    # later implementation cards, must match the policy's approved value/label.
    require(CONFIG.exists(), f"missing consensus override config: {CONFIG}")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    nvda = cfg.get("NVDA", {}).get("FY2027 Q1", {})
    require(nvda.get("revenue_estimate") == 79_190_000_000, "NVDA FY2027 Q1 revenue_estimate mismatch")
    require(nvda.get("eps_estimate") == 1.77, "NVDA FY2027 Q1 eps_estimate mismatch")
    require("Investing.com" in (nvda.get("source") or ""), "override source is not Investing.com")
    require(nvda.get("as_of") == "2026-05-20", "override as_of mismatch")

    print("READY t_77a5af44 revenue source policy verified")


if __name__ == "__main__":
    main()
