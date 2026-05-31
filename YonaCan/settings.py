"""
YonaCan - Settings Manager
Handles persistent user settings with backward compatibility.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

from config import (
    DEFAULT_BITRATE, DEFAULT_LOG_DIR, DEFAULT_LOG_MAX_SIZE_MB
)


# Default settings - used when config file is missing or has missing fields
DEFAULT_SETTINGS = {
    # Connection
    "bitrate": DEFAULT_BITRATE,
    "last_device": "",
    
    # Logging
    "log_directory": DEFAULT_LOG_DIR,
    "log_filename": "can_log",
    "log_max_size_mb": DEFAULT_LOG_MAX_SIZE_MB,
    
    # Data Viewer
    "auto_scroll": True,
    
    # DBC files
    "last_dbc_path": "",
    "last_pv_dbc_path": "",

    # Log Import Viewer
    "last_log_import_path": "",
    "last_log_import_file_type": "cl2000",
    "last_log_import_dbc_path": "",
    "last_isobus_ddi_path": "",
    "last_log_import_viz_mode": "bytes",
    "log_import_max_plot_points": 2500,

    # ISO BUS raw-data viewer
    "isobus_raw_pgn": 61184,
    "isobus_raw_id_indices": [0],
    "graph_plot_mode": "line",
    
    # Simulator
    "sim_selected_spns": [],
    "sim_spn_configs": {},
    
    # Raw Data Analyzer
    "graph_running": True,
    "graph_samples": 100,
    "graph_zoom": 1.0,  # 1.0 = 100%, 0.5 = 50%, 2.0 = 200%
    
    # Window
    "window_width": 900,
    "window_height": 600,
    "window_x": None,  # None = center
    "window_y": None,
}


class SettingsManager:
    """
    Manages persistent application settings.
    Automatically handles backward compatibility - missing fields use defaults.
    """
    
    def __init__(self, config_dir: str = None):
        """
        Initialize settings manager.
        
        Args:
            config_dir: Directory for config file. Defaults to user's app data.
        """
        if config_dir is None:
            # Use AppData/Local on Windows, ~/.config on Linux/Mac
            if os.name == 'nt':
                config_dir = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'YonaCan')
            else:
                config_dir = os.path.join(os.path.expanduser('~'), '.config', 'yonacan')
        
        self._config_dir = Path(config_dir)
        self._config_file = self._config_dir / 'settings.json'
        self._settings: Dict[str, Any] = {}
        
        # Load settings (or use defaults)
        self.load()
    
    def load(self) -> None:
        """Load settings from file, using defaults for missing fields."""
        # Start with defaults
        self._settings = DEFAULT_SETTINGS.copy()
        
        # Try to load from file
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                
                # Merge saved settings into defaults (saved values override defaults)
                for key, value in saved_settings.items():
                    if key in self._settings:
                        self._settings[key] = value
                    # Ignore unknown keys (from future versions)
                    
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load settings: {e}")
                # Keep defaults
    
    def save(self) -> bool:
        """
        Save current settings to file.
        
        Returns:
            True if saved successfully, False otherwise.
        """
        try:
            # Ensure directory exists
            self._config_dir.mkdir(parents=True, exist_ok=True)
            
            # Write settings
            with open(self._config_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2)
            
            return True
            
        except (IOError, OSError) as e:
            print(f"Warning: Could not save settings: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.
        
        Args:
            key: Setting key
            default: Default value if key not found (overrides DEFAULT_SETTINGS)
        
        Returns:
            Setting value
        """
        if default is not None:
            return self._settings.get(key, default)
        return self._settings.get(key, DEFAULT_SETTINGS.get(key))
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a setting value (does not auto-save).
        
        Args:
            key: Setting key
            value: Setting value
        """
        self._settings[key] = value
    
    def __getitem__(self, key: str) -> Any:
        """Get setting via indexing: settings['key']"""
        return self.get(key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Set setting via indexing: settings['key'] = value"""
        self.set(key, value)
    
    @property
    def config_file_path(self) -> str:
        """Get the path to the config file."""
        return str(self._config_file)
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self._settings = DEFAULT_SETTINGS.copy()

