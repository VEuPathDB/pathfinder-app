---
type: Convention
title: Recording the audit models
description: How the intron-check results under tests/fixtures/audit_models are written again from the library's recorded wires, with no site request, after a veupathdb-mcp release.
tags: [audit, fixtures, tests, veupathdb-mcp]
generated: { by: claude-code/opus-5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What the files are

`apps/api/src/pathfinder/tests/fixtures/audit_models/` holds four `IntronAudit`
results: `pkac_introns.json` (PcyM_0736700, MISSING_EXON), `afu8_introns.json`
(Afu8g00850, REPLACED), `agap7279_introns.json` (AGAP007279, an intron across an
assembly gap) and `agap3685_introns.json` (AGAP003685, RETAINED).
`tests/_support/audit_answers.py` loads them with `IntronAudit.model_validate_json`.

Each file is what `audit_intron_support` returns at the pinned veupathdb-mcp
release, run against the wire the library's own recorded tests
(`ai-wdk-mcp: tests/unit/audit/test_introns_recorded.py`) replay. The library's
test helpers patch every read, so the run makes no site request.

# When to record them again

Record them again in the change that takes a veupathdb-mcp release that changes
the intron check or its result model. A file that no longer validates fails
`tests/_support/audit_answers.py` at import.

# How

The installed release runs the check. The library checkout supplies only its
test helpers and its recorded wires, so it must be at the tag that
`apps/api/pyproject.toml` pins.

1. Put `~/repos/ai-wdk-mcp` at the pinned tag (the git command is the user's):
   `git -C ~/repos/ai-wdk-mcp switch --detach v0.2.0-b45`, with the tag read from
   `[tool.uv.sources]`.
2. From `apps/api`, run the recorder:

   ```bash
   PYTHONPATH=$HOME/repos/ai-wdk-mcp uv run python -m pytest \
     scripts/record_audit_models.py \
     -p tests.conftest -p tests.unit.conftest -p no:cacheprovider -q
   ```

   `scripts/record_audit_models.py` writes the four files. The two `-p` options
   load the library's conftests, which give each test a guest token and a
   settings source without a network.
3. Run `uv run pytest src/pathfinder/tests/unit/domain/audit -q`. A fact test
   that fails names a value the new release states differently. Change the
   expectation to the value the file now holds.
