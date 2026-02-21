from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


_AUX_PO_PATTERN = re.compile(r"^\s*([A-Za-z0-9]+)\s*[xX]\s*([A-Za-z0-9]+)\s*$")


def normalize_header(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("º", "o").replace("°", "o")
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").lower()
    return re.sub(r"_+", "_", normalized)


def normalize_code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "nat"}:
        return ""
    if re.fullmatch(r"-?\d+\.0+", text):
        return text.split(".")[0]
    return text


def parse_decimal_ptbr(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if math.isnan(value):
            return Decimal("0")
        return Decimal(str(value))
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return Decimal("0")
    text = text.replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        # Handles cases with thousand separators in dot-only values.
        if text.count(".") > 1:
            head, tail = text.rsplit(".", 1)
            text = head.replace(".", "") + "." + tail
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Valor monetário inválido: {value!r}") from exc


def to_decimal(value: Any) -> Decimal:
    return parse_decimal_ptbr(value)


def parse_aoxpo(value: str) -> tuple[str, str]:
    if value is None:
        raise ValueError("AOxPO vazio")
    text = str(value).strip()
    match = _AUX_PO_PATTERN.match(text)
    if not match:
        raise ValueError(f"Formato AOxPO inválido: {value!r}")
    ao, po = match.groups()
    ao_norm = normalize_code(ao)
    po_norm = normalize_code(po)
    if ao_norm.isdigit() and len(ao_norm) <= 4:
        ao_norm = ao_norm.zfill(4)
    if po_norm.isdigit() and len(po_norm) <= 4:
        po_norm = po_norm.zfill(4)
    return ao_norm, po_norm


def to_local_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def decimal_to_str(value: Decimal | Any) -> str:
    if value is None:
        return "0"
    if not isinstance(value, Decimal):
        value = to_decimal(value)
    return format(value, "f")
