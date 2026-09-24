---
type: Backlog
---

# A private dataset is uploaded and analysed

Release a16. A researcher's own expression data cannot enter PathFinder; every
analysis runs on the site's curated studies. VEuPathDB's VDI takes a user upload
and installs it as an EDA study in that user's account, and the client library
already has a VDI client.

## What

An upload flow in the EDA tab: the file goes to VDI under the researcher's own
token, the install is polled as a durable task with progress rows, and once the
study is installed it appears in the study picker under "Your datasets". The
existing analysis path (subset, DESeq2, export as a step) runs on it unchanged,
because an installed user dataset is an EDA study like any other.

## Constraints

The upload runs under the researcher's WDK token, never the service token; a
failed install is reported with VDI's own message; the dataset is private to the
account and PathFinder stores no copy of the file. Regression tests: a recorded
VDI install sequence drives the task to completion; the picker lists the study;
a DESeq2 run on it exports a step with the site's count.
