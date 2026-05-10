import asyncio
from fastapi.websockets import WebSocket
from agents.base_agent import BaseAgent


def _trim_to_sentence(text: str) -> str:
    """Recorta hasta el último signo de puntuación; si no hay ninguno, agrega un punto para que el historial no quede colgado."""
    last = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    if last > len(text) // 3:
        return text[: last + 1]
    return text.rstrip() + "."


class Orchestrator:
    def __init__(self, agents: list[BaseAgent], topic: str, max_turns: int):
        self.agents = agents
        self.topic = topic
        self.max_turns = max_turns
        self._stop = False
        # lista de (agent_id, text) para toda la conversación
        self._log: list[tuple[str, str]] = []

    def stop(self):
        self._stop = True

    def _history_for(self, agent: BaseAgent) -> list[dict]:
        """
        Construye el historial desde la perspectiva del agente dado.
        Sus propias respuestas son 'assistant', las del otro son 'user'.
        El primer mensaje siempre es 'user' (la apertura del debate).
        """
        if not self._log:
            return [{"role": "user", "content": f"El tema del debate es: {self.topic}. Presentá tu postura inicial."}]

        messages = []
        for speaker_id, text in self._log:
            role = "assistant" if speaker_id == agent.id else "user"
            # fusionar mensajes consecutivos del mismo role para evitar errores en algunos modelos
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + text
            else:
                messages.append({"role": role, "content": text})

        # el último mensaje debe ser 'user' para que el agente responda
        if messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "Continuá tu argumento."})

        return messages

    async def run(self, websocket: WebSocket):
        for turn in range(self.max_turns):
            if self._stop:
                break

            agent = self.agents[turn % len(self.agents)]
            history = self._history_for(agent)
            full_response = ""

            await websocket.send_json({"type": "turn_start", "agent": agent.id})

            try:
                async for token in agent.generate(history):
                    if self._stop:
                        break
                    full_response += token
                    await websocket.send_json({"type": "token", "agent": agent.id, "content": token})
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})
                return

            if full_response:
                self._log.append((agent.id, _trim_to_sentence(full_response)))

            await websocket.send_json({"type": "turn_end", "agent": agent.id})
            await asyncio.sleep(0.2)

        await websocket.send_json({"type": "conversation_end"})
