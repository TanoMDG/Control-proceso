from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.core import (AppliedLimit, Catalog, LaboratoryAnalysis, LaboratoryAnalysisResult, LaboratoryConfigurationSieve, LaboratoryDeviationEvent, LaboratoryDetermination, LaboratoryFrequency, LaboratoryGranulometryResult, LaboratoryPointDetermination, LaboratorySamplePoint, LaboratorySieve, LaboratoryUnit, Limit, LimitVersion, MUA, OperationalRecord, ReactionPlan)
from app.schemas import LaboratoryAnalysisInput
from app.services.limits import evaluate_limit


PENDING_CONFIGURATION = "Pendiente de configuracion: faltan puntos, determinaciones, unidades o frecuencias de laboratorio."


def effective_configuration(db: Session, point_id: UUID, configuration_id: UUID, on_date: date) -> LaboratoryPointDetermination:
    configuration = db.get(LaboratoryPointDetermination, configuration_id)
    if configuration is None or configuration.id_punto != point_id or not configuration.activo or not (configuration.vigente_desde <= on_date and (configuration.vigente_hasta_exclusiva is None or on_date < configuration.vigente_hasta_exclusiva)):
        raise HTTPException(status_code=422, detail="La determinacion no esta configurada para el punto y fecha de muestreo")
    point, determination, unit = db.get(LaboratorySamplePoint, point_id), db.get(LaboratoryDetermination, configuration.id_determinacion), db.get(LaboratoryUnit, configuration.id_unidad)
    if point is None or not point.activo or determination is None or not determination.activo or unit is None or not unit.activo:
        raise HTTPException(status_code=422, detail="La configuracion de laboratorio esta inactiva")
    return configuration


def configured_sieves(db: Session, configuration_id: UUID) -> set[UUID]:
    return set(db.scalars(select(LaboratoryConfigurationSieve.id_tamiz).join(LaboratorySieve).where(LaboratoryConfigurationSieve.id_configuracion == configuration_id, LaboratorySieve.activo.is_(True))))


def validate_context_links(db: Session, payload: LaboratoryAnalysisInput) -> None:
    if payload.id_mua and db.get(MUA, payload.id_mua) is None:
        raise HTTPException(status_code=422, detail="La MUA vinculada no existe")
    if payload.id_registro_stock:
        stock = db.get(OperationalRecord, payload.id_registro_stock)
        if stock is None or stock.modulo != "M3" or stock.datos.get("tipo_registro") != "stock_silo":
            raise HTTPException(status_code=422, detail="El vinculo de stock debe referir un registro M3 de stock de silo")
    if payload.id_registro_proceso:
        process = db.get(OperationalRecord, payload.id_registro_proceso)
        if process is None or process.estado == "ANULADO":
            raise HTTPException(status_code=422, detail="El vinculo de proceso debe referir un registro operativo vigente")
    if payload.id_producto:
        product = db.get(Catalog, payload.id_producto)
        if product is None or not product.activo or product.tipo != "producto":
            raise HTTPException(status_code=422, detail="El producto debe ser un catalogo activo de tipo producto")


def evaluate_result(db: Session, analysis: LaboratoryAnalysis, result: LaboratoryAnalysisResult) -> None:
    configuration = db.get(LaboratoryPointDetermination, result.id_configuracion)
    assert configuration is not None
    if configuration.id_limite is None:
        return
    version = db.scalar(select(LimitVersion).where(LimitVersion.id_limite == configuration.id_limite, LimitVersion.vigente_desde <= analysis.fecha_operativa, or_(LimitVersion.vigente_hasta_exclusiva.is_(None), LimitVersion.vigente_hasta_exclusiva > analysis.fecha_operativa), LimitVersion.estado != "CANCELADA").order_by(LimitVersion.vigente_desde.desc()))
    if version is None:
        return
    outcome = evaluate_limit(version, result.valor)
    applied = db.scalar(select(AppliedLimit).where(AppliedLimit.tabla_origen == "analisis_laboratorio_resultado", AppliedLimit.id_registro == result.id, AppliedLimit.campo == str(result.id_configuracion)))
    if applied is None:
        db.add(AppliedLimit(tabla_origen="analisis_laboratorio_resultado", id_registro=result.id, campo=str(result.id_configuracion), id_limite=configuration.id_limite, id_limite_version=version.id, valor_medido=result.valor, resultado=outcome))
    else:
        applied.id_limite_version, applied.valor_medido, applied.resultado = version.id, result.valor, outcome
    event = db.scalar(select(LaboratoryDeviationEvent).where(LaboratoryDeviationEvent.id_resultado == result.id, LaboratoryDeviationEvent.id_limite_version == version.id))
    if outcome == "FUERA_DE_RANGO" and version.id_desvio and db.get(ReactionPlan, version.id_desvio):
        if event is None:
            db.add(LaboratoryDeviationEvent(id_resultado=result.id, id_limite=configuration.id_limite, id_limite_version=version.id, id_desvio=version.id_desvio, valor_actual=result.valor))
        else:
            event.valor_actual, event.estado = result.valor, "ABIERTO"
    elif event is not None and event.estado != "INVALIDADO":
        event.estado = "INVALIDADO"


