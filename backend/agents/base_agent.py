import httpx
import json
from typing import AsyncIterator
from agents.personas import Persona
from config import OLLAMA_HOST


class BaseAgent:
    def __init__(self, persona: Persona, max_words: int):
        self.persona = persona
        self.max_words = max_words

    @property
    def id(self) -> str:
        return self.persona.id

    async def generate(
        self,
        history: list[dict],
        extra_system_context: str | None = None,
    ) -> AsyncIterator[str]:
        system_messages = [{"role": "system", "content": self.persona.system_prompt}]
        if extra_system_context:
            system_messages.append({"role": "system", "content": extra_system_context})
        messages = system_messages + history

        word_count = 0
        buffer = ""

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_HOST}/api/chat",
                json={"model": self.persona.model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("message", {}).get("content", "")
                    if not token:
                        continue

                    buffer += token
                    # contar palabras a medida que llegan
                    words_in_buffer = buffer.split()
                    new_words = len(words_in_buffer) - word_count

                    if word_count + new_words >= self.max_words:
                        # emitir hasta llegar al límite y cortar
                        remaining = self.max_words - word_count
                        if remaining > 0:
                            partial = " ".join(words_in_buffer[:remaining])
                            # emitir solo la parte nueva
                            yield partial[len(" ".join(words_in_buffer[:word_count])):].lstrip()
                        return

                    word_count += new_words
                    yield token

                    if chunk.get("done"):
                        return
