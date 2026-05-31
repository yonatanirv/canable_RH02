"""
YonaCan - Imported log file parser (CSS CL2000, YonaCan CSV).
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Iterator, Optional, Tuple

from dbc_handler import extract_j1939_pgn


class LogFileType(Enum):
    CL2000 = "cl2000"
    YONACAN_CSV = "yonacan_csv"


@dataclass
class LogSessionInfo:
    """Metadata from log file header."""
    session_start: Optional[datetime] = None
    bitrate: int = 250000
    logger_type: str = ""


@dataclass
class LogFrame:
    """One CAN frame from an imported log file."""
    timestamp: float  # Unix seconds (absolute wall time when known)
    can_id: int
    data: bytes
    is_extended: bool
    pgn: int
    line_no: int = 0


@dataclass
class PgnSummary:
    """Aggregated info for one PGN in a log file."""
    pgn: int
    count: int = 0
    last_can_id: int = 0
    last_data: bytes = field(default_factory=bytes)
    last_timestamp: float = 0.0


ProgressCallback = Callable[[int, int], None]

_CL2000_ROW_TS = re.compile(
    r"^(\d{1,2})T(\d{2})(\d{2})(\d{2})(\d{0,9})$", re.IGNORECASE
)


def _is_extended_id(can_id: int) -> bool:
    return can_id > 0x7FF


def _pgn_from_id(can_id: int, is_extended: bool) -> int:
    if is_extended:
        return extract_j1939_pgn(can_id)
    return can_id


def parse_cl2000_header(path: str) -> LogSessionInfo:
    """Read # comment header from a CL2000 export."""
    info = LogSessionInfo()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _ in range(30):
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith("#"):
                    break
                body = line.lstrip("#").strip()
                if body.lower().startswith("time:"):
                    val = body.split(":", 1)[1].strip()
                    for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            info.session_start = datetime.strptime(val, fmt)
                            break
                        except ValueError:
                            continue
                elif body.lower().startswith("bit-rate:"):
                    try:
                        info.bitrate = int(body.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                elif body.lower().startswith("logger type:"):
                    info.logger_type = body.split(":", 1)[1].strip()
    except OSError:
        pass
    return info


def _parse_cl2000_row_timestamp(
    ts_raw: str,
    session: LogSessionInfo,
    line_no: int,
    t0_unix: Optional[float],
) -> float:
    """
    Parse CL2000 row timestamp (e.g. 07T140657143) using session date from header.
    Falls back to seconds relative to first frame.
    """
    m = _CL2000_ROW_TS.match(ts_raw.strip())
    if m and session.session_start is not None:
        day = int(m.group(1))
        hour = int(m.group(2))
        minute = int(m.group(3))
        sec = int(m.group(4))
        ms_str = (m.group(5) or "0").ljust(3, "0")[:3]
        msec = int(ms_str)
        base = session.session_start
        try:
            dt = base.replace(
                day=day, hour=hour, minute=minute, second=sec, microsecond=msec * 1000
            )
            return dt.timestamp()
        except ValueError:
            pass
    try:
        raw = float(ts_raw)
        if t0_unix is not None:
            return t0_unix + raw
        return raw
    except ValueError:
        if t0_unix is not None:
            return t0_unix + float(line_no) * 0.001
        return float(line_no)


def _parse_cl2000_row(
    parts: list,
    line_no: int,
    session: LogSessionInfo,
    t0_unix: Optional[float],
) -> Optional[LogFrame]:
    if len(parts) < 4:
        return None
    try:
        msg_type = int(parts[1].strip())
    except ValueError:
        return None
    if msg_type != 1:
        return None
    try:
        can_id = int(parts[2].strip(), 16)
        data = bytes.fromhex(parts[3].strip())
    except ValueError:
        return None
    is_ext = _is_extended_id(can_id)
    ts = _parse_cl2000_row_timestamp(parts[0].strip(), session, line_no, t0_unix)
    return LogFrame(
        timestamp=ts,
        can_id=can_id,
        data=data,
        is_extended=is_ext,
        pgn=_pgn_from_id(can_id, is_ext),
        line_no=line_no,
    )


def _iter_cl2000_frames(
    path: str, session: Optional[LogSessionInfo] = None
) -> Iterator[LogFrame]:
    if session is None:
        session = parse_cl2000_header(path)
    t0_unix: Optional[float] = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        in_data = False
        for line_no, line in enumerate(fh, 1):
            line = line.rstrip("\n\r")
            if not in_data:
                if line.strip().lower() == "timestamp;type;id;data":
                    in_data = True
                continue
            if not line or line.startswith("#"):
                continue
            parts = line.split(";")
            frame = _parse_cl2000_row(parts, line_no, session, t0_unix)
            if frame is None:
                continue
            if t0_unix is None:
                t0_unix = frame.timestamp
            yield frame


def _iter_yonacan_csv_frames(path: str) -> Iterator[LogFrame]:
    session_start: Optional[datetime] = None
    t0_unix: Optional[float] = None
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, 2):
            id_str = row.get("CAN_ID", "").strip()
            data_str = row.get("Data_Hex", "").strip().replace(" ", "")
            if not id_str or not data_str:
                continue
            try:
                can_id = int(id_str, 16)
                data = bytes.fromhex(data_str.replace("0x", ""))
            except ValueError:
                continue
            ts_iso = row.get("Timestamp", "").strip()
            if ts_iso:
                try:
                    ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    try:
                        offset = float(row.get("Time_Offset_s", line_no))
                        if t0_unix is None:
                            t0_unix = 0.0
                        ts = (t0_unix or 0.0) + offset
                    except (ValueError, TypeError):
                        ts = float(line_no)
            else:
                try:
                    offset = float(row.get("Time_Offset_s", line_no))
                    if session_start is not None:
                        ts = session_start.timestamp() + offset
                    elif t0_unix is not None:
                        ts = t0_unix + offset
                    else:
                        if t0_unix is None:
                            t0_unix = 0.0
                        ts = offset
                except (ValueError, TypeError):
                    ts = float(line_no)
            if t0_unix is None:
                t0_unix = ts
            is_ext = _is_extended_id(can_id)
            yield LogFrame(
                timestamp=ts,
                can_id=can_id,
                data=data,
                is_extended=is_ext,
                pgn=_pgn_from_id(can_id, is_ext),
                line_no=line_no,
            )


