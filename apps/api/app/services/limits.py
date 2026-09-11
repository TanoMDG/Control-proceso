from decimal import Decimal

from app.models.core import LimitVersion


def evaluate_limit(version: LimitVersion, value: Decimal) -> str:
    """Evaluates configured operators; inclusivity is never inferred by the client."""
    if version.nivel == "INFORMATIVO" or (version.valor_min is None and version.valor_max is None):
        return "INFORMATIVO"
    if version.valor_min is not None:
        if version.operador_min == ">" and value <= version.valor_min:
            return "FUERA_DE_RANGO"
        if version.operador_min == ">=" and value < version.valor_min:
            return "FUERA_DE_RANGO"
    if version.valor_max is not None:
        if version.operador_max == "<" and value >= version.valor_max:
            return "FUERA_DE_RANGO"
        if version.operador_max == "<=" and value > version.valor_max:
            return "FUERA_DE_RANGO"
    return "EN_RANGO"
