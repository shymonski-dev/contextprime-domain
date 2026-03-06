"""
CLI helpers for domain-pack discovery, validation, and benchmark smoke tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional

from .legal import LegalDomainPack
from .loader import (
    load_domain_pack_from_dir,
    summarize_domain_pack,
    validate_domain_pack,
    validate_domain_pack_dir,
)
from .registry import DomainRegistry


def build_domain_registry(
    *,
    search_paths: Optional[Iterable[str]] = None,
    include_builtin: bool = True,
) -> DomainRegistry:
    """Build a registry from explicit search paths."""
    builtins = [LegalDomainPack()] if include_builtin else []
    registry = DomainRegistry(builtins)
    if search_paths:
        registry.discover_from_paths(Path(path) for path in search_paths)
    return registry


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Manage ContextPrime domain packs")
    parser.add_argument(
        "--search-path",
        action="append",
        default=[],
        help="Additional domain-pack search path (repeatable)",
    )
    parser.add_argument(
        "--no-builtin",
        action="store_true",
        help="Exclude built-in domain packs from the registry",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-packs", help="List discovered domain packs")
    list_parser.set_defaults(handler=_handle_list_packs)

    show_parser = subparsers.add_parser("show-pack", help="Show one domain-pack summary")
    show_parser.add_argument("target", help="Pack name")
    show_parser.set_defaults(handler=_handle_show_pack)

    validate_parser = subparsers.add_parser("validate-pack", help="Validate one pack")
    validate_parser.add_argument("target", help="Pack directory or discovered pack name")
    validate_parser.set_defaults(handler=_handle_validate_pack)

    test_parser = subparsers.add_parser("test-pack", help="Smoke-test pack benchmark datasets")
    test_parser.add_argument("target", help="Pack directory or discovered pack name")
    test_parser.add_argument(
        "--dataset",
        default=None,
        help="Optional benchmark dataset name to test",
    )
    test_parser.set_defaults(handler=_handle_test_pack)

    args = parser.parse_args(argv)
    return int(args.handler(args))


def _handle_list_packs(args: argparse.Namespace) -> int:
    registry = build_domain_registry(
        search_paths=args.search_path,
        include_builtin=not args.no_builtin,
    )
    summaries = registry.summaries()
    if args.json:
        print(json.dumps(summaries, indent=2))
        return 0

    for summary in summaries:
        print(
            f"{summary['name']}\tversion={summary['version']}\t"
            f"api={summary['api_version']}\tsource={summary['source']}"
        )
    return 0


def _handle_show_pack(args: argparse.Namespace) -> int:
    registry = build_domain_registry(
        search_paths=args.search_path,
        include_builtin=not args.no_builtin,
    )
    pack = registry.get(args.target)
    if pack is None:
        raise SystemExit(f"Unknown domain pack: {args.target}")

    summary = summarize_domain_pack(pack)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"name: {summary['name']}")
    print(f"version: {summary['version']}")
    print(f"api_version: {summary['api_version']}")
    print(f"source: {summary['source']}")
    print(f"description: {summary['description']}")
    datasets = summary.get("benchmark_datasets", [])
    if datasets:
        print("benchmark_datasets:")
        for dataset in datasets:
            print(f"  - {dataset['name']} ({dataset['format']}) -> {dataset['path']}")
    models = summary.get("models", [])
    if models:
        print("models:")
        for model in models:
            target = model.get("path") or model.get("model") or "<unspecified>"
            print(f"  - {model['slot']} -> {target}")
    return 0


def _handle_validate_pack(args: argparse.Namespace) -> int:
    report = _resolve_validation_report(args)
    if args.json:
        print(
            json.dumps(
                {
                    "pack_name": report.pack_name,
                    "source": report.source,
                    "valid": report.valid,
                    "errors": [message.__dict__ for message in report.errors],
                    "warnings": [message.__dict__ for message in report.warnings],
                    "metadata": report.metadata,
                },
                indent=2,
            )
        )
        return 0 if report.valid else 1

    print(f"pack: {report.pack_name}")
    print(f"source: {report.source}")
    print(f"valid: {report.valid}")
    for message in report.errors:
        print(f"ERROR: {message.message}")
    for message in report.warnings:
        print(f"WARNING: {message.message}")
    return 0 if report.valid else 1


def _handle_test_pack(args: argparse.Namespace) -> int:
    target_path = Path(args.target)
    if target_path.exists():
        pack = load_domain_pack_from_dir(target_path)
        report = validate_domain_pack(pack)
        if not report.valid:
            return _handle_validate_pack(args)
        dataset_summaries = report.metadata.get("benchmark_datasets", [])
        dataset_names = [item["name"] for item in dataset_summaries]
        if args.dataset:
            dataset_names = [args.dataset]
        output = {
            "pack_name": report.pack_name,
            "datasets": [],
        }
        for dataset in dataset_names:
            dataset_path = next(
                (
                    item["path"] for item in dataset_summaries
                    if item["name"] == dataset
                ),
                None,
            )
            if dataset_path is None:
                raise SystemExit(f"Unknown benchmark dataset for pack: {dataset}")
            samples = pack.load_benchmark_samples(dataset) or []
            output["datasets"].append(
                {"name": dataset, "path": dataset_path, "samples": len(samples)}
            )
    else:
        registry = build_domain_registry(
            search_paths=args.search_path,
            include_builtin=not args.no_builtin,
        )
        pack = registry.get(args.target)
        if pack is None:
            raise SystemExit(f"Unknown domain pack: {args.target}")
        datasets = registry.collect_benchmark_datasets(names=[pack.name])
        dataset_names = [dataset.name for dataset in datasets]
        if args.dataset:
            dataset_names = [args.dataset]
        output = {"pack_name": pack.name, "datasets": []}
        for dataset_name in dataset_names:
            samples = registry.load_benchmark_samples(
                pack_name=pack.name,
                dataset_name=dataset_name,
            )
            dataset = registry.get_benchmark_dataset(pack_name=pack.name, dataset_name=dataset_name)
            output["datasets"].append(
                {
                    "name": dataset_name,
                    "path": dataset.path if dataset else "",
                    "samples": len(samples),
                }
            )

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"pack: {output['pack_name']}")
        for dataset in output["datasets"]:
            print(f"{dataset['name']}\tsamples={dataset['samples']}\tpath={dataset['path']}")
    return 0


def _resolve_validation_report(args: argparse.Namespace):
    target_path = Path(args.target)
    if target_path.exists():
        return validate_domain_pack_dir(target_path)

    registry = build_domain_registry(
        search_paths=args.search_path,
        include_builtin=not args.no_builtin,
    )
    reports = registry.validate_packs(names=[args.target])
    if not reports:
        raise SystemExit(f"Unknown domain pack: {args.target}")
    return reports[0]


if __name__ == "__main__":
    raise SystemExit(main())
