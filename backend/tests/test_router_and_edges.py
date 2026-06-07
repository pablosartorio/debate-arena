"""Tests del router_node y las funciones de edges.

Son nodos/funciones puras: state dict de entrada -> dict (o literal) de salida,
sin llamadas a LLM. Patrón AAA: arrange state, act (llamar la función),
assert resultado esperado.
"""

from graph.edges import route_after_moderate, route_after_speak, route_from_router
from graph.nodes.router_node import router_node

# ---------- router_node ----------


async def test_router_picks_first_agent_on_turn_zero():
    state = {
        "current_turn": 0,
        "turn_order": ["alice", "bob"],
        "max_turns": 4,
    }

    result = await router_node(state, config={})

    assert result["current_agent_id"] == "alice"
    assert result["debate_status"] == "speaking"


async def test_router_alternates_on_next_turn():
    state = {
        "current_turn": 1,
        "turn_order": ["alice", "bob"],
        "max_turns": 4,
    }

    result = await router_node(state, config={})

    assert result["current_agent_id"] == "bob"


async def test_router_wraps_around_after_full_rotation():
    # 2 % 2 = 0 -> vuelve al primer agente
    state = {
        "current_turn": 2,
        "turn_order": ["alice", "bob"],
        "max_turns": 4,
    }

    result = await router_node(state, config={})

    assert result["current_agent_id"] == "alice"


async def test_router_falls_back_to_agent_ids_when_no_turn_order():
    state = {
        "current_turn": 0,
        "agent1_id": "alice",
        "agent2_id": "bob",
        "max_turns": 4,
    }

    result = await router_node(state, config={})

    assert result["current_agent_id"] == "alice"


# ---------- route_from_router ----------


def test_route_from_router_continues_when_turns_remain():
    state = {"current_turn": 0, "max_turns": 4}
    assert route_from_router(state) == "speak"


def test_route_from_router_ends_when_max_turns_reached():
    state = {"current_turn": 4, "max_turns": 4}
    assert route_from_router(state) == "end"


def test_route_from_router_ends_on_stop_request():
    state = {"current_turn": 0, "max_turns": 4, "stop_requested": True}
    assert route_from_router(state) == "end"


# ---------- route_after_speak ----------


def test_route_after_speak_goes_to_moderate():
    state = {"current_turn": 1, "max_turns": 4}
    assert route_after_speak(state) == "moderate"


def test_route_after_speak_still_moderates_last_turn():
    # Aunque se hayan agotado los turnos, igual moderamos el ultimo turno:
    # el cierre lo decide route_after_moderate (asi el ultimo turno se puntua).
    state = {"current_turn": 4, "max_turns": 4}
    assert route_after_speak(state) == "moderate"


def test_route_after_speak_ends_on_error():
    state = {"current_turn": 1, "max_turns": 4, "error": "algo se rompió"}
    assert route_after_speak(state) == "end"


def test_route_after_speak_ends_on_stop():
    state = {"current_turn": 1, "max_turns": 4, "stop_requested": True}
    assert route_after_speak(state) == "end"


# ---------- route_after_moderate ----------


def test_route_after_moderate_returns_router_when_turns_remain():
    state = {"current_turn": 1, "max_turns": 4}
    assert route_after_moderate(state) == "router"


def test_route_after_moderate_ends_when_turns_exhausted():
    # El ultimo turno ya fue moderado; al estar agotados los turnos, cerramos.
    state = {"current_turn": 4, "max_turns": 4}
    assert route_after_moderate(state) == "end"


def test_route_after_moderate_goes_to_intervene_when_pending():
    state = {"current_turn": 1, "max_turns": 4, "pending_intervention": {"reason": "off_topic"}}
    assert route_after_moderate(state) == "intervene"


def test_route_after_moderate_skips_intervene_on_last_turn():
    # No tiene sentido intervenir sobre el ultimo turno: cerramos directamente.
    state = {
        "current_turn": 4,
        "max_turns": 4,
        "pending_intervention": {"reason": "off_topic"},
    }
    assert route_after_moderate(state) == "end"


def test_route_after_moderate_ends_on_stop():
    # Aunque haya intervención pendiente, si el debate fue stoppeado cerramos.
    state = {
        "current_turn": 1,
        "max_turns": 4,
        "pending_intervention": {"reason": "off_topic"},
        "stop_requested": True,
    }
    assert route_after_moderate(state) == "end"
