from pathlib import Path

from contextprime_domain import (
    LegalDomainPack,
    get_default_domain_registry,
    load_domain_pack_from_dir,
)
from contextprime_domain.cli import main as domain_cli_main
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