def store_analysis(db: Session, analysis: LaboratoryAnalysis, payload: LaboratoryAnalysisInput) -> None:
    if payload.instante_muestreo.tzinfo is None:
        raise HTTPException(status_code=422, detail="instante_muestreo debe incluir zona horaria")
    point = db.get(LaboratorySamplePoint, payload.id_punto)
    if point is None or not point.activo:
        raise HTTPException(status_code=422, detail="Punto de muestreo inexistente o inactivo")
    validate_context_links(db, payload)
    analysis.id_punto, analysis.fecha_operativa, analysis.turno_codigo, analysis.instante_muestreo = payload.id_punto, payload.fecha_operativa, payload.turno_codigo, payload.instante_muestreo
    analysis.id_mua, analysis.id_registro_stock, analysis.id_registro_proceso, analysis.silo, analysis.id_producto = payload.id_mua, payload.id_registro_stock, payload.id_registro_proceso, payload.silo, payload.id_producto
    received_configurations: set[UUID] = set()
    for item in payload.resultados:
        if item.id_configuracion in received_configurations:
            raise HTTPException(status_code=422, detail="No se puede repetir una determinacion en el mismo analisis")
        configuration = effective_configuration(db, payload.id_punto, item.id_configuracion, payload.fecha_operativa)
        determination = db.get(LaboratoryDetermination, configuration.id_determinacion)
        if determination.tipo_resultado != "NUMERICO":
            raise HTTPException(status_code=422, detail="La determinacion granulometrica debe cargarse por tamiz")
        unit = db.get(LaboratoryUnit, configuration.id_unidad)
        result = db.scalar(select(LaboratoryAnalysisResult).where(LaboratoryAnalysisResult.id_analisis == analysis.id, LaboratoryAnalysisResult.id_configuracion == item.id_configuracion))
        if result is None:
            result = LaboratoryAnalysisResult(id_analisis=analysis.id, id_configuracion=item.id_configuracion, valor=item.valor, unidad=unit.codigo)
            db.add(result); db.flush()
        else:
            result.valor, result.unidad = item.valor, unit.codigo
        evaluate_result(db, analysis, result)
        received_configurations.add(item.id_configuracion)
    grouped_sieves: dict[UUID, set[UUID]] = {}
    for item in payload.granulometria:
        configuration = effective_configuration(db, payload.id_punto, item.id_configuracion, payload.fecha_operativa)
        determination = db.get(LaboratoryDetermination, configuration.id_determinacion)
        if determination.tipo_resultado != "GRANULOMETRIA":
            raise HTTPException(status_code=422, detail="El tamiz solo es valido para una determinacion granulometrica configurada")
        allowed = configured_sieves(db, configuration.id)
        if item.id_tamiz not in allowed:
            raise HTTPException(status_code=422, detail="El tamiz no esta configurado para la determinacion y el punto")
        grouped_sieves.setdefault(item.id_configuracion, set())
        if item.id_tamiz in grouped_sieves[item.id_configuracion]:
            raise HTTPException(status_code=422, detail="No se puede repetir un tamiz en el mismo analisis")
        grouped_sieves[item.id_configuracion].add(item.id_tamiz)
        result = db.scalar(select(LaboratoryGranulometryResult).where(LaboratoryGranulometryResult.id_analisis == analysis.id, LaboratoryGranulometryResult.id_configuracion == item.id_configuracion, LaboratoryGranulometryResult.id_tamiz == item.id_tamiz))
        if result is None:
            db.add(LaboratoryGranulometryResult(id_analisis=analysis.id, id_configuracion=item.id_configuracion, id_tamiz=item.id_tamiz, valor=item.valor))
        else:
            result.valor = item.valor
    for configuration_id, sieves in grouped_sieves.items():
        if sieves != configured_sieves(db, configuration_id):
            raise HTTPException(status_code=422, detail="La torre granulometrica debe incluir exactamente los tamices configurados")
    if not payload.resultados and not payload.granulometria:
        raise HTTPException(status_code=422, detail="El analisis requiere al menos un resultado configurado")


