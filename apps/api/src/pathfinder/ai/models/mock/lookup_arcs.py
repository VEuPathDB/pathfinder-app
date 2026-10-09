"""The mock's answer to a pick refused for want of a lookup: it reads the
options first, then binds. The odorant-binding arc picks a family from the
name-ranked list, is refused, looks the concept up and binds the family the
lookup matched."""

from __future__ import annotations

import re
from collections.abc import Mapping

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart
from veupathdb_mcp.catalog import VocabLookup

from pathfinder.ai.models.mock.history import acted_tool_names
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    instructions_of,
    refusal_of,
    returns_of,
    structure_dropped,
)
from pathfinder.ai.models.mock.specs import (
    CriterionSpec,
    SpecPlan,
    criterion_replies,
    frame_call,
    leaf,
    without_dropped,
)

_DEMAND = re.compile(
    r"get_parameter_options\(search_name='(?P<search>[^']+)', "
    r"parameter_id='(?P<param>[^']+)'"
)
INTERPRO = "GenesByInterproDomain"
DOMAINS = "domain_typeahead"
AEDES = "Aedes aegypti LVP_AGWG"
# The InterPro entry of the CSP family a name-ranked list offers, and of the OBP
# family a lookup reaches.
CSP_FAMILY = "IPR005055"
OBP_FAMILY = "IPR006170"
OBP_PHRASINGS = ["odorant binding", "OBP", "PBP/GOBP"]


class _OptionsReply(ToolAnswer):
    name: str = ""
    vocab_lookup: VocabLookup | None = None


def looked_up(messages: list[ModelMessage], param: str) -> bool:
    """Whether a read of the run narrowed ``param`` by a query."""
    return any(
        reply.name == param and reply.vocab_lookup is not None
        for reply in returns_of(messages, "get_parameter_options", _OptionsReply)
    )


def looked_up_values(messages: list[ModelMessage], param: str) -> list[str] | None:
    found = [
        reply.vocab_lookup
        for reply in returns_of(messages, "get_parameter_options", _OptionsReply)
        if reply.name == param and reply.vocab_lookup is not None
    ]
    if not found:
        return None
    return [value for match in found[-1].matches for value in match.values]


def lookup_the_refused_pick(
    spec: SpecPlan,
    messages: list[ModelMessage],
    phrasings: Mapping[str, list[str]] | None = None,
) -> ToolCallPart | None:
    """The lookup the newest ``set_criterion`` refusal asks for, once, under
    the criterion's other values. The query is the phrasings given for the
    parameter, else the entries the criterion proposes."""
    refusal = refusal_of(messages, "set_criterion")
    found = _DEMAND.search(refusal or "")
    if found is None:
        return None
    search, param = found["search"], found["param"]
    if looked_up(messages, param):
        return None
    crit = next(
        c for c in spec.criteria if c.search_name == search and param in c.values
    )
    context = {
        name: value
        for name, value in crit.values.items()
        if value is not None and name != param
    }
    return scripted_call(
        "get_parameter_options",
        {
            "search_name": search,
            "parameter_id": param,
            "context_values": context,
            "query": (phrasings or {}).get(param) or crit.values[param],
        },
    )


def odorant_binding_spec(family: str) -> SpecPlan:
    """The Aedes odorant-binding criterion on one InterPro family."""
    domain = CriterionSpec(
        criterion_id="c_obp",
        text=f"{AEDES} odorant-binding protein genes",
        search_name=INTERPRO,
        role="seed",
        values={
            "organism": [AEDES],
            "domain_database": "INTERPRO",
            DOMAINS: [family],
            "domain_accession": "N/A",
        },
    )
    return SpecPlan(
        title=f"{AEDES} odorant-binding protein genes",
        criteria=(domain,),
        structure=leaf(domain),
    )


def odorant_binding_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Pick the CSP family until a lookup ran, then the OBP family it matched."""
    family = OBP_FAMILY if looked_up(messages, DOMAINS) else CSP_FAMILY
    spec = without_dropped(odorant_binding_spec(family), structure_dropped(messages))
    return lookup_the_refused_pick(
        spec, messages, {DOMAINS: OBP_PHRASINGS}
    ) or frame_call(
        spec,
        acted_tool_names(messages),
        criterion_replies(messages),
        instructions_of(messages),
    )


__all__ = [
    "AEDES",
    "CSP_FAMILY",
    "DOMAINS",
    "INTERPRO",
    "OBP_FAMILY",
    "OBP_PHRASINGS",
    "looked_up",
    "looked_up_values",
    "lookup_the_refused_pick",
    "odorant_binding_frame",
    "odorant_binding_spec",
]
