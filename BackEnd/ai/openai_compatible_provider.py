from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openai import OpenAI


ALLOWED_ECSS_REQUIREMENT_CATEGORIES = [
    "functional",
    "mission",
    "interface",
    "environmental",
    "operational",
    "human factor",
    "physical",
    "product assurance",
    "configuration",
    "design",
    "verification",
]

ALLOWED_REQUIREMENT_STATUSES = [
    "extracted",
    "under_specified",
    "requires_review",
]

ECSS_FORBIDDEN_OR_WEAK_TERMS = [
    "and/or",
    "etc.",
    "goal",
    "shall be included but not limited to",
    "relevant",
    "necessary",
    "appropriate",
    "as far as possible",
    "optimize",
    "minimize",
    "maximize",
    "typical",
    "rapid",
    "user-friendly",
    "easy",
    "sufficient",
    "enough",
    "suitable",
    "satisfactory",
    "adequate",
    "quick",
    "first rate",
    "best possible",
    "great",
    "small",
    "large",
    "state of the art",
    "high-rate",
    "high resolution",
    "high-resolution",
    "high-stability",
    "comprehensive",
    "efficient",
    "best possible",
]


class OpenAICompatibleProvider:
    """
    STAR provider for OpenAI-compatible local or remote LLM endpoints.

    For Ollama, use:
        base_url = "http://localhost:11434/v1"
        api_key = "local"
        model = "qwen2.5:7b"

    This version uses ECSS-E-ST-10-06C-inspired requirement extraction rules.
    The PDF itself is not sent to the model at runtime; STAR sends a compact
    operational checklist derived from the standard.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        timeout_s: int = 300,
        max_output_tokens: int = 2200,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_output_tokens = max_output_tokens

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout_s,
        )

    def extract_requirements(self, document_text: str) -> list[dict[str, Any]]:
        system_prompt = (
            "You are STAR's ECSS-based requirement extraction assistant for preliminary "
            "space mission studies. Be selective: identify technical needs before rewriting. Return only valid JSON. Do not include markdown "
            "fences, explanations, chain-of-thought, comments, or text outside JSON."
        )

        ecss_rules = self._load_ecss_requirement_quality_rules()

        user_prompt = f"""
TASK
Extract candidate technical requirements from the input mission request according to ECSS-E-ST-10-06C-inspired technical requirement writing rules.

REFERENCE RULES
{ecss_rules}

OUTPUT FORMAT
Return only valid JSON with this exact structure:
{{
  "requirements": [
    {{
      "id": "REQ-001",
      "text": "The product shall ...",
      "category": "functional | mission | interface | environmental | operational | human factor | physical | product assurance | configuration | design | verification",
      "status": "extracted | under_specified | requires_review",
      "source": "mission_request_document",
      "confidence": 0.0
    }}
  ]
}}

ALLOWED CATEGORIES
- functional
- mission
- interface
- environmental
- operational
- human factor
- physical
- product assurance
- configuration
- design
- verification

CATEGORY RULES
- Use "functional" for what the product/system shall perform to satisfy a need.
- Use "mission" for requirements induced by the mission scenario, mission profile, orbit mission concept, target area, mission lifetime, or mission-level task.
- Use "interface" for interconnections or relationships with other systems, including ground segment, downlink, telemetry, data exchange, electrical, mechanical, thermal, or protocol interfaces.
- Use "environmental" for natural or induced environments, including radiation, illumination, atmosphere, contamination, thermal environment, glint/reflection effects, or interaction with observing environment.
- Use "operational" for operability, operational profiles, modes, autonomy, control, acquisition operations, contingency, or data handling operations.
- Use "human factor" only when the requirement concerns human capabilities, workload, perception, display, or human interaction.
- Use "physical" for mass, dimensions, aperture, swath, GSD, structural or physical boundary conditions.
- Use "product assurance" for reliability, availability, maintainability, safety, quality assurance, or health monitoring.
- Use "configuration" for product composition, number of satellites, number of planes, architecture composition, or configured elements.
- Use "design" only when the mission request imposes a design solution, technology, construction standard, component, material, orbital architecture, payload type, or implementation method.
- Use "verification" only when the mission request imposes a verification method, test, analysis, inspection, demonstration, or verification standard.

