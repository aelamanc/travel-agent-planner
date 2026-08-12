"""Single import site for the Anthropic async client.

Construction never requires ANTHROPIC_API_KEY to be set — the SDK only
raises on an actual API call, not at client construction — so strategies
can be instantiated (and tested) without a key.
"""

from anthropic import AsyncAnthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def get_async_client() -> AsyncAnthropic:
    return AsyncAnthropic()
