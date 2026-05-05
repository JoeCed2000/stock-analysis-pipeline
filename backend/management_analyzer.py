"""Management tone analyzer — NLP sentiment on MD&A and risk factor text."""
import re
import json
import os
from typing import Dict, List, Optional


def load_tone_config() -> Dict:
    """Load tone analysis configuration from tone_config.json, falling back to defaults."""
    config_path = os.path.join(os.path.dirname(__file__), "tone_config.json")
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict) or "signals" not in cfg:
            raise ValueError("Invalid config structure")
        return cfg
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load tone_config.json: {e}, using defaults")
        return None


def _get_signals(config: Dict, category: str, defaults: List[str]) -> List[str]:
    """Get signal patterns from config or fallback to defaults."""
    if config and "signals" in config and category in config["signals"]:
        return config["signals"][category]
    return defaults


def analyze_management_tone(mda_text: str, risk_text: str) -> Dict:
    """
    Analyze management discourse from MD&A and Risk Factors text.
    Returns a structured tone analysis.
    """
    if not mda_text or len(mda_text) < 200:
        return {
            "tone": "DATA NOT AVAILABLE",
            "confidence": "DATA NOT AVAILABLE",
            "visibility": "DATA NOT AVAILABLE",
            "concrete_promises": [],
            "defensive_signals": [],
            "key_themes": [],
        }

    # Load config (with fallback to hardcoded defaults)
    cfg = load_tone_config()

    # Count sentiment signals
    positive = _count_matches(mda_text, _get_signals(cfg, "positive", POSITIVE_SIGNALS))
    negative = _count_matches(mda_text, _get_signals(cfg, "negative", NEGATIVE_SIGNALS))
    defensive = _count_matches(mda_text, _get_signals(cfg, "defensive", DEFENSIVE_SIGNALS))
    confident = _count_matches(mda_text, _get_signals(cfg, "confidence", CONFIDENCE_SIGNALS))
    hedging = _count_matches(mda_text, _get_signals(cfg, "hedging", HEDGING_SIGNALS))

    # Extract promises and themes
    promises = _extract_promises(mda_text)
    themes = _extract_themes(mda_text)

    # Determine tone
    if positive > negative * 2 and confident > hedging:
        tone = "Confident / Optimistic"
    elif positive > negative and confident >= hedging:
        tone = "Cautiously Optimistic"
    elif negative > positive:
        tone = "Defensive / Cautious"
    else:
        tone = "Neutral / Measured"

    # Confidence level
    if confident > hedging * 2:
        confidence_level = "High — confident management, minimal hedging"
    elif confident > hedging:
        confidence_level = "Moderate — statements tempered with caveats"
    else:
        confidence_level = "Low — cautious tone, heavy hedging"

    # Visibility
    if confident > 3 and defensive < 3:
        visibility = "Good — clearly stated outlook"
    elif confident > 1:
        visibility = "Limited — mixed signals"
    else:
        visibility = "Low — lacks clear guidance"

    return {
        "tone": tone,
        "confidence": confidence_level,
        "visibility": visibility,
        "concrete_promises": promises[:5],
        "defensive_signals": defensive_signals_found(mda_text, risk_text),
        "key_themes": themes[:5],
        "stats": {
            "positive_signals": positive,
            "negative_signals": negative,
            "defensive_signals": defensive,
            "confidence_markers": confident,
            "hedging_markers": hedging,
        }
    }


def extract_risks_from_10k(risk_text: str) -> List[Dict]:
    """Extract risk factors from 10-K Risk Factors section text."""
    if not risk_text or len(risk_text) < 200:
        return []

    risks = []
    risk_keywords = [
        ("Competition", ["competit", "competitor", "competitive pressure"]),
        ("Supply Chain", ["supply chain", "supplier", "manufacturing", "foundry"]),
        ("Customer Concentration", ["concentrat", "large customer", "key customer", "depend"]),
        ("Regulation", ["regulat", "compliance", "government", "legislation", "export control"]),
        ("Geopolitical", ["geopolit", "china", "trade restriction", "sanction", "tariff"]),
        ("Technology", ["technolog", "rapid change", "disruption", "innovation"]),
        ("Cybersecurity", ["cyber", "security breach", "data", "hack"]),
        ("Intellectual Property", ["intellectual property", "patent", "proprietary"]),
        ("Currency/FX", ["foreign exchange", "currency", "fx", "exchange rate"]),
        ("Litigation", ["litigation", "lawsuit", "legal", "proceeding"]),
    ]

    for category, keywords in risk_keywords:
        for kw in keywords:
            if kw in risk_text.lower():
                # Extract the sentence containing the keyword
                sentences = re.split(r'(?<=[.!?])\s+', risk_text)
                matching = [s for s in sentences if kw in s.lower()]
                description = matching[0][:200].strip() if matching else f"Risk related to {category.lower()}"
                severity = _assess_severity(description, category)
                risks.append({
                    "category": category,
                    "description": description,
                    "severity": severity,
                    "source": "SEC 10-K Risk Factors"
                })
                break

    return risks


# ── Sentiment lexicons ──

POSITIVE_SIGNALS = [
    r'\bgrow(?:th|ing)\b', r'\bstrong\b', r'\brecord\b', r'\bincreas\w+\b',
    r'\bexpand\w*\b', r'\bopportunit\w+\b', r'\bmomentum\b', r'\bleader\w*\b',
    r'\baccelerat\w*\b', r'\bdemand\b', r'\boutperform\w*\b', r'\bexceed\w*\b',
    r'\bconfiden\w*\b', r'\boptimis\w*\b', r'\bpositive\b', r'\bimproving\b',
    r'\bfavorab\w+\b', r'\bbest-in-class\b', r'\binnovation\b', r'\binvest(?:ing|ment)\b',
]

