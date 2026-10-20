# gatherer-source

## Input
- context.md
- _bmad/_config/manifest.yaml

## Output
work/source-receipt.json

## Contract
Collect source hashes using prepare-design.py; receipt schema: schemaVersion, sources[{path,sha256}],framework,version,scopeAmendment.

One artifact per node. Framework memlog updates use the unchanged BMAD helper as a deterministic side-effect. Preserve others' work. No approval, commit, push or app implementation.