ECSS-BASED REQUIREMENT WRITING RULES
- Apply ECSS-E-ST-10-06C technical requirement writing principles.
- Extract only technical requirements, not general descriptive background.
- First identify the technical need; then rewrite it as a concise ECSS-style requirement.
- Do not simply rewrite each sentence from the mission request as a "shall" statement.
- Do not copy long phrases from the mission request except for proper nouns, numerical values, units, named configurations and declared interfaces.
- Express each requirement as one single, self-contained technical statement.
- Each requirement shall contain one need only.
- Each requirement shall be clear, unique, unambiguous, traceable and verifiable.
- Each requirement shall be written using "shall".
- Each requirement shall state what is necessary, not how to implement the solution, unless the implementation method is explicitly imposed by the mission request.
- Preserve numerical values and units when explicitly provided.
- Do not invent numerical values, units, tolerances or verification criteria.
- If a requirement is qualitative but not quantified, set status = "under_specified".
- If a requirement cannot be verified from the available information, set status = "requires_review".
- Do not merge mission objective, design solution, operational scenario, verification method, budget, rationale and implementation narrative into the same requirement.
- Do not extract pure narrative, motivation, justification, background, financial planning, budget allocation, procurement cost, or explanatory text as technical requirements.
- Do not use ambiguous or weak terms in the rewritten requirement text, including rapid, suitable, sufficient, adequate, optimized, minimized, maximized, state of the art, as far as possible, and/or, etc., high-rate, high-resolution, high-stability, comprehensive, efficient, or best possible, unless a measurable criterion is also present.
- If the source statement contains a weak term but no measurable criterion, rewrite the need without the weak term and set status = "under_specified".
- Avoid the generic subject "The product" when the system or subsystem name is known. Prefer specific subjects such as "The IRIS-IT constellation", "The spacecraft", "The optical payload", "The ground segment", or "The mission".
- Avoid implementation narrative unless the text explicitly imposes the implementation as a requirement.
- If a statement describes a selected design solution rather than a need, classify it as "design" or "configuration" only if the mission request explicitly imposes that solution.

FILTERING PROCESS
- Step 1: identify candidate technical needs.
- Step 2: discard narrative, rationale, descriptive implementation sequence, context and programmatic-only information.
- Step 3: merge duplicate or overlapping candidates.
- Step 4: rewrite only valid technical needs as ECSS-style requirements.
- Step 5: assign status based on specificity and verifiability.
- Do not expose these steps in the output.

EXTRACTION CONTROL RULES
- Extract at most 16 high-level technical requirements.
- Prefer mission-driving and STAR-analysis-relevant requirements over implementation narrative.
- Do not create a separate requirement for every numerical detail.
- Group closely related numerical details into one requirement when they define the same technical need.
- Treat cost, budget allocation, payment, procurement cost, schedule of delivery, or place of delivery as programmatic context, not as technical requirements.
- Do not output a budget or cost requirement unless the text explicitly states a technical design constraint derived from budget.
- Group detailed data handling operations into one operational or interface requirement unless separate technical constraints are explicitly imposed.
- Group astronomy-impact statements into one environmental requirement unless separate measurable constraints are explicitly imposed.
- Stop after extracting the requirements needed to support preliminary STAR mission analysis.
- Return JSON immediately after the requirement list.

STATUS RULES
- Use "extracted" when the technical requirement is explicitly stated and sufficiently specific.
- Use "under_specified" when the need is present but lacks quantitative values, tolerance, boundary condition, or acceptance criteria.
- Use "requires_review" when the item is ambiguous, mixes multiple needs, appears programmatic rather than technical, or needs human confirmation.

CONFIDENCE RULES
- Use confidence between 0.85 and 0.95 for explicit and well-formed technical requirements.
- Use confidence between 0.60 and 0.84 for under-specified requirements.
- Use confidence between 0.40 and 0.59 for requirements requiring human review.
- Do not use confidence = 1.0.

DO NOT
- Do not output categories outside the allowed category list.
- Do not output statuses outside the allowed status list.
- Do not output missing parameters.
- Do not output workflow steps.
- Do not output markdown.
- Do not output explanatory text outside the JSON.

MISSION REQUEST
\"\"\"
{document_text[:12000]}
\"\"\"

Return JSON only.
"""

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.choices[0].message.content or ""
        data = self._parse_json_response(content)
        requirements = data.get("requirements", [])

        if not isinstance(requirements, list):
            raise ValueError("LLM response JSON does not contain a requirements list.")

        return self._normalize_requirements(requirements)

    def _load_ecss_requirement_quality_rules(self) -> str:
        """
        Load the compact ECSS-based checklist from the local knowledge base.
        Falls back to an embedded checklist if the file is not available.
        """
        star_root_dir = Path(__file__).resolve().parents[2]
        rules_path = (
            star_root_dir / "Input" / "input_base_knowledge" / "knowledge_base"
            / "standards" / "ecss_requirement_quality_rules.md"
        )

        if rules_path.exists():
            return rules_path.read_text(encoding="utf-8").strip()

        return """
