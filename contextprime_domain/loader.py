"""
Filesystem loader for declarative domain packs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json
import re
import importlib

import yaml
from loguru import logger

from .base import (
    DomainModelBinding,
    DomainModelResolution,
    DomainBenchmarkDataset,
    DomainBenchmarkSample,
    DomainDetection,
    DomainPack,
    DomainPackValidationMessage,
    DomainPackValidationReport,
    DomainQueryClassification,
    DomainValidationIssue,
    DomainValidatorSpec,
)
from .manifest import (
    DOMAIN_PACK_API_VERSION,
    DOMAIN_PACK_SCHEMA_VERSION,
    DomainBenchmarkDatasetManifest,
    DomainModelManifest,
    DomainPackManifest,
    DomainTagRuleManifest,
)


def _assert_within_source_dir(resolved: Path, source_dir: Path) -> None:
    source = source_dir.resolve()
    if not str(resolved).startswith(str(source) + "/") and resolved != source:
        raise ValueError(
            f"path escapes pack directory: {resolved} is not within {source}"
        )


class FileSystemDomainPack(DomainPack):
    """Domain pack backed by a `domain_pack.yaml` manifest."""

    def __init__(self, manifest: DomainPackManifest, *, source_dir: Path) -> None:
        self.manifest = manifest
        self.source_dir = Path(source_dir)
        self.name = manifest.name
        self.description = manifest.description or f"Domain pack loaded from {self.source_dir}"

    def pack_version(self) -> str:
        return str(self.manifest.version)

    def api_version(self) -> str:
        return str(self.manifest.api_version)

    def detect_document(self, parsed_doc: object) -> Optional[DomainDetection]:
        detection = self.manifest.document_detection
        if not detection.patterns:
            return None

        text = str(getattr(parsed_doc, "text", "") or "")[:10000]
        elements = getattr(parsed_doc, "elements", []) or []
        for element in elements[:50]:
            text += " " + str(getattr(element, "content", "") or "")

        match_count = 0
        for pattern in detection.patterns:
            if re.search(pattern, text, re.IGNORECASE):
                match_count += 1

        if match_count < detection.min_matches:
            return None

        confidence = min(0.99, 0.5 + (0.12 * match_count))
        return DomainDetection(
            name=self.name,
            confidence=confidence,
            metadata={
                "pattern_matches": match_count,
                "manifest_version": self.manifest.version,
                "source_dir": str(self.source_dir),
            },
        )

    def classify_heading(self, *, content: str, level: int, metadata: Dict[str, object]):
        return self._match_tag_rule(content, self.manifest.doctags.headings)

    def classify_paragraph(self, *, content: str, metadata: Dict[str, object]):
        return self._match_tag_rule(content, self.manifest.doctags.paragraphs)

    def classify_query(self, query: str) -> Optional[DomainQueryClassification]:
        query_cfg = self.manifest.query_routing
        query_text = str(query or "").strip()
        if not query_text:
            return None

        if query_cfg.markers and not any(
            re.search(pattern, query_text, re.IGNORECASE)
            for pattern in query_cfg.markers
        ):
            return None

        for rule in query_cfg.rules:
            flags = re.IGNORECASE if rule.ignore_case else 0
            if re.search(rule.pattern, query_text, flags):
                return DomainQueryClassification(
                    domain=self.name,
                    query_type=rule.query_type,
                    confidence=rule.confidence,
                    recommended_strategy=rule.recommended_strategy,
                    metadata={
                        **rule.metadata,
                        "manifest_version": self.manifest.version,
                        "source_dir": str(self.source_dir),
                    },
                )

        if query_cfg.default_query_type:
            return DomainQueryClassification(
                domain=self.name,
                query_type=query_cfg.default_query_type,
                confidence=query_cfg.default_confidence,
                recommended_strategy=query_cfg.default_strategy,
                metadata={
                    "default_rule": True,
                    "manifest_version": self.manifest.version,
                    "source_dir": str(self.source_dir),
                },
            )

        return None

    def query_expansions(self) -> Dict[str, List[str]]:
        return dict(self.manifest.query_expansions)

    def synthesis_profile(self) -> Dict[str, object]:
        return dict(self.manifest.synthesis_profile)

    def validator_names(self) -> List[str]:
        names: List[str] = []
        for item in self.manifest.validators:
            if isinstance(item, str):
                token = item.strip()
            else:
                token = item.name.strip()
            if token:
                names.append(token)
        return names

    def validator_specs(self) -> List[DomainValidatorSpec]:
        specs: List[DomainValidatorSpec] = []
        for item in self.manifest.validators:
            if isinstance(item, str):
                token = item.strip()
                if not token:
                    continue
                specs.append(DomainValidatorSpec(name=token, validator_type=token))
                continue

            config = dict(item.config)
            if item.pattern:
                config.setdefault("pattern", item.pattern)
                config.setdefault("ignore_case", item.ignore_case)
            if item.section:
                config.setdefault("section", item.section)
            specs.append(
                DomainValidatorSpec(
                    name=item.name,
                    validator_type=item.validator_type,
                    message=item.message,
                    severity=item.severity,
                    config=config,
                )
            )
        return specs

    def validate_answer(
        self,
        *,
        answer: str,
        query: str,
        results: List[Dict[str, Any]],
        synthesis_profile: Dict[str, Any],
    ) -> List[DomainValidationIssue]:
        issues: List[DomainValidationIssue] = []
        for spec in self.validator_specs():
            vtype = spec.validator_type
            if vtype == "pattern_present":
                pattern = spec.config.get("pattern", "")
                if pattern and not re.search(pattern, answer, re.IGNORECASE):
                    issues.append(
                        DomainValidationIssue(
                            validator_name=spec.name,
                            message=spec.message or f"Answer does not match required pattern: {pattern}",
                            severity=spec.severity,
                        )
                    )
            elif vtype == "pattern_absent":
                pattern = spec.config.get("pattern", "")
                if pattern and re.search(pattern, answer, re.IGNORECASE):
                    issues.append(
                        DomainValidationIssue(
                            validator_name=spec.name,
                            message=spec.message or f"Answer contains disallowed pattern: {pattern}",
                            severity=spec.severity,
                        )
                    )
            elif vtype == "section_present":
                section = spec.config.get("section", "")
                if section and section.lower() not in answer.lower():
                    issues.append(
                        DomainValidationIssue(
                            validator_name=spec.name,
                            message=spec.message or f"Answer is missing required section: {section}",
                            severity=spec.severity,
                        )
                    )
            else:
                logger.debug(
                    "Domain pack {} has no runtime implementation for validator type {}",
                    self.name,
                    vtype,
                )
        return issues

    def benchmark_metadata(self) -> Dict[str, object]:
        return dict(self.manifest.benchmark_metadata)

    def model_bindings(self) -> List[DomainModelBinding]:
        bindings: List[DomainModelBinding] = []
        for slot, binding in self.manifest.models.items():
            bindings.append(self._to_model_binding(slot, binding))
        return bindings

    def verifier_config(self) -> Dict[str, Any]:
        verifier = self.manifest.verifier
        if verifier is None:
            return {}
        return {
            "mode": verifier.mode,
            "retry_limit": verifier.retry_limit,
            "timeout_seconds": verifier.timeout_seconds,
            "max_issues": verifier.max_issues,
            "pass_threshold": verifier.pass_threshold,
            **dict(verifier.config),
        }

    def benchmark_datasets(self) -> List[DomainBenchmarkDataset]:
        datasets: List[DomainBenchmarkDataset] = []
        for dataset in self.manifest.benchmark_datasets:
            datasets.append(self._to_benchmark_dataset(dataset))
        return datasets

    def load_benchmark_samples(self, dataset_name: str) -> Optional[List[Any]]:
        dataset = self._find_benchmark_dataset(dataset_name)
        if dataset is None:
            return None

        return self._load_benchmark_samples(Path(dataset.path))

    def _match_tag_rule(self, content: str, rules: Iterable[DomainTagRuleManifest]):
        for rule in rules:
            flags = re.IGNORECASE if rule.ignore_case else 0
            if re.search(rule.pattern, content, flags):
                tag_type = self._resolve_tag_type(rule)
                if tag_type is not None:
                    return tag_type
        return None

    def _resolve_tag_type(self, rule: DomainTagRuleManifest):
        tag_type = str(rule.tag_type or "").strip().lower()
        if tag_type:
            return tag_type
        logger.warning(
            "Domain pack {} references unknown DocTag type {}",
            self.name,
            rule.tag_type,
        )
        return None

    def _load_benchmark_samples(self, path: Path) -> List[DomainBenchmarkSample]:
        samples: List[DomainBenchmarkSample] = []
        with path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid benchmark row in {}", path)
                    continue
                if isinstance(payload, dict):
                    query = str(payload.get("query", "")).strip()
                    if not query:
                        continue
                    samples.append(
                        DomainBenchmarkSample(
                            query=query,
                            expected_ids=[str(item) for item in payload.get("expected_ids", [])],
                            expected_terms=[str(item) for item in payload.get("expected_terms", [])],
                            answer_terms=[str(item) for item in payload.get("answer_terms", [])],
                            metadata=dict(payload.get("metadata") or {}),
                        )
                    )
        return samples

    def _to_benchmark_dataset(
        self,
        dataset: DomainBenchmarkDatasetManifest,
    ) -> DomainBenchmarkDataset:
        resolved_path = (self.source_dir / dataset.path).resolve()
        _assert_within_source_dir(resolved_path, self.source_dir)
        return DomainBenchmarkDataset(
            name=dataset.name,
            path=str(resolved_path),
            format=dataset.format,
            description=dataset.description,
            task_types=list(dataset.task_types),
            metadata={
                **dict(dataset.metadata),
                "pack_name": self.name,
                "manifest_version": self.manifest.version,
                "source_dir": str(self.source_dir),
            },
        )

    def _find_benchmark_dataset(
        self,
        dataset_name: str,
    ) -> Optional[DomainBenchmarkDataset]:
        token = str(dataset_name or "").strip()
        if not token:
            return None
        for dataset in self.benchmark_datasets():
            if dataset.name == token:
                return dataset
        return None

    def _to_model_binding(
        self,
        slot: str,
        binding: DomainModelManifest,
    ) -> DomainModelBinding:
        if binding.path:
            resolved_path = (self.source_dir / binding.path).resolve()
            _assert_within_source_dir(resolved_path, self.source_dir)
            resolved_path = str(resolved_path)
        else:
            resolved_path = None
        return DomainModelBinding(
            slot=str(slot).strip(),
            model=str(binding.model).strip() if binding.model else None,
            backend=str(binding.backend).strip() if binding.backend else None,
            path=resolved_path,
            required=bool(binding.required),
            config=dict(binding.config),
        )


def load_domain_manifest(path: Path) -> DomainPackManifest:
    """Load and validate a domain-pack manifest file."""
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Domain manifest must be a mapping: {path}")
    return DomainPackManifest.model_validate(payload)


def load_domain_pack_from_dir(directory: Path) -> FileSystemDomainPack:
    """Load a declarative domain pack from a directory."""
    source_dir = Path(directory)
    manifest_path = source_dir / "domain_pack.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Domain manifest not found: {manifest_path}")
    manifest = load_domain_manifest(manifest_path)
    errors, _ = _validate_manifest_compatibility(manifest)
    if errors:
        messages = "; ".join(e.message for e in errors)
        raise ValueError(f"Incompatible domain manifest at {manifest_path}: {messages}")
    return FileSystemDomainPack(manifest, source_dir=source_dir)


def summarize_domain_pack(pack: DomainPack) -> Dict[str, Any]:
    """Return a serializable summary of one pack."""
    datasets = pack.benchmark_datasets()
    return {
        "name": pack.name,
        "description": getattr(pack, "description", ""),
        "version": str(pack.pack_version()),
        "api_version": str(pack.api_version()),
        "pack_type": pack.__class__.__name__,
        "source": str(getattr(pack, "source_dir", "builtin")),
        "models": [
            {
                "slot": binding.slot,
                "model": binding.model,
                "backend": binding.backend,
                "path": binding.path,
                "required": binding.required,
            }
            for binding in pack.model_bindings()
        ],
        "benchmark_datasets": [
            {
                "name": dataset.name,
                "path": dataset.path,
                "format": dataset.format,
                "task_types": list(dataset.task_types),
            }
            for dataset in datasets
        ],
        "benchmark_metadata": dict(pack.benchmark_metadata() or {}),
    }


def validate_domain_pack(pack: DomainPack) -> DomainPackValidationReport:
    """Validate one already-loaded pack."""
    errors: List[DomainPackValidationMessage] = []
    warnings: List[DomainPackValidationMessage] = []

    if not str(getattr(pack, "name", "") or "").strip():
        errors.append(
            DomainPackValidationMessage(
                level="error",
                field="name",
                message="pack name must not be empty",
            )
        )

    api_version = str(pack.api_version() or "").strip()
    if api_version != DOMAIN_PACK_API_VERSION:
        errors.append(
            DomainPackValidationMessage(
                level="error",
                field="api_version",
                message=(
                    f"unsupported api_version '{api_version}'; "
                    f"expected {DOMAIN_PACK_API_VERSION}"
                ),
            )
        )

    seen_datasets = set()
    seen_slots = set()
    for binding in pack.model_bindings():
        slot = str(binding.slot or "").strip()
        if not slot:
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field="models",
                    message="domain model binding is missing a slot name",
                )
            )
            continue
        if slot in seen_slots:
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field=f"models.{slot}",
                    message=f"duplicate domain model slot: {slot}",
                )
            )
            continue
        seen_slots.add(slot)

        if binding.path and not Path(binding.path).exists():
            level = "error" if binding.required else "warning"
            target = errors if binding.required else warnings
            target.append(
                DomainPackValidationMessage(
                    level=level,
                    field=f"models.{slot}.path",
                    message=f"domain model asset not found: {binding.path}",
                )
            )

    for dataset in pack.benchmark_datasets():
        if dataset.name in seen_datasets:
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field=f"benchmark_datasets.{dataset.name}",
                    message=f"duplicate benchmark dataset name: {dataset.name}",
                )
            )
            continue
        seen_datasets.add(dataset.name)

        if dataset.format != "jsonl":
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field=f"benchmark_datasets.{dataset.name}.format",
                    message=f"unsupported benchmark dataset format: {dataset.format}",
                )
            )
            continue

        dataset_path = Path(dataset.path)
        if not dataset_path.exists():
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field=f"benchmark_datasets.{dataset.name}.path",
                    message=f"benchmark dataset not found: {dataset_path}",
                )
            )
            continue

        try:
            samples = pack.load_benchmark_samples(dataset.name)
        except Exception as err:
            errors.append(
                DomainPackValidationMessage(
                    level="error",
                    field=f"benchmark_datasets.{dataset.name}",
                    message=f"failed to load benchmark dataset: {err}",
                )
            )
            continue

        if samples is None:
            warnings.append(
                DomainPackValidationMessage(
                    level="warning",
                    field=f"benchmark_datasets.{dataset.name}",
                    message="pack does not provide a benchmark loader for this dataset",
                )
            )
        elif len(samples) == 0:
            warnings.append(
                DomainPackValidationMessage(
                    level="warning",
                    field=f"benchmark_datasets.{dataset.name}",
                    message="benchmark dataset loaded but contains no usable samples",
                )
            )

    report = DomainPackValidationReport(
        pack_name=pack.name,
        source=str(getattr(pack, "source_dir", "builtin")),
        valid=not errors,
        errors=errors,
        warnings=warnings,
        metadata=summarize_domain_pack(pack),
    )
    return report


def resolve_domain_model_binding(
    pack: DomainPack,
    slot: str,
) -> Optional[DomainModelResolution]:
    """Resolve one model binding for diagnostics and runtime selection."""
    token = str(slot or "").strip()
    if not token:
        return None
    for binding in pack.model_bindings():
        if binding.slot != token:
            continue
        available = True
        reason = None
        if binding.path and not Path(binding.path).exists():
            available = False
            reason = f"asset not found: {binding.path}"
        return DomainModelResolution(
            slot=binding.slot,
            pack_name=pack.name,
            model=binding.model,
            backend=binding.backend,
            path=binding.path,
            available=available,
            reason=reason,
            config=dict(binding.config),
        )
    return None


def validate_domain_pack_dir(directory: Path) -> DomainPackValidationReport:
    """Load and validate a pack from one directory."""
    source_dir = Path(directory)
    manifest_path = source_dir / "domain_pack.yaml"
    if not manifest_path.exists():
        return DomainPackValidationReport(
            pack_name=source_dir.name,
            source=str(source_dir),
            valid=False,
            errors=[
                DomainPackValidationMessage(
                    level="error",
                    field="domain_pack.yaml",
                    message=f"domain manifest not found: {manifest_path}",
                )
            ],
            metadata={"source": str(source_dir)},
        )

    try:
        manifest = load_domain_manifest(manifest_path)
    except Exception as err:
        return DomainPackValidationReport(
            pack_name=source_dir.name,
            source=str(source_dir),
            valid=False,
            errors=[
                DomainPackValidationMessage(
                    level="error",
                    field="domain_pack.yaml",
                    message=f"failed to load manifest: {err}",
                )
            ],
            metadata={"source": str(source_dir)},
        )

    report = validate_domain_pack(FileSystemDomainPack(manifest, source_dir=source_dir))
    compatibility_errors, compatibility_warnings = _validate_manifest_compatibility(manifest)
    return DomainPackValidationReport(
        pack_name=report.pack_name,
        source=report.source,
        valid=report.valid and not compatibility_errors,
        errors=report.errors + compatibility_errors,
        warnings=report.warnings + compatibility_warnings,
        metadata=report.metadata,
    )


def _validate_manifest_compatibility(
    manifest: DomainPackManifest,
) -> tuple[List[DomainPackValidationMessage], List[DomainPackValidationMessage]]:
    errors: List[DomainPackValidationMessage] = []
    warnings: List[DomainPackValidationMessage] = []

    if int(manifest.schema_version) != DOMAIN_PACK_SCHEMA_VERSION:
        errors.append(
            DomainPackValidationMessage(
                level="error",
                field="schema_version",
                message=(
                    f"unsupported schema_version '{manifest.schema_version}'; "
                    f"expected {DOMAIN_PACK_SCHEMA_VERSION}"
                ),
            )
        )

    current_version = _current_contextprime_version()
    if manifest.min_contextprime_version and _compare_versions(
        current_version,
        str(manifest.min_contextprime_version),
    ) < 0:
        errors.append(
            DomainPackValidationMessage(
                level="error",
                field="min_contextprime_version",
                message=(
                    f"pack requires ContextPrime >= {manifest.min_contextprime_version}, "
                    f"current version is {current_version}"
                ),
            )
        )
    if manifest.max_contextprime_version and _compare_versions(
        current_version,
        str(manifest.max_contextprime_version),
    ) > 0:
        warnings.append(
            DomainPackValidationMessage(
                level="warning",
                field="max_contextprime_version",
                message=(
                    f"pack declares support up to ContextPrime {manifest.max_contextprime_version}, "
                    f"current version is {current_version}"
                ),
            )
        )
    return errors, warnings


def _current_contextprime_version() -> str:
    try:
        module = importlib.import_module("contextprime")
        return str(getattr(module, "__version__", "0.0.0"))
    except Exception:
        return "0.0.0"


def _compare_versions(left: str, right: str) -> int:
    try:
        from packaging.version import Version
        lv = Version(str(left or "0.0.0"))
        rv = Version(str(right or "0.0.0"))
        if lv < rv:
            return -1
        if lv > rv:
            return 1
        return 0
    except Exception:
        pass

    def normalize(value: str) -> List[int]:
        parts = re.findall(r"\d+", str(value or ""))
        values = [int(part) for part in parts[:3]]
        while len(values) < 3:
            values.append(0)
        return values

    left_values = normalize(left)
    right_values = normalize(right)
    if left_values < right_values:
        return -1
    if left_values > right_values:
        return 1
    return 0


def discover_domain_packs(paths: Iterable[Path]) -> List[FileSystemDomainPack]:
    """Discover domain packs from one or more search roots."""
    discovered: List[FileSystemDomainPack] = []
    seen = set()

    for raw_path in paths:
        root = Path(raw_path).expanduser()
        if not root.exists():
            continue

        candidate_dirs: List[Path]
        if (root / "domain_pack.yaml").exists():
            candidate_dirs = [root]
        else:
            candidate_dirs = [
                child for child in sorted(root.iterdir())
                if child.is_dir() and (child / "domain_pack.yaml").exists()
            ]

        for candidate_dir in candidate_dirs:
            try:
                pack = load_domain_pack_from_dir(candidate_dir)
            except Exception as err:
                logger.warning("Skipping invalid domain pack at {}: {}", candidate_dir, err)
                continue

            if pack.name in seen:
                logger.warning(
                    "Duplicate domain pack name {} discovered at {}; keeping first occurrence",
                    pack.name,
                    candidate_dir,
                )
                continue

            seen.add(pack.name)
            discovered.append(pack)

    return discovered
