# Authoring Packs

A domain pack is a directory with a `domain_pack.yaml` manifest and optional
assets such as benchmark files or local model references.

## Minimal Example

```yaml
name: contracts
version: "1.0.0"
api_version: "1"
description: Contract analysis pack
document_detection:
  min_matches: 2
  patterns:
    - "\\bagreement\\b"
    - "\\bparty\\b"
doctags:
  headings:
    - pattern: "^(Definitions)$"
      tag_type: "definition"
query_expansions:
  indemnity:
    - risk allocation
synthesis_profile:
  requires_citations: true
  required_sections:
    - answer
    - supporting_authorities
benchmark_datasets:
  - name: contract_eval
    path: benchmarks/contract_eval.jsonl
```

## Workflow

1. Create the manifest.
2. Add any benchmark datasets or local model files.
3. Run `contextprime-domain validate-pack ./your_pack`.
4. Run `contextprime-domain test-pack ./your_pack`.
5. Integrate the pack into your host runtime.

## Pack Responsibilities

Packs should contribute:

- domain detection
- query routing hints
- query expansions
- synthesis contracts
- validators
- benchmark datasets

Packs should not assume the host runtime’s internal enums or classes.
Return semantic tag keys and generic metadata instead.

## Regex Patterns

All regex patterns declared in `document_detection.patterns`, `doctags`,
`query_routing.rules`, and `query_routing.markers` are validated for
syntactic correctness at manifest load time — an invalid pattern raises
an error immediately.

However, syntactically valid patterns that cause catastrophic backtracking
(e.g. `(a+)+$`) are **not** blocked at load time. Authors are responsible
for testing patterns against representative inputs before distribution.
Use anchored patterns and avoid deeply nested quantifiers.
