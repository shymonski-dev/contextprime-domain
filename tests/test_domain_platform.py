import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from contextprime_domain import (
    LegalDomainPack,
    get_default_domain_registry,
    load_domain_pack_from_dir,
)
from contextprime_domain.cli import main as domain_cli_main
from contextprime_domain.loader import (
    _compare_versions,
    validate_domain_pack,
    validate_domain_pack_dir,
)
from contextprime_domain.manifest import DomainVerifierConfigManifest
from contextprime_domain.registry import DomainRegistry, reset_default_domain_registry


class _ParsedDoc:
    def __init__(self, text: str, elements=None):
        self.text = text
        self.elements = elements or []


class _Element:
    def __init__(self, content: str):
        self.content = content


def test_builtin_legal_pack_detects_document():
    registry = get_default_domain_registry()
    parsed_doc = _ParsedDoc(
        "Article 6 Schedule 1 Regulation (EU) 2016/679 provisions.",
        elements=[_Element("Article 6"), _Element("Processing shall be lawful.")],
    )

    detection = registry.detect_document(parsed_doc)

    assert detection is not None
    assert detection.name == "legal"


def test_builtin_legal_pack_returns_semantic_tag_keys():
    pack = LegalDomainPack()

    assert pack.classify_heading(content="Article 6", level=2, metadata={}) == "article"
    assert (
        pack.classify_paragraph(
            content="Processing is permitted subject to Article 17 of this regulation.",
            metadata={},
        )
        == "cross_reference"
    )


