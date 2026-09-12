from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.core import AppliedLimit, Catalog, DeviationEvent, DeviationHistory, LimitVersion, OperationalRecord, ReactionPlan, SiloScale, SiloScalePoint
from app.services.limits import evaluate_limit

MODULE_SECTOR = {"M1": "Molienda", "M2": "Molienda", "M3": "Molienda", "M6": "Molienda", "M8": "Prensas", "M9": "Prensas", "M10": "Prensas"}
LIMIT_FIELDS = {"M1": {"humedad_verdes": "L02", "residuo": "L03", "aeroseparador": "L04"}, "M2": {"humedad_salida": "L10"}, "M3": {"humedad": "L12", "temperatura": "L13", "humedad_ksider": "L24", "toneladas_calculadas": "L26"}, "M9": {"humedad_pasta": "L31", "presion": "L32", "humedad_residual": "L37"}}
THICKNESS_LIMITS_BY_FORMAT = {"64X64": "L33", "64X122": "L34"}
DISPERSION_LIMITS = ("L42", "L43", "L44")
FALLBACK_PRESSES = {"L6": ("PH Siti",), "L7": ("PH5000-1", "PH5000-2")}


def decimal_value(data: dict, field: str, required: bool = True) -> Decimal | None:
    value = data.get(field)
    if value is None:
        if required:
            raise HTTPException(status_code=422, detail=f"{field} es obligatorio")
        return None
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail=f"{field} debe ser numerico") from exc
    if not decimal.is_finite():
        raise HTTPException(status_code=422, detail=f"{field} debe ser un numero finito")
    return decimal


def active_catalog(db: Session, kind: str, code: str) -> Catalog:
    item = db.scalar(select(Catalog).where(Catalog.tipo == kind, Catalog.codigo == code, Catalog.activo.is_(True)))
    if item is None:
        raise HTTPException(status_code=422, detail=f"{kind} inexistente o inactivo: {code}")
    return item


def normalized_line(value) -> str:
    line = str(value or "").upper()
    if line not in FALLBACK_PRESSES:
        raise HTTPException(status_code=422, detail="linea debe ser L6 o L7")
    return line


def presses_for_line(db: Session, line: str) -> tuple[str, ...]:
    configured = list(db.scalars(select(Catalog).where(Catalog.tipo == "prensa", Catalog.activo.is_(True))))
    matching = tuple(item.codigo for item in configured if (item.atributos or {}).get("linea") == line)
    return matching or FALLBACK_PRESSES[line]


def validate_press_line(db: Session, line: str, press: str) -> str:
    press = str(press or "").strip()
    if not press:
        raise HTTPException(status_code=422, detail="prensa es obligatorio")
    configured = db.scalar(select(Catalog).where(Catalog.tipo == "prensa", Catalog.codigo == press, Catalog.activo.is_(True)))
    if configured is not None:
        if (configured.atributos or {}).get("linea") != line:
            raise HTTPException(status_code=422, detail="La prensa no pertenece fisicamente a la linea seleccionada")
        return configured.codigo
    upper = press.upper()
    if (line == "L6" and "PH SITI" in upper) or (line == "L7" and upper.startswith("PH5000")):
        return press
    raise HTTPException(status_code=422, detail="La prensa no pertenece fisicamente a la linea seleccionada")


def selected_format(db: Session, code: str) -> tuple[Catalog, Decimal, Decimal]:
    item = active_catalog(db, "formato", str(code or ""))
    attributes = item.atributos or {}
    nominal = decimal_value(attributes, "espesor_nominal_mm")
    tolerance = decimal_value(attributes, "tolerancia_mm")
    if tolerance < 0:
        raise HTTPException(status_code=422, detail="La tolerancia del formato no puede ser negativa")
    return item, nominal, tolerance


