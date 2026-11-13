---
type: Decision
title: A genome fact and a site link are read from the site
description: Explore and the Lead read records that are not genes with list_record_columns and read_search_table, Explore's catalog lookup names the record columns nearest its query, and the VEuPathDB links a message holds are read before the agent runs; a tool per record type, columns in the search ranking, FRAME holding the tools and a web fetch were rejected.
tags: [explore, lead, catalog, organism, orthomcl, links]
generated: { by: claude-code/opus-5.5, at: 2026-11-10T00:00:00Z }
status: stable
---

# What was decided

Gene counts, BUSCO scores and assembly versions are columns of the organism record
(`genecount`, `busco_genome`, `busco_protein`, `busco_lineage_dataset`), and OrthoMCL keeps
its proteome counts in the `DataSummary` table of its `helper` record. A search ranking never
finds a column, so Strategist read them from nowhere.

- `list_record_columns` and `read_search_table` (`ai/tools/standalone/record_reads.py`) wrap
  the tool server's records package for Explore and the Lead
  (`veupathdb-mcp: docs/knowledge/decisions/a-record-that-is-not-a-gene-is-read-as-a-table.md`). Either may name another
  site, so OrthoMCL reads the portal's organism record for a BUSCO score. A gene record type
  is refused: a gene result is a strategy step. Each row a read returns is a `ReadFact` of the
  turn, under a heading that names the search and how many rows show, so the facts part
  states the numbers and the reply does not.
- The message reader reads a question whose answer lists genomes or proteomes with the
  figures the site keeps about each as effect `none`, wants `look_up`
  (`ai/prompts/message_reading.md`). A count or a set of genes, proteins or groups a search
  finds stays effect `new`. The pinned Operational Spec asks for `frame_problem` only on a
  turn whose message asks for a build, or one not read.
- Explore's `search_for_searches` ends on a `recordColumns` entry with the columns and tables
  nearest its query (`record_columns_block`). A site that holds no genes also ranks the
  portal's. The entry is absent when none is close or the index does not answer, and FRAME's
  lookup carries none.
- A fresh Explore or Lead turn reads up to three links its message holds into a configured
  site (`ai/lead/linked_pages.py`), each within 30 seconds, and pins the readings under "Pages
  the message links to". A result page of a search that is not a gene search arrives as its
  rows; any other page arrives as what it names. A link to a site the deployment does not
  read is named as such.

# Rejected

- A tool per record type, such as an organism table: the catalog says what each site carries.
- Column matches inside the search ranking: a column would compete with the search that
  answers a gene question.
- The tools on FRAME: FRAME frames gene strategies, and a genome table answers no criterion;
  it would only grow every build's prompt.
- Fetching a page as a web page: the result rows load after the page opens, so a fetch reads
  nothing, and a link pasted into a web search finds nothing.

# What falsifies it

`tests/unit/ai/tools/test_record_reads.py`,
`tests/unit/ai/explore/test_explore_lookup_names_record_columns.py`,
`tests/unit/ai/lead/test_linked_pages.py`,
`tests/unit/ai/lead/test_the_spec_pin_asks_for_a_frame_only_on_a_build.py` and
`tests/unit/ai/graph/test_a_turn_reads_the_pages_its_message_links_to.py`.
