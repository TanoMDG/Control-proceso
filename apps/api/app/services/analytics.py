from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import AnalyticsRun, AppliedLimit, DeviationEvent, LimitVersion, OperationalRecord, ProductionCalendar, ShiftFact, TemporalMeasurementFact

MEASUREMENTS = {"M1": {"humedad_verdes": "%", "residuo": "%", "aeroseparador": "%"}, "M2": {"humedad_salida": "%", "dosificacion_calc": "L/t"}, "M3": {"humedad": "%", "temperatura": "C", "humedad_ksider": "%", "toneladas_calculadas": "t"}}


def number(value):
    try: return Decimal(str(value))
    except Exception: return None


def rebuild_analytics(db: Session) -> AnalyticsRun:
    run = AnalyticsRun(estado="EN_PROCESO", alcance={"origen": "registro_operativo"})
    db.add(run); db.flush()
    db.execute(delete(TemporalMeasurementFact)); db.execute(delete(ShiftFact))
    records = list(db.scalars(select(OperationalRecord).where(OperationalRecord.estado != "ANULADO").order_by(OperationalRecord.instante_medicion)))
    applied = {(row.id_registro, row.campo): row for row in db.scalars(select(AppliedLimit).where(AppliedLimit.tabla_origen == "registro_operativo"))}
    buckets = defaultdict(lambda: {"values": defaultdict(list), "stops": [], "deviations": defaultdict(int)})
    for record in records:
        key = (record.fecha_operativa, record.turno_codigo, "PLANTA", record.sector)
        bucket = buckets[key]
        for metric, unit in MEASUREMENTS.get(record.modulo, {}).items():
            value = number(record.datos.get(metric))
            if value is None: continue
            evaluation = applied.get((record.id, metric))
            version = db.get(LimitVersion, evaluation.id_limite_version) if evaluation else None
            context = {"modulo": record.modulo, "sector": record.sector}
            if version: context["banda_limite"] = {"min": float(version.valor_min) if version.valor_min is not None else None, "max": float(version.valor_max) if version.valor_max is not None else None, "resultado": evaluation.resultado}
            db.add(TemporalMeasurementFact(fecha_operativa=record.fecha_operativa, turno_codigo=record.turno_codigo, instante_operativo=record.instante_medicion, tabla_origen="registro_operativo", id_registro_origen=record.id, metrica=metric, valor=value, unidad=unit, origen_dato=record.origen_dato, contexto=context))
            bucket["values"][metric].append(float(value))
        if record.modulo == "M1" and record.datos.get("tipo_registro") == "resumen_turno":
            for metric in ("toneladas_procesadas", "horas_marcha"):
                value = number(record.datos.get(metric))
                if value is not None: bucket["values"][metric].append(float(value))
        if record.modulo == "M6" and record.datos.get("fin"):
            duration = number(record.datos.get("duracion_corregida_horas") or record.datos.get("duracion_calculada_horas"))
            if duration is not None: bucket["stops"].append({"causa": record.datos.get("causa", "SIN_CAUSA"), "duracion_horas": float(duration), "inicio": record.datos.get("inicio"), "fin": record.datos.get("fin")})
    for event in db.scalars(select(DeviationEvent)):
        record = db.get(OperationalRecord, event.id_registro)
        if record and record.estado != "ANULADO": buckets[(record.fecha_operativa, record.turno_codigo, "PLANTA", record.sector)]["deviations"][event.estado] += 1
    calendar = {(row.fecha_operativa, row.turno_codigo): float(row.horas_programadas or 0) for row in db.scalars(select(ProductionCalendar).where(ProductionCalendar.programado.is_(True)))}
    for key, bucket in buckets.items():
        scheduled = calendar.get(key[:2], 0)
        intervals = sorted((datetime.fromisoformat(stop["inicio"]), datetime.fromisoformat(stop["fin"])) for stop in bucket["stops"])
        union, last = 0.0, None
        for start, end in intervals:
            if last is None or start > last[1]:
                union += (end - start).total_seconds() / 3600; last = [start, end]
            elif end > last[1]:
                union += (end - last[1]).total_seconds() / 3600; last[1] = end
        metrics = {metric: sum(values) / len(values) for metric, values in bucket["values"].items()}
        metrics.update({"horas_programadas": scheduled, "indisponibilidad_horas": union, "disponibilidad": (scheduled - union) / scheduled if scheduled else None, "paradas": bucket["stops"], "desvios_por_estado": dict(bucket["deviations"])})
        db.add(ShiftFact(fecha_operativa=key[0], turno_codigo=key[1], linea_clave=key[2], contexto_clave=key[3], metricas=metrics))
    run.estado, run.completado_en = "COMPLETADO", datetime.now(timezone.utc)
    return run
