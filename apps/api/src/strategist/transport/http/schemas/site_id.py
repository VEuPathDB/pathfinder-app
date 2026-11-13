"""The bounded site-id type every request model uses.

The narrowest column holding a site id is String(50); an unbounded request
field lets a longer value reach INSERT, where the database error becomes a
500 instead of a 422.
"""

from typing import Annotated

from pydantic import Field

SiteId = Annotated[str, Field(min_length=1, max_length=50)]
