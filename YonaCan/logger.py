"""
YonaCan - CAN Data Logger
Handles logging CAN frames to files with rotation support.
"""

import os
import csv
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

from can_interface import CANFrame
from config import DEFAULT_LOG_DIR, DEFAULT_LOG_MAX_SIZE_MB


class CANLogger:
    """
    CAN frame logger with file rotation support.
    Uses _p# suffix for file rotation (e.g., mylog.csv, mylog_p1.csv, mylog_p2.csv)
    """
    
    def __init__(
        self,
        log_dir: str = DEFAULT_LOG_DIR,
        max_size_mb: float = DEFAULT_LOG_MAX_SIZE_MB,
        filename: str = ""  # Custom filename (without extension)
    ):
        self._log_dir = Path(log_dir)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._base_filename = filename  # User-specified filename
        
        self._file: Optional[any] = None
        self._writer: Optional[csv.writer] = None
        self._current_file_path: Optional[Path] = None
        self._frame_count: int = 0
        self._part_number: int = 0  # For _p# suffix
        self._logging: bool = False
        self._start_time: Optional[datetime] = None
        
    @property
    def log_dir(self) -> Path:
        """Get log directory as Path."""
        return self._log_dir
    
    @log_dir.setter
    def log_dir(self, value):
        """Set log directory (accepts str or Path)."""
        self._log_dir = Path(value) if isinstance(value, str) else value
    
    @property
    def base_filename(self) -> str:
        """Get base filename."""
        return self._base_filename
    
    @base_filename.setter
    def base_filename(self, value: str):
        """Set base filename (without extension)."""
        # Remove extension if provided
        self._base_filename = value.replace('.csv', '').replace('.CSV', '')
    
    def _generate_filename(self, part: int = 0) -> str:
        """Generate filename with optional part number."""
        if self._base_filename:
            base = self._base_filename
        else:
            # Default: timestamp-based name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"can_log_{timestamp}"
        
        if part > 0:
            return f"{base}_p{part}.csv"
        return f"{base}.csv"
    
    def start(self) -> str:
        """
        Start logging to a new file.
        Returns the file path.
        """
        if self._logging:
            self.stop()
        
        # Ensure log directory exists
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        self._start_time = datetime.now()
        self._part_number = 0
        filename = self._generate_filename(0)
        self._current_file_path = self._log_dir / filename
        
        # If file exists and we have a custom name, find next available part
        if self._base_filename and self._current_file_path.exists():
            self._part_number = 1
            while True:
                filename = self._generate_filename(self._part_number)
                self._current_file_path = self._log_dir / filename
                if not self._current_file_path.exists():
                    break
                self._part_number += 1
        
        # Open file and create CSV writer
        self._file = open(self._current_file_path, 'w', newline='', encoding='utf-8')
        self._writer = csv.writer(self._file)
        
        # Write header
        self._write_header()
        
        self._frame_count = 0
        self._logging = True
        
        return str(self._current_file_path)
    
    def _write_header(self):
        """Write CSV header row."""
        self._writer.writerow([
            "Timestamp",
            "Time_Offset_s",
            "Direction",
            "CAN_ID",
            "DLC",
            "Data_Hex",
            "Data_ASCII",
            "Extended",
            "Remote",
            "Error"
        ])
        self._file.flush()
    
    def stop(self) -> dict:
        """
        Stop logging and close the file.
        Returns statistics.
        """
        stats = {
            "frames_logged": self._frame_count,
            "files_created": self._part_number + 1,
            "duration_s": 0,
            "last_file": str(self._current_file_path) if self._current_file_path else None
        }
        
        if self._start_time:
            stats["duration_s"] = (datetime.now() - self._start_time).total_seconds()
        
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
            self._writer = None
        
        self._logging = False
        return stats
    
    def log_frame(self, frame: CANFrame):
        """Log a single CAN frame."""
        if not self._logging or not self._writer:
            return
        
        try:
            # Write frame to CSV
            self._writer.writerow([
                datetime.now().isoformat(),
                f"{frame.timestamp:.6f}",
                frame.direction.value,
                frame.id_hex,
                frame.dlc,
                frame.data_hex,
                frame.data_ascii,
                frame.is_extended,
                frame.is_remote,
                frame.is_error
            ])
            
            self._frame_count += 1
            
            # Flush periodically
            if self._frame_count % 100 == 0:
                self._file.flush()
                
                # Check file size for rotation
                self._check_rotation()
                
        except Exception as e:
            print(f"Logging error: {e}")
    
    def _check_rotation(self):
        """Check if file needs rotation based on size."""
        if not self._current_file_path or not self._file:
            return
        
        try:
            current_size = self._current_file_path.stat().st_size
            
            if current_size >= self.max_size_bytes:
                self._rotate_file()
        except Exception:
            pass
    
    def _rotate_file(self):
        """Rotate to a new log file with _p# suffix."""
        if not self._logging:
            return
        
        # Close current file
        if self._file:
            self._file.close()
        
        # Increment part number and generate new filename
        self._part_number += 1
        filename = self._generate_filename(self._part_number)
        self._current_file_path = self._log_dir / filename
        
        # Open new file
        self._file = open(self._current_file_path, 'w', newline='', encoding='utf-8')
        self._writer = csv.writer(self._file)
        
        # Write header
        self._write_header()
        
        print(f"Log rotated to: {self._current_file_path}")
    
    @property
    def is_logging(self) -> bool:
        return self._logging
    
    @property
    def current_file(self) -> Optional[str]:
        return str(self._current_file_path) if self._current_file_path else None
    
    @property
    def frames_logged(self) -> int:
        return self._frame_count
    
    @property
    def part_number(self) -> int:
        return self._part_number
    
    @property
    def current_file_size_mb(self) -> float:
        """Get current log file size in MB."""
        if self._current_file_path and self._current_file_path.exists():
            return self._current_file_path.stat().st_size / (1024 * 1024)
        return 0.0
