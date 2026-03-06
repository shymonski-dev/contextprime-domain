"""
Registry for pluggable domain packs.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from .base import (
    DomainBenchmarkDataset,
    DomainDetection,
    DomainModelBinding,
    DomainModelResolution,
    DomainPack,
    DomainQueryClassification,
    DomainValidationIssue,
    DomainValidatorSpec,
)
from .legal import LegalDomainPack
from .loader import (
    discover_domain_packs,
    resolve_domain_model_binding,
    summarize_domain_pack,
    validate_domain_pack,
)


class DomainRegistry:
    """In-process registry for installed domain packs."""

    def __init__(self, packs: Optional[Iterable[DomainPack]] = None) -> None:
        self._packs: Dict[str, DomainPack] = {}
        for pack in packs or []:
            self.register(pack)

    def register(self, pack: DomainPack) -> None:
        self._packs[pack.name] = pack

    def discover_from_paths(self, paths: Iterable[Path]) -> List[str]:
        """Discover and register packs from filesystem search paths."""
        loaded_names: List[str] = []
        for pack in discover_domain_packs(paths):
            if pack.name in self._packs:
                logger.warning(
                    "Domain pack {} from {} already registered; keeping existing",
                    pack.name,
                    getattr(pack, "source_dir", "<unknown>"),
                )
                loaded_names.append(pack.name)
                continue
            self.register(pack)
            loaded_names.append(pack.name)
        return loaded_names

    def get(self, name: str) -> Optional[DomainPack]:
        return self._packs.get(name)

    def names(self) -> List[str]:
        return sorted(self._packs.keys())

    def summaries(self, names: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        """Return serializable summaries for resolved packs."""
        return [summarize_domain_pack(pack) for pack in self.resolve(names)]

    def resolve(self, names: Optional[Iterable[str]] = None) -> List[DomainPack]:
        if names is None:
            return [self._packs[name] for name in self.names()]

        resolved: List[DomainPack] = []
        seen = set()
        for name in names:
            pack_name = str(name).strip().lower()
            if not pack_name or pack_name in seen:
                continue
            seen.add(pack_name)
            pack = self._packs.get(pack_name)
            if pack is not None:
                resolved.append(pack)
        return resolved

    def detect_document(
        self,
        parsed_doc: object,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Optional[DomainDetection]:
        best_match: Optional[DomainDetection] = None
        for pack in self.resolve(names):
            detection = pack.detect_document(parsed_doc)
            if detection is None:
                continue
            if best_match is None or detection.confidence > best_match.confidence:
                best_match = detection
        return best_match

    def classify_query(
        self,
        query: str,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Optional[DomainQueryClassification]:
        best_match: Optional[DomainQueryClassification] = None
        for pack in self.resolve(names):
            classification = pack.classify_query(query)
            if classification is None:
                continue
            if best_match is None or classification.confidence > best_match.confidence:
                best_match = classification
        return best_match

    def collect_query_expansions(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Dict[str, List[str]]:
        merged: Dict[str, List[str]] = {}
        for pack in self.resolve(names):
            for term, expansions in pack.query_expansions().items():
                values = merged.setdefault(term.lower(), [])
                seen = {item.lower() for item in values}
                for expansion in expansions:
                    normalized = str(expansion).strip()
                    if not normalized or normalized.lower() in seen:
                        continue
                    seen.add(normalized.lower())
                    values.append(normalized)
        return merged

    def collect_synthesis_profile(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Dict[str, object]:
        """Merge synthesis profiles from resolved domain packs."""
        merged: Dict[str, object] = {}
        merged_lists: Dict[str, List[str]] = {}

        for pack in self.resolve(names):
            profile = dict(pack.synthesis_profile() or {})
            for key, value in profile.items():
                if isinstance(value, list):
                    bucket = merged_lists.setdefault(key, [])
                    seen = {item.lower() for item in bucket}
                    for item in value:
                        token = str(item).strip()
                        if token and token.lower() not in seen:
                            seen.add(token.lower())
                            bucket.append(token)
                else:
                    merged[key] = value

        for key, values in merged_lists.items():
            if values:
                merged[key] = values
        return merged

    def collect_validator_names(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> List[str]:
        """Collect validator names from resolved domain packs."""
        validators: List[str] = []
        seen = set()
        for pack in self.resolve(names):
            for name in pack.validator_names():
                token = str(name).strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                validators.append(token)
        return validators

    def collect_validator_specs(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> List[DomainValidatorSpec]:
        """Collect validator specs from resolved domain packs."""
        validators: List[DomainValidatorSpec] = []
        seen = set()
        for pack in self.resolve(names):
            for spec in pack.validator_specs():
                key = (spec.name, spec.validator_type, repr(spec.config))
                if key in seen:
                    continue
                seen.add(key)
                validators.append(spec)
        return validators

    def collect_model_bindings(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Dict[str, DomainModelBinding]:
        """Collect one effective model binding per slot from resolved packs."""
        bindings: Dict[str, DomainModelBinding] = {}
        for pack in self.resolve(names):
            for binding in pack.model_bindings():
                slot = str(binding.slot or "").strip()
                if slot:
                    bindings[slot] = binding
        return bindings

    def collect_verifier_config(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Merge verifier configuration from resolved packs."""
        merged: Dict[str, Any] = {}
        for pack in self.resolve(names):
            config = dict(pack.verifier_config() or {})
            for key, value in config.items():
                merged[key] = value
        return merged

    def resolve_model_binding(
        self,
        *,
        slot: str,
        names: Optional[Iterable[str]] = None,
    ) -> Optional[DomainModelBinding]:
        """Resolve one effective model binding for a slot."""
        return self.collect_model_bindings(names=names).get(str(slot).strip())

    def model_resolutions(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> List[DomainModelResolution]:
        """Resolve model binding diagnostics for active packs."""
        resolutions: List[DomainModelResolution] = []
        seen = set()
        for pack in self.resolve(names):
            for binding in pack.model_bindings():
                key = (pack.name, binding.slot)
                if key in seen:
                    continue
                seen.add(key)
                resolution = resolve_domain_model_binding(pack, binding.slot)
                if resolution is not None:
                    resolutions.append(resolution)
        return resolutions

    def collect_benchmark_datasets(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> List[DomainBenchmarkDataset]:
        """Collect benchmark datasets exposed by resolved domain packs."""
        datasets: List[DomainBenchmarkDataset] = []
        seen = set()
        for pack in self.resolve(names):
            for dataset in pack.benchmark_datasets():
                key = (pack.name, dataset.name)
                if key in seen:
                    continue
                seen.add(key)
                datasets.append(dataset)
        return datasets

    def get_benchmark_dataset(
        self,
        *,
        pack_name: str,
        dataset_name: str,
    ) -> Optional[DomainBenchmarkDataset]:
        """Resolve one benchmark dataset from one domain pack."""
        pack = self.get(str(pack_name).strip().lower())
        if pack is None:
            return None
        for dataset in pack.benchmark_datasets():
            if dataset.name == str(dataset_name).strip():
                return dataset
        return None

    def load_benchmark_samples(
        self,
        *,
        pack_name: str,
        dataset_name: str,
    ) -> List[Any]:
        """Load benchmark samples from one pack-owned dataset."""
        pack = self.get(str(pack_name).strip().lower())
        if pack is None:
            raise KeyError(f"Unknown domain pack: {pack_name}")
        samples = pack.load_benchmark_samples(str(dataset_name).strip())
        if samples is None:
            raise KeyError(
                f"Unknown benchmark dataset '{dataset_name}' for domain pack '{pack_name}'"
            )
        return list(samples)

    def validate_packs(
        self,
        *,
        names: Optional[Iterable[str]] = None,
    ) -> List[Any]:
        """Validate resolved packs and return one report per pack."""
        return [validate_domain_pack(pack) for pack in self.resolve(names)]

    def validate_answer(
        self,
        *,
        answer: str,
        query: str,
        results: List[Dict[str, Any]],
        synthesis_profile: Dict[str, Any],
        names: Optional[Iterable[str]] = None,
    ) -> List[DomainValidationIssue]:
        """Run pack-provided validation hooks over a synthesized answer."""
        issues: List[DomainValidationIssue] = []
        for pack in self.resolve(names):
            issues.extend(
                pack.validate_answer(
                    answer=answer,
                    query=query,
                    results=results,
                    synthesis_profile=synthesis_profile,
                )
            )
        return issues


_DEFAULT_REGISTRY: Optional[DomainRegistry] = None
_DEFAULT_REGISTRY_LOCK = threading.Lock()


def get_default_domain_registry() -> DomainRegistry:
    """Return the default registry with built-in domain packs registered."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is not None:
        return _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        if _DEFAULT_REGISTRY is not None:
            return _DEFAULT_REGISTRY
        builtins: List[DomainPack] = [LegalDomainPack()]
        search_paths: List[Path] = []
        include_builtin = True

        env_include_builtin = os.getenv("DOMAIN_INCLUDE_BUILTIN")
        if env_include_builtin is not None:
            include_builtin = env_include_builtin.strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }

        env_search_paths = os.getenv("DOMAIN_SEARCH_PATHS", "").strip()
        if env_search_paths:
            raw_paths = []
            for chunk in env_search_paths.split(os.pathsep):
                raw_paths.extend(part.strip() for part in chunk.split(","))
            search_paths = [Path(path) for path in raw_paths if path]

        try:
            from contextprime.core.config import get_settings

            settings = get_settings()
            if env_include_builtin is None:
                include_builtin = bool(getattr(settings.domain, "include_builtin", True))
            if not env_search_paths:
                search_paths = [Path(path) for path in getattr(settings.domain, "search_paths", [])]
        except Exception as err:
            logger.debug("Falling back to standalone domain registry settings: {}", err)

        _DEFAULT_REGISTRY = DomainRegistry(builtins if include_builtin else [])
        if search_paths:
            _DEFAULT_REGISTRY.discover_from_paths(search_paths)
    return _DEFAULT_REGISTRY


def reset_default_domain_registry() -> None:
    """Reset the cached default domain registry."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