def analysis_output(db: Session, analysis: LaboratoryAnalysis) -> dict:
    return {"id": analysis.id, "client_uuid": analysis.client_uuid, "id_punto": analysis.id_punto, "fecha_operativa": analysis.fecha_operativa, "turno_codigo": analysis.turno_codigo, "instante_muestreo": analysis.instante_muestreo, "id_mua": analysis.id_mua, "id_registro_stock": analysis.id_registro_stock, "id_registro_proceso": analysis.id_registro_proceso, "silo": analysis.silo, "id_producto": analysis.id_producto, "estado": analysis.estado, "revision": analysis.revision, "creado_por": analysis.creado_por, "resultados": list(db.scalars(select(LaboratoryAnalysisResult).where(LaboratoryAnalysisResult.id_analisis == analysis.id))), "granulometria": list(db.scalars(select(LaboratoryGranulometryResult).where(LaboratoryGranulometryResult.id_analisis == analysis.id)))}


def agenda(db: Session, start: datetime, end: datetime, point_id: UUID | None = None) -> dict:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise HTTPException(status_code=422, detail="El rango de agenda debe incluir zona horaria y ser valido")
    frequencies = list(db.scalars(select(LaboratoryFrequency).where(LaboratoryFrequency.activo.is_(True), LaboratoryFrequency.vigente_desde < end, or_(LaboratoryFrequency.vigente_hasta_exclusiva.is_(None), LaboratoryFrequency.vigente_hasta_exclusiva > start))))
    expected: list[dict] = []
    for frequency in frequencies:
        configuration = db.get(LaboratoryPointDetermination, frequency.id_configuracion)
        if configuration is None or not configuration.activo or (point_id and configuration.id_punto != point_id):
            continue
        cursor = frequency.vigente_desde
        step = timedelta(seconds=float(frequency.intervalo_horas) * 3600)
        while cursor < start:
            cursor += step
        while cursor < end and (frequency.vigente_hasta_exclusiva is None or cursor < frequency.vigente_hasta_exclusiva):
            expected.append({"id_configuracion": str(configuration.id), "id_punto": str(configuration.id_punto), "esperado_en": cursor, "vence_en": cursor + step})
            cursor += step
    analyses = list(db.scalars(select(LaboratoryAnalysis).where(LaboratoryAnalysis.estado != "ANULADO", LaboratoryAnalysis.instante_muestreo >= start, LaboratoryAnalysis.instante_muestreo < end)))
    result_times: dict[tuple[UUID, UUID], list[datetime]] = {}
    for analysis in analyses:
        for result in db.scalars(select(LaboratoryAnalysisResult).where(LaboratoryAnalysisResult.id_analisis == analysis.id)):
            result_times.setdefault((analysis.id_punto, result.id_configuracion), []).append(analysis.instante_muestreo)
        for result in db.scalars(select(LaboratoryGranulometryResult).where(LaboratoryGranulometryResult.id_analisis == analysis.id)):
            result_times.setdefault((analysis.id_punto, result.id_configuracion), []).append(analysis.instante_muestreo)
    for row in expected:
        performed = any(row["esperado_en"] <= sample < row["vence_en"] for sample in result_times.get((UUID(row["id_punto"]), UUID(row["id_configuracion"])), []))
        row["cumplido"] = performed
    total = len(expected)
    return {"desde": start, "hasta": end, "agenda": expected, "cumplimiento": {"esperados": total, "realizados": sum(1 for row in expected if row["cumplido"]), "porcentaje": round(100 * sum(1 for row in expected if row["cumplido"]) / total, 2) if total else None}, "mensaje_configuracion": None if total else PENDING_CONFIGURATION}
