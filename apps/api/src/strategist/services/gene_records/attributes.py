"""The attribute each gene record type names a gene's product in."""

_PRODUCT_ATTRIBUTE = {"transcript": "gene_product", "gene": "product"}


def product_attribute(record_type: str) -> str | None:
    """The attribute that holds the gene product on the record type, or None
    when the record type names no gene product."""
    return _PRODUCT_ATTRIBUTE.get(record_type)
