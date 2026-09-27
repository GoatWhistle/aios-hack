"""OpenAI-compatible gateways use explicit credentials and endpoint settings."""
from backend.contexts.assistant.infrastructure.llm.openrouter import OpenRouterClient


class OpenAICompatibleClient(OpenRouterClient):
    @property
    def provider(self) -> str:
        return "openai-compatible"
