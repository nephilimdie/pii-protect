from app.plugins.base import BasePlugin


class ExampleEchoPlugin(BasePlugin):
    """Minimal no-op plugin used as the compatibility template."""

    name = "example.echo"

    async def on_anonymize(self, text, entities):
        return entities

    async def on_deanonymize(self, text, mapping):
        return text
