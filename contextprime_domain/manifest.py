"""
Manifest models for declarative domain packs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


DOMAIN_PACK_SCHEMA_VERSION = 1
DOMAIN_PACK_API_VERSION = "1"


class DomainTagRuleManifest(BaseModel):
    """Declarative rule for mapping content to a DocTag type."""

    pattern: str
    tag_type: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    ignore_case: bool = True


class DomainQueryRuleManifest(BaseModel):
    """Declarative rule for classifying domain-specific queries."""

    pattern: str
    query_type: str
    recommended_strategy: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    ignore_case: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DomainValidatorManifest(BaseModel):
    """Declarative validator rule for synthesized answers."""

    name: str
    validator_type: str = "builtin"
    severity: str = "warning"
    message: Optional[str] = None
    pattern: Optional[str] = None
    ignore_case: bool = True
    section: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class DomainModelManifest(BaseModel):
    """Declarative optional model binding for a domain pack."""

    model: Optional[str] = None
    backend: Optional[str] = None
    path: Optional[str] = None
    required: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_model_reference(self) -> "DomainModelManifest":
        if not str(self.model or "").strip() and not str(self.path or "").strip():
            raise ValueError("domain model binding must define either model or path")
        return self


class DomainVerifierConfigManifest(BaseModel):
    """Declarative verifier policy for post-synthesis model checks."""

    mode: str = "advisory"
    retry_limit: int = 0
    timeout_seconds: float = 1.0
    max_issues: int = 4
    pass_threshold: float = 0.5
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"off", "advisory", "blocking", "blocking_with_retry"}:
            raise ValueError(
                "verifier mode must be one of: off, advisory, blocking, blocking_with_retry"
            )
        return normalized


class DomainBenchmarkDatasetManifest(BaseModel):
    """Declarative benchmark dataset reference for a domain pack."""

    name: str
    path: str
    format: str = "jsonl"
    description: str = ""
    task_types: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"jsonl"}:
            raise ValueError("benchmark dataset format must be 'jsonl'")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("benchmark dataset path must not be empty")
        return normalized


class DomainDocumentDetectionManifest(BaseModel):
    """Document-domain detection configuration."""

    patterns: List[str] = Field(default_factory=list)
    min_matches: int = Field(default=1, ge=1)


class DomainDocTagsManifest(BaseModel):
    """DocTag mapping configuration."""

    headings: List[DomainTagRuleManifest] = Field(default_factory=list)
    paragraphs: List[DomainTagRuleManifest] = Field(default_factory=list)


class DomainQueryRoutingManifest(BaseModel):
    """Query routing specialization configuration."""

    markers: List[str] = Field(default_factory=list)
    rules: List[DomainQueryRuleManifest] = Field(default_factory=list)
    default_query_type: Optional[str] = None
    default_strategy: Optional[str] = None
    default_confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class DomainPackManifest(BaseModel):
    """Top-level manifest for a declarative domain pack."""

    schema_version: int = DOMAIN_PACK_SCHEMA_VERSION
    api_version: str = DOMAIN_PACK_API_VERSION
    name: str
    version: str = "1"
    description: str = ""
    min_contextprime_version: Optional[str] = None
    max_contextprime_version: Optional[str] = None
    document_detection: DomainDocumentDetectionManifest = Field(
        default_factory=DomainDocumentDetectionManifest
    )
    doctags: DomainDocTagsManifest = Field(default_factory=DomainDocTagsManifest)
    query_routing: DomainQueryRoutingManifest = Field(default_factory=DomainQueryRoutingManifest)
    query_expansions: Dict[str, List[str]] = Field(default_factory=dict)
    models: Dict[str, DomainModelManifest] = Field(default_factory=dict)
    verifier: Optional[DomainVerifierConfigManifest] = None
    synthesis_profile: Dict[str, Any] = Field(default_factory=dict)
    validators: List[str | DomainValidatorManifest] = Field(default_factory=list)
    benchmark_datasets: List[DomainBenchmarkDatasetManifest] = Field(default_factory=list)
    benchmark_metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            raise ValueError("pack name must not be empty")
        for char in normalized:
            if not (char.isalnum() or char in {"-", "_"}):
                raise ValueError(
                    "pack name may only contain lowercase letters, digits, '-' and '_'"
                )
        return normalized

    @field_validator("api_version")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("api_version must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_dataset_names(self) -> "DomainPackManifest":
        seen = set()
        for dataset in self.benchmark_datasets:
            if dataset.name in seen:
                raise ValueError(f"duplicate benchmark dataset name: {dataset.name}")
            seen.add(dataset.name)
        return self
