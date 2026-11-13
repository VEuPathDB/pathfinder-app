"""The budget every pinned sheet is rendered under."""

from __future__ import annotations

from collections.abc import Callable, Sequence

# The open sheets are re-sent on every request and no processor shortens them.
# 100,000 characters is about 25,000 tokens at four characters per token.
PINNED_SHEETS_MAX_CHARS = 100_000


def blocks_within_budget[KeyT](
    keys: Sequence[KeyT],
    render: Callable[[KeyT], str],
    render_cut: Callable[[KeyT], str],
    *,
    cut_last: bool = False,
) -> list[str]:
    """The rendered blocks, cut oldest first until they fit the budget.

    ``cut_last`` says whether the newest block may be cut too. A caller sets it
    when a cut block's values have another route; a caller whose newest block is
    the only place its values exist leaves it false.
    """
    blocks = [render(key) for key in keys]
    cuttable = keys if cut_last else keys[:-1]
    for index, key in enumerate(cuttable):
        if sum(map(len, blocks)) <= PINNED_SHEETS_MAX_CHARS:
            break
        blocks[index] = render_cut(key)
    return blocks
