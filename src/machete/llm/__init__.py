from machete.llm.protocol import LLMProvider, MockProvider

__all__ = ["LLMProvider", "MockProvider"]


def __getattr__(name: str):
    """Lazy imports for optional providers — avoids ImportError if SDK not installed."""
    if name == "AnthropicProvider":
        from machete.llm.protocol import AnthropicProvider

        return AnthropicProvider
    if name == "OpenAIProvider":
        from machete.llm.protocol import OpenAIProvider

        return OpenAIProvider
    raise AttributeError(f"module 'machete.llm' has no attribute {name!r}")
