"""Parse VirtualDJ M3U history in media-entry order."""

import re

VDJ_FIELD = re.compile(r"<(\w+)>(.*?)</\1>")
VDJ_FIELDS = {
    "artist": ("artist", str),
    "title": ("title", str),
    "remix": ("remix", str),
    "songlength": ("duration_seconds", float),
    "time": ("play_time", str),
    "lastplaytime": ("last_play_timestamp", int),
    "filesize": ("file_size_bytes", int),
}


def parse_m3u(contents: str) -> list[dict]:
    entries = []
    metadata = {}
    for line_number, raw_line in enumerate(contents.removeprefix("\ufeff").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTVDJ:"):
            metadata = {}
            for tag, value in VDJ_FIELD.findall(line):
                if tag in VDJ_FIELDS and value.strip():
                    field, convert = VDJ_FIELDS[tag]
                    try:
                        metadata[field] = convert(value)
                    except ValueError as error:
                        raise ValueError(
                            f"Line {line_number}: invalid VirtualDJ {tag}: {value!r}"
                        ) from error
        elif not line.startswith("#"):
            entries.append(
                {"position": len(entries) + 1, "path": line, **metadata}
            )
            metadata = {}
    return entries
