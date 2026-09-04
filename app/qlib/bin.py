"""Convert exported CSV files into Qlib's local day-frequency binary layout."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import struct
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field


class BinManifest(BaseModel):
    format: str = "qlib-local-bin-v1"
    frequency: str = "day"
    calendar_count: int
    instruments: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _float(value: str) -> float:
    return float(value) if value.strip() else math.nan


class QlibBinWriter:
    def convert(self, source: Path, output: Path) -> BinManifest:
        csv_files = sorted(source.glob("*.csv"))
        if not csv_files:
            raise ValueError("source contains no CSV files")
        if output.exists() and any(output.iterdir()):
            raise ValueError("output directory must be empty")
        datasets: dict[str, tuple[list[str], dict[date, dict[str, str]]]] = {}
        calendar: set[date] = set()
        all_fields: set[str] = set()
        for path in csv_files:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fields = [
                    item
                    for item in reader.fieldnames or []
                    if item not in {"date", "symbol"}
                ]
                rows: dict[date, dict[str, str]] = {}
                symbol = ""
                for row in reader:
                    trading_date = date.fromisoformat(row["date"])
                    symbol = row["symbol"].upper()
                    if not re.fullmatch(r"[A-Z0-9._-]{1,32}", symbol):
                        raise ValueError(f"invalid symbol in {path.name}")
                    if trading_date in rows:
                        raise ValueError(
                            f"duplicate date in {path.name}: {trading_date}"
                        )
                    rows[trading_date] = row
                    calendar.add(trading_date)
                if not rows or not symbol:
                    continue
                datasets[symbol] = (fields, rows)
                all_fields.update(fields)
        ordered_calendar = sorted(calendar)
        if not ordered_calendar:
            raise ValueError("source contains no dated rows")
        output.mkdir(parents=True, exist_ok=True)
        calendar_dir = output / "calendars"
        instruments_dir = output / "instruments"
        features_dir = output / "features"
        calendar_dir.mkdir()
        instruments_dir.mkdir()
        features_dir.mkdir()
        calendar_path = calendar_dir / "day.txt"
        calendar_path.write_text(
            "".join(f"{item.isoformat()}\n" for item in ordered_calendar),
            encoding="utf-8",
        )
        positions = {item: index for index, item in enumerate(ordered_calendar)}
        instrument_lines: list[str] = []
        for symbol, (fields, rows) in sorted(datasets.items()):
            first, last = min(rows), max(rows)
            instrument_lines.append(
                f"{symbol}\t{first.isoformat()}\t{last.isoformat()}\n"
            )
            relevant_dates = [
                item for item in ordered_calendar if first <= item <= last
            ]
            target = features_dir / symbol.lower()
            target.mkdir()
            for field in fields:
                values = [
                    _float(rows.get(item, {}).get(field, "")) for item in relevant_dates
                ]
                payload = struct.pack(
                    f"<{len(values) + 1}f", float(positions[first]), *values
                )
                (target / f"{field.lower()}.day.bin").write_bytes(payload)
        instruments_path = instruments_dir / "all.txt"
        instruments_path.write_text("".join(instrument_lines), encoding="utf-8")
        hashes = {
            str(path.relative_to(output)): _hash(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
        }
        manifest = BinManifest(
            calendar_count=len(ordered_calendar),
            instruments=sorted(datasets),
            fields=sorted(all_fields),
            files=hashes,
        )
        (output / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Qlib local binary dataset")
    parser.add_argument("--source", type=Path, default=Path("data/qlib/source"))
    parser.add_argument("--output", type=Path, default=Path("data/qlib/bin"))
    args = parser.parse_args()
    manifest = QlibBinWriter().convert(args.source, args.output)
    print(json.dumps(manifest.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