def iter_log_frames(
    path: str,
    file_type: LogFileType,
    session: Optional[LogSessionInfo] = None,
) -> Iterator[LogFrame]:
    if file_type == LogFileType.CL2000:
        yield from _iter_cl2000_frames(path, session)
    else:
        yield from _iter_yonacan_csv_frames(path)


def _count_lines(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def scan_log(
    path: str,
    file_type: LogFileType,
    progress_cb: Optional[ProgressCallback] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
    session: Optional[LogSessionInfo] = None,
) -> Tuple[Dict[int, PgnSummary], LogSessionInfo]:
    """Single pass: build PGN index with counts and last frame per PGN."""
    if file_type == LogFileType.CL2000 and session is None:
        session = parse_cl2000_header(path)
    elif session is None:
        session = LogSessionInfo()

    total_est = _count_lines(path)
    index: Dict[int, PgnSummary] = {}
    lines_done = 0
    for frame in iter_log_frames(path, file_type, session):
        if cancel_flag and cancel_flag():
            break
        lines_done += 1
        if progress_cb and lines_done % 5000 == 0:
            progress_cb(lines_done, total_est)
        pgn = frame.pgn
        if pgn not in index:
            index[pgn] = PgnSummary(
                pgn=pgn,
                count=1,
                last_can_id=frame.can_id,
                last_data=frame.data,
                last_timestamp=frame.timestamp,
            )
        else:
            s = index[pgn]
            s.count += 1
            s.last_can_id = frame.can_id
            s.last_data = frame.data
            s.last_timestamp = frame.timestamp
    if progress_cb:
        progress_cb(lines_done, total_est)
    return index, session


def iter_frames_for_pgn(
    path: str,
    file_type: LogFileType,
    pgn: int,
    progress_cb: Optional[ProgressCallback] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
    max_frames: int = 5000,
    session: Optional[LogSessionInfo] = None,
) -> Iterator[LogFrame]:
    """Stream frames matching a PGN (for graphs)."""
    lines_done = 0
    yielded = 0
    for frame in iter_log_frames(path, file_type, session):
        if cancel_flag and cancel_flag():
            break
        lines_done += 1
        if progress_cb and lines_done % 10000 == 0:
            progress_cb(lines_done, 0)
        if frame.pgn != pgn:
            continue
        yield frame
        yielded += 1
        if yielded >= max_frames:
            break