ECSS-E-ST-10-06C operational checklist:
- Technical requirements shall be separately stated.
- Technical requirements shall be quantifiable when they express performance.
- Technical requirements shall be justified and traceable.
- Technical requirements shall be unambiguous, unique, identifiable, singular, complete and verifiable.
- Technical requirements should be written as what is necessary, not how to perform the task.
- The verbal form "shall" shall be used for requirements.
- Requirements should be positive complete sentences with a verb and a noun.
- Avoid weak or ambiguous terms including and/or, etc., relevant, necessary, appropriate, as far as possible, optimize, minimize, maximize, typical, rapid, user-friendly, easy, sufficient, suitable, adequate, quick, best possible, small, large, state of the art.
"""

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").strip()

        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    def _normalize_requirements(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed_categories = set(ALLOWED_ECSS_REQUIREMENT_CATEGORIES)
        allowed_statuses = set(ALLOWED_REQUIREMENT_STATUSES)

        normalized = []
        seen_texts = set()

        for index, req in enumerate(requirements[:16], start=1):
            text = str(req.get("text") or "").strip()

            if not text:
                continue

            text = self._normalize_requirement_text(text)
            text_key = re.sub(r"\s+", " ", text.lower()).strip()
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)

            category = str(req.get("category", "functional")).strip()
            if category not in allowed_categories:
                category = self._map_legacy_category(category)

            status = str(req.get("status", "requires_review")).strip()
            if status not in allowed_statuses:
                status = "requires_review"

            quality_flags = self._ecss_quality_flags(text)

            if quality_flags and status == "extracted":
                # Keep explicit requirements usable, but mark likely quality issues for review.
                status = "under_specified" if self._only_under_specified_flags(quality_flags) else "requires_review"

            try:
                confidence = float(req.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5

            confidence = max(0.0, min(0.95, confidence))

            normalized.append(
                {
                    "id": f"REQ-{len(normalized) + 1:03d}",
                    "text": text,
                    "category": category,
                    "status": status,
                    "source": str(req.get("source", "mission_request_document")),
                    "confidence": confidence,
                    "quality_flags": quality_flags,
                    "standard_reference": "ECSS-E-ST-10-06C-inspired",
                }
            )

        return normalized

    def _normalize_requirement_text(self, text: str) -> str:
        value = re.sub(r"\s+", " ", text).strip()

        # Convert common non-ECSS verbal forms into "shall" when safe.
        replacements = [
            (r"\bmust\b", "shall"),
            (r"\bwill\b", "shall"),
            (r"\bis required to\b", "shall"),
            (r"\bare required to\b", "shall"),
        ]
        for pattern, replacement in replacements:
            value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)

        if " shall " not in f" {value.lower()} ":
            # Do not invent a system name if the model omitted it.
            # Use a neutral subject to enforce ECSS-style requirement wording.
            first = value[0].lower() + value[1:] if value else value
            value = f"The system shall {first}"

        if not value.endswith("."):
            value += "."

        return value

    def _map_legacy_category(self, category: str) -> str:
        legacy = category.strip().lower()
        mapping = {
            "mission_objective": "mission",
            "payload": "design",
            "orbit": "mission",
            "eps": "functional",
            "performance": "functional",
            "analysis": "functional",
            "constraint": "design",
            "general": "functional",
        }
        return mapping.get(legacy, "functional")

    def _ecss_quality_flags(self, text: str) -> list[str]:
        lowered = text.lower()
        flags = []

        if " shall " not in f" {lowered} ":
            flags.append("missing_shall")

        for term in ECSS_FORBIDDEN_OR_WEAK_TERMS:
            if term in lowered:
                flags.append(f"weak_or_forbidden_term:{term}")

        if len(text.split()) > 38:
            flags.append("too_long")

        if re.search(r"\bshall\b.*\bshall\b", lowered):
            flags.append("possibly_compound_requirement")

        if " and " in lowered and any(token in lowered for token in [" shall ", " provide ", " perform ", " generate ", " support ", " downlink "]):
            flags.append("check_singularity")

        vague_quantifiers = [
            "frequent",
            "high-revisit",
            "high revisit",
            "high-resolution",
            "high resolution",
            "high-rate",
            "high rate",
            "high-stability",
            "high stability",
            "comprehensive",
            "low-cost",
            "low cost",
            "persistent",
            "timely",
            "accurate",
            "optimized",
            "efficient",
        ]
        if any(term in lowered for term in vague_quantifiers) and not re.search(r"\d", text):
            flags.append("under_quantified")

        if any(term in lowered for term in ["budget", "cost", "euros", "million"]):
            flags.append("programmatic_information")

        return sorted(set(flags))

    def _only_under_specified_flags(self, quality_flags: list[str]) -> bool:
        allowed = {"under_quantified", "check_singularity", "too_long"}
        return all(flag in allowed for flag in quality_flags)
