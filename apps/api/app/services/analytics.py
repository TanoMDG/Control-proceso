from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import AnalyticsRun, AppliedLimit, DeviationEvent, LaboratoryAnalysis, LaboratoryAnalysisResult, LaboratoryDeviationEvent, LaboratoryPointDetermination, LaboratorySamplePoint, LaboratoryUnit, LimitVersion, MaintenanceCorrelation, MaintenanceRecord, OperationalRecord, ProductionCalendar, ShiftFact, TemporalMeasurementFact

MEASUREMENTS = {"M1": {"humedad_verdes": "%", "residuo": "%", "aeroseparador": "%"}, "M2": {"humedad_salida": "%", "dosificacion_calc": "L/t"}, "M3": {"humedad": "%", "temperatura": "C", "humedad_ksider": "%", "toneladas_calculadas": "t"}, "M9": {"humedad_pasta": "%", "presion": "kg/cm2", "humedad_residual": "%"}}


def number(value):
    try: return Decimal(str(value))
    except Exception: return None


def rebuild_analytics(db: Session) -> AnalyticsRun:
    run = AnalyticsRun(estado="EN_PROCESO", alcance={"origen": "registro_operativo"})
    db.add(run); db.flush()
    # PLC facts are acquired independently and must survive an operational KPI rebuild.
    db.execute(delete(TemporalMeasurementFact).where(TemporalMeasurementFact.tabla_origen.in_(("registro_operativo", "registro_mantenimiento"))))
    db.execute(delete(ShiftFact))
    records = list(db.scalars(select(OperationalRecord).where(OperationalRecord.estado != "ANULADO").order_by(OperationalRecord.instante_medicion)))
    applied = {(row.id_registro, row.campo): row for row in db.scalars(select(AppliedLimit).where(AppliedLimit.tabla_origen == "registro_operativo"))}
    buckets = defaultdict(lambda: {"values": defaultdict(list), "stops": [], "deviations": defaultdict(int), "maintenance_types": defaultdict(int), "maintenance_correlations": defaultdict(int)})
    for record in records:
        line = record.datos.get("linea") if record.modulo in {"M8", "M9", "M10"} else None
        key = (record.fecha_operativa, record.turno_codigo, line or "PLANTA", record.sector)
        bucket = buckets[key]
        for metric, unit in MEASUREMENTS.get(record.modulo, {}).items():
            value = number(record.datos.get(metric))
            if value is None: continue
            evaluation = applied.get((record.id, metric))
            version = db.get(LimitVersion, evaluation.id_limite_version) if evaluation else None
            context = {"modulo": record.modulo, "sector": record.sector, "linea": line, "prensa": record.datos.get("prensa"), "formato": record.datos.get("formato")}
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
        if record.modulo == "M8":
            duration = number(record.datos.get("duracion_min"))
            if duration is not None:
                bucket["values"]["duracion_vaciado_min"].append(float(duration))
                bucket["values"]["vaciados_tolva"].append(1.0)
        if record.modulo == "M10":
            bucket["values"]["controles_espesor"].append(1.0)
            for detail in record.datos.get("detalles", []):
                value = number(detail.get("espesor_mm"))
                if value is None:
                    continue
                field = f"espesor_mm:{detail['prensa']}:{detail['cavidad']}:{detail['sector']}"
                evaluation = applied.get((record.id, field))
                version = db.get(LimitVersion, evaluation.id_limite_version) if evaluation else None
                context = {"modulo": "M10", "sector": record.sector, "linea": line, "prensa": detail["prensa"], "cavidad": detail["cavidad"], "sector_grilla": detail["sector"], "formato": record.datos.get("formato")}
                if version:
                    context["banda_limite"] = {"min": float(version.valor_min) if version.valor_min is not None else None, "max": float(version.valor_max) if version.valor_max is not None else None, "resultado": evaluation.resultado}
                db.add(TemporalMeasurementFact(fecha_operativa=record.fecha_operativa, turno_codigo=record.turno_codigo, instante_operativo=record.instante_medicion, tabla_origen="registro_operativo", id_registro_origen=record.id, metrica="espesor_mm", valor=value, unidad="mm", origen_dato=record.origen_dato, contexto=context))
                bucket["values"]["espesor_mm"].append(float(value))
            dispersion = number(record.datos.get("dispersion_mm"))
            if dispersion is not None:
                bucket["values"]["dispersion_mm"].append(float(dispersion))
    correlations_by_record = defaultdict(list)
    for correlation in db.scalars(select(MaintenanceCorrelation)):
        correlations_by_record[correlation.id_registro_mantenimiento].append(correlation)
    for record in db.scalars(select(MaintenanceRecord).order_by(MaintenanceRecord.inicio)):
        key = (record.fecha_operativa, record.turno_codigo, "PLANTA", "Mantenimiento")
        bucket = buckets[key]
        bucket["values"]["intervenciones_mantenimiento"].append(1.0)
        bucket["maintenance_types"][record.tipo] += 1
        if record.fin is not None:
            duration = (record.fin - record.inicio).total_seconds() / 3600
            bucket["values"]["horas_mantenimiento"].append(duration)
            db.add(TemporalMeasurementFact(fecha_operativa=record.fecha_operativa, turno_codigo=record.turno_codigo, instante_operativo=record.inicio, tabla_origen="registro_mantenimiento", id_registro_origen=record.id, metrica="duracion_mantenimiento_horas", valor=Decimal(str(duration)), unidad="h", origen_dato="digital_directo", contexto={"modulo": "M7", "sector": "Mantenimiento", "equipo_id": str(record.id_equipo), "tipo": record.tipo, "madirex_informativo": bool(record.campos_madirex)}))
        for correlation in correlations_by_record[record.id]:
            bucket["maintenance_correlations"][correlation.tipo_referencia] += 1
    lab_results = defaultdict(list)
    for analysis in db.scalars(select(LaboratoryAnalysis).where(LaboratoryAnalysis.estado != "ANULADO").order_by(LaboratoryAnalysis.instante_muestreo)):
        point = db.get(LaboratorySamplePoint, analysis.id_punto)
        if point is None:
            continue
        key = (analysis.fecha_operativa, analysis.turno_codigo, "LABORATORIO", point.sector)
        bucket = buckets[key]
        bucket["values"]["analisis_laboratorio"].append(1.0)
        for result in db.scalars(select(LaboratoryAnalysisResult).where(LaboratoryAnalysisResult.id_analisis == analysis.id)):
            configuration = db.get(LaboratoryPointDetermination, result.id_configuracion)
            if configuration is None:
                continue
            unit = db.get(LaboratoryUnit, configuration.id_unidad)
            metric = f"laboratorio:{configuration.id_determinacion}"
            value = number(result.valor)
            if value is not None:
                lab_results[analysis.id].append(result.id)
                bucket["values"]["resultados_laboratorio"].append(1.0)
                bucket["values"][metric].append(float(value))
                applied = db.scalar(select(AppliedLimit).where(AppliedLimit.tabla_origen == "analisis_laboratorio_resultado", AppliedLimit.id_registro == result.id))
                version = db.get(LimitVersion, applied.id_limite_version) if applied else None
                context = {"modulo": "M17", "sector": point.sector, "punto_muestreo": point.codigo, "id_configuracion": str(configuration.id)}
                if version:
                    context["banda_limite"] = {"min": float(version.valor_min) if version.valor_min is not None else None, "max": float(version.valor_max) if version.valor_max is not None else None, "resultado": applied.resultado}
                db.add(TemporalMeasurementFact(fecha_operativa=analysis.fecha_operativa, turno_codigo=analysis.turno_codigo, instante_operativo=analysis.instante_muestreo, tabla_origen="analisis_laboratorio", id_registro_origen=analysis.id, metrica=metric, valor=value, unidad=unit.codigo if unit else None, origen_dato="digital_directo", contexto=context))
    for event in db.scalars(select(LaboratoryDeviationEvent)):
        result = db.get(LaboratoryAnalysisResult, event.id_resultado)
        analysis = db.get(LaboratoryAnalysis, result.id_analisis) if result else None
        point = db.get(LaboratorySamplePoint, analysis.id_punto) if analysis else None
        if analysis and point and analysis.estado != "ANULADO":
            buckets[(analysis.fecha_operativa, analysis.turno_codigo, "LABORATORIO", point.sector)]["deviations"][event.estado] += 1
    for event in db.scalars(select(DeviationEvent)):
        record = db.get(OperationalRecord, event.id_registro)
        if record and record.estado != "ANULADO":
            line = record.datos.get("linea") if record.modulo in {"M8", "M9", "M10"} else None
            buckets[(record.fecha_operativa, record.turno_codigo, line or "PLANTA", record.sector)]["deviations"][event.estado] += 1
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
        metrics = {metric: round(sum(values) if metric in {"vaciados_tolva", "controles_espesor", "intervenciones_mantenimiento", "horas_mantenimiento", "analisis_laboratorio", "resultados_laboratorio"} else sum(values) / len(values), 5) for metric, values in bucket["values"].items()}
        metrics.update({"horas_programadas": scheduled, "indisponibilidad_horas": union, "disponibilidad": (scheduled - union) / scheduled if scheduled else None, "paradas": bucket["stops"], "desvios_por_estado": dict(bucket["deviations"]), "mantenimiento_por_tipo": dict(bucket["maintenance_types"]), "correlaciones_mantenimiento": dict(bucket["maintenance_correlations"])})
        db.add(ShiftFact(fecha_operativa=key[0], turno_codigo=key[1], linea_clave=key[2], contexto_clave=key[3], metricas=metrics))
    run.estado, run.completado_en = "COMPLETADO", datetime.now(timezone.utc)
    return run
