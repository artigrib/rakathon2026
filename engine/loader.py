"""Robust loader for messy NIS exports (CSV or XLSX, wrapped rows, shifted columns)."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .textfix import repair

FILES = {
    "patients": "1_patients",
    "smoking": "2_smoking_history",
    "ct": "3_chest_ct_examinations",
    "contacts": "4_patients_contact_history",
}

SMOKING_SOURCES = {"anamnesis", "questionnaire", "diagnosis", "unknown"}


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _split_line(line: str) -> list[str]:
    line = line.strip()
    # Whole row wrapped in quotes with inner quotes doubled: "a,b,""c"""
    if len(line) >= 2 and line[0] == '"' and line[-1] == '"' and line.count('"') % 2 == 0:
        inner = line[1:-1]
        if '","' not in inner:  # not a normally quoted multi-field row
            line = inner.replace('""', '"')
    return next(csv.reader([line]))


def _read_lines(path: Path) -> list[list[str]]:
    if path.suffix.lower() == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        for r in wb.active.iter_rows(values_only=True):
            cells = [c for c in r if c is not None]
            if not cells:
                continue
            if len(cells) == 1 and isinstance(cells[0], str) and "," in cells[0]:
                rows.append(_split_line(cells[0]))  # whole CSV row stuck in one cell
            else:
                rows.append(["" if c is None else str(c) for c in r])
        return rows
    text = _decode(path.read_bytes())
    return [_split_line(l) for l in text.splitlines() if l.strip()]


def find_file(data_dir: Path, stem: str) -> Path | None:
    for ext in (".xlsx", ".csv"):
        for p in sorted(data_dir.glob(f"{stem}*{ext}")):
            return p
    return None


def _repair_smoking(row: list[str], n: int) -> tuple[list[str], str | None]:
    """Rows missing a column: re-anchor on the `source` enum (expected index 7)."""
    if len(row) == n:
        return row, None
    src_idx = next((i for i, v in enumerate(row) if v in SMOKING_SOURCES), None)
    if len(row) < n and src_idx is not None and src_idx < 7:
        fixed = row[:src_idx] + [""] * (7 - src_idx) + row[src_idx:]
        fixed = (fixed + [""] * n)[:n]
        return fixed, f"Řádek měl {len(row)} sloupců místo {n}; doplněno podle pole 'source'"
    return (row + [""] * n)[:n], f"Řádek měl {len(row)} sloupců místo {n}; nelze spolehlivě opravit"


def load(data_dir: str | Path) -> tuple[dict[str, list[dict]], list[dict]]:
    data_dir = Path(data_dir)
    tables: dict[str, list[dict]] = {}
    issues: list[dict] = []
    enc_fixed, enc_bad = 0, set()
    for key, stem in FILES.items():
        path = find_file(data_dir, stem)
        if path is None:
            tables[key] = []
            issues.append({"file": stem, "row": None, "patient_id": None, "code": "MISSING_FILE",
                           "text": f"Soubor {stem} nebyl nalezen"})
            continue
        rows = _read_lines(path)
        header = [h.strip() for h in rows[0]]
        out = []
        for i, row in enumerate(rows[1:], start=2):
            row = [c.strip() if isinstance(c, str) else c for c in row]
            problem = None
            if key == "smoking":
                row, problem = _repair_smoking(row, len(header))
            elif len(row) != len(header):
                problem = f"Řádek má {len(row)} sloupců místo {len(header)}"
                row = (row + [""] * len(header))[: len(header)]
            rec = dict(zip(header, row))
            for k, v in rec.items():
                if isinstance(v, str):
                    fixed, bad = repair(v)
                    if fixed != v:
                        enc_fixed += 1
                    if bad:
                        enc_bad.add(v)
                    rec[k] = fixed
            rec["_row"] = i
            rec["_repaired"] = bool(problem)
            if problem:
                issues.append({"file": path.name, "row": i, "patient_id": rec.get("patient_id"),
                               "code": "MISSING_COLUMN", "text": problem})
            out.append(rec)
        tables[key] = out
    if enc_fixed:
        issues.append({"file": "*", "row": None, "patient_id": None, "code": "ENCODING_REPAIRED",
                       "text": f"Opraveno {enc_fixed} hodnot s poškozenou diakritikou"})
    for v in sorted(enc_bad):
        issues.append({"file": "*", "row": None, "patient_id": None, "code": "ENCODING_UNKNOWN",
                       "text": f"Nelze opravit diakritiku: {v}"})
    return tables, issues
