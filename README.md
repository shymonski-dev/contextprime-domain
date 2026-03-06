# contextprime-domain

`contextprime-domain` is a standalone domain-pack platform for document RAG
systems. It provides a lightweight way to define, validate, load, and inspect
pluggable domain packs without coupling them to one specific retrieval or agent
runtime.

It was extracted from ContextPrime so domain specialization can be versioned,
distributed, and published independently.

## What It Includes

- domain pack interfaces
- declarative manifest schema
- filesystem loader
- registry and discovery helpers
- benchmark dataset loading
- CLI for pack inspection and validation
- a built-in legal example pack

## Install

```bash
pip install -e .
```

## CLI

```bash
contextprime-domain list-packs
contextprime-domain show-pack legal
contextprime-domain validate-pack ./examples/contracts
contextprime-domain test-pack ./examples/contracts
```

Module form:

```bash
python -m contextprime_domain list-packs
```

## Example Pack

See [examples/contracts/domain_pack.yaml](examples/contracts/domain_pack.yaml) for a minimal declarative pack.

## Design Notes

- Packs return semantic tag keys like `article` or `definition`. The host
  runtime is responsible for mapping those onto its own internal enums.
- The package stays lightweight on purpose. It does not import retrieval,
  agent, or API runtimes.
- `contextprime_domain.registry.get_default_domain_registry()` can read
  `DOMAIN_INCLUDE_BUILTIN` and `DOMAIN_SEARCH_PATHS` directly from the
  environment. If `contextprime` is installed, it can also fall back to that
  settings layer.
- The registry singleton is thread-safe; `get_default_domain_registry()` can
  be called concurrently from multiple threads.
- All manifest-supplied regex patterns are validated at load time. Invalid
  patterns raise `ValidationError` immediately. See `docs/AUTHORING.md` for
  guidance on avoiding catastrophic backtracking.
- Manifest-supplied file paths for benchmark datasets and model bindings are
  checked for containment within the pack directory. Paths that escape raise
  `ValueError`.
- Optional: install `contextprime-domain[full]` to enable correct pre-release
  version comparison via the `packaging` library.

## Repository Layout

```text
contextprime-domain-repo/
├── contextprime_domain/
├── docs/
├── examples/
├── tests/
├── pyproject.toml
└── RELEASE_NOTES.md
```

## Verification

```bash
python -m pytest -q
python -m contextprime_domain --json list-packs
```

## License

MIT. See [LICENSE](LICENSE).
