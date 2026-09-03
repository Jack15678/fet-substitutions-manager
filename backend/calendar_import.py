"""Parse the school's fixed-format Word calendar without Microsoft Word."""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
VAL = f"{{{W}}}val"
MAX_CONTENT_TYPES_BYTES = 256 * 1024
MAX_DOCUMENT_XML_BYTES = 8 * 1024 * 1024

TITLE_RE = re.compile(r"(20\d{2})\s*[-－–—]\s*(20\d{2})\s*年度")
DATE_RE = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})\s*/\s*(?P<month>\d{1,2})"
    r"(?:\s*[-－–—]\s*(?P<end_day>\d{1,2})\s*/\s*(?P<end_month>\d{1,2}))?"
)
MONTHS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
REVIEW_RE = re.compile(r"測驗|考試|運動會|修業旅行|家教會旅行|家長日|開放日|結業禮|畢業禮|水運會")
PARTIAL_SCOPE_RE = re.compile(r"P\.?\s*[1-6]|(?:小|中)[一二三四五六1-6]|TSA", re.IGNORECASE)


def _text(node) -> str:
    return re.sub(r"\s+", " ", "".join(node.xpath(".//w:t/text()", namespaces=NS))).strip()


def _load_document(content: bytes):
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError("不是有效的 DOCX 檔案")
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("不是有效的 DOCX 檔案")
            if archive.getinfo("[Content_Types].xml").file_size > MAX_CONTENT_TYPES_BYTES:
                raise ValueError("DOCX 內容過大")
            if archive.getinfo("word/document.xml").file_size > MAX_DOCUMENT_XML_BYTES:
                raise ValueError("DOCX 文件內容過大")
            if b"wordprocessingml.document.main+xml" not in archive.read("[Content_Types].xml"):
                raise ValueError("不是有效的 DOCX 檔案")
            document_xml = archive.read("word/document.xml")
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("不是有效的 DOCX 檔案") from exc

    try:
        return etree.fromstring(
            document_xml,
            parser=etree.XMLParser(resolve_entities=False, no_network=True, recover=False),
        )
    except etree.XMLSyntaxError as exc:
        raise ValueError("DOCX 內的文件內容已損壞") from exc


def _month_label(value: str):
    match = re.search(r"(?:(\d{2,4})年)?([一二三四五六七八九十]+|\d{1,2})月", value.replace(" ", ""))
    if not match:
        return None
    month_text = match.group(2)
    month = int(month_text) if month_text.isdigit() else MONTHS.get(month_text)
    if not month or not 1 <= month <= 12:
        return None
    year_text = match.group(1)
    year = None if not year_text else int(year_text) + (2000 if len(year_text) == 2 else 0)
    return year, month


def _border_kind(cell):
    active = []
    for name in ("tl2br", "tr2bl"):
        border = cell.find(f"./w:tcPr/w:tcBorders/w:{name}", namespaces=NS)
        active.append(border is not None and border.get(VAL) == "single")
    if all(active):
        return "school_holiday"
    if any(active):
        return "self_decided"
    return None


def _event_date(day: int, month: int, row_year: int, row_month: int) -> date:
    year = row_year
    if month - row_month > 6:
        year -= 1
    elif row_month - month > 6:
        year += 1
    return date(year, month, day)


def _clean_note(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" ,，;；、")
    return re.sub(r"\s*\d+\s*天\s*$", "", value).strip()


def _days(start: date, end: date):
    if end < start or (end - start).days > 370:
        raise ValueError("校曆包含無效的日期範圍")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _events(summaries):
    result = []
    for summary_index, (text, row_year, row_month) in enumerate(summaries):
        matches = list(DATE_RE.finditer(text))
        for index, match in enumerate(matches):
            note = _clean_note(text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else None])
            if not note or note in {"或", "或於"}:
                continue
            try:
                start = _event_date(int(match.group("day")), int(match.group("month")), row_year, row_month)
                if match.group("end_day"):
                    end = _event_date(
                        int(match.group("end_day")), int(match.group("end_month")), row_year, row_month
                    )
                    if end < start:
                        end = date(end.year + 1, end.month, end.day)
                else:
                    end = start
                _days(start, end)
            except ValueError as exc:
                raise ValueError("校曆摘要包含無效日期") from exc
            result.append({"start": start, "end": end, "note": note, "summary_index": summary_index})
    result.sort(key=lambda event: (event["start"], event["end"]))
    for event in result:
        if event["note"] == "翌日假期":
            previous = next(
                (
                    candidate
                    for candidate in reversed(result)
                    if candidate["summary_index"] == event["summary_index"]
                    and candidate["end"] == event["start"] - timedelta(days=1)
                ),
                None,
            )
            if previous:
                event["note"] = f"{previous['note']}翌日假期"
    return result


