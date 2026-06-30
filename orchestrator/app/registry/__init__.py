"""registry_search infrastructure for stack-check (and later triage/portfolio/
registry-maintenance). Loads the GitHub-YAML capability registry, applies the
locked flatten layer, and answers queries deterministically.
"""

from .flatten import flatten_record, flatten_records
from .search import registry_search
from .source import FilesystemRegistry, InMemoryRegistry, RegistrySource

__all__ = [
    "flatten_record",
    "flatten_records",
    "registry_search",
    "RegistrySource",
    "InMemoryRegistry",
    "FilesystemRegistry",
]
