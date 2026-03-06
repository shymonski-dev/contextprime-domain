"""
Built-in legal domain pack.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

from .base import DomainDetection, DomainPack, DomainQueryClassification


class LegalDomainPack(DomainPack):
    """Built-in domain pack for UK/EU legal and regulatory content."""

    name = "legal"
    description = "UK/EU legal and regulatory document specialization"

    _document_patterns = (
        r"\bArticle\s+\d+",
        r"\bSchedule\s+\d+",
        r"\bRegulation\s+\(EU\)",
        r"\bAct\s+\d{4}",
        r"\bStatutory\s+Instrument",
        r"\bSection\s+\d+\s+of\s+the",
        r"\bHer\s+Majesty",
        r"\bParliament\s+of",
    )
    _query_markers = (
        r"\barticle\s+\d+",
        r"\bschedule\s+\d+",
        r"\brecital\s+\d+",
        r"\bgdpr\b",
        r"\bregulation\s+\(eu\)",
        r"\bdirective\b",
        r"\blegal basis\b",
        r"\bcontroller\b",
        r"\bprocessor\b",
        r"\bderogation\b",
    )

    def detect_document(self, parsed_doc: Any) -> Optional[DomainDetection]:
        text = str(getattr(parsed_doc, "text", "") or "")[:10000]
        elements = getattr(parsed_doc, "elements", []) or []
        for element in elements[:50]:
            text += " " + str(getattr(element, "content", "") or "")

        match_count = sum(
            1
            for pattern in self._document_patterns
            if re.search(pattern, text, re.IGNORECASE)
        )
        if match_count < 3:
            return None

        confidence = min(0.98, 0.55 + (0.12 * match_count))
        return DomainDetection(
            name=self.name,
            confidence=confidence,
            metadata={"pattern_matches": match_count},
        )

    def classify_heading(
        self,
        *,
        content: str,
        level: int,
        metadata: Dict[str, Any],
    ) -> Optional[Any]:
        if re.match(r"^(?:Article|Art\.)\s+\d+", content, re.IGNORECASE):
            return "article"
        if re.match(r"^(?:Schedule|Annex|Appendix)\s", content, re.IGNORECASE):
            return "schedule"
        if re.match(r"^(?:Definitions?|Interpretation)$", content, re.IGNORECASE):
            return "definition"
        return None

    def classify_paragraph(
        self,
        *,
        content: str,
        metadata: Dict[str, Any],
    ) -> Optional[Any]:
        if re.match(r'^"[A-Z]', content):
            return "definition"
        if re.search(
            r"\bexcept\s+(?:where|as|when|in\s+cases?\s+where)\b",
            content,
            re.IGNORECASE,
        ):
            return "exception"
        if re.search(
            r"\b(?:see|pursuant\s+to|as\s+defined\s+in|subject\s+to)\s+[Aa]rticle\s+\d+",
            content,
        ):
            return "cross_reference"
        return None

    def classify_query(self, query: str) -> Optional[DomainQueryClassification]:
        query_lower = query.lower().strip()
        if not any(re.search(pattern, query_lower) for pattern in self._query_markers):
            return None

        if re.search(r"\b(trace|follow|cross[- ]?reference|referenced by|chain of)\b", query_lower):
            return DomainQueryClassification(
                domain=self.name,
                query_type="multi_hop",
                confidence=0.9,
                recommended_strategy="multi_stage",
                metadata={"intent": "citation_trace"},
            )
        if re.search(r"\b(compare|difference|contrast|versus|vs)\b", query_lower):
            return DomainQueryClassification(
                domain=self.name,
                query_type="comparison",
                confidence=0.84,
                recommended_strategy="hybrid",
                metadata={"intent": "legal_comparison"},
            )
        if re.search(r"\b(exception|derogation|legal basis|why|obligation|lawful)\b", query_lower):
            return DomainQueryClassification(
                domain=self.name,
                query_type="analytical",
                confidence=0.83,
                recommended_strategy="hybrid",
                metadata={"intent": "legal_analysis"},
            )
        return DomainQueryClassification(
            domain=self.name,
            query_type="definition",
            confidence=0.76,
            recommended_strategy="hybrid",
            metadata={"intent": "legal_lookup"},
        )

    def query_expansions(self) -> Dict[str, List[str]]:
        return {
            "gdpr": [
                "general data protection regulation",
                "regulation eu 2016 679",
                "data protection regulation",
            ],
            "dpa": [
                "data protection act",
                "data processing agreement",
            ],
            "controller": [
                "data controller",
                "data fiduciary",
            ],
            "processor": [
                "data processor",
                "service provider",
            ],
            "recital": [
                "preamble recital",
                "regulatory recital",
            ],
        }

    def synthesis_profile(self) -> Dict[str, Any]:
        return {
            "requires_citations": True,
            "sections": ["answer", "supporting_authorities", "exceptions", "scope_limits"],
        }

    def validator_names(self) -> List[str]:
        return ["citation_presence", "scope_boundary"]

    def benchmark_metadata(self) -> Dict[str, Any]:
        return {"recommended_tasks": ["citation_trace", "exception_detection", "temporal_applicability"]}
