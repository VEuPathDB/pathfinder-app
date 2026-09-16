"""What ``build_error_directive`` tells the model after a tool failed."""

from __future__ import annotations

from pathfinder.ai.capabilities.error_classification import (
    build_error_directive,
)

_SAMPLE_NEXT_ACTIONS = [
    "Call search_for_searches to find the correct name",
    "Retry with the corrected search name",
]
_SAMPLE_DO_NOT = "Do not retry with the same invalid search name"
_SAMPLE_DETAIL = "Search 'GenesByBadName' does not exist on this site"


class TestBuildErrorDirectiveFormat:
    """The directive contains every required section."""

    def test_contains_error_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "ERROR:" in directive

    def test_contains_tool_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "TOOL:" in directive
        assert "search_genes" in directive

    def test_contains_next_actions_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "NEXT_ACTIONS:" in directive

    def test_contains_do_not_section(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "DO NOT:" in directive

    def test_contains_detail_section(self) -> None:
        detail = "server error details here"
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=detail,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "DETAIL:" in directive
        assert detail in directive

    def test_tool_name_appears_in_tool_line(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="get_strategy",
            tool_args={"id": "123"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "get_strategy" in directive

    def test_error_type_string_in_directive(self) -> None:
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "WDKError (TRANSIENT)" in directive

    def test_works_with_no_args(self) -> None:
        directive = build_error_directive(
            error_type="RuntimeError (UNKNOWN)",
            tool_name="my_tool",
            tool_args={},
            detail="something unexpected",
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "TOOL:" in directive
        assert "my_tool" in directive

    def test_next_actions_appear_in_output(self) -> None:
        actions = [
            "Call search_for_searches to find the correct name",
            "Retry with the corrected search name",
        ]
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=actions,
            do_not=_SAMPLE_DO_NOT,
        )
        assert actions[0] in directive
        assert actions[1] in directive

    def test_do_not_string_appears_in_output(self) -> None:
        do_not = "Do not retry with the same invalid search name"
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=do_not,
        )
        assert do_not in directive

    def test_detail_string_appears_in_output(self) -> None:
        detail = "Search 'GenesByOrthologPattern' returned 0 results - check JSESSIONID"
        directive = build_error_directive(
            error_type="WDKError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={},
            detail=detail,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert detail in directive

    def test_next_actions_are_numbered(self) -> None:
        actions = ["First action", "Second action", "Third action"]
        directive = build_error_directive(
            error_type="WDKError (TRANSIENT)",
            tool_name="search_genes",
            tool_args={},
            detail=_SAMPLE_DETAIL,
            next_actions=actions,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "1. First action" in directive
        assert "2. Second action" in directive
        assert "3. Third action" in directive


class TestBuildErrorDirectiveArgSanitization:
    """Long argument values are truncated to a bounded length."""

    _LONG_VALUE = "x" * 500

    def test_long_arg_value_is_truncated(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert self._LONG_VALUE not in directive

    def test_tool_line_stays_reasonable(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE, "extra": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        tool_line = next(
            (line for line in directive.splitlines() if line.startswith("TOOL:")),
            "",
        )
        assert len(tool_line) < 500

    def test_truncated_value_has_ellipsis(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": self._LONG_VALUE},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "..." in directive

    def test_short_args_not_truncated(self) -> None:
        directive = build_error_directive(
            error_type="NotFoundError (SEMANTIC)",
            tool_name="search_genes",
            tool_args={"query": "malaria"},
            detail=_SAMPLE_DETAIL,
            next_actions=_SAMPLE_NEXT_ACTIONS,
            do_not=_SAMPLE_DO_NOT,
        )
        assert "malaria" in directive
