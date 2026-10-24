"""The Lead's rules for the reads that count a search without a step."""

COUNT_RULES = """\
- **A comparison of counts is a question, answered by ``compare_search_variants``.** "How does \
  that count compare with the reference strain", "would a domain search find more genes than \
  this name search", "how many would remain at 5-fold": each side is one variant. A variant \
  runs as an anonymous report, so no step is added and the strategy keeps its root and its \
  count; a variant of a search one step runs is also counted in the result in place. The card \
  shows every size, overlap and failed variant. State each side with ``[compare:<variant>]``, \
  say what the difference means for the question, and when one side answers it better, offer that change on a ``propose_changes`` \
  card; never join the sides into the strategy with a combine. A failed variant is stated with \
  its error. ``compare_variants_scored`` ranks the same variants against an attached control \
  set by the metric the researcher chose: report the winner and the trade-off, and a variant \
  whose scoring failed is reported as failed with its one error line, never another reason. \
  Each variant carries the control ids its result holds, which answer a membership question.
- **A count of a search the strategy does not run is ``count_search``.** "Would a domain \
  search find more genes" names a search no step runs, so ``compare_search_variants`` refuses \
  it: count it with ``count_search`` and answer in a sentence that names the search and \
  states the count with ``[compare:<label>]``. A name the \
  catalog does not list comes back with the searches the catalog lookup finds for it, so a \
  search is absent only when that lookup finds none.
- **A count per value of a column is counted on the step that holds the records.** \
  ``step_columns`` names the step's columns, then ``count_step_by_column`` counts one marked \
  countable. When no step holds those records, the question is a build (``new_strategy`` \
  with no strategy, ``extend_strategy`` on one), and the count follows the build, through a \
  transform when the records are a result's members. ``count_by_column`` counts only one \
  catalog search's whole result, unchanged, with no step, and only by a search name the \
  catalog lists. Name the value with the most and its count with \
  ``[tally:<id>.<value>]``, the total with ``[tally:<id>]`` and the number of values with \
  ``[tally:<id>:values]``; never a value's count for another number.
- **"Which of these genes also ..." is ``genes_in_search``.** It runs the search over the \
  gene ids, by default the records this conversation showed last, and changes nothing. A \
  record read never answers it. State each gene with ``[record:<id>]`` and the genes held with \
  ``[compare:asked genes,<label>:shared]``. When it holds none of them, say so, cite \
  ``[compare:asked genes]`` and state no shared count.
"""
