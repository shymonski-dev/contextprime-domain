"""
Domain pack interfaces for distributable domain specialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DomainDetection:
    """Detected document-domain match."""

    name: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainQueryClassification:
    """Domain-aware query classification override."""

    domain: str
    query_type: str
    confidence: float = 0.75
    recommended_strategy: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainValidationIssue:
    """Issue returned by a domain validator."""

    validator_name: str
    message: str
    severity: str = "warning"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainValidatorSpec:
    """Declarative validator specification exposed by a domain pack."""

    name: str
    validator_type: str
    message: Optional[str] = None
    severity: str = "warning"
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainModelBinding:
    """Optional model binding exposed by a domain pack."""

    slot: str
    model: Optional[str] = None
    backend: Optional[str] = None
    path: Optional[str] = None
    required: bool = False
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainModelResolution:
    """Resolved model binding and fallback diagnostics."""

    slot: str
    pack_name: str
    model: Optional[str]
    backend: Optional[str]
    path: Optional[str]
    available: bool
    applied: bool = False
    reason: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainVerifierResult:
    """Outcome of a post-synthesis verifier check."""

    passed: bool
    severity: str = "warning"
    issues: List[DomainValidationIssue] = field(default_factory=list)
    suggested_revision: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    executed: bool = True


@dataclass(frozen=True)
class DomainBenchmarkDataset:
    """Benchmark dataset exposed by a domain pack."""

    name: str
    path: str
    format: str = "jsonl"
    description: str = ""
    task_types: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainBenchmarkSample:
    """Single benchmark sample loaded from a pack dataset."""

    query: str
    expected_ids: List[str] = field(default_factory=list)
    expected_terms: List[str] = field(default_factory=list)
    answer_terms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainPackValidationMessage:
    """Validation message emitted while checking a domain pack."""

    level: str
    message: str
    field: Optional[str] = None


@dataclass(frozen=True)
class DomainPackValidationReport:
    """Validation summary for a domain pack."""

    pack_name: str
    source: str
    valid: bool
    errors: List[DomainPackValidationMessage] = field(default_factory=list)
    warnings: List[DomainPackValidationMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DomainPack:
    """
    Base interface for pluggable domain packs.

    Implementations can specialize document detection, DocTag mapping,
    query classification, query expansion, synthesis contracts, and
    benchmark metadata without changing the core engine.
    """

    name: str = "base"
    description: str = "Base domain pack"

    def pack_version(self) -> str:
        """Return the version of the pack itself."""
        return "builtin"

    def api_version(self) -> str:
        """Return the domain-pack API version implemented by this pack."""
        return "1"

    def detect_document(self, parsed_doc: Any) -> Optional[DomainDetection]:
        """Return a detected domain match for a parsed document."""
        return None

    def classify_heading(
        self,
        *,
        content: str,
        level: int,
        metadata: Dict[str, Any],
    ) -> Optional[Any]:
        """Optionally override heading tag classification."""
        return None

    def classify_paragraph(
        self,
        *,
        content: str,
        metadata: Dict[str, Any],
    ) -> Optional[Any]:
        """Optionally override paragraph tag classification."""
        return None

    def classify_query(self, query: str) -> Optional[DomainQueryClassification]:
        """Optionally provide a domain-aware query classification."""
        return None

    def query_expansions(self) -> Dict[str, List[str]]:
        """Optional domain-specific query expansion mappings."""
        return {}

    def synthesis_profile(self) -> Dict[str, Any]:
        """Optional synthesis/output contract hints for future use."""
        return {}

    def validator_names(self) -> List[str]:
        """Optional validator names exposed by this domain pack."""
        return []

    def validator_specs(self) -> List[DomainValidatorSpec]:
        """Optional validator specs exposed by this domain pack."""
        return [
            DomainValidatorSpec(name=name, validator_type=name)
            for name in self.validator_names()
        ]

    def validate_answer(
        self,
        *,
        answer: str,
        query: str,
        results: List[Dict[str, Any]],
        synthesis_profile: Dict[str, Any],
    ) -> List[DomainValidationIssue]:
        """Optional hook for custom validator logic in Python-based packs."""
        return []

    def benchmark_metadata(self) -> Dict[str, Any]:
        """Optional benchmark dataset metadata for future evaluation hooks."""
        return {}

    def model_bindings(self) -> List[DomainModelBinding]:
        """Optional model bindings for synthesis or retrieval subsystems."""
        return []

    def verifier_config(self) -> Dict[str, Any]:
        """Optional post-synthesis verifier configuration."""
        return {}

    def benchmark_datasets(self) -> List[DomainBenchmarkDataset]:
        """Optional benchmark datasets exposed by this pack."""
        return []

    def load_benchmark_samples(self, dataset_name: str) -> Optional[List[Any]]:
        """Optional hook for loading benchmark samples for one dataset."""
        return None
