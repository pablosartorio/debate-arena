"""Aristas condicionales del grafo de debate."""

from typing import Literal

from graph.state import DebateState


def route_after_speak(state: DebateState) -> Literal["moderate", "end"]:
    """
    Despues de que un agente habla, SIEMPRE moderamos su turno —incluido el
    ultimo— salvo que haya error o stop, en cuyo caso cerramos directamente.

    La decision de "quedan turnos" se toma despues, en route_after_moderate.
    Asi todos los turnos se evaluan y los cumulative_scores quedan parejos
    (antes el ultimo turno se salteaba y sesgaba al ganador).
    """
    if state.get("stop_requested"):
        return "end"
    if state.get("error"):
        return "end"

    return "moderate"


def route_from_router(state: DebateState) -> Literal["speak", "end"]:
    """
    El router determina si hay un turno mas para correr.
    """
    if state.get("stop_requested"):
        return "end"
    if state.get("error"):
        return "end"

    current_turn = state.get("current_turn", 0)
    max_turns = state.get("max_turns", 0)
    if current_turn >= max_turns:
        return "end"

    return "speak"


def route_after_moderate(state: DebateState) -> Literal["intervene", "router", "end"]:
    """
    Tras moderar el turno decidimos el siguiente paso:
      - stop/error -> end (cerramos el debate).
      - turnos agotados -> end (no tiene sentido intervenir sobre el ultimo turno).
      - intervencion pendiente -> intervene (el moderador habla).
      - en otro caso -> router (siguiente turno).
    """
    if state.get("stop_requested") or state.get("error"):
        return "end"

    current_turn = state.get("current_turn", 0)
    max_turns = state.get("max_turns", 0)
    if current_turn >= max_turns:
        return "end"

    if state.get("pending_intervention"):
        return "intervene"
    return "router"
