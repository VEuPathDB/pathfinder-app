"""Eval-data governance: the consent flag, extraction into staging, curation.

Raw conversations never reach the corpus. Extraction runs for consenting users
only, redacts, and writes a staged candidate; curation promotes a redacted case
into the repo corpus and ends the association.
"""
