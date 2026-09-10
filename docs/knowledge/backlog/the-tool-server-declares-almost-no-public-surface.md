---
type: Backlog
---

# The tool server declares almost no public surface

**What I did.** Counted what this application imports out of `veupathdb_mcp`:

```
grep -rhoE "from veupathdb_mcp[.a-z_]* import|import veupathdb_mcp[.a-z_]*" \
  apps/api/src/pathfinder --include='*.py' | sort -u | wc -l
```

69 distinct import statements. Resolving each name against the installed
distribution gives 66 distinct names: 6 packages (`veupathdb_mcp`,
`.catalog`, `.gene_lookup`, `.tools`, `.wdk`, `.wdk.enrichment`) and 60
submodules underneath them.

**What I got.** 52 of those 60 submodules are named nowhere in their own
package's `__init__.py`. Two `__init__.py` in the distribution declare an
`__all__` at all: `catalog` names 34 symbols and `gene_lookup` names 8.
`veupathdb_mcp/__init__.py` is three lines holding a docstring and
`__version__`; `wdk/__init__.py`, `embeddings/__init__.py`,
`controls/__init__.py` and `tools/__init__.py` are empty files. So the
application reaches almost every one of these names by its file path inside
the package, not through a surface the package publishes.

**Why that's wrong.** The name of a file is not a contract. The sixth
import-linter contract in `apps/api/pyproject.toml`, "The application imports
no private module of an installed distribution", closes only the half that a
leading underscore marks: it lists four `veupathdb_mcp` modules by hand. The
other 52 carry no marking at all, so the tool server cannot rename, split or
merge one of its own files without breaking this application, and it has no way
to know which of its files are load-bearing here. The break arrives as an
`ImportError` at startup on the release that takes the new tag, not as a failed
gate in the repository that made the change.

**Why it happens.** `veupathdb_mcp` was extracted from this application, so its
modules kept the shape the application's import sites already had. Nothing in
the extraction added a package-level surface, and no gate asks for one.

**Fix.** In `VEuPathDB/ai-wdk-mcp`, give each package an `__init__.py` with an
`__all__` that re-exports what a consumer is meant to use, the way
`veupathdb_mcp.catalog` and `veupathdb_mcp.gene_lookup` already do; release a
tag; then rewrite this application's import sites onto the package names and
add the submodules to the sixth contract's `forbidden_modules`, so a new deep
import fails `uv run lint-imports` here.

**What you'd get.** The count above falls from 66 names to the handful of
packages that publish a surface, and a file rename in the tool server is a
refactor in one repository instead of an outage in this one.
