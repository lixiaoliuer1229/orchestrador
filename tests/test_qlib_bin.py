import math
import struct

from app.qlib.bin import QlibBinWriter
from app.qlib.export import QlibCsvExporter
from tests.test_qlib_export import DATES, FakeMarketRepo, FakeSignalRepo


def test_bin_writer_creates_qlib_local_layout(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "bin"
    QlibCsvExporter(FakeMarketRepo(), FakeSignalRepo()).export(
        source, "CN", DATES[0], DATES[-1]
    )

    manifest = QlibBinWriter().convert(source, output)

    assert (output / "calendars/day.txt").read_text().splitlines() == [
        item.isoformat() for item in DATES
    ]
    assert (output / "instruments/all.txt").read_text().strip() == (
        "SH600519\t2025-01-02\t2025-01-06"
    )
    values = struct.unpack(
        "<4f", (output / "features/sh600519/close.day.bin").read_bytes()
    )
    assert values[0] == 0
    assert values[1] == 21
    assert math.isnan(values[2])
    assert values[3] == 21
    assert manifest.calendar_count == 3
    assert manifest.instruments == ["SH600519"]
    assert "features/sh600519/close.day.bin" in manifest.files


def test_bin_writer_requires_empty_output(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "bin"
    QlibCsvExporter(FakeMarketRepo()).export(source, "CN", DATES[0], DATES[-1])
    output.mkdir()
    (output / "existing").write_text("keep")

    try:
        QlibBinWriter().convert(source, output)
    except ValueError as exc:
        assert str(exc) == "output directory must be empty"
    else:
        raise AssertionError("non-empty output should fail")
