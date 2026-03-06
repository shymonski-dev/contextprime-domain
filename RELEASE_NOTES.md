# Release Notes

## 0.3.0

Security, correctness, and design improvements following a full code review.
All changes are backward-compatible for compliant packs.

### Security (0.1.1)

- **Path traversal blocked** — manifest-supplied paths for benchmark datasets
  and model bindings are now resolved and checked for containment within the
  pack directory. A path that escapes raises `ValueError` at access time.
- **Regex validation at load time** — all regex pattern fields in manifests
  (`document_detection.patterns`, `doctags`, `query_routing.rules`,
  `query_routing.markers`, `validators`) are compiled with `re.compile` during
  Pydantic validation. Invalid patterns raise `ValidationError` immediately on
  manifest load rather than at query time.

### Correctness (0.1.2)

- **`DomainValidationIssue` import fixed** in `loader.py` — the type was used
  in the return annotation of `validate_answer` but not imported.
- **Duplicate `api_version` error eliminated** — `_validate_manifest_compatibility`
  no longer re-checks `api_version`; the check in `validate_domain_pack` is
  the single authoritative one.
- **Compatibility check on load** — `load_domain_pack_from_dir` now calls
  `_validate_manifest_compatibility` and raises `ValueError` if the manifest's
  `schema_version` is incompatible, rather than silently loading it.
- **Pack collision policy aligned** — `DomainRegistry.discover_from_paths` now
  uses first-wins (skipping duplicates), consistent with `discover_domain_packs`.
- **Field constraints added** to `DomainVerifierConfigManifest`:
  `retry_limit` (≥ 0), `max_issues` (≥ 0), `timeout_seconds` (≥ 0),
  `pass_threshold` (0.0 – 1.0).

### Design (0.2.0)

- **Thread-safe registry singleton** — `get_default_domain_registry` uses
  double-checked locking with `threading.Lock`.
- **Lowercase name enforcement** — `DomainPack.__init_subclass__` validates
  subclass names at class-definition time using the same rules as the manifest
  schema. `name` and `description` are annotated as `ClassVar`.
- **Open list-key merging** — `DomainRegistry.collect_synthesis_profile` now
  merges any list-typed profile key, not just the previous hardcoded five.
  Third-party packs can introduce new list keys without silent data loss.
- **Pre-release version comparison** — `_compare_versions` tries
  `packaging.version.Version` first (correct pre-release ordering) and falls
  back to digit-extraction. `packaging` is an optional dependency (`pip install
  contextprime-domain[full]`).

### Quality (0.3.0)

- **`validate_answer` implemented** for `FileSystemDomainPack` — dispatches
  on three built-in validator types: `pattern_present`, `pattern_absent`,
  `section_present`. Unknown types log at DEBUG and are skipped.
- **Streaming benchmark file reader** — `_load_benchmark_samples` now iterates
  line-by-line instead of reading the entire file into memory.
- **Exports expanded** — `DomainTagRuleManifest` and `DomainQueryRuleManifest`
  are now part of the public API (`__all__`).
- **CLI exit codes fixed** — error paths in `_handle_show_pack` and
  `_handle_test_pack` now print to stderr and return `1` instead of
  `raise SystemExit(message)`.
- **AUTHORING.md updated** with regex pattern authoring guidance.

### Tests

Test suite expanded from 5 to 21 tests, covering all identified gaps:
path traversal, invalid regex patterns, api_version deduplication, schema
version loading, field constraints, concurrent registry access, synthesis
profile merging, pre-release version comparison, query classification,
CLI commands, and pack collision behaviour.

---

## 0.1.0

Initial standalone release of `contextprime-domain`.

### Included

- base domain-pack interfaces
- manifest schema and validation
- filesystem discovery and loading
- registry helpers
- CLI for listing, validating, and smoke-testing packs
- built-in legal example pack

### Intended Use

This package is designed to sit underneath a retrieval/runtime layer such as
ContextPrime, while remaining usable independently for pack development and
distribution.
