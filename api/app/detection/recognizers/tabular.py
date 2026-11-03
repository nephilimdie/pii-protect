"""Use CSV parsing for semantics and lexical field boundaries for source offsets."""
import csv
import io
import re

from app.detection.recognizers.common import entity
from app.detection.recognizers.key_value import _type_for

_EMPTY = {"", "null", "none", "n/a", "-"}


def detect_tabular(text: str) -> list:
    lines = text.splitlines(keepends=True)
    if len(lines) < 2:
        return []
    try:
        dialect = csv.Sniffer().sniff(lines[0], delimiters=",;\t")
        reader = csv.reader(io.StringIO(text), dialect, strict=True)
        header = next(reader)
    except (csv.Error, StopIteration):
        return []
    types = [_type_for(key.strip()) for key in header]
    if len(header) < 2 or not any(types):
        return []
    sep = re.escape(dialect.delimiter)
    field = re.compile(rf'(?:^|{sep})(?P<value>"(?:[^"]|"")*"|[^"{sep}\r\n]*)(?={sep}|\r?\n?$)')
    previous = reader.line_num
    offset = sum(map(len, lines[:previous]))
    found = []
    try:
        for row in reader:
            record = "".join(lines[previous:reader.line_num])
            matches = list(field.finditer(record))
            if len(row) == len(header) == len(matches):
                for typ, value, match in zip(types, row, matches):
                    if not typ or value.strip().lower() in _EMPTY:
                        continue
                    start, end = match.span("value")
                    if record[start:end].startswith('"'):
                        start, end = start + 1, end - 1
                    while start < end and record[start].isspace():
                        start += 1
                    while end > start and record[end - 1].isspace():
                        end -= 1
                    if start < end:
                        found.append(entity(text, offset + start, offset + end, typ))
            offset += len(record)
            previous = reader.line_num
    except csv.Error:
        return []  # malformed tables must not produce guessed column associations
    return found
