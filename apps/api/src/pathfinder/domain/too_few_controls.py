from __future__ import annotations

from veupathdb_mcp.separation import TooFewControls

from pathfinder.domain.read_facts import ReadFact, ReadRow


def too_few_controls_fact(short: TooFewControls) -> ReadFact:
    return ReadFact(
        title="Too few controls for any search to beat chance",
        rows=[
            ReadRow(label="positive controls", value=str(short.positives)),
            ReadRow(label="negative controls", value=str(short.negatives)),
            ReadRow(
                label="best p-value any search can reach",
                value=f"{short.best_p_value:.3f}",
            ),
            ReadRow(label="a result needs p under", value=f"{short.threshold:g}"),
            ReadRow(label="negative controls to add", value=str(short.more_negatives)),
            ReadRow(
                label="or positive controls to add", value=str(short.more_positives)
            ),
        ],
    )


__all__ = ["too_few_controls_fact"]
