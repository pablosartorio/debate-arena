import asyncio
import logging
import uuid
from typing import Any

import config
from fastapi import WebSocket

from agents.personas import PERSONAS
from db.repository import DebateRepository
from graph.graph import build_graph
from graph.state import initial_state

logger = logging.getLogger(__name__)


_END_SENTINEL: dict = {"__sentinel__": "end"}


class DebateSession:
    """
    Maneja un debate por WebSocket: crea la queue, lanza el grafo como task,
    y drena la queue para enviar eventos al cliente. Una sola sesion activa
    por WebSocket; si entra un nuevo `start` se cancela la anterior.
    """

    def __init__(self, websocket: WebSocket, repo: DebateRepository):
        self.websocket = websocket
        self.repo = repo
        self._task: asyncio.Task | None = None
        self._drain_task: asyncio.Task | None = None
        self._queue: asyncio.Queue | None = None
        self._stop_event = asyncio.Event()
        self.debate_id: str | None = None
        # cache para que cancel() pueda persistir el status correcto
        self._final_status: str | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, payload: dict[str, Any]):
        # cancelar sesion anterior antes de empezar otra
        await self.cancel()

        debate_id = str(uuid.uuid4())
        self.debate_id = debate_id

        topic = payload.get("topic") or config.DEFAULT_TOPIC
        max_turns = int(payload.get("max_turns") or config.DEFAULT_MAX_TURNS)
        max_words = int(payload.get("max_words") or config.DEFAULT_MAX_WORDS)
        agent1_id = payload.get("agent1_id") or config.DEFAULT_AGENT1_ID
        agent2_id = payload.get("agent2_id") or config.DEFAULT_AGENT2_ID
        model = payload.get("model") or config.DEFAULT_MODEL

        if agent1_id not in PERSONAS or agent2_id not in PERSONAS:
            await self.websocket.send_json({"type": "error", "message": "Personaje no encontrado."})
            return

        enable_scouting = bool(payload.get("enable_scouting", config.ENABLE_SCOUTING_DEFAULT))
        enable_moderation = bool(payload.get("enable_moderation", config.ENABLE_MODERATION_DEFAULT))
        enable_tools = bool(payload.get("enable_tools", config.ENABLE_TOOLS_DEFAULT))
        research_mode = bool(payload.get("research_mode", config.RESEARCH_MODE_DEFAULT))

        # registrar el debate ANTES de iniciar el grafo: si la persistencia
        # falla preferimos saberlo aca, no a mitad del primer turno.
        try:
            await self.repo.create_debate(
                debate_id=debate_id,
                topic=topic,
                agent1_id=agent1_id,
                agent2_id=agent2_id,
                model=model,
                max_turns=max_turns,
                max_words=max_words,
            )
        except Exception:
            logger.exception("failed to create debate row; continuing without persistence")

        state = initial_state(
            debate_id=debate_id,
            topic=topic,
            max_turns=max_turns,
            max_words=max_words,
            agent1_id=agent1_id,
            agent2_id=agent2_id,
            model=model,
            enable_scouting=enable_scouting,
            enable_moderation=enable_moderation,
            enable_tools=enable_tools,
            research_mode=research_mode,
        )

        self._queue = asyncio.Queue(maxsize=config.WS_QUEUE_MAX_SIZE)
        self._stop_event = asyncio.Event()
        self._final_status = None

        graph = build_graph()
        graph_config = {
            "configurable": {
                "ws_queue": self._queue,
                "stop_event": self._stop_event,
                "debate_id": debate_id,
                "repo": self.repo,
            },
            # 4 nodos por turno (router + plan + speak + moderate) + scout + finalize.
            # Con max 50 turnos: ~202. 400 deja margen para Etapa 7 (intervene).
            "recursion_limit": 400,
        }

        self._task = asyncio.create_task(self._run_graph(graph, state, graph_config))
        self._drain_task = asyncio.create_task(self._drain())

    async def _run_graph(self, graph, state, graph_config):
        debate_id = self.debate_id
        try:
            await graph.ainvoke(state, config=graph_config)
            self._final_status = "completed"
        except asyncio.CancelledError:
            self._final_status = "stopped"
            raise
        except Exception as e:
            logger.exception("graph execution failed")
            self._final_status = "error"
            try:
                await self._queue.put({"type": "error", "message": str(e)})
            except Exception:
                pass
        finally:
            # asegurar que el draining termine aunque el grafo no haya emitido conversation_end
            try:
                self._queue.put_nowait(_END_SENTINEL)
            except asyncio.QueueFull:
                # forzar entrega
                try:
                    await asyncio.wait_for(self._queue.put(_END_SENTINEL), timeout=2.0)
                except Exception:
                    pass

            # persistir status final (si stop fue por cancelacion del WS, esto
            # corre en cancel() en su lugar para evitar race conditions)
            if debate_id and self._final_status and self._final_status != "stopped":
                try:
                    await self.repo.update_debate_status(debate_id, self._final_status)
                except Exception:
                    logger.exception("failed to update debate status to %s", self._final_status)

    async def _drain(self):
        assert self._queue is not None
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        self._queue.get(), timeout=config.WS_DRAIN_TIMEOUT_SECONDS
                    )
                except TimeoutError:
                    logger.warning("ws drain timed out, closing session")
                    break

                if event is _END_SENTINEL:
                    break

                try:
                    await self.websocket.send_json(event)
                except Exception:
                    logger.exception("websocket send failed")
                    break

                if event.get("type") == "conversation_end":
                    break
        except asyncio.CancelledError:
            raise

    async def stop(self):
        self._stop_event.set()

    async def cancel(self):
        """Cancela el debate en curso (si lo hay) y limpia tasks."""
        self._stop_event.set()
        debate_id = self.debate_id
        was_running = self.is_running

        for task in (self._task, self._drain_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # si cancelamos un debate que estaba corriendo, marcarlo como 'stopped'
        if was_running and debate_id and self._final_status in (None, "stopped"):
            try:
                await self.repo.update_debate_status(debate_id, "stopped")
            except Exception:
                logger.exception("failed to mark debate as stopped")

        self._task = None
        self._drain_task = None
        self._queue = None
        self.debate_id = None
        self._final_status = None
