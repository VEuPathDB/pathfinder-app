from pathfinder.ai.agents.state import ParamVocabSnapshot


def render_param_vocab(
    name: str,
    snap: ParamVocabSnapshot,
    *,
    indent: int = 6,
) -> list[str]:
    """Render one parameter's snapshot: name, type, help (what it does),
    default, and enumerated vocab. Shared by the discovery-instruction
    injection (planning/execution) and the Lead's Ledger detail view."""
    head_pad = " " * indent
    detail_pad = " " * (indent + 4)
    head = f"{head_pad}- `{name}` ({snap.param_type})"
    if snap.required:
        head += " [required]"
    if snap.default_value is not None:
        head += f" default={snap.default_value!r}"
    out = [head]
    if snap.help:
        out.append(f"{detail_pad}{snap.help}")
    if snap.allowed_values:
        out.extend(
            f"{detail_pad}• {v.value!r} - {v.display}" for v in snap.allowed_values
        )
    elif snap.allowed_values_tree:
        out.extend(
            f"{detail_pad}{line}" for line in snap.allowed_values_tree.splitlines()
        )
    else:
        out.append(f"{detail_pad}(no enumerated vocab - free-form value)")
    return out
