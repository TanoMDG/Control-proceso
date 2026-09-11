from __future__ import annotations


RECORD_TRANSITIONS = {
    "BORRADOR": {"CERRADO", "ANULADO"},
    "CERRADO": {"VALIDADO", "ANULADO"},
    "VALIDADO": {"ANULADO"},
    "ANULADO": set(),
}


def can_transition_record(current: str, target: str, *, actor_role: str, is_creator: bool) -> bool:
    if target not in RECORD_TRANSITIONS.get(current, set()):
        return False
    if actor_role in {"SUPERVISION", "ADMIN"}:
        return True
    return current == "BORRADOR" and is_creator and target == "CERRADO"


def can_edit_record(state: str, *, actor_role: str, is_creator: bool, shift_closed: bool) -> bool:
    if actor_role in {"SUPERVISION", "ADMIN"}:
        return state != "ANULADO"
    return state == "BORRADOR" and is_creator and not shift_closed