def _is_holiday(event) -> bool:
    return "假期" in event["note"] or "暑假" in event["note"]


def _is_teacher_development(event) -> bool:
    note = event["note"]
    return "教師" in note and "發展日" in note and ("學生放假" in note or "學生不用上課" in note)


def _suggested_ranges(events):
    def first(pattern):
        return next((event for event in events if re.search(pattern, event["note"])), None)

    first_start = first(r"開學日")
    first_end = first(r"上學期.*結業禮")
    second_start = first(r"下學期.*開課")
    second_ends = [event for event in events if re.search(r"結業禮|畢業禮", event["note"])]
    if second_start:
        second_ends = [event for event in second_ends if event["start"] >= second_start["start"]]
    second_end = max(second_ends, key=lambda event: event["end"], default=None)

    def value(start, end):
        return {
            "start": start["start"].isoformat() if start else None,
            "end": end["end"].isoformat() if end else None,
        }

    return {
        "full_year": value(first_start, second_end or first_end),
        "first_term": value(first_start, first_end),
        "second_term": value(second_start, second_end),
    }


def _group_closures(records, holiday_events):
    groups = []
    for record in records:
        current = {
            "start": record["date"],
            "end": record["date"],
            "dates": [record["date"]],
            "note": record["note"],
            "kind": record["kind"],
        }
        if groups:
            previous = groups[-1]
            adjacent = date.fromisoformat(record["date"]) == date.fromisoformat(previous["end"]) + timedelta(days=1)
            if adjacent and (previous["note"], previous["kind"]) == (record["note"], record["kind"]):
                previous["end"] = record["date"]
                previous["dates"].append(record["date"])
                continue
        groups.append(current)

    index = 0
    while index + 1 < len(groups):
        left, right = groups[index], groups[index + 1]
        covering = next(
            (
                event
                for event in holiday_events
                if event["note"] == left["note"] == right["note"]
                and left["kind"] == right["kind"]
                and event["start"] <= date.fromisoformat(left["start"])
                and event["end"] >= date.fromisoformat(right["end"])
            ),
            None,
        )
        if not covering:
            index += 1
            continue
        dates = left["dates"] + right["dates"]
        present = set(dates)
        left.update(end=right["end"], dates=dates)
        left["excluded_dates"] = [
            day.isoformat()
            for day in _days(date.fromisoformat(left["start"]), date.fromisoformat(left["end"]))
            if day.isoformat() not in present
        ]
        groups.pop(index + 1)
    for group in groups:
        group["key"] = f"{group['kind']}:{group['start']}:{group['end']}"
        group["name"] = group["note"]
    return groups