def normalized_data(db: Session, module: str, source: dict, operational_date) -> dict:
    data = dict(source)
    if module == "M1":
        box = data.get("box_activo")
        if box not in {1, 2, 3, 6, "1", "2", "3", "6"}:
            raise HTTPException(status_code=422, detail="box_activo solo admite 1, 2, 3 o 6")
        for field in ("humedad_verdes", "residuo", "aeroseparador"):
            data[field] = str(decimal_value(data, field))
        if data.get("temperatura_quemador") is not None:
            data["temperatura_quemador"] = str(decimal_value(data, "temperatura_quemador"))
    elif module == "M2":
        pasta, agua = decimal_value(data, "caudal_pasta"), decimal_value(data, "caudal_agua")
        if pasta <= 0:
            raise HTTPException(status_code=422, detail="caudal_pasta debe ser mayor a cero")
        data["caudal_pasta"], data["caudal_agua"] = str(pasta), str(agua)
        data["humedad_salida"] = str(decimal_value(data, "humedad_salida"))
        data["dosificacion_calc"] = str(agua / pasta)
    elif module == "M3":
        kind = data.get("tipo_registro")
        if kind == "lecho":
            data["humedad"], data["temperatura"] = str(decimal_value(data, "humedad")), str(decimal_value(data, "temperatura"))
        elif kind == "ksider_rechazo":
            if decimal_value(data, "segundos_pesada") != Decimal("60"):
                raise HTTPException(status_code=422, detail="La pesada K-Sider debe durar 60 segundos")
            data["humedad_ksider"] = str(decimal_value(data, "humedad_ksider"))
        elif kind == "stock_silo":
            height = decimal_value(data, "altura_libre_m")
            if height < 0 or height > 11:
                raise HTTPException(status_code=422, detail="altura_libre_m debe estar entre 0 y 11")
            silo = int(data.get("silo", 0))
            if silo not in range(1, 17):
                raise HTTPException(status_code=422, detail="silo debe estar entre 1 y 16")
            line = str(data.get("linea", ""))
            if line and ((line == "L6" and silo <= 8) or (line == "L7" and silo >= 9)):
                raise HTTPException(status_code=422, detail="El silo no pertenece fisicamente a la linea seleccionada")
            group = "1-8" if silo <= 8 else "9-16"
            scale = db.scalar(select(SiloScale).where(SiloScale.grupo_silos == group, SiloScale.vigente_desde <= operational_date).order_by(SiloScale.vigente_desde.desc()))
            if scale is None:
                raise HTTPException(status_code=422, detail="No hay escala de silo vigente")
            points = list(db.scalars(select(SiloScalePoint).where(SiloScalePoint.id_escala == scale.id).order_by(SiloScalePoint.altura_m)))
            lower = max((point for point in points if point.altura_m <= height), key=lambda point: point.altura_m, default=None)
            upper = min((point for point in points if point.altura_m >= height), key=lambda point: point.altura_m, default=None)
            if lower is None or upper is None:
                raise HTTPException(status_code=422, detail="La altura no puede interpolarse en la escala vigente")
            tonnes = lower.toneladas if lower.altura_m == upper.altura_m else lower.toneladas + (height - lower.altura_m) * (upper.toneladas - lower.toneladas) / (upper.altura_m - lower.altura_m)
            data.update({"silo": silo, "altura_libre_m": str(height), "toneladas_calculadas": str(tonnes), "id_escala_version": str(scale.id)})
        else:
            raise HTTPException(status_code=422, detail="tipo_registro M3 invalido")
    elif module == "M6":
        if data.get("causa") == "P12" and not data.get("descripcion"):
            raise HTTPException(status_code=422, detail="descripcion es obligatoria para P12")
        start, end = datetime.fromisoformat(data["inicio"]), datetime.fromisoformat(data["fin"]) if data.get("fin") else None
        if start.tzinfo is None or (end and end.tzinfo is None) or (end and end < start):
            raise HTTPException(status_code=422, detail="Intervalo de parada invalido")
        if end:
            data["duracion_calculada_horas"] = str((end - start).total_seconds() / 3600)
    elif module == "M8":
        line = normalized_line(data.get("linea"))
        if not data.get("causa_vaciado"):
            raise HTTPException(status_code=422, detail="causa_vaciado es obligatorio")
        duration = decimal_value(data, "duracion_min")
        if duration < 0:
            raise HTTPException(status_code=422, detail="duracion_min no puede ser negativo")
        data.update({"linea": line, "prensa": validate_press_line(db, line, data.get("prensa")), "duracion_min": str(duration), "recordatorio_descarte_min": "10"})
    elif module == "M9":
        line = normalized_line(data.get("linea"))
        format_item, nominal, tolerance = selected_format(db, data.get("formato"))
        data.update({"linea": line, "prensa": validate_press_line(db, line, data.get("prensa")), "formato": format_item.codigo, "formato_aplicado": {"codigo": format_item.codigo, "espesor_nominal_mm": str(nominal), "tolerancia_mm": str(tolerance)}})
        for field in ("humedad_pasta", "presion", "humedad_residual"):
            data[field] = str(decimal_value(data, field))
    elif module == "M10":
        line = normalized_line(data.get("linea"))
        format_item, nominal, tolerance = selected_format(db, data.get("formato"))
        details = data.get("detalles")
        if not isinstance(details, list):
            raise HTTPException(status_code=422, detail="detalles de espesor obligatorios")
        presses = presses_for_line(db, line)
        expected = {(press, cavity, sector) for press in presses for cavity in (1, 2) for sector in range(1, 10)}
        seen, values, normalized_details, thickness_warnings = set(), [], [], []
        for detail in details:
            if not isinstance(detail, dict):
                raise HTTPException(status_code=422, detail="detalle de espesor invalido")
            try:
                cavity, sector = int(detail.get("cavidad")), int(detail.get("sector"))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="cavidad y sector de espesor deben ser enteros") from exc
            press = validate_press_line(db, line, detail.get("prensa"))
            key = (press, cavity, sector)
            if key not in expected or key in seen:
                raise HTTPException(status_code=422, detail="detalle de espesor invalido")
            value = decimal_value(detail, "espesor_mm")
            seen.add(key)
            values.append(value)
            normalized_details.append({"prensa": press, "cavidad": cavity, "sector": sector, "espesor_mm": str(value)})
            if value < nominal - tolerance or value > nominal + tolerance:
                thickness_warnings.append({"prensa": press, "cavidad": cavity, "sector": sector, "espesor_mm": str(value)})
        if seen != expected:
            raise HTTPException(status_code=422, detail="Cada prensa y cavidad requiere su grilla completa de 3x3 sectores")
        minimum, maximum = min(values), max(values)
        dispersion_warnings = []
        for limit_id in DISPERSION_LIMITS:
            version = db.scalar(select(LimitVersion).where(LimitVersion.id_limite == limit_id, LimitVersion.vigente_desde <= operational_date, LimitVersion.estado != "CANCELADA").order_by(LimitVersion.vigente_desde.desc()))
            if version is not None and evaluate_limit(version, maximum - minimum) == "FUERA_DE_RANGO":
                dispersion_warnings.append(limit_id)
        format_snapshot = {"codigo": format_item.codigo, "espesor_nominal_mm": str(nominal), "tolerancia_mm": str(tolerance)}
        if (format_item.atributos or {}).get("id_limite_espesor"):
            format_snapshot["id_limite_espesor"] = str(format_item.atributos["id_limite_espesor"])
        data.update({
            "linea": line,
            "formato": format_item.codigo,
            "formato_aplicado": format_snapshot,
            "detalles": normalized_details,
            "espesor_min": str(minimum),
            "espesor_max": str(maximum),
            "dispersion_mm": str(maximum - minimum),
            "advertencia_espesor": bool(thickness_warnings),
            "detalles_fuera_tolerancia": thickness_warnings,
            "advertencia_dispersion": bool(dispersion_warnings),
            "limites_dispersion_advertidos": dispersion_warnings,
        })
    return data


