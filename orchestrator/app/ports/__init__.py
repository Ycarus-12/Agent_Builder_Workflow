"""External seams as ports. Application code depends on these interfaces, never
on a concrete provider (keep the seam — context §6, CLAUDE.md non-negotiables).
In-memory fakes let the whole spine run and test offline.
"""

from .datastore import Datastore, InMemoryDatastore
from .emailer import Emailer, InMemoryEmailer, SentEmail
from .gateway import FakeModelGateway, ModelGateway
from .identity import FakeIdentityProvider, IdentityProvider, RequestorIdentity

__all__ = [
    "ModelGateway",
    "FakeModelGateway",
    "Datastore",
    "InMemoryDatastore",
    "Emailer",
    "InMemoryEmailer",
    "SentEmail",
    "IdentityProvider",
    "FakeIdentityProvider",
    "RequestorIdentity",
]
