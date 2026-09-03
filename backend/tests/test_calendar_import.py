import calendar
import os
import sys
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calendar_import import MAX_DOCUMENT_XML_BYTES, parse_calendar_docx  # noqa: E402


def _cell(text="", border=None):
    borders = ""
    if border:
        names = ("tl2br", "tr2bl") if border == "both" else ("tl2br",)
        borders = "<w:tcBorders>" + "".join(f'<w:{name} w:val="single"/>' for name in names) + "</w:tcBorders>"
    return f"<w:tc><w:tcPr>{borders}</w:tcPr><w:p><w:r><w:t>{escape(str(text))}</w:t></w:r></w:p></w:tc>"


def _row(values, borders=None):
    borders = borders or {}
    return "<w:tr>" + "".join(_cell(value, borders.get(index)) for index, value in enumerate(values)) + "</w:tr>"


def _fixture_docx():
    marked = {
        (2025, 10, 1): "both",
        (2025, 10, 10): "one",
        (2025, 12, 8): "both",
        (2026, 5, 24): "both",
        (2026, 5, 25): "both",
    }
    day = date(2026, 7, 13)
    while day <= date(2026, 8, 31):
        if day != date(2026, 8, 22):
            marked[(day.year, day.month, day.day)] = "both"
        day += timedelta(days=1)

    summaries = {
        (2025, 9, 1): "1/9開學日",
        (2025, 10, 1): "1/10國慶日假期",
        (2025, 10, 6): "6/10教師專業發展日(學生放假一天) 9/10第23屆運動會 10/10翌日假期",
        (2025, 12, 8): "8/12立法會選舉日翌日",
        (2026, 1, 30): "30/1上學期結業禮",
        (2026, 2, 2): "2/2下學期開課",
        (2026, 5, 25): "25/5佛誕假期",
        (2026, 7, 10): "10/7第60屆畢業禮",
        (2026, 7, 13): "13/7-31/8暑假49天",
    }
    labels = {
        (2025, 9): "25年九月",
        (2025, 10): "十月",
        (2025, 12): "十二月",
        (2026, 1): "26年一月",
        (2026, 2): "二月",
        (2026, 5): "五月",
        (2026, 7): "七月",
        (2026, 8): "八月",
    }
    rows = [
        _row(["月份", "星期", "", "", "", "", "", "", "週次", "週訓中心", "週內事項摘要", "長週"]),
        _row(["", "日", "一", "二", "三", "四", "五", "六", "", "", "", ""]),
    ]
    for year, month in labels:
        for week_index, week in enumerate(calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)):
            values = [labels[(year, month)] if week_index == 0 else "", *[value or "" for value in week], "", "", "", ""]
            summary = next((text for (sy, sm, sd), text in summaries.items() if (sy, sm) == (year, month) and sd in week), "")
            values[10] = summary
            borders = {
                weekday + 1: marked[(year, month, value)]
                for weekday, value in enumerate(week)
                if value and (year, month, value) in marked
            }
            rows.append(_row(values, borders))

    document = (
        f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        f'<w:p><w:r><w:t>測試學校 2025-2026年度 校曆表</w:t></w:r></w:p><w:tbl>{"".join(rows)}</w:tbl>'
        f'</w:body></w:document>'
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
    return output.getvalue()


def test_parse_fixed_format_calendar_and_preserve_marked_exception():
    result = parse_calendar_docx(_fixture_docx())

    assert result["school_year"] == "2025-2026"
    assert (result["calendar_start"], result["calendar_end"]) == ("2025-09-01", "2026-08-31")
    assert result["suggested_ranges"] == {
        "full_year": {"start": "2025-09-01", "end": "2026-07-10"},
        "first_term": {"start": "2025-09-01", "end": "2026-01-30"},
        "second_term": {"start": "2026-02-02", "end": "2026-07-10"},
    }
    assert result["summary"] == {
        "school_holiday_days": 53,
        "self_decided_days": 1,
        "teacher_development_days": 1,
        "closure_days": 55,
    }

    closures = {item["date"]: item for item in result["closures"]}
    assert closures["2025-10-01"]["note"] == "國慶日假期"
    assert closures["2025-10-10"]["kind"] == "self_decided"
    assert closures["2025-10-10"]["note"] == "第23屆運動會翌日假期"
    assert closures["2025-10-06"]["kind"] == "teacher_development"
    assert closures["2025-12-08"]["note"] == "立法會選舉日翌日"
    assert closures["2026-05-24"]["note"] == "佛誕假期"
    assert closures["2026-05-25"]["note"] == "佛誕假期"
    assert "2026-08-22" not in closures

    summer = next(group for group in result["groups"] if group["name"] == "暑假")
    assert (summer["start"], summer["end"]) == ("2026-07-13", "2026-08-31")
    assert len(summer["dates"]) == 49
    assert summer["excluded_dates"] == ["2026-08-22"]
    assert result["warnings"] == ["暑假文字日期範圍內有未標記日期，已按日期格排除：2026-08-22"]
    assert all(item["selected"] is False for item in result["review_days"])


@pytest.mark.parametrize("content", [b"", b"not a zip file"])
def test_rejects_invalid_docx(content):
    with pytest.raises(ValueError, match="DOCX"):
        parse_calendar_docx(content)


def test_rejects_oversized_document_xml_before_decompression():
    output = BytesIO()
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", b" " * (MAX_DOCUMENT_XML_BYTES + 1))

    with pytest.raises(ValueError, match="過大"):
        parse_calendar_docx(output.getvalue())