def evaluate_record(db: Session, record: OperationalRecord, actor_id) -> None:
    fields = LIMIT_FIELDS.get(record.modulo, {})
    if record.modulo == "M3":
        kind = record.datos.get("tipo_registro")
        fields = {key: value for key, value in fields.items() if (kind == "lecho" and key in {"humedad", "temperatura"}) or (kind == "ksider_rechazo" and key == "humedad_ksider") or (kind == "stock_silo" and key == "toneladas_calculadas")}
    evaluations = [(field, limit_id, decimal_value(record.datos, field)) for field, limit_id in fields.items()]
    if record.modulo == "M10":
        format_limit = (record.datos.get("formato_aplicado") or {}).get("id_limite_espesor") or THICKNESS_LIMITS_BY_FORMAT.get(str(record.datos.get("formato", "")).upper())
        if format_limit:
            evaluations.extend((f"espesor_mm:{detail['prensa']}:{detail['cavidad']}:{detail['sector']}", format_limit, decimal_value(detail, "espesor_mm")) for detail in record.datos["detalles"])
        evaluations.extend((f"dispersion_mm:{limit_id}", limit_id, decimal_value(record.datos, "dispersion_mm")) for limit_id in DISPERSION_LIMITS)
    for field, limit_id, value in evaluations:
        version = db.scalar(select(LimitVersion).where(LimitVersion.id_limite == limit_id, LimitVersion.vigente_desde <= record.fecha_operativa, LimitVersion.estado != "CANCELADA").order_by(LimitVersion.vigente_desde.desc()))
        if version is None:
            continue
        result = evaluate_limit(version, value)
        applied = db.scalar(select(AppliedLimit).where(AppliedLimit.tabla_origen == "registro_operativo", AppliedLimit.id_registro == record.id, AppliedLimit.campo == field))
        if applied is None:
            applied = AppliedLimit(tabla_origen="registro_operativo", id_registro=record.id, campo=field, id_limite=limit_id, id_limite_version=version.id, valor_medido=value, resultado=result)
            db.add(applied)
        else:
            applied.id_limite_version, applied.valor_medido, applied.resultado = version.id, value, result
        key = f"{record.id}:{field}:{version.id}"
        event = db.scalar(select(DeviationEvent).where(DeviationEvent.clave_idempotencia == key))
        if result == "FUERA_DE_RANGO" and version.id_desvio:
            plan = db.get(ReactionPlan, version.id_desvio)
            if plan is None:
                continue
            if event is None:
                scope = f"{record.modulo}:{field}:{record.datos.get('punto', record.datos.get('silo', 'general'))}"
                previous = db.scalar(select(DeviationEvent).join(OperationalRecord, OperationalRecord.id == DeviationEvent.id_registro).where(DeviationEvent.secuencia_clave == scope, OperationalRecord.instante_medicion < record.instante_medicion, DeviationEvent.estado != "INVALIDADO").order_by(OperationalRecord.instante_medicion.desc()))
                event = DeviationEvent(id_registro=record.id, campo=field, id_limite=limit_id, id_limite_version=version.id, id_desvio=version.id_desvio, clave_idempotencia=key, secuencia_clave=scope, estado="ESCALADO" if previous else "ABIERTO", valor_actual=value, vence_en=datetime.now(timezone.utc) + timedelta(hours=float(plan.plazo_horas)) if plan.plazo_horas else None)
                db.add(event)
                db.flush()
                db.add(DeviationHistory(id_evento=event.id, estado_anterior=None, estado_nuevo=event.estado, comentario="Escalado por segunda medicion consecutiva" if previous else None, id_usuario=actor_id))
            else:
                event.valor_actual = value
        elif event is not None and event.estado != "INVALIDADO":
            previous_state = event.estado
            event.estado = "INVALIDADO"
            db.add(DeviationHistory(id_evento=event.id, estado_anterior=previous_state, estado_nuevo="INVALIDADO", comentario="Correccion deja la medicion en rango", id_usuario=actor_id))
