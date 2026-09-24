---
type: Backlog
---

# The title and the compactor are metered

Two model calls of a turn spend tokens that no usage row records: the thread
title (`ai/conversation/title_generator.py::generate_conversation_title`, the
default provider's smallest model, once per turn with a user message) and the
scratchpad compaction (`ai/agents/compactor.py::build_compactor_agent`, run
from `ai/graph/nodes.py` when the verification digest settles). Both resolve
their model through `platform/model_keys.py::keyed_model`, so each already runs
on the key that pays for its provider; neither reports its `RunUsage`.

Charge each on the row of its payer with `turn_paid_by(model_id)`, the way the
Lead's residual is charged in `ai/graph/_lead_capture.py`, and decide whether
the thread's own usage chunks show them. The quota pill's figures and the
monthly allowance are short by these calls until then.
