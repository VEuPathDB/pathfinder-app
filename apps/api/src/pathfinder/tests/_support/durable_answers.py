"""The results a finished durable task reports: a reduction and a parameter sweep."""

from __future__ import annotations

from typing import Any

PCA_RESULT: dict[str, Any] = {
    "statistic": {
        "id": "stat_pca",
        "kind": "pca",
        "title": "Principal components of 40 samples",
        "rows": [
            {"name": "samples", "value": "40 samples"},
            {"name": "groups", "value": "2 groups"},
            {"name": "PC1", "value": "61%"},
            {"name": "PC2", "value": "17%"},
        ],
    }
}

SWEEP_RESULT: dict[str, Any] = {
    "searchName": "GenesWithSignalPeptide",
    "objective": "mcc",
    "best": {"score": 0.8},
    "controlSet": {"id": "cs-signal", "name": "signal peptide controls"},
    "variants": [
        {
            "variantId": "v1",
            "status": "success",
            "params": {"signalp_version": {"type": "string", "value": "6.0"}},
            "score": 0.8,
            "positive": {
                "recoveredIds": ["PF3D7_0100100"],
                "missedIds": ["PF3D7_0100200"],
            },
            "negative": {"admittedIds": [], "excludedIds": ["PF3D7_0100300"]},
        }
    ],
}
