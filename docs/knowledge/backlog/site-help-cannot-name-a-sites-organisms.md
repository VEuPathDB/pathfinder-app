---
type: Backlog
---

# Site help cannot name a site's organisms

**What I did.** Two site_help threads. On cryptodb: "Which VEuPathDB sites are there, what does this one cover, and what is the difference between a search and a transform?" On toxodb (`525c0209-66d8-4abf-827b-c8624e884cbd`): "Which Toxoplasma strains does this site cover, and what is the difference between a search and a transform here?"

**What I got.** Both answered every other part well (14 sites listed, the site described, search against transform explained). On the organism question, cryptodb's reply said the catalog tool "does not expose the individual organism names", and toxodb's said "the available catalog tools do not return the actual strain-name values, so I can't reliably enumerate the strains from them", after four tool calls (`list_veupathdb_sites`, `describe_site`, `wdk_list_record_types`, `wdk_search_for_searches`).

**Why that's wrong.** "Which organisms does this site cover" is the first question a researcher asks a site's help assistant, the site's own home page answers it, and the assistant is honest that it cannot. Twice out of two threads that asked.

**Why it happens.** `assistants/site_help/` gives the agent two catalog tools plus a declared wdk-mcp source; none of them reads a parameter's vocabulary, and the organism list lives in the `organism` parameter of the site's searches (a tree-box vocabulary the catalog already holds, the same one `get_parameter_options` serves to FRAME).

**Fix.** `describe_site` carries the site's organism list, read from the catalog's `organism` parameter vocabulary at the top level (species, not every strain, with a count of the strains under each). If the vocabulary is large, the tool returns the top-level terms and says how many leaves each has. Red first: `describe_site("toxodb")` names Toxoplasma gondii and its strain count; the site_help agent's answer to the organism question quotes them.

**What you'd get.** "ToxoDB covers Toxoplasma gondii (12 strains including ME49, GT1, VEG), Hammondia, Neospora ...", from the catalog rather than from the model's memory.
