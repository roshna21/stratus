"""Everything that talks to Azure.

Azure-specific types stop at this boundary. The rest of Stratus works only
with the types defined in stratus.models.
"""

from stratus.azure.reader import (
    STRATUS_TAG,
    STRATUS_TAG_VALUE,
    AzureReader,
    FakeAzureReader,
    LiveAzureReader,
)

__all__ = [
    "AzureReader",
    "FakeAzureReader",
    "LiveAzureReader",
    "STRATUS_TAG",
    "STRATUS_TAG_VALUE",
]
