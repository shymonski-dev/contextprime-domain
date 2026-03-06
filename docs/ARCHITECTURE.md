# Architecture

`contextprime-domain` is intentionally narrow.

## Core Modules

- `base.py`: contracts and dataclasses
- `manifest.py`: declarative schema
- `loader.py`: filesystem loading and validation
- `registry.py`: in-process registry and discovery
- `cli.py`: user-facing pack tooling
- `legal.py`: built-in example pack

## Boundary

This package defines the domain-specialization layer only.

It does not own:

- chunking
- retrieval
- reranking
- synthesis
- API serving
- agent orchestration

Those belong in the host runtime.

## Integration Model

Host systems should:

1. load packs through `DomainRegistry`
2. map semantic tag keys to host-specific enums
3. consume query routing and synthesis metadata
4. optionally honor declared model bindings
