---
type: Backlog
title: A failed import tells the researcher to upload again
description: VDI ends an import `failed` when the site's plugin faults and `invalid` when it refuses the data; the researcher's dataset listing shows both as the plugin's message, so a faulted upload of a correct file reads as a fault in the file.
tags: [eda, user-datasets, vdi]
generated: { by: claude-code/fable-5-1, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A failed import tells the researcher to upload again

**What I did.** The live private-dataset check uploaded the curated heat shock
counts (5,720 genes by 12 samples, stranded, no `label` column) to plasmodb as the
dev account, four times with the same bytes.

**What I got.** `ooZ5x1R1sN0YY` and `ldZ50VR8RQ0YR` ended `import: failed` with
`import exited with unexpected status 255`; `twZ5UARpAo0Zg` and `B9Z5gARpAQ1ZZ`
installed. The researcher's dataset listing
(`services/eda/private_datasets.py::_own`) shows a failed upload with that text
and nothing else, as the site's own page does.

**Why that's wrong.** The text names no fault in the file, because there is none:
the same bytes install on the next upload. A researcher reads it as a problem with
their counts and edits a correct file.

**Why it happens.** `_own` carries VDI's failure messages verbatim and does not
read the import status: `failed` is the plugin exiting with a status other than 0
or 99 (its own fault), `invalid` is the plugin refusing the data with exit 99 and a
message that names what is wrong.

**Fix.** The listing reads `status.import_.status`. A `failed` import says the
site's importer faulted and the same files can be uploaded again; an `invalid`
import carries the site's messages as it does now. The distinction is the client
library's (`veupathdb-py: docs/knowledge/wdk/rest/vdi-surface.md`).

**What you'd get.** The row for a faulted upload reads "The site's importer
faulted on this upload; upload the same files again", and only a refused upload
names a fault in the file.
