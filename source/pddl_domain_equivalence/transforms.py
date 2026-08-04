"""Extension contract reserved for future controlled-compilation support.

No non-identity transform is enabled by the current comparator.  A future third level
can apply registered transforms, retain their certificates, and then reuse the level-two
and level-one checkers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .model import Domain


@dataclass(frozen=True)
class TransformedDomain:
    domain: Domain
    transform_name: str
    certificate: dict[str, Any]


class DomainTransform(Protocol):
    """A semantics-preserving, auditable domain-to-domain transformation."""

    name: str

    def apply(self, domain: Domain) -> TransformedDomain:
        """Return the transformed domain and a machine-readable map-back certificate."""


class IdentityTransform:
    name = "identity"

    def apply(self, domain: Domain) -> TransformedDomain:
        return TransformedDomain(domain, self.name, {"kind": "identity"})
