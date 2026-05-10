"""Aristas condicionales del grafo de debate."""

from typing import Literal

from graph.state import DebateState


def route_after_speak(state: DebateState) -> Literal["router", "end"]:
    """
    Despues de que un agente habla, decide si seguimos con el siguiente turno
    o terminamos el debate.
    """
    if state.get("stop_requested"):
        return "end"
    if state.get("error"):
        return "end"

    current_turn = state.get("current_turn", 0)
    max_turns = state.get("max_turns", 0)
    if current_turn >= max_turns:
        return "end"

    return "router"


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


def route_after_moderate(state: DebateState) -> Literal["intervene", "router"]:
    """
    Si el moderador marco una intervencion pendiente, vamos a intervene_node.
    Si no, volvemos al router para el siguiente turno.
    Stop/error siguen al router que termina el debate igual.
    """
    if state.get("stop_requested") or state.get("error"):
        return "router"
    if state.get("pending_intervention"):
        return "intervene"
    return "router"