NEGATIVE_SIGNALS = [
    r'\bdeclin\w*\b', r'\bdecreas\w+\b', r'\bchalleng\w*\b', r'\bheadwind\b',
    r'\buncertain\w*\b', r'\bvolatil\w*\b', r'\bweak\b', r'\bpressur\w*\b',
    r'\brisk\b', r'\bslowdown\b', r'\bimpair\w*\b', r'\bloss\w*\b',
    r'\bdelay\w*\b', r'\bdisrupt\w*\b', r'\badverse\b', r'\bnegativ\w+\b',
]

DEFENSIVE_SIGNALS = [
    r'\bcould\b', r'\bmay\b', r'\bmight\b', r'\bpotential\w*\b',
    r'\bpossib\w+\b', r'\bhowever\b', r'\balthough\b', r'\bwhile\b',
    r'\bsubject to\b', r'\bdepend\w*\b', r'\bfluctuat\w*\b',
    r'\bif\b', r'\bno assurance\b', r'\bcannot guarantee\b',
    r'\bunpredictab\w+\b', r'\bunlikely\b',
]

CONFIDENCE_SIGNALS = [
    r'\bexpect\w*\b', r'\banticipat\w*\b', r'\bbelieve\w*\b', r'\bconfiden\w*\b',
    r'\bwill\b', r'\bcommit\w*\b', r'\bguidance\b', r'\boutlook\b',
    r'\btarget\b', r'\bgoal\b', r'\bplan\b', r'\bstrateg\w+\b',
    r'\bposition\w*\b', r'\bdemonstrat\w*\b', r'\btrack record\b',
    r'\bwell positioned\b', r'\bwell-positioned\b',
]

HEDGING_SIGNALS = [
    r'\bmay\b', r'\bmight\b', r'\bcould\b', r'\bwould\b',
    r'\bpossible\b', r'\bpotential\w*\b', r'\bif\b', r'\bassum\w+\b',
    r'\bestimat\w*\b', r'\bapproximat\w+\b', r'\bsubject to\b',
    r'\bno assurance\b', r'\bcannot\b', r'\buncertain\b',
    r'\bunknown\b', r'\bunclear\b', r'\bdepend\b',
]


def _count_matches(text: str, patterns: List[str]) -> int:
    """Count how many unique patterns match in text."""
    count = 0
    t = text.lower()
    for pat in patterns:
        if re.search(pat, t, re.IGNORECASE):
            count += 1
    return count


def _extract_promises(text: str) -> List[str]:
    """Extract concrete promises/commitments from text."""
    promise_patterns = [
        (r'(?:expect\w*\s+to|plan\w*\s+to|will)\s+([^.]{20,120}\.)', "Engagement"),
        (r'(?:target\w*\s+(?:of\s+)?|goal\s+(?:of\s+)?)([^.]{20,120}\.)', "Objectif"),
        (r'(?:committed\s+to|commit\w*\s+to)\s+([^.]{20,120}\.)', "Engagement"),
        (r'(?:guidance\s+(?:of|for|is)\s+)([^.]{20,120}\.)', "Guidance"),
    ]

    promises = []
    for pattern, ptype in promise_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            txt = match.group(1).strip()
            if len(txt) > 20:
                promises.append(f"[{ptype}] {txt[:150]}")

    return promises[:8]


def _extract_themes(text: str) -> List[str]:
    """Extract key business themes."""
    theme_patterns = [
        (r'AI\b|artificial intelligence', "Artificial Intelligence"),
        (r'data center', "Data Center"),
        (r'cloud\b', "Cloud Computing"),
        (r'autonom\w+\s+(?:vehicle|driving)', "Autonomous Vehicles"),
        (r'gaming\b', "Gaming"),
        (r'generative\s+AI', "Generative AI"),
        (r'\bLLM\b|large language model', "LLMs"),
        (r'robotics?\b', "Robotics"),
        (r'digital twin', "Digital Twins"),
        (r'omniverse\b', "Omniverse"),
        (r'healthcare\b|medical', "Healthcare"),
        (r'enterprise\b', "Enterprise"),
        (r'software\b', "Software"),
        (r'subscription\b', "Subscription Model"),
    ]

    found = set()
    themes = []
    for pattern, label in theme_patterns:
        if re.search(pattern, text, re.IGNORECASE) and label not in found:
            found.add(label)
            themes.append(label)

    return themes


def defensive_signals_found(mda_text: str, risk_text: str) -> List[str]:
    """Identify specific defensive signals."""
    signals = []
    combined = (mda_text + " " + risk_text).lower()

    checks = [
        ("macroeconomic", "Macroeconomic references — defensive"),
        ("inflation", "Inflation mentioned as risk"),
        ("recession", "Recession mentioned"),
        ("supply chain constraint", "Supply chain constraints"),
        ("export control", "Export controls"),
        ("trade restriction", "Trade restrictions"),
        ("foreign exchange", "FX risk"),
        ("customer concentration", "Customer concentration"),
        ("regulatory", "Regulatory risks"),
        ("litigation", "Ongoing litigation"),
        ("goodwill impairment", "Impairment risk"),
        ("seasonal", "Seasonality"),
    ]

    for keyword, label in checks:
        if keyword in combined:
            signals.append(label)

    return signals[:6]


def _assess_severity(description: str, category: str) -> str:
    """Assess risk severity based on language in description."""
    d = description.lower()
    critical_words = ["material", "significant", "substantial", "critical", "could materially"]
    moderate_words = ["may", "could", "potential", "might", "possible"]

    if any(w in d for w in critical_words):
        return "high"
    if category in ("Geopolitical", "Regulation", "Supply Chain"):
        return "medium"
    if any(w in d for w in moderate_words):
        return "medium"
    return "low"
