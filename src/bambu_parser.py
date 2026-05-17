"""Deterministic Bambu Lab invoice parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Iterable, List, Tuple


MATERIAL_ALIASES = [
    "PLA Basic",
    "PLA Matte",
    "PLA Silk",
    "PLA-CF",
    "PETG Basic",
    "TPU 95A",
    "PA6-GF",
    "ABS",
]

NOISE_WORDS = {
    "bambu",
    "lab",
    "labs",
    "filament",
    "with",
    "spool",
    "refill",
    "for",
    "ams",
    "printer",
    "printing",
    "material",
    "sku",
    "item",
    "order",
    "qty",
    "quantity",
    "unit",
    "price",
    "total",
    "subtotal",
    "tax",
    "shipping",
}

COLOR_STOPWORDS = {
    "kg",
    "g",
    "mm",
    "usd",
    "eur",
    "gbp",
    "pcs",
    "pc",
    "x",
}

MONEY_RE = re.compile(r"(?:USD|US\$|EUR|GBP|[$€£])\s*([0-9]+(?:[.,][0-9]{2}))|([0-9]+(?:[.,][0-9]{2}))\s*(?:USD|EUR|GBP)", re.I)
QUANTITY_PATTERNS = [
    re.compile(r"\b(?:qty|quantity)\s*[:#-]?\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:pcs?|pieces|spools?)\b", re.I),
    re.compile(r"(?:x|×)\s*(\d{1,3})\b", re.I),
]
WEIGHT_RE = re.compile(r"\b(0?\.5|0,5|0\.75|0,75|1|2|3)\s*kg\b|\b(500|750|1000|2000|3000)\s*g\b", re.I)
DIAMETER_RE = re.compile(r"\b(1\.75|2\.85|3(?:\.0)?)\s*mm\b", re.I)


@dataclass
class ParseResult:
    filaments: List[Dict]
    warnings: List[str]


def parse_bambu_invoice_text(text: str) -> ParseResult:
    """Parse Bambu invoice/order OCR text into importer filament rows."""
    warnings: List[str] = []
    rows: List[Dict] = []

    for line in _candidate_lines(text):
        material = _extract_material(line)
        if not material:
            continue

        price, price_warning = _extract_unit_price(line)
        if price_warning:
            warnings.append(f"{price_warning}: {line}")

        quantity = _extract_quantity(line)
        color, color_warning = _extract_color(line, material)
        if color_warning:
            warnings.append(f"{color_warning}: {line}")

        row = {
            "brand": "Bambu Lab",
            "material": material,
            "color": color or "Unknown",
            "diameter": _extract_diameter(line),
            "weight": _extract_weight(line),
            "price": price,
            "quantity": quantity,
        }
        rows.append(row)

    if not rows:
        warnings.append("No Bambu filament line items were detected in the document text.")

    return ParseResult(filaments=_merge_duplicate_rows(rows), warnings=warnings)


def _candidate_lines(text: str) -> Iterable[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    for index, line in enumerate(lines):
        if _extract_material(line) and _has_filament_context(line):
            yield line
            continue

        # Some OCR output splits item names and totals across adjacent fragments.
        # Only join when the current fragment already contains a material marker;
        # otherwise headings like "Invoice" can duplicate the next clean row.
        if not _extract_material(line):
            continue
        combined = " ".join(lines[index:index + 3])
        if combined != line and _extract_material(combined) and _has_filament_context(combined):
            yield combined


def _has_filament_context(line: str) -> bool:
    lower = line.lower()
    excluded = ("subtotal", "shipping", "tax", "discount", "coupon", "invoice total", "grand total")
    if any(word in lower for word in excluded):
        return False
    return "bambu" in lower or "filament" in lower or "pla" in lower or "petg" in lower or "tpu" in lower or "abs" in lower


def _extract_material(line: str) -> str | None:
    normalized = _normalize_material_text(line)
    for material in MATERIAL_ALIASES:
        if _normalize_material_text(material) in normalized:
            return material
    return None


def _normalize_material_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _extract_quantity(line: str) -> int:
    for pattern in QUANTITY_PATTERNS:
        match = pattern.search(line)
        if match:
            quantity = int(match.group(1))
            if quantity > 0:
                return quantity
    return 1


def _extract_unit_price(line: str) -> Tuple[float, str | None]:
    amounts = []
    for match in MONEY_RE.finditer(line):
        raw = match.group(1) or match.group(2)
        try:
            amounts.append(Decimal(raw.replace(",", ".")))
        except InvalidOperation:
            continue

    if not amounts:
        return 0.0, "No price found for detected Bambu filament row"

    quantity = _extract_quantity(line)
    if len(amounts) >= 2:
        amount = amounts[0]
    elif quantity > 1:
        amount = (amounts[0] / Decimal(quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        amount = amounts[0]

    return float(amount), None


def _extract_weight(line: str) -> float:
    match = WEIGHT_RE.search(line)
    if not match:
        return 1000.0
    kg_value, g_value = match.groups()
    if kg_value:
        return float(Decimal(kg_value.replace(",", ".")) * Decimal(1000))
    return float(g_value)


def _extract_diameter(line: str) -> float:
    match = DIAMETER_RE.search(line)
    if not match:
        return 1.75
    return float(match.group(1))


def _extract_color(line: str, material: str) -> Tuple[str | None, str | None]:
    cleaned = line
    cleaned = re.sub(re.escape(material), " ", cleaned, flags=re.I)
    for token in ["Bambu Lab", "Bambu", "Filament", "with Spool", "Refill"]:
        cleaned = re.sub(re.escape(token), " ", cleaned, flags=re.I)
    cleaned = MONEY_RE.sub(" ", cleaned)
    cleaned = WEIGHT_RE.sub(" ", cleaned)
    cleaned = DIAMETER_RE.sub(" ", cleaned)
    for pattern in QUANTITY_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\b[A-Z0-9]{3,}[-_][A-Z0-9-]+\b", " ", cleaned)
    cleaned = re.sub(r"[()\[\],|/]+", " ", cleaned)
    words = [word.strip("-_:;") for word in cleaned.split()]

    color_words = []
    for word in words:
        lower = word.lower()
        if not lower or lower in NOISE_WORDS or lower in COLOR_STOPWORDS:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", lower):
            continue
        color_words.append(word)

    if not color_words:
        return None, "No color found for detected Bambu filament row"

    # Keep the trailing descriptive phrase; OCR often leaves order labels at the start.
    color = " ".join(color_words[-4:])
    return color.strip(), None


def _merge_duplicate_rows(rows: List[Dict]) -> List[Dict]:
    merged: Dict[Tuple, Dict] = {}
    for row in rows:
        key = (
            row["brand"].lower(),
            row["material"].lower(),
            row["color"].lower(),
            row["diameter"],
            row["weight"],
            row["price"],
        )
        if key in merged:
            merged[key]["quantity"] += row.get("quantity", 1)
        else:
            merged[key] = row.copy()
    return list(merged.values())
