from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol, Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import PlcAcquisitionStatus, PlcRawReading, PlcReadSource, PlcReadTag, PlcReadingAggregate, TemporalMeasurementFact


QUALITY_RANK = {"GOOD": 0, "UNCERTAIN": 1, "BAD": 2}


@dataclass(frozen=True)
class PlcReadValue:
    tag_id: UUID
    raw_value: Decimal
    source_timestamp: datetime
    quality: str


class ReadOnlyPlcAdapter(Protocol):
    """Read-only boundary; adapters expose no write operation."""

    name: str

    def read(self, tags: Sequence[PlcReadTag]) -> list[PlcReadValue]: ...


class TestSimulatorAdapter:
    """The sole F6 adapter. Values must be explicitly configured per test tag."""

    name = "TEST_SIMULATOR"

    def read(self, tags: Sequence[PlcReadTag]) -> list[PlcReadValue]:
        timestamp = datetime.now(timezone.utc)
        values: list[PlcReadValue] = []
        for tag in tags:
            if tag.valor_simulado_crudo is None or tag.calidad_simulada is None:
                continue
            values.append(PlcReadValue(tag.id, tag.valor_simulado_crudo, timestamp, tag.calidad_simulada))
        return values


def readonly_adapter(source: PlcReadSource) -> ReadOnlyPlcAdapter:
    if source.adaptador != "TEST_SIMULATOR":
        raise ValueError("Adaptador de solo lectura no disponible")
    return TestSimulatorAdapter()


def aggregation_start(timestamp: datetime, seconds: int) -> datetime:
    epoch = int(timestamp.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % seconds), tz=timezone.utc)


def aggregate_tag_window(db: Session, tag: PlcReadTag, timestamp: datetime) -> None:
    start = aggregation_start(timestamp, tag.agregacion_segundos)
    end = start + timedelta(seconds=tag.agregacion_segundos)
    readings = list(db.scalars(select(PlcRawReading).where(PlcRawReading.id_tag == tag.id, PlcRawReading.instante_fuente >= start, PlcRawReading.instante_fuente < end).order_by(PlcRawReading.instante_fuente)))
    if not readings:
        return
    values = [row.valor_escalado for row in readings if row.calidad == "GOOD"]
    worst_quality = max((row.calidad for row in readings), key=lambda quality: QUALITY_RANK[quality])
    aggregate = db.scalar(select(PlcReadingAggregate).where(PlcReadingAggregate.id_tag == tag.id, PlcReadingAggregate.desde == start))
    payload = {
        "hasta_exclusiva": end,
        "cantidad_muestras": len(readings),
        "valor_minimo": min(values) if values else None,
        "valor_maximo": max(values) if values else None,
        "valor_promedio": sum(values) / len(values) if values else None,
        "ultimo_valor": readings[-1].valor_escalado if readings[-1].calidad == "GOOD" else None,
        "calidad": worst_quality,
    }
    if aggregate is None:
        db.add(PlcReadingAggregate(id_tag=tag.id, desde=start, **payload))
    else:
        for field, value in payload.items():
            setattr(aggregate, field, value)


def enforce_retention(db: Session, tag: PlcReadTag, now: datetime) -> None:
    raw_before = now - timedelta(days=tag.retencion_crudo_dias)
    expired_ids = select(PlcRawReading.id).where(PlcRawReading.id_tag == tag.id, PlcRawReading.instante_fuente < raw_before)
    db.execute(delete(TemporalMeasurementFact).where(TemporalMeasurementFact.tabla_origen == "plc_lectura_cruda", TemporalMeasurementFact.id_registro_origen.in_(expired_ids)))
    db.execute(delete(PlcRawReading).where(PlcRawReading.id_tag == tag.id, PlcRawReading.instante_fuente < raw_before))
    aggregate_before = now - timedelta(days=tag.retencion_agregado_dias)
    db.execute(delete(PlcReadingAggregate).where(PlcReadingAggregate.id_tag == tag.id, PlcReadingAggregate.hasta_exclusiva < aggregate_before))


def acquire_test_samples(db: Session, source: PlcReadSource) -> int:
    adapter = readonly_adapter(source)
    now = datetime.now(timezone.utc)
    status = db.get(PlcAcquisitionStatus, source.id)
    if status is None:
        status = PlcAcquisitionStatus(id_fuente=source.id, estado="CONFIGURADO")
        db.add(status)
    status.ultimo_intento_en, status.ultimo_error = now, None
    tags = list(db.scalars(select(PlcReadTag).where(PlcReadTag.id_fuente == source.id, PlcReadTag.activo.is_(True))))
    latest = {tag.id: db.scalar(select(PlcRawReading).where(PlcRawReading.id_tag == tag.id).order_by(PlcRawReading.adquirido_en.desc()).limit(1)) for tag in tags}
    eligible = [tag for tag in tags if latest[tag.id] is None or (now - latest[tag.id].adquirido_en).total_seconds() >= tag.muestreo_segundos]
    count = 0
    for sample in adapter.read(eligible):
        tag = next(tag for tag in eligible if tag.id == sample.tag_id)
        scaled = sample.raw_value * tag.escala_factor + tag.escala_offset
        raw = PlcRawReading(id_tag=tag.id, instante_fuente=sample.source_timestamp, valor_crudo=sample.raw_value, valor_escalado=scaled, unidad=tag.unidad, calidad=sample.quality, adaptador=adapter.name)
        db.add(raw)
        db.flush()
        db.add(TemporalMeasurementFact(
            fecha_operativa=sample.source_timestamp.date(), turno_codigo=tag.turno_codigo,
            instante_operativo=sample.source_timestamp, tabla_origen="plc_lectura_cruda",
            id_registro_origen=raw.id, metrica=tag.metrica,
            valor=scaled if sample.quality == "GOOD" else None, unidad=tag.unidad,
            origen_dato="plc_solo_lectura",
            contexto={"fuente_plc_id": str(source.id), "tag_plc_id": str(tag.id),
                      "referencia_tag": tag.referencia_tag, "calidad": sample.quality,
                      "adaptador": adapter.name, "valor_crudo": str(sample.raw_value)},
        ))
        aggregate_tag_window(db, tag, sample.source_timestamp)
        enforce_retention(db, tag, now)
        count += 1
    if count:
        status.estado = "ACTIVO"
        status.ultima_muestra_en = now
    elif status.ultima_muestra_en is None:
        status.estado = "CONFIGURADO"
    return count
