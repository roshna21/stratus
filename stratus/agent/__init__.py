"""The part of Stratus that reasons.

Exactly one thing here calls a language model: turning an ambiguous English
sentence into infrastructure configuration. Everything else in the project is
ordinary code, because everything else has one correct answer.

Which model does that reasoning sits behind the providers boundary, so it is
a configuration choice rather than something the code is welded to.
"""

from stratus.agent.generator import (
    GeneratedConfig,
    GeneratedFile,
    GenerationFailed,
    TerraformGenerator,
)
from stratus.agent.providers import (
    ModelProvider,
    ProviderResponse,
    TokenUsage,
    available_providers,
    get_provider,
)

__all__ = [
    "TerraformGenerator",
    "GeneratedConfig",
    "GeneratedFile",
    "GenerationFailed",
    "ModelProvider",
    "ProviderResponse",
    "TokenUsage",
    "get_provider",
    "available_providers",
]
