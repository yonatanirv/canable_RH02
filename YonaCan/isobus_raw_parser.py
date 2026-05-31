"""
YonaCan - ISO BUS proprietary / raw-data PGN parsing (e.g. PGN 61184 / 0xEF00).

Message-type identifier = one or more consecutive payload bytes (any position B0–B7).
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from log_import_parser import (
    LogFileType,
    LogSessionInfo,
    ProgressCallback,
    _count_lines,
    iter_log_frames,
    parse_cl2000_header,
)

# ISO 11783 proprietary A2 PGN (decimal 61184, hex 0xEF00)
DEFAULT_RAW_DATA_PGN = 61184

# Message key: byte values at selected indices, in index order
MessageKey = Tuple[int, ...]


@dataclass
class IsobusTypeSummary:
    """One message-type identifier seen on the raw-data PGN."""
    message_key: MessageKey
    count: int = 0
    last_can_id: int = 0
    last_data: bytes = field(default_factory=bytes)
    last_timestamp: float = 0.0
    max_data_len: int = 0


def parse_pgn_value(text: str) -> int:
    """Parse PGN from decimal or 0x hex string."""
    s = text.strip()
    if not s:
        raise ValueError("empty PGN")
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s)


def validate_id_byte_indices(indices: List[int]) -> Optional[str]:
    """
    Return an error message if identifier byte selection is invalid, else None.
    Identifier bytes must be non-empty, in B0–B7, unique, and consecutive.
    """
    if not indices:
        return (
            "Select at least one byte as the message identifier "
            "(check the boxes under “Identifier bytes”)."
        )
    if len(indices) > 8:
        return "At most 8 identifier bytes are allowed."
    if any(i < 0 or i > 7 for i in indices):
        return "Byte indices must be B0 through B7."
    if len(indices) != len(set(indices)):
        return "Each byte can only be selected once for the identifier."
    sorted_idx = sorted(indices)
    for j in range(1, len(sorted_idx)):
        if sorted_idx[j] != sorted_idx[j - 1] + 1:
            return (
                "Identifier bytes must be consecutive "
                f"(e.g. B{sorted_idx[0]}–B{sorted_idx[j - 1]} then B{sorted_idx[j]} breaks the range)."
            )
    return None


def normalize_id_indices(indices: List[int]) -> Tuple[int, ...]:
    """Sort and tuple-ize after validation."""
    return tuple(sorted(indices))


def extract_message_key(
    data: bytes,
    id_indices: Tuple[int, ...],
) -> Optional[MessageKey]:
    """Read message-type key from selected byte positions."""
    if not id_indices:
        return None
    if len(data) <= max(id_indices):
        return None
    return tuple(data[i] for i in id_indices)


def format_message_key(key: MessageKey) -> str:
    if not key:
        return "(empty)"
    return " ".join(f"0x{b:02X}" for b in key)


def format_id_indices_label(id_indices: Tuple[int, ...]) -> str:
    if len(id_indices) == 1:
        return f"B{id_indices[0]}"
    return f"B{id_indices[0]}–B{id_indices[-1]}"


def payload_byte_indices(
    id_indices: Tuple[int, ...],
    data_len: int,
) -> List[int]:
    """Frame byte indices that are not part of the identifier."""
    id_set = set(id_indices)
    return [i for i in range(min(8, data_len)) if i not in id_set]


def scan_isobus_raw_log(
    path: str,
    file_type: LogFileType,
    raw_pgn: int = DEFAULT_RAW_DATA_PGN,
    id_indices: Tuple[int, ...] = (0,),
    progress_cb: Optional[ProgressCallback] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
    session: Optional[LogSessionInfo] = None,
) -> Tuple[Dict[MessageKey, IsobusTypeSummary], LogSessionInfo]:
    """Index message-type keys on the configured raw-data PGN."""
    if file_type == LogFileType.CL2000 and session is None:
        session = parse_cl2000_header(path)
    elif session is None:
        session = LogSessionInfo()

    total_est = _count_lines(path)
    index: Dict[MessageKey, IsobusTypeSummary] = {}
    lines_done = 0
    for frame in iter_log_frames(path, file_type, session):
        if cancel_flag and cancel_flag():
            break
        lines_done += 1
        if progress_cb and lines_done % 5000 == 0:
            progress_cb(lines_done, total_est)
        if frame.pgn != raw_pgn:
            continue
        msg_key = extract_message_key(frame.data, id_indices)
        if msg_key is None:
            continue
        if msg_key not in index:
            index[msg_key] = IsobusTypeSummary(
                message_key=msg_key,
                count=1,
                last_can_id=frame.can_id,
                last_data=frame.data,
                last_timestamp=frame.timestamp,
                max_data_len=len(frame.data),
            )
        else:
            s = index[msg_key]
            s.count += 1
            s.last_can_id = frame.can_id
            s.last_data = frame.data
            s.last_timestamp = frame.timestamp
            s.max_data_len = max(s.max_data_len, len(frame.data))
    if progress_cb:
        progress_cb(lines_done, total_est)
    return index, session


def iter_frames_for_isobus_type(
    path: str,
    file_type: LogFileType,
    raw_pgn: int,
    message_key: MessageKey,
    id_indices: Tuple[int, ...] = (0,),
    max_frames: int = 5000,
    session: Optional[LogSessionInfo] = None,
    cancel_flag: Optional[Callable[[], bool]] = None,
) -> Iterator:
    """Yield LogFrame entries matching raw PGN and message-type key."""
    yielded = 0
    for frame in iter_log_frames(path, file_type, session):
        if cancel_flag and cancel_flag():
            break
        if frame.pgn != raw_pgn:
            continue
        key = extract_message_key(frame.data, id_indices)
        if key != message_key:
            continue
        yield frame
        yielded += 1
        if yielded >= max_frames:
            break


def build_type_history_cache(
    path: str,
    file_type: LogFileType,
    raw_pgn: int,
    message_key: MessageKey,
    id_indices: Tuple[int, ...],
    max_frames: int,
    session: Optional[LogSessionInfo],
) -> Dict:
    """
    Build byte time-series for one message type.
    Returns {"bytes": List[List[(t,v)]], "max_len": int}.
    """
    byte_pts: List[List[Tuple[float, float]]] = [[] for _ in range(8)]
    max_len = 0
    for frame in iter_frames_for_isobus_type(
            path, file_type, raw_pgn, message_key, id_indices,
            max_frames=max_frames, session=session):
        max_len = max(max_len, len(frame.data))
        for i in range(min(8, len(frame.data))):
            byte_pts[i].append((frame.timestamp, float(frame.data[i])))
    return {"bytes": byte_pts, "max_len": max_len}