def test_filesystem_pack_load_and_benchmark_samples(tmp_path):
    pack_dir = tmp_path / "privacy"
    pack_dir.mkdir()
    benchmarks_dir = pack_dir / "benchmarks"
    benchmarks_dir.mkdir()
    (benchmarks_dir / "privacy_eval.jsonl").write_text(
        '{"query":"What is a privacy notice?","expected_terms":["privacy notice"]}\n',
        encoding="utf-8",
    )
    (pack_dir / "domain_pack.yaml").write_text(
        """
name: privacy
version: "1"
query_expansions:
  privacy:
    - data protection
benchmark_datasets:
  - name: privacy_eval
    path: benchmarks/privacy_eval.jsonl
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    pack = load_domain_pack_from_dir(pack_dir)
    samples = pack.load_benchmark_samples("privacy_eval")

    assert pack.name == "privacy"
    assert samples is not None
    assert samples[0].query == "What is a privacy notice?"


def test_registry_discovers_pack_from_env(monkeypatch, tmp_path):
    pack_dir = tmp_path / "compliance"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        """
name: compliance
version: "1"
query_expansions:
  compliance:
    - policy control
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOMAIN_SEARCH_PATHS", str(tmp_path))
    monkeypatch.setenv("DOMAIN_INCLUDE_BUILTIN", "false")
    reset_default_domain_registry()
    try:
        registry = get_default_domain_registry()
        assert registry.names() == ["compliance"]
    finally:
        reset_default_domain_registry()


def test_cli_validate_and_test_pack(tmp_path):
    pack_dir = tmp_path / "finance"
    pack_dir.mkdir()
    (pack_dir / "finance_eval.jsonl").write_text(
        '{"query":"What is EBITDA?","expected_terms":["earnings"]}\n',
        encoding="utf-8",
    )
    (pack_dir / "domain_pack.yaml").write_text(
        """
name: finance
version: "1"
benchmark_datasets:
  - name: finance_eval
    path: finance_eval.jsonl
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    assert domain_cli_main(["validate-pack", str(pack_dir)]) == 0
    assert domain_cli_main(["test-pack", str(pack_dir)]) == 0


# Stage 1 — Security tests


def test_path_traversal_benchmark_raises(tmp_path):
    pack_dir = tmp_path / "evil"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: evil\nbenchmark_datasets:\n  - name: x\n    path: ../../etc/passwd\n",
        encoding="utf-8",
    )
    pack = load_domain_pack_from_dir(pack_dir)
    with pytest.raises(ValueError, match="escapes pack directory"):
        pack.benchmark_datasets()


def test_path_traversal_model_raises(tmp_path):
    pack_dir = tmp_path / "evil"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: evil\nmodels:\n  encoder:\n    path: ../../secret_model.pkl\n",
        encoding="utf-8",
    )
    pack = load_domain_pack_from_dir(pack_dir)
    with pytest.raises(ValueError, match="escapes pack directory"):
        pack.model_bindings()


def test_invalid_document_detection_pattern_raises(tmp_path):
    pack_dir = tmp_path / "bad"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: bad\ndocument_detection:\n  patterns:\n    - '(((unclosed'\n",
        encoding="utf-8",
    )
    with pytest.raises((ValidationError, ValueError)):
        load_domain_pack_from_dir(pack_dir)


def test_invalid_query_rule_pattern_raises(tmp_path):
    pack_dir = tmp_path / "bad"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: bad\nquery_routing:\n  rules:\n    - pattern: '[invalid'\n      query_type: test\n",
        encoding="utf-8",
    )
    with pytest.raises((ValidationError, ValueError)):
        load_domain_pack_from_dir(pack_dir)


# Stage 2 — Correctness tests


def test_validate_answer_returns_list(tmp_path):
    pack_dir = tmp_path / "simple"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text("name: simple\nversion: '1'\n", encoding="utf-8")
    pack = load_domain_pack_from_dir(pack_dir)
    result = pack.validate_answer(answer="test", query="q", results=[], synthesis_profile={})
    assert isinstance(result, list)


def test_api_version_error_not_duplicated(tmp_path):
    pack_dir = tmp_path / "wrongver"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: wrongver\nschema_version: 1\napi_version: '999'\n", encoding="utf-8"
    )
    report = validate_domain_pack_dir(pack_dir)
    api_errors = [e for e in report.errors if e.field == "api_version"]
    assert len(api_errors) == 1, f"Expected 1 api_version error, got {len(api_errors)}"


def test_incompatible_schema_version_raises_on_load(tmp_path):
    pack_dir = tmp_path / "badschema"
    pack_dir.mkdir()
    (pack_dir / "domain_pack.yaml").write_text(
        "name: badschema\nschema_version: 99\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Incompatible"):
        load_domain_pack_from_dir(pack_dir)


def test_pass_threshold_out_of_range_raises():
    with pytest.raises(ValidationError):
        DomainVerifierConfigManifest(pass_threshold=2.0)


def test_retry_limit_negative_raises():
    with pytest.raises(ValidationError):
        DomainVerifierConfigManifest(retry_limit=-1)


def test_classify_query_legal_pack_multi_hop():
    pack = LegalDomainPack()
    result = pack.classify_query("trace cross-reference gdpr article 6")
    assert result is not None
    assert result.query_type == "multi_hop"


def test_cli_list_packs():
    assert domain_cli_main(["list-packs"]) == 0


def test_cli_show_pack():
    assert domain_cli_main(["show-pack", "legal"]) == 0


def test_pack_collision_first_wins(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "domain_pack.yaml").write_text(
        "name: shared\nversion: '1'\ndescription: 'first'\n", encoding="utf-8"
    )
    (dir_b / "domain_pack.yaml").write_text(
        "name: shared\nversion: '2'\ndescription: 'second'\n", encoding="utf-8"
    )
    registry = DomainRegistry()
    registry.discover_from_paths([tmp_path])
    pack = registry.get("shared")
    assert pack is not None
    assert pack.pack_version() == "1", "First-registered pack should win"


# Stage 3 — Design tests


def test_concurrent_get_default_registry():
    reset_default_domain_registry()
    try:
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(id(get_default_domain_registry())))
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(results)) == 1, f"Expected 1 registry instance, got {len(set(results))}"
    finally:
        reset_default_domain_registry()


def test_collect_synthesis_profile_merges_unknown_list_key(tmp_path):
    dir_a = tmp_path / "pack_a"
    dir_b = tmp_path / "pack_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "domain_pack.yaml").write_text(
        "name: pack-a\nversion: '1'\nsynthesis_profile:\n  output_formats:\n    - pdf\n",
        encoding="utf-8",
    )
    (dir_b / "domain_pack.yaml").write_text(
        "name: pack-b\nversion: '1'\nsynthesis_profile:\n  output_formats:\n    - docx\n",
        encoding="utf-8",
    )
    pack_a = load_domain_pack_from_dir(dir_a)
    pack_b = load_domain_pack_from_dir(dir_b)
    registry = DomainRegistry([pack_a, pack_b])
    profile = registry.collect_synthesis_profile()
    assert set(profile.get("output_formats", [])) == {"pdf", "docx"}


def test_compare_versions_prerelease():
    # With packaging installed, pre-release should sort before release
    try:
        from packaging.version import Version  # noqa: F401
        packaging_available = True
    except ImportError:
        packaging_available = False

    if packaging_available:
        assert _compare_versions("1.0.0a1", "1.0.0") < 0
        assert _compare_versions("1.0.0", "1.0.0a1") > 0
    else:
        pytest.skip("packaging not installed; pre-release comparison not available")
