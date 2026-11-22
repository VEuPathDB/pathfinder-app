from __future__ import annotations

import pytest
from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    ParamValue,
    StringValue,
)

from strategist.domain.strategy import value_binding


@pytest.mark.parametrize(
    ("name", "value", "published", "at_default"),
    [
        ("organism", MultiPickValue(values=["b", "a"]), '["a","b"]', True),
        ("variation_sample_meta", FilterValue(), '{"filters": []}', True),
        ("variation_sample_meta", FilterValue(), "[]", False),
        ("text", StringValue(value="1"), "1.0", False),
        ("text", StringValue(value="1"), None, False),
    ],
    ids=["pick-order", "spaced-no-filter", "unread-wire", "string-spelling", "none"],
)
def test_a_value_is_at_the_default_the_site_publishes(
    name: str, value: ParamValue, published: str | None, at_default: bool
) -> None:
    assert value_binding._at_default(name, value, published) is at_default