def parse_calendar_docx(content: bytes) -> dict:
    """Return a review-ready representation of the fixed-format school calendar."""

    root = _load_document(content)
    body_text = " ".join(_text(node) for node in root.xpath("/w:document/w:body/w:p", namespaces=NS))
    title = TITLE_RE.search(body_text)
    if not title or int(title.group(2)) != int(title.group(1)) + 1:
        raise ValueError("不支援此校曆格式：找不到學年標題")
    school_start, school_end = map(int, title.groups())

    calendar_dates = set()
    marked = {}
    summaries = []
    current_year, current_month = school_start, None
    supported_tables = 0

    for table in root.xpath("//w:tbl", namespaces=NS):
        rows = table.xpath("./w:tr", namespaces=NS)
        if len(rows) < 3 or "月份" not in _text(rows[0]) or "週內事項摘要" not in _text(rows[0]):
            continue
        supported_tables += 1
        for row in rows[2:]:
            cells = row.xpath("./w:tc", namespaces=NS)
            if len(cells) < 11:
                continue
            month_label = _month_label(_text(cells[0]))
            if month_label:
                explicit_year, month = month_label
                if explicit_year:
                    current_year = explicit_year
                elif current_month is not None and month < current_month:
                    current_year += 1
                current_month = month
            if current_month is None:
                continue

            summary_text = _text(cells[10])
            if summary_text:
                summaries.append((summary_text, current_year, current_month))

            for cell in cells[1:8]:
                day_match = re.match(r"\s*(\d{1,2})", _text(cell))
                if not day_match:
                    continue
                try:
                    cell_date = date(current_year, current_month, int(day_match.group(1)))
                except ValueError as exc:
                    raise ValueError("校曆日期格包含無效日期") from exc
                calendar_dates.add(cell_date)
                kind = _border_kind(cell)
                if kind:
                    marked[cell_date] = kind

    if not supported_tables or not calendar_dates:
        raise ValueError("不支援此校曆格式：找不到校曆表格")
    if min(calendar_dates).year < school_start or max(calendar_dates).year > school_end:
        raise ValueError("校曆日期與學年標題不一致")

    events = _events(summaries)
    teacher_events = [event for event in events if _is_teacher_development(event)]
    if not marked and not teacher_events:
        raise ValueError("不支援此校曆格式：找不到假期標記")

    internal = []
    defaults = {"school_holiday": "學校假期", "self_decided": "學校自決假期"}
    for closure_date, kind in sorted(marked.items()):
        candidates = [event for event in events if event["start"] <= closure_date <= event["end"]]
        candidates.sort(key=lambda event: (not _is_holiday(event), (event["end"] - event["start"]).days))
        event = candidates[0] if candidates else None
        internal.append(
            {
                "day": closure_date,
                "date": closure_date.isoformat(),
                "note": event["note"] if event else defaults[kind],
                "kind": kind,
                "event": event,
            }
        )

    existing = {record["day"] for record in internal}
    for event in teacher_events:
        for closure_date in _days(event["start"], event["end"]):
            if closure_date not in existing:
                internal.append(
                    {
                        "day": closure_date,
                        "date": closure_date.isoformat(),
                        "note": event["note"],
                        "kind": "teacher_development",
                        "event": event,
                    }
                )
                existing.add(closure_date)
    internal.sort(key=lambda record: record["day"])

    # Fill an unlabeled marked day from the one named holiday beside it (e.g. 24-25 May).
    run = []
    for record in internal + [None]:
        if record and (not run or (record["kind"] == run[-1]["kind"] and record["day"] == run[-1]["day"] + timedelta(days=1))):
            run.append(record)
            continue
        named = {(item["note"], id(item["event"])) for item in run if item["event"]}
        if len(named) == 1:
            source = next(item["event"] for item in run if item["event"])
            for item in run:
                if not item["event"]:
                    item.update(note=source["note"], event=source)
        run = [record] if record else []

    closures = [{key: record[key] for key in ("date", "note", "kind")} for record in internal]
    holiday_events = [event for event in events if _is_holiday(event)]
    groups = _group_closures(closures, holiday_events)

    warnings = []
    marked_dates = set(marked)
    for event in holiday_events:
        excluded = [day for day in _days(event["start"], event["end"]) if day in calendar_dates and day not in marked_dates]
        if excluded:
            warnings.append(
                f"{event['note']}文字日期範圍內有未標記日期，已按日期格排除："
                + "、".join(day.isoformat() for day in excluded)
            )

    expected_total = re.search(r"學校假期合計[：:]?\s*(\d+)日", body_text)
    expected_self = re.search(r"包括\s*(\d+)日自決假期", body_text)
    if expected_total and int(expected_total.group(1)) != len(marked):
        warnings.append(f"文件列明 {expected_total.group(1)} 日學校假期，但日期格辨識到 {len(marked)} 日")
    self_count = sum(kind == "self_decided" for kind in marked.values())
    if expected_self and int(expected_self.group(1)) != self_count:
        warnings.append(f"文件列明 {expected_self.group(1)} 日自決假期，但日期格辨識到 {self_count} 日")

    review_days = []
    for event in events:
        if (
            _is_holiday(event)
            or _is_teacher_development(event)
            or not REVIEW_RE.search(event["note"])
            or PARTIAL_SCOPE_RE.search(event["note"])
        ):
            continue
        review_days.append(
            {
                "start": event["start"].isoformat(),
                "end": event["end"].isoformat(),
                "dates": [day.isoformat() for day in _days(event["start"], event["end"])],
                "note": event["note"],
                "selected": False,
            }
        )

    school_count = sum(record["kind"] == "school_holiday" for record in internal)
    teacher_count = sum(record["kind"] == "teacher_development" for record in internal)
    return {
        "school_year": f"{school_start}-{school_end}",
        "calendar_start": min(calendar_dates).isoformat(),
        "calendar_end": max(calendar_dates).isoformat(),
        "suggested_ranges": _suggested_ranges(events),
        "closures": closures,
        "groups": groups,
        "review_days": review_days,
        "summary": {
            "school_holiday_days": school_count,
            "self_decided_days": self_count,
            "teacher_development_days": teacher_count,
            "closure_days": len(internal),
        },
        "warnings": warnings,
    }
