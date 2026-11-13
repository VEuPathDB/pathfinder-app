"""The eval corpus and the shapes it is made of.

This package holds data and pure functions only: the staged extract shape, the
first-pass redaction, the promoted case shape, the structural comparison, and
the file store under ``corpus/``. Nothing here reaches a database or a network,
so the extraction service, the curation command and the runner can all read it.
"""
