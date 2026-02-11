"""
YonaCan - DBC File Handler
Handles loading and parsing DBC files for CAN bus simulation.
Extracts PGN/SPN information with full signal metadata.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

try:
    import cantools
    CANTOOLS_AVAILABLE = True
except ImportError:
    CANTOOLS_AVAILABLE = False


def extract_j1939_pgn(can_id: int) -> int:
    """
    Extract PGN from a 29-bit J1939 CAN ID.

    J1939 29-bit CAN ID layout:
        Bits 28-26: Priority (3 bits)
        Bit 25:     Reserved
        Bit 24:     Data Page
        Bits 23-16: PDU Format (PF)
        Bits 15-8:  PDU Specific (PS)
        Bits 7-0:   Source Address (SA)

    PGN extraction:
        If PF >= 240 (0xF0): PGN = R|DP|PF|PS  (PDU2 - broadcast)
        If PF <  240:        PGN = R|DP|PF|00   (PDU1 - PS is destination)
    """
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    dp = (can_id >> 24) & 0x01
    r = (can_id >> 25) & 0x01

    if pf < 240:
        # PDU1: PS is destination address, not part of PGN
        pgn = (r << 17) | (dp << 16) | (pf << 8)
    else:
        # PDU2: PS is group extension, part of PGN
        pgn = (r << 17) | (dp << 16) | (pf << 8) | ps
    return pgn


@dataclass
class SPNInfo:
    """Signal/SPN information from a DBC file."""
    name: str
    start_bit: int
    length: int
    byte_order: str  # 'little_endian' or 'big_endian'
    is_signed: bool
    factor: float
    offset: float
    minimum: float
    maximum: float
    unit: str
    comment: str = ""
    receivers: List[str] = field(default_factory=list)

    @property
    def byte_order_short(self) -> str:
        """Human-readable byte order."""
        return "Little Endian" if self.byte_order == 'little_endian' else "Big Endian"

    @property
    def type_str(self) -> str:
        """Signed/unsigned display string."""
        return "Signed" if self.is_signed else "Unsigned"

    @property
    def range_str(self) -> str:
        """Formatted range string."""
        if self.minimum == 0 and self.maximum == 0:
            return ""
        return f"[{self.minimum}, {self.maximum}]"


@dataclass
class PGNInfo:
    """Message/PGN information from a DBC file."""
    can_id: int
    pgn: int
    name: str
    dlc: int
    sender: str
    is_extended: bool
    signals: List[SPNInfo] = field(default_factory=list)
    comment: str = ""

    @property
    def can_id_hex(self) -> str:
        """CAN ID as hex string."""
        if self.is_extended:
            return f"0x{self.can_id:08X}"
        return f"0x{self.can_id:03X}"

    @property
    def pgn_hex(self) -> str:
        """PGN as hex string."""
        return f"0x{self.pgn:04X}"

    @property
    def pgn_decimal(self) -> int:
        """PGN as decimal."""
        return self.pgn

    @property
    def frame_type_str(self) -> str:
        """Frame type display string."""
        return "Extended (29-bit)" if self.is_extended else "Standard (11-bit)"


@dataclass
class DBCConfig:
    """Configuration summary from a loaded DBC file."""
    filepath: str
    filename: str
    version: str
    num_messages: int
    num_signals: int
    nodes: List[str]
    has_extended_ids: bool
    has_standard_ids: bool
    has_big_endian: bool
    has_little_endian: bool
    has_signed: bool
    has_unsigned: bool

    @property
    def frame_types_str(self) -> str:
        """Summary of frame types found."""
        types = []
        if self.has_extended_ids:
            types.append("Extended (29-bit)")
        if self.has_standard_ids:
            types.append("Standard (11-bit)")
        return " + ".join(types) or "None"

    @property
    def byte_orders_str(self) -> str:
        """Summary of byte orders found."""
        orders = []
        if self.has_big_endian:
            orders.append("Big Endian")
        if self.has_little_endian:
            orders.append("Little Endian")
        return " + ".join(orders) or "None"

    @property
    def value_types_str(self) -> str:
        """Summary of value types found."""
        types = []
        if self.has_signed:
            types.append("Signed")
        if self.has_unsigned:
            types.append("Unsigned")
        return " + ".join(types) or "None"

    @property
    def nodes_summary(self) -> str:
        """Summary of nodes (truncated if too many)."""
        if not self.nodes:
            return "None defined"
        if len(self.nodes) <= 5:
            return ", ".join(self.nodes)
        return ", ".join(self.nodes[:5]) + f"... ({len(self.nodes)} total)"


class DBCHandler:
    """Handles loading and parsing DBC files for CAN bus simulation."""

    def __init__(self):
        self.db = None
        self.pgns: List[PGNInfo] = []
        self.config: Optional[DBCConfig] = None
        self._filepath: str = ""

    @staticmethod
    def is_available() -> bool:
        """Check if cantools library is available."""
        return CANTOOLS_AVAILABLE

    def load(self, filepath: str) -> DBCConfig:
        """
        Load and parse a DBC file.

        Args:
            filepath: Path to the .dbc file

        Returns:
            DBCConfig with summary of loaded file

        Raises:
            ImportError: If cantools is not installed
            FileNotFoundError: If file doesn't exist
            Exception: If parsing fails
        """
        if not CANTOOLS_AVAILABLE:
            raise ImportError(
                "cantools library is required for DBC file support.\n"
                "Install with: pip install cantools"
            )

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"DBC file not found: {filepath}")

        self._filepath = filepath
        self.db = cantools.database.load_file(filepath)

        # Parse messages and signals
        self.pgns = []
        has_extended = False
        has_standard = False
        has_big_endian = False
        has_little_endian = False
        has_signed = False
        has_unsigned = False
        total_signals = 0

        for msg in self.db.messages:
            is_ext = getattr(msg, 'is_extended_frame', False)
            if is_ext:
                has_extended = True
                pgn_num = extract_j1939_pgn(msg.frame_id)
            else:
                has_standard = True
                pgn_num = msg.frame_id

            signals = []
            for sig in msg.signals:
                byte_order = getattr(sig, 'byte_order', 'little_endian') or 'little_endian'
                is_signed = getattr(sig, 'is_signed', False)

                if byte_order == 'big_endian':
                    has_big_endian = True
                else:
                    has_little_endian = True

                if is_signed:
                    has_signed = True
                else:
                    has_unsigned = True

                # Handle None values for min/max
                sig_min = sig.minimum if sig.minimum is not None else 0.0
                sig_max = sig.maximum if sig.maximum is not None else 0.0
                sig_scale = sig.scale if sig.scale is not None else 1.0
                sig_offset = sig.offset if sig.offset is not None else 0.0

                spn = SPNInfo(
                    name=sig.name,
                    start_bit=sig.start,
                    length=sig.length,
                    byte_order=byte_order,
                    is_signed=is_signed,
                    factor=sig_scale,
                    offset=sig_offset,
                    minimum=sig_min,
                    maximum=sig_max,
                    unit=getattr(sig, 'unit', '') or '',
                    comment=getattr(sig, 'comment', '') or '',
                    receivers=list(getattr(sig, 'receivers', []) or [])
                )
                signals.append(spn)
                total_signals += 1

            # Sort signals within each PGN by name
            signals.sort(key=lambda s: s.name)

            sender = msg.senders[0] if msg.senders else ""

            pgn_info = PGNInfo(
                can_id=msg.frame_id,
                pgn=pgn_num,
                name=msg.name,
                dlc=msg.length,
                sender=sender,
                is_extended=is_ext,
                signals=signals,
                comment=getattr(msg, 'comment', '') or ''
            )
            self.pgns.append(pgn_info)

        # Sort PGNs by PGN number, then by name
        self.pgns.sort(key=lambda p: (p.pgn, p.name))

        # Build config summary
        nodes = []
        if hasattr(self.db, 'nodes'):
            nodes = [n.name for n in self.db.nodes]

        self.config = DBCConfig(
            filepath=filepath,
            filename=os.path.basename(filepath),
            version=getattr(self.db, 'version', '') or '',
            num_messages=len(self.pgns),
            num_signals=total_signals,
            nodes=nodes,
            has_extended_ids=has_extended,
            has_standard_ids=has_standard,
            has_big_endian=has_big_endian,
            has_little_endian=has_little_endian,
            has_signed=has_signed,
            has_unsigned=has_unsigned
        )

        return self.config

    @property
    def is_loaded(self) -> bool:
        """Check if a DBC file is loaded."""
        return self.db is not None and len(self.pgns) > 0

    def get_selected_spn_info(self, selected_keys: set) -> List[Tuple[PGNInfo, SPNInfo]]:
        """
        Get full info for selected SPNs.

        Args:
            selected_keys: Set of "pgn_name.spn_name" keys

        Returns:
            List of (PGNInfo, SPNInfo) tuples for selected SPNs
        """
        result = []
        for pgn in self.pgns:
            for spn in pgn.signals:
                key = f"{pgn.name}.{spn.name}"
                if key in selected_keys:
                    result.append((pgn, spn))
        return result

