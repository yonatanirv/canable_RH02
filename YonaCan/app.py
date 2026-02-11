"""
YonaCan - Main Application GUI
Modern CAN bus analyzer for candleLight devices.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Set
import queue
from collections import defaultdict, deque
import time

from config import (
    APP_NAME, APP_VERSION, COLORS, 
    SUPPORTED_BITRATES, DEFAULT_BITRATE,
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    DATA_VIEWER_MAX_ROWS, DATA_VIEWER_UPDATE_MS,
    DEFAULT_LOG_MAX_SIZE_MB, DEFAULT_LOG_DIR,
    DEFAULT_GRAPH_UPDATE_RATE_MS
)
from can_interface import CANInterface, CANFrame, CANDevice, FrameDirection
from logger import CANLogger
from settings import SettingsManager
from dbc_handler import DBCHandler, DBCConfig, PGNInfo, SPNInfo, extract_j1939_pgn


class YonaCanApp:
    """Main application class."""
    
    def __init__(self):
        # Load settings first
        self.settings = SettingsManager()
        
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        
        # Restore window size/position from settings
        width = self.settings.get("window_width", WINDOW_MIN_WIDTH)
        height = self.settings.get("window_height", WINDOW_MIN_HEIGHT)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.root.configure(bg=COLORS["bg_dark"])
        
        # Restore window position if saved
        win_x = self.settings.get("window_x")
        win_y = self.settings.get("window_y")
        if win_x is not None and win_y is not None:
            self.root.geometry(f"+{win_x}+{win_y}")
        
        # Initialize components
        self.can_interface = CANInterface()
        self.logger = CANLogger()
        self.frame_queue: queue.Queue = queue.Queue()
        self.devices: List[CANDevice] = []
        
        # UI State
        self._frame_count = 0
        self._rx_count = 0
        self._tx_count = 0
        
        # Raw data tracking
        self._can_id_data: Dict[int, CANFrame] = {}  # Last frame per CAN ID
        self._can_id_counts: Dict[int, int] = defaultdict(int)  # Frame count per ID
        self._selected_can_id: Optional[int] = None
        
        # Simulator state
        self._dbc_handler = DBCHandler()
        self._sim_selected_spns: Set[str] = set()  # Set of "pgn_name.spn_name" keys
        self._sim_spn_tree_items: Dict[str, str] = {}  # spn_key -> tree item id
        self._sim_tree_item_to_key: Dict[str, str] = {}  # tree item id -> spn_key
        self._sim_pgn_tree_items: Dict[str, str] = {}  # pgn_name -> tree item id
        
        # Signal generation state
        self._sim_gen_widgets: Dict[str, Dict] = {}  # spn_key -> widget dict
        self._sim_spn_configs: Dict[str, Dict] = {}  # spn_key -> saved config dict
        self._sim_running_flag = False
        self._sim_thread: Optional[threading.Thread] = None
        self._sim_sweep_values: Dict[str, float] = {}  # Current sweep value per SPN
        self._sim_tx_count = 0
        self._sim_error_count = 0
        self._sim_start_time = 0.0
        
        # Parsed Data Viewer state
        self._pv_dbc = DBCHandler()
        self._pv_msg_by_id: Dict[int, any] = {}    # frame_id -> cantools message
        self._pv_msg_by_pgn: Dict[int, any] = {}   # PGN number -> cantools message
        self._pv_spn_history: Dict[str, deque] = {} # "pgn.spn" -> deque[(ts, val)]
        self._pv_latest_values: Dict[str, Tuple[float, float]] = {}  # -> (ts, val)
        self._pv_graph_slots: List[Dict] = []       # Active graph widget dicts
        self._pv_selected_graph_spns: List[str] = []  # Ordered SPN keys in graphs
        self._pv_tree_items: Dict[str, str] = {}    # spn_key -> tree item id
        self._pv_pgn_tree_items: Dict[int, str] = {} # pgn_number -> tree item id
        self._pv_last_draw = 0.0
        self._pv_graph_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6"]
        # RX-driven PGN tracking: pgn_number -> info dict
        self._pv_rx_pgns: Dict[int, Dict] = {}
        
        # Byte history for line graphs (8 deques storing (timestamp, value) tuples)
        self._byte_history: List[deque[Tuple[float, int]]] = [deque(maxlen=1000) for _ in range(8)]
        self._graph_running = self.settings.get("graph_running", True)
        self._graph_samples = self.settings.get("graph_samples", 100)
        self._graph_zoom = self.settings.get("graph_zoom", 1.0)
        self._graph_update_rate_ms = self.settings.get("graph_update_rate_ms", DEFAULT_GRAPH_UPDATE_RATE_MS)
        self._last_graph_draw = 0.0
        self._byte_active = [True] * 8
        
        # Setup UI
        self._setup_styles()
        self._create_widgets()
        self._bind_events()
        
        # Apply saved settings to UI
        self._apply_settings()
        
        # Start UI update loop
        self._schedule_update()
        
    def _apply_settings(self):
        """Apply saved settings to UI elements."""
        # Bitrate
        self.bitrate_var.set(str(self.settings.get("bitrate", DEFAULT_BITRATE)))
        
        # Logging settings
        self.log_dir_var.set(self.settings.get("log_directory", DEFAULT_LOG_DIR))
        self.log_filename_var.set(self.settings.get("log_filename", "can_log"))
        self.max_size_var.set(str(self.settings.get("log_max_size_mb", DEFAULT_LOG_MAX_SIZE_MB)))
        
        # Auto-scroll
        self.autoscroll_var.set(self.settings.get("auto_scroll", True))
        
        # Graph settings
        self._graph_samples = self.settings.get("graph_samples", 100)
        self._graph_zoom = self.settings.get("graph_zoom", 1.0)
        self._graph_running = self.settings.get("graph_running", True)
        try:
            self._graph_update_rate_ms = int(self.settings.get("graph_update_rate_ms", DEFAULT_GRAPH_UPDATE_RATE_MS))
        except (ValueError, TypeError):
            self._graph_update_rate_ms = DEFAULT_GRAPH_UPDATE_RATE_MS
        
        # Update graph controls
        self.samples_var.set(str(self._graph_samples))
        self.zoom_var.set(f"{int(self._graph_zoom * 100)}%")
        if hasattr(self, "rate_var"):
            self.rate_var.set(str(self._graph_update_rate_ms))
        self._update_graph_button_state()
        
        # Restore last DBC file (parsed viewer)
        last_pv_dbc = self.settings.get("last_pv_dbc_path", "")
        if last_pv_dbc and os.path.isfile(last_pv_dbc):
            try:
                self._pv_load_dbc_file(last_pv_dbc)
            except Exception as e:
                print(f"Could not restore parsed-viewer DBC: {e}")
        
        # Restore last DBC file (simulator) + selected SPNs + configs
        last_dbc = self.settings.get("last_dbc_path", "")
        if last_dbc and os.path.isfile(last_dbc):
            try:
                config = self._dbc_handler.load(last_dbc)
                self.dbc_path_var.set(last_dbc)
                self._update_dbc_config_display(config)
                # Restore selected SPNs and their configs
                saved_spns = self.settings.get("sim_selected_spns", [])
                saved_configs = self.settings.get("sim_spn_configs", {})
                if saved_spns:
                    self._sim_selected_spns = set(saved_spns)
                    self._sim_spn_configs = dict(saved_configs)
                self._populate_spn_tree()
                self._update_signal_gen_table()
            except Exception as e:
                print(f"Could not restore DBC: {e}")
        
    def _save_settings(self):
        """Save current settings from UI."""
        # Connection
        self.settings["bitrate"] = int(self.bitrate_var.get())
        
        # Logging
        self.settings["log_directory"] = self.log_dir_var.get()
        self.settings["log_filename"] = self.log_filename_var.get()
        self.settings["log_max_size_mb"] = float(self.max_size_var.get())
        
        # Data viewer
        self.settings["auto_scroll"] = self.autoscroll_var.get()
        
        # Graph settings
        self.settings["graph_running"] = self._graph_running
        self.settings["graph_samples"] = self._graph_samples
        self.settings["graph_zoom"] = self._graph_zoom
        self.settings["graph_update_rate_ms"] = self._graph_update_rate_ms
        
        # Window geometry
        self.settings["window_width"] = self.root.winfo_width()
        self.settings["window_height"] = self.root.winfo_height()
        self.settings["window_x"] = self.root.winfo_x()
        self.settings["window_y"] = self.root.winfo_y()
        
        # Simulator config
        self._capture_sim_gen_values()
        self.settings["sim_selected_spns"] = list(self._sim_selected_spns)
        self.settings["sim_spn_configs"] = self._sim_spn_configs
        
        # Save to file
        self.settings.save()
        
    def _setup_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Frame styles
        style.configure("Dark.TFrame", background=COLORS["bg_dark"])
        style.configure("Medium.TFrame", background=COLORS["bg_medium"])
        
        # Label styles
        style.configure("Dark.TLabel", 
                       background=COLORS["bg_dark"], 
                       foreground=COLORS["fg_primary"],
                       font=("Segoe UI", 10))
        style.configure("Medium.TLabel", 
                       background=COLORS["bg_medium"], 
                       foreground=COLORS["fg_primary"],
                       font=("Segoe UI", 10))
        style.configure("Title.TLabel",
                       background=COLORS["bg_medium"],
                       foreground=COLORS["accent"],
                       font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel",
                       background=COLORS["bg_medium"],
                       foreground=COLORS["fg_secondary"],
                       font=("Segoe UI", 9))
        
        # Button styles
        style.configure("Accent.TButton",
                       background=COLORS["accent"],
                       foreground=COLORS["fg_primary"],
                       font=("Segoe UI", 10),
                       padding=(10, 5))
        style.map("Accent.TButton",
                 background=[("active", COLORS["accent_hover"])])
        
        style.configure("Success.TButton",
                       background=COLORS["success"],
                       foreground=COLORS["bg_dark"],
                       font=("Segoe UI", 10, "bold"),
                       padding=(12, 6))
        
        style.configure("Error.TButton",
                       background=COLORS["error"],
                       foreground=COLORS["fg_primary"],
                       font=("Segoe UI", 10, "bold"),
                       padding=(12, 6))
        
        style.configure("Small.TButton",
                       font=("Segoe UI", 9),
                       padding=(6, 3))
        
        # Notebook (tabs) style
        style.configure("TNotebook", background=COLORS["bg_dark"])
        style.configure("TNotebook.Tab", 
                       background=COLORS["bg_medium"],
                       foreground=COLORS["fg_primary"],
                       padding=(15, 8),
                       font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                 background=[("selected", COLORS["accent"])],
                 foreground=[("selected", COLORS["fg_primary"])])
        
        # Treeview dark styling
        style.configure("Treeview",
                       background=COLORS["bg_dark"],
                       foreground=COLORS["fg_primary"],
                       fieldbackground=COLORS["bg_dark"],
                       font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                       background=COLORS["bg_medium"],
                       foreground=COLORS["fg_primary"],
                       font=("Segoe UI", 10, "bold"))
        style.map("Treeview",
                 background=[("selected", COLORS["accent"])],
                 foreground=[("selected", COLORS["fg_primary"])])

    def _create_widgets(self):
        """Create all UI widgets."""
        # Main container
        main_frame = ttk.Frame(self.root, style="Dark.TFrame", padding=5)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === Connection Bar (always visible) ===
        self._create_connection_bar(main_frame)
        
        # === Notebook (Tabs) ===
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # Tab 1: Device Config (Data Viewer + Logging)
        self.tab_config = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_config, text="📊 Data Viewer")
        self._create_config_tab(self.tab_config)
        
        # Tab 2: Raw Data Viewer
        self.tab_raw = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_raw, text="🔬 Raw Data Analyzer")
        self._create_raw_data_tab(self.tab_raw)
        
        # Tab 3: Parsed Data Viewer
        self.tab_parsed = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_parsed, text="📈 Parsed Data Viewer")
        self._create_parsed_viewer_tab(self.tab_parsed)
        
        # Tab 4: CAN Simulator
        self.tab_simulator = ttk.Frame(self.notebook, style="Dark.TFrame")
        self.notebook.add(self.tab_simulator, text="🔧 CAN Simulator")
        self._create_simulator_tab(self.tab_simulator)
        
    def _create_connection_bar(self, parent):
        """Create compact connection bar at top."""
        conn_frame = ttk.Frame(parent, style="Medium.TFrame", padding=8)
        conn_frame.pack(fill=tk.X)
        
        # Device selection
        ttk.Label(conn_frame, text="Device:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(conn_frame, textvariable=self.device_var, 
                                         state="readonly", width=40)
        self.device_combo.pack(side=tk.LEFT, padx=(0, 5))
        
        # Scan button
        self.scan_btn = ttk.Button(conn_frame, text="🔍 Scan", 
                                   command=self._scan_devices, style="Accent.TButton", width=8)
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Bitrate selection
        ttk.Label(conn_frame, text="Bitrate:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        
        self.bitrate_var = tk.StringVar(value=str(DEFAULT_BITRATE))
        bitrate_combo = ttk.Combobox(conn_frame, textvariable=self.bitrate_var,
                                     values=[str(b) for b in SUPPORTED_BITRATES],
                                     state="readonly", width=10)
        bitrate_combo.pack(side=tk.LEFT, padx=(0, 15))
        
        # Connect/Disconnect buttons
        self.connect_btn = ttk.Button(conn_frame, text="▶ Connect",
                                      command=self._connect, style="Success.TButton", width=10)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.disconnect_btn = ttk.Button(conn_frame, text="⏹ Stop",
                                         command=self._disconnect, style="Error.TButton",
                                         state=tk.DISABLED, width=8)
        self.disconnect_btn.pack(side=tk.LEFT)
        
        # Connection status
        self.conn_status_var = tk.StringVar(value="● Disconnected")
        self.conn_status = ttk.Label(conn_frame, textvariable=self.conn_status_var,
                                     style="Status.TLabel")
        self.conn_status.pack(side=tk.RIGHT, padx=10)
        
    def _create_config_tab(self, parent):
        """Create the Device Config tab with data viewer and logging."""
        # === Data Viewer Section ===
        viewer_frame = ttk.Frame(parent, style="Medium.TFrame", padding=8)
        viewer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Title row
        title_row = ttk.Frame(viewer_frame, style="Medium.TFrame")
        title_row.pack(fill=tk.X)
        
        ttk.Label(title_row, text="Real-Time Frames", style="Title.TLabel").pack(side=tk.LEFT)
        
        # Frame counters
        self.counter_var = tk.StringVar(value="RX: 0 | TX: 0 | Total: 0")
        ttk.Label(title_row, textvariable=self.counter_var, 
                 style="Status.TLabel").pack(side=tk.RIGHT, padx=10)
        
        # Clear button
        ttk.Button(title_row, text="🗑 Clear", command=self._clear_data,
                  style="Accent.TButton", width=8).pack(side=tk.RIGHT, padx=5)
        
        # Auto-scroll checkbox
        self.autoscroll_var = tk.BooleanVar(value=True)
        autoscroll_cb = tk.Checkbutton(title_row, text="Auto-scroll",
                                       variable=self.autoscroll_var,
                                       bg=COLORS["bg_medium"],
                                       fg=COLORS["fg_primary"],
                                       selectcolor=COLORS["bg_dark"],
                                       activebackground=COLORS["bg_medium"],
                                       activeforeground=COLORS["fg_primary"])
        autoscroll_cb.pack(side=tk.RIGHT, padx=10)
        
        # Treeview for data
        tree_frame = ttk.Frame(viewer_frame, style="Medium.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        
        # Columns
        columns = ("num", "time", "dir", "id", "dlc", "data", "ascii")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                 selectmode="extended")
        
        # Column headings and widths
        self.tree.heading("num", text="#")
        self.tree.heading("time", text="Time (s)")
        self.tree.heading("dir", text="Dir")
        self.tree.heading("id", text="CAN ID")
        self.tree.heading("dlc", text="DLC")
        self.tree.heading("data", text="Data (Hex)")
        self.tree.heading("ascii", text="ASCII")
        
        self.tree.column("num", width=50, anchor=tk.CENTER)
        self.tree.column("time", width=80, anchor=tk.CENTER)
        self.tree.column("dir", width=40, anchor=tk.CENTER)
        self.tree.column("id", width=80, anchor=tk.CENTER)
        self.tree.column("dlc", width=40, anchor=tk.CENTER)
        self.tree.column("data", width=200, anchor=tk.W)
        self.tree.column("ascii", width=80, anchor=tk.W)
        
        # Scrollbar
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tags for coloring
        self.tree.tag_configure("rx", foreground=COLORS["can_rx"])
        self.tree.tag_configure("tx", foreground=COLORS["can_tx"])
        
        # === Logging Section ===
        log_frame = ttk.Frame(parent, style="Medium.TFrame", padding=8)
        log_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        ttk.Label(log_frame, text="📁 Logging", style="Title.TLabel").pack(anchor=tk.W)
        
        # Controls row
        log_controls = ttk.Frame(log_frame, style="Medium.TFrame")
        log_controls.pack(fill=tk.X, pady=(8, 0))
        
        # Filename
        ttk.Label(log_controls, text="Filename:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        
        self.log_filename_var = tk.StringVar(value="can_log")
        filename_entry = ttk.Entry(log_controls, textvariable=self.log_filename_var, width=20)
        filename_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Directory
        ttk.Label(log_controls, text="Dir:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        
        self.log_dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)
        log_dir_entry = ttk.Entry(log_controls, textvariable=self.log_dir_var, width=35)
        log_dir_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(log_controls, text="📂", command=self._browse_log_dir, width=3).pack(side=tk.LEFT, padx=(0, 10))
        
        # Max size
        ttk.Label(log_controls, text="Max MB:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        
        self.max_size_var = tk.StringVar(value=str(DEFAULT_LOG_MAX_SIZE_MB))
        max_size_entry = ttk.Entry(log_controls, textvariable=self.max_size_var, width=6)
        max_size_entry.pack(side=tk.LEFT, padx=(0, 15))
        
        # Start/Stop buttons
        self.log_start_btn = ttk.Button(log_controls, text="▶ Start Log",
                                        command=self._start_logging, style="Success.TButton", width=10)
        self.log_start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.log_stop_btn = ttk.Button(log_controls, text="⏹ Stop",
                                       command=self._stop_logging, style="Error.TButton",
                                       state=tk.DISABLED, width=8)
        self.log_stop_btn.pack(side=tk.LEFT)
        
        # Logging status
        self.log_status_var = tk.StringVar(value="Not logging")
        ttk.Label(log_controls, textvariable=self.log_status_var,
                 style="Status.TLabel").pack(side=tk.RIGHT, padx=10)
        
    def _create_raw_data_tab(self, parent):
        """Create the Raw Data Analyzer tab."""
        # Use PanedWindow for resizable sections
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # === Left Panel: CAN ID List ===
        left_frame = ttk.Frame(paned, style="Medium.TFrame", padding=8)
        paned.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="CAN IDs Detected", style="Title.TLabel").pack(anchor=tk.W)
        
        # CAN ID listbox
        list_frame = ttk.Frame(left_frame, style="Medium.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        
        self.canid_listbox = tk.Listbox(list_frame, 
                                        bg=COLORS["bg_dark"],
                                        fg=COLORS["fg_primary"],
                                        selectbackground=COLORS["accent"],
                                        selectforeground=COLORS["fg_primary"],
                                        font=("Consolas", 11),
                                        activestyle='none')
        self.canid_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canid_listbox.bind('<<ListboxSelect>>', self._on_canid_select)
        
        canid_vsb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.canid_listbox.yview)
        self.canid_listbox.configure(yscrollcommand=canid_vsb.set)
        canid_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Clear IDs button
        ttk.Button(left_frame, text="🗑 Clear IDs", command=self._clear_canid_list,
                  style="Accent.TButton").pack(pady=(8, 0))
        
        # === Right Panel: Data Visualization ===
        right_frame = ttk.Frame(paned, style="Medium.TFrame", padding=8)
        paned.add(right_frame, weight=3)
        
        # Selected ID display
        self.selected_id_var = tk.StringVar(value="Select a CAN ID from the list")
        ttk.Label(right_frame, textvariable=self.selected_id_var, 
                 style="Title.TLabel").pack(anchor=tk.W)
        
        # Use vertical paned window so user can resize bit/grid vs graphs
        vertical_paned = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        vertical_paned.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # === Bit-Level Visualization ===
        bit_frame = ttk.LabelFrame(vertical_paned, text="Bit-Level View (8 bytes × 8 bits)", padding=10)
        vertical_paned.add(bit_frame, weight=1)
        
        # Create 8x8 grid of bit indicators
        self.bit_canvas = tk.Canvas(bit_frame, 
                                    width=500, height=120,
                                    bg=COLORS["bg_dark"], 
                                    highlightthickness=0)
        self.bit_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Draw initial bit grid
        self._draw_bit_grid()
        
        # === Byte-Level Line Graphs ===
        graph_frame = ttk.LabelFrame(vertical_paned, text="Byte Values Over Time", padding=10)
        vertical_paned.add(graph_frame, weight=3)
        
        # Graph controls
        controls_frame = ttk.Frame(graph_frame, style="Medium.TFrame")
        controls_frame.pack(fill=tk.X, pady=(0, 8))
        
        # Start/Stop button
        self.graph_start_stop_btn = ttk.Button(controls_frame, text="⏸ Pause",
                                               command=self._toggle_graph,
                                               style="Small.TButton", width=8)
        self.graph_start_stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Samples control
        ttk.Label(controls_frame, text="Samples:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        self.samples_var = tk.StringVar(value="100")
        samples_combo = ttk.Combobox(controls_frame, textvariable=self.samples_var,
                                     values=["50", "100", "200", "500", "1000"],
                                     state="readonly", width=6)
        samples_combo.pack(side=tk.LEFT, padx=(0, 10))
        samples_combo.bind('<<ComboboxSelected>>', self._on_samples_change)
        
        # Zoom control
        ttk.Label(controls_frame, text="Zoom:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        self.zoom_var = tk.StringVar(value="100%")
        zoom_combo = ttk.Combobox(controls_frame, textvariable=self.zoom_var,
                                  values=["50%", "75%", "100%", "150%", "200%"],
                                  state="readonly", width=6)
        zoom_combo.pack(side=tk.LEFT, padx=(0, 10))
        zoom_combo.bind('<<ComboboxSelected>>', self._on_zoom_change)

        # Graph update rate
        ttk.Label(controls_frame, text="Update (ms):", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        self.rate_var = tk.StringVar(value=str(self._graph_update_rate_ms))
        rate_combo = ttk.Combobox(controls_frame, textvariable=self.rate_var,
                                  values=["50", "75", "100", "150", "200", "300", "400", "500"],
                                  state="readonly", width=6)
        rate_combo.pack(side=tk.LEFT, padx=(0, 10))
        rate_combo.bind('<<ComboboxSelected>>', self._on_graph_rate_change)
        
        # Clear graph button
        ttk.Button(controls_frame, text="🗑 Clear Graph", command=self._clear_byte_history,
                  style="Small.TButton").pack(side=tk.LEFT, padx=(10, 0))
        
        # Legend
        legend_frame = ttk.Frame(controls_frame, style="Medium.TFrame")
        legend_frame.pack(side=tk.RIGHT)
        
        self._byte_colors = ["#e74c3c", "#e67e22", "#f39c12", "#2ecc71", 
                            "#1abc9c", "#3498db", "#9b59b6", "#95a5a6"]
        self._byte_buttons: List[tk.Button] = []

        for i, color in enumerate(self._byte_colors):
            btn = tk.Button(legend_frame,
                           text=f"B{i}",
                           bg=color,
                           fg="white",
                           font=("Consolas", 8, "bold"),
                           width=3,
                           relief=tk.SUNKEN,
                           bd=2,
                           command=lambda idx=i: self._toggle_byte_active(idx))
            btn.pack(side=tk.LEFT, padx=1)
            self._byte_buttons.append(btn)
        self._update_byte_button_states()
        
        # Graph canvas
        self.byte_canvas = tk.Canvas(graph_frame,
                                     bg=COLORS["bg_dark"],
                                     highlightthickness=0)
        self.byte_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind resize event
        self.byte_canvas.bind('<Configure>', self._on_byte_canvas_resize)
        
    def _toggle_graph(self):
        """Toggle graph running state."""
        self._graph_running = not self._graph_running
        self._update_graph_button_state()
        if self._graph_running:
            self._maybe_draw_graph(force=True)
    
    def _toggle_byte_active(self, byte_idx: int):
        """Toggle whether a byte's data is plotted."""
        self._byte_active[byte_idx] = not self._byte_active[byte_idx]
        self._update_byte_button_state(byte_idx)
        self._maybe_draw_graph(force=True)

    def _update_byte_button_states(self):
        """Refresh the visual state for all byte selector buttons."""
        for idx in range(len(self._byte_buttons)):
            self._update_byte_button_state(idx)

    def _update_byte_button_state(self, byte_idx: int):
        """Update a single byte button's relief based on its state."""
        btn = self._byte_buttons[byte_idx]
        if self._byte_active[byte_idx]:
            btn.configure(relief=tk.SUNKEN)
        else:
            btn.configure(relief=tk.RAISED)

    def _on_graph_rate_change(self, event):
        """Handle graph update rate changes from the UI."""
        try:
            rate = max(10, int(self.rate_var.get()))
        except ValueError:
            rate = DEFAULT_GRAPH_UPDATE_RATE_MS
        self._graph_update_rate_ms = rate
        self._maybe_draw_graph(force=True)

    def _maybe_draw_graph(self, force: bool = False):
        """Throttle graph redraws according to the configured rate."""
        if not self._graph_running and not force:
            return
        now = time.time()
        if force or (now - self._last_graph_draw) * 1000.0 >= self._graph_update_rate_ms:
            self._draw_line_graph()
            self._last_graph_draw = now

    def _format_time_label(self, timestamp: float) -> str:
        """Format a timestamp label for the time axis."""
        return f"{timestamp:.2f}s"

    def _update_graph_button_state(self):
        """Update the start/stop button text."""
        if self._graph_running:
            self.graph_start_stop_btn.configure(text="⏸ Pause")
        else:
            self.graph_start_stop_btn.configure(text="▶ Resume")
    
    def _on_samples_change(self, event):
        """Handle samples selection change."""
        try:
            self._graph_samples = int(self.samples_var.get())
        except ValueError:
            self._graph_samples = 100
        self._maybe_draw_graph(force=True)
    
    def _on_zoom_change(self, event):
        """Handle zoom selection change."""
        zoom_str = self.zoom_var.get().replace('%', '')
        try:
            self._graph_zoom = int(zoom_str) / 100.0
        except ValueError:
            self._graph_zoom = 1.0
        self._maybe_draw_graph(force=True)
    
    def _clear_byte_history(self):
        """Clear byte history for graphs."""
        for hist in self._byte_history:
            hist.clear()
        self._maybe_draw_graph(force=True)
        
    def _draw_bit_grid(self, data: bytes = None):
        """Draw the bit-level visualization grid."""
        self.bit_canvas.delete("all")
        
        if data is None:
            data = bytes(8)
        
        # Pad data to 8 bytes
        data = bytes(data) + bytes(8 - len(data))
        
        box_size = 22
        gap = 3
        start_x = 60
        start_y = 10
        
        # Draw byte labels
        for byte_idx in range(8):
            y = start_y + byte_idx * (box_size + gap)
            self.bit_canvas.create_text(25, y + box_size//2,
                                       text=f"B{byte_idx}:",
                                       fill=COLORS["fg_secondary"],
                                       font=("Consolas", 9))
            
            # Draw hex value
            byte_val = data[byte_idx] if byte_idx < len(data) else 0
            self.bit_canvas.create_text(start_x + 8 * (box_size + gap) + 30, 
                                       y + box_size//2,
                                       text=f"0x{byte_val:02X}",
                                       fill=COLORS["fg_primary"],
                                       font=("Consolas", 10))
        
        # Draw bit labels at top
        for bit_idx in range(8):
            x = start_x + bit_idx * (box_size + gap) + box_size//2
            self.bit_canvas.create_text(x, start_y - 5,
                                       text=f"{7-bit_idx}",
                                       fill=COLORS["fg_secondary"],
                                       font=("Consolas", 8))
        
        # Draw bit boxes
        for byte_idx in range(8):
            byte_val = data[byte_idx] if byte_idx < len(data) else 0
            y = start_y + byte_idx * (box_size + gap)
            
            for bit_idx in range(8):
                x = start_x + bit_idx * (box_size + gap)
                bit_val = (byte_val >> (7 - bit_idx)) & 1
                
                # Color based on bit value
                if bit_val:
                    fill_color = COLORS["success"]  # Green for 1
                    text_color = COLORS["bg_dark"]
                else:
                    fill_color = COLORS["bg_light"]  # Dark for 0
                    text_color = COLORS["fg_secondary"]
                
                # Draw box
                self.bit_canvas.create_rectangle(x, y, x + box_size, y + box_size,
                                                fill=fill_color, outline=COLORS["bg_medium"])
                
                # Draw bit value
                self.bit_canvas.create_text(x + box_size//2, y + box_size//2,
                                           text=str(bit_val),
                                           fill=text_color,
                                           font=("Consolas", 10, "bold"))
    
    def _on_byte_canvas_resize(self, event):
        """Handle byte canvas resize."""
        self._maybe_draw_graph(force=True)
    
    def _draw_line_graph(self):
        """Draw byte-level line graphs."""
        self.byte_canvas.delete("all")
        
        # Get canvas dimensions
        width = self.byte_canvas.winfo_width()
        height = self.byte_canvas.winfo_height()
        
        if width < 50 or height < 50:
            return
        
        margin_left = 45
        margin_right = 15
        margin_top = 20
        margin_bottom = 25
        
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        # Apply zoom
        effective_samples = max(1, int(self._graph_samples / self._graph_zoom))
        
        # Draw background grid
        self._draw_graph_grid(margin_left, margin_top, graph_width, graph_height)
        
        # Draw axis labels
        self.byte_canvas.create_text(margin_left - 25, margin_top,
                                    text="255", fill=COLORS["fg_secondary"],
                                    font=("Consolas", 8), anchor=tk.E)
        self.byte_canvas.create_text(margin_left - 25, margin_top + graph_height // 2,
                                    text="128", fill=COLORS["fg_secondary"],
                                    font=("Consolas", 8), anchor=tk.E)
        self.byte_canvas.create_text(margin_left - 25, margin_top + graph_height,
                                    text="0", fill=COLORS["fg_secondary"],
                                    font=("Consolas", 8), anchor=tk.E)
        
        active_histories = []
        min_time = float("inf")
        max_time = 0.0
        
        for byte_idx in range(8):
            if not self._byte_active[byte_idx]:
                continue
            history = list(self._byte_history[byte_idx])
            if len(history) < 2:
                continue
            
            # Get last N samples based on effective samples
            history = history[-effective_samples:]
            if not history:
                continue
            
            active_histories.append((byte_idx, history))
            min_time = min(min_time, history[0][0])
            max_time = max(max_time, history[-1][0])
        
        if min_time == float("inf"):
            min_time = 0.0
            max_time = 1.0
        elif max_time <= min_time:
            max_time = min_time + 0.001
        
        time_span = max(0.001, max_time - min_time)
        
        # Draw each byte's line
        for byte_idx, history in active_histories:
            points = []
            for timestamp, value in history:
                x = margin_left + ((timestamp - min_time) / time_span) * graph_width
                y = margin_top + graph_height - (value / 255.0) * graph_height
                points.extend([x, y])
            
            if len(points) >= 4:
                self.byte_canvas.create_line(points, 
                                            fill=self._byte_colors[byte_idx],
                                            width=2,
                                            smooth=True)
        
        # Draw time axis labels
        label_y = margin_top + graph_height + 12
        self.byte_canvas.create_text(margin_left, label_y,
                                     text=self._format_time_label(min_time),
                                     fill=COLORS["fg_secondary"],
                                     font=("Consolas", 8), anchor=tk.NW)
        self.byte_canvas.create_text(margin_left + graph_width, label_y,
                                     text=self._format_time_label(max_time),
                                     fill=COLORS["fg_secondary"],
                                     font=("Consolas", 8), anchor=tk.NE)
    
    def _draw_graph_grid(self, x, y, width, height):
        """Draw background grid for the graph."""
        # Horizontal grid lines
        for i in range(5):
            ly = y + (i / 4) * height
            self.byte_canvas.create_line(x, ly, x + width, ly,
                                        fill=COLORS["bg_light"], dash=(2, 4))
        
        # Vertical grid lines
        for i in range(11):
            lx = x + (i / 10) * width
            self.byte_canvas.create_line(lx, y, lx, y + height,
                                        fill=COLORS["bg_light"], dash=(2, 4))
        
        # Border
        self.byte_canvas.create_rectangle(x, y, x + width, y + height,
                                         outline=COLORS["fg_secondary"])
    
    def _on_canid_select(self, event):
        """Handle CAN ID selection from list."""
        selection = self.canid_listbox.curselection()
        if not selection:
            return
        
        # Parse CAN ID from listbox item
        item_text = self.canid_listbox.get(selection[0])
        # Format: "0x123  (456 frames)"
        can_id_str = item_text.split()[0]
        
        try:
            can_id = int(can_id_str, 16)
            self._selected_can_id = can_id
            self.selected_id_var.set(f"Tracking CAN ID: {can_id_str}")
            
            # Clear history when selecting new ID
            self._clear_byte_history()
            
            # Update visualizations with last known data
            if can_id in self._can_id_data:
                frame = self._can_id_data[can_id]
                self._draw_bit_grid(frame.data)
                self._maybe_draw_graph(force=True)
        except ValueError:
            pass
    
    def _clear_canid_list(self):
        """Clear the CAN ID list."""
        self.canid_listbox.delete(0, tk.END)
        self._can_id_data.clear()
        self._can_id_counts.clear()
        self._selected_can_id = None
        self.selected_id_var.set("Select a CAN ID from the list")
        self._draw_bit_grid()
        self._clear_byte_history()
        
    # ========================================================================
    # Parsed Data Viewer Tab
    # ========================================================================

    def _create_parsed_viewer_tab(self, parent):
        """Create the Parsed Data Viewer tab."""
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # === Left Panel: DBC + SPN Tree ===
        left_frame = ttk.Frame(paned, style="Medium.TFrame", padding=8)
        paned.add(left_frame, weight=1)

        # --- DBC File Loading ---
        dbc_frame = ttk.LabelFrame(left_frame, text="📄 DBC File", padding=8)
        dbc_frame.pack(fill=tk.X, pady=(0, 5))

        file_row = ttk.Frame(dbc_frame, style="Medium.TFrame")
        file_row.pack(fill=tk.X, pady=(0, 4))

        self._pv_dbc_path_var = tk.StringVar(value="No file loaded")
        pv_dbc_entry = ttk.Entry(file_row, textvariable=self._pv_dbc_path_var,
                                  width=40, state="readonly")
        pv_dbc_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(file_row, text="📂 Browse", command=self._pv_load_dbc,
                   style="Accent.TButton", width=10).pack(side=tk.LEFT)

        # DBC metadata
        self._pv_dbc_info_var = tk.StringVar(value="")
        ttk.Label(dbc_frame, textvariable=self._pv_dbc_info_var,
                  style="Status.TLabel", wraplength=350).pack(fill=tk.X)

        # --- SPN Tree (RX-data-driven) ---
        tree_lf = ttk.LabelFrame(left_frame, text="📡 Received PGNs / SPNs (click to graph)",
                                  padding=4)
        tree_lf.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self._pv_sel_var = tk.StringVar(value="Waiting for CAN data…")
        ttk.Label(tree_lf, textvariable=self._pv_sel_var,
                  style="Status.TLabel").pack(fill=tk.X, pady=(0, 4))

        # Search entry
        search_row = ttk.Frame(tree_lf, style="Medium.TFrame")
        search_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_row, text="🔍", style="Medium.TLabel").pack(side=tk.LEFT)
        self._pv_search_var = tk.StringVar()
        pv_search = ttk.Entry(search_row, textvariable=self._pv_search_var, width=25)
        pv_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        self._pv_search_var.trace_add("write", lambda *_: self._pv_populate_tree())

        tree_frame = ttk.Frame(tree_lf)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self._pv_tree = ttk.Treeview(tree_frame, columns=("value", "unit"),
                                      show="tree headings", selectmode="none")
        self._pv_tree.heading("#0", text="PGN / SPN", anchor=tk.W)
        self._pv_tree.heading("value", text="Value", anchor=tk.E)
        self._pv_tree.heading("unit", text="Unit", anchor=tk.W)
        self._pv_tree.column("#0", width=200, stretch=True)
        self._pv_tree.column("value", width=80, anchor=tk.E)
        self._pv_tree.column("unit", width=50, anchor=tk.W)

        pv_vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                command=self._pv_tree.yview)
        self._pv_tree.configure(yscrollcommand=pv_vsb.set)
        self._pv_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pv_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._pv_tree.tag_configure("pgn", foreground=COLORS["accent"])
        self._pv_tree.tag_configure("pgn_unknown",
                                     foreground=COLORS["warning"])
        self._pv_tree.tag_configure("spn", foreground=COLORS["fg_primary"])
        self._pv_tree.tag_configure("spn_graphed",
                                     foreground=COLORS["success"],
                                     font=("Segoe UI", 10, "bold"))
        self._pv_tree.bind("<ButtonRelease-1>", self._pv_on_tree_click)

        # === Right Panel: Graphs ===
        right_frame = ttk.Frame(paned, style="Dark.TFrame", padding=4)
        paned.add(right_frame, weight=3)

        self._pv_graph_container = ttk.Frame(right_frame, style="Dark.TFrame")
        self._pv_graph_container.pack(fill=tk.BOTH, expand=True)

        self._pv_placeholder = ttk.Label(
            self._pv_graph_container,
            text="📈 Select up to 5 SPNs from the tree to view live graphs",
            style="Status.TLabel", anchor=tk.CENTER)
        self._pv_placeholder.pack(fill=tk.BOTH, expand=True, pady=50)

    # --- Parsed Viewer: DBC Loading ---

    def _pv_load_dbc(self):
        """Browse and load a DBC file for the parsed viewer."""
        last_pv = self.settings.get("last_pv_dbc_path", "")
        if last_pv and os.path.isdir(os.path.dirname(last_pv)):
            initial_dir = os.path.dirname(last_pv)
        else:
            initial_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "DBCs")
            if not os.path.isdir(initial_dir):
                initial_dir = os.path.expanduser("~")

        filepath = filedialog.askopenfilename(
            title="Select DBC File for Parsed Viewer",
            filetypes=[("DBC Files", "*.dbc"), ("All Files", "*.*")],
            initialdir=initial_dir)
        if not filepath:
            return
        self._pv_load_dbc_file(filepath)

    def _pv_load_dbc_file(self, filepath: str):
        """Load and apply a DBC file for the parsed viewer."""
        try:
            if not DBCHandler.is_available():
                messagebox.showerror("Missing Library",
                    "cantools library required.\nInstall: pip install cantools")
                return

            config = self._pv_dbc.load(filepath)
            self._pv_dbc_path_var.set(filepath)
            self.settings["last_pv_dbc_path"] = filepath
            self.settings.save()

            # Build fast lookup maps
            self._pv_msg_by_id.clear()
            self._pv_msg_by_pgn.clear()
            for msg in self._pv_dbc.db.messages:
                self._pv_msg_by_id[msg.frame_id] = msg
                is_ext = getattr(msg, 'is_extended_frame', False)
                if is_ext:
                    pgn = extract_j1939_pgn(msg.frame_id)
                    self._pv_msg_by_pgn[pgn] = msg

            # Show metadata
            self._pv_dbc_info_var.set(
                f"{config.num_messages} PGNs, {config.num_signals} SPNs | "
                f"Frames: {config.frame_types_str} | "
                f"Nodes: {config.nodes_summary}")

            # Clear decoded data & graphs (keeping raw RX PGN tracking)
            self._pv_spn_history.clear()
            self._pv_latest_values.clear()
            for slot in list(self._pv_graph_slots):
                self._pv_remove_graph(slot["spn_key"])

            # Re-evaluate already-received PGNs against new DBC
            for pgn_num, info in self._pv_rx_pgns.items():
                msg = self._pv_msg_by_pgn.get(pgn_num)
                if msg is None:
                    # Also try exact frame_id match for standard frames
                    msg = self._pv_msg_by_id.get(pgn_num)
                if msg:
                    info["name"] = msg.name
                    info["msg"] = msg
                    info["is_known"] = True
                    # Decode last received data
                    try:
                        decoded = msg.decode(
                            info["last_data"], scaling=True,
                            decode_choices=False)
                        for sig_name, value in decoded.items():
                            spn_key = f"{msg.name}.{sig_name}"
                            fval = float(value)
                            self._pv_latest_values[spn_key] = (
                                info["last_ts"], fval)
                    except Exception:
                        pass
                else:
                    info["name"] = "Unknown"
                    info["msg"] = None
                    info["is_known"] = False

            # Rebuild tree from received data
            self._pv_populate_tree()

        except Exception as e:
            messagebox.showerror("DBC Load Error",
                f"Failed to load DBC file:\n{e}")

    # --- Parsed Viewer: SPN Tree ---

    def _pv_populate_tree(self):
        """Populate the SPN tree from received PGNs (RX-data-driven)."""
        self._pv_tree.delete(*self._pv_tree.get_children())
        self._pv_tree_items.clear()
        self._pv_pgn_tree_items.clear()

        if not self._pv_rx_pgns:
            self._pv_sel_var.set("Waiting for CAN data…")
            return

        filt = self._pv_search_var.get().strip().lower()

        for pgn_num in sorted(self._pv_rx_pgns.keys()):
            pgn_info = self._pv_rx_pgns[pgn_num]
            pgn_name = pgn_info["name"]
            is_known = pgn_info["is_known"]
            pgn_hex = f"0x{pgn_num:04X}"
            count = pgn_info["count"]

            if is_known:
                msg = pgn_info["msg"]
                # Filter check
                pgn_matches = (not filt or filt in pgn_name.lower()
                               or filt in pgn_hex.lower()
                               or filt in str(pgn_num))
                matching_sigs = [
                    s for s in msg.signals
                    if (pgn_matches or filt in s.name.lower())
                ] if filt else list(msg.signals)

                if not matching_sigs:
                    continue

                # Known PGN: parent with SPN children
                pgn_id = self._pv_tree.insert(
                    "", tk.END,
                    text=f"📦 {pgn_name} ({pgn_hex})",
                    values=(f"{count} frames", ""),
                    tags=("pgn",), open=True)
                self._pv_pgn_tree_items[pgn_num] = pgn_id

                for sig in sorted(matching_sigs, key=lambda s: s.name):
                    spn_key = f"{msg.name}.{sig.name}"
                    is_graphed = spn_key in self._pv_selected_graph_spns
                    checkbox = "☑" if is_graphed else "☐"
                    tag = "spn_graphed" if is_graphed else "spn"

                    val_str = "--"
                    if spn_key in self._pv_latest_values:
                        _, val = self._pv_latest_values[spn_key]
                        val_str = f"{val:.4g}"

                    item_id = self._pv_tree.insert(
                        pgn_id, tk.END,
                        text=f"  {checkbox} {sig.name}",
                        values=(val_str, getattr(sig, 'unit', '') or ""),
                        tags=(tag,))
                    self._pv_tree_items[spn_key] = item_id
            else:
                # Unknown PGN: leaf node with raw hex
                if filt and (filt not in pgn_hex.lower()
                             and filt not in str(pgn_num)
                             and filt not in "unknown"):
                    continue

                raw_hex = (pgn_info["last_data"].hex(' ').upper()
                           if pgn_info.get("last_data") else "--")
                pgn_id = self._pv_tree.insert(
                    "", tk.END,
                    text=f"⚠ PGN {pgn_hex} ({pgn_num}) — Unknown",
                    values=(raw_hex, f"{count} frm"),
                    tags=("pgn_unknown",))
                self._pv_pgn_tree_items[pgn_num] = pgn_id

        n = len(self._pv_selected_graph_spns)
        rx_count = len(self._pv_rx_pgns)
        known = sum(1 for p in self._pv_rx_pgns.values() if p["is_known"])
        self._pv_sel_var.set(
            f"Graphing: {n}/5 | RX: {rx_count} PGNs ({known} known)")

    def _pv_on_tree_click(self, event):
        """Handle click on the SPN tree — toggle graph assignment."""
        item_id = self._pv_tree.identify_row(event.y)
        if not item_id:
            return

        # Only handle SPN items (children, not PGN parents)
        parent = self._pv_tree.parent(item_id)
        if not parent:
            return  # Clicked a PGN header

        # Find the SPN key
        spn_key = None
        for key, tid in self._pv_tree_items.items():
            if tid == item_id:
                spn_key = key
                break
        if not spn_key:
            return

        if spn_key in self._pv_selected_graph_spns:
            # Deselect — remove graph
            self._pv_remove_graph(spn_key)
            txt = self._pv_tree.item(item_id, "text")
            self._pv_tree.item(item_id,
                               text=txt.replace("☑", "☐", 1),
                               tags=("spn",))
        else:
            if len(self._pv_selected_graph_spns) >= 5:
                messagebox.showwarning("Graph Limit",
                    "Maximum 5 graphs. Deselect one first.")
                return
            self._pv_add_graph(spn_key)
            txt = self._pv_tree.item(item_id, "text")
            self._pv_tree.item(item_id,
                               text=txt.replace("☐", "☑", 1),
                               tags=("spn_graphed",))

        n = len(self._pv_selected_graph_spns)
        rx_count = len(self._pv_rx_pgns)
        known = sum(1 for p in self._pv_rx_pgns.values() if p["is_known"])
        self._pv_sel_var.set(
            f"Graphing: {n}/5 | RX: {rx_count} PGNs ({known} known)")

    # --- Parsed Viewer: Graph Management ---

    def _pv_add_graph(self, spn_key: str):
        """Create a new live graph slot for the given SPN."""
        if len(self._pv_graph_slots) >= 5:
            return

        # Hide placeholder
        self._pv_placeholder.pack_forget()

        # Resolve SPN info
        pgn_name, spn_name = spn_key.split(".", 1)
        spn_info = None
        for pgn in self._pv_dbc.pgns:
            if pgn.name == pgn_name:
                for s in pgn.signals:
                    if s.name == spn_name:
                        spn_info = s
                        break
                break

        unit = spn_info.unit if spn_info else ""
        color_idx = len(self._pv_graph_slots)
        color = self._pv_graph_colors[color_idx % len(self._pv_graph_colors)]

        # --- Build graph frame ---
        gf = ttk.LabelFrame(self._pv_graph_container,
                             text=f"📈 {spn_name}  ({pgn_name})",
                             padding=4)
        gf.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        ctrl = ttk.Frame(gf, style="Medium.TFrame")
        ctrl.pack(fill=tk.X, pady=(0, 4))

        # Current value
        value_var = tk.StringVar(value="--")
        val_lbl = ttk.Label(ctrl, textvariable=value_var,
                            font=("Consolas", 11, "bold"),
                            foreground=color,
                            background=COLORS["bg_medium"])
        val_lbl.pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(ctrl, text=unit, style="Status.TLabel").pack(
            side=tk.LEFT, padx=(0, 10))

        # Y-scale mode
        ttk.Label(ctrl, text="Y:", style="Medium.TLabel").pack(
            side=tk.LEFT, padx=(0, 3))
        y_mode_var = tk.StringVar(value="Auto")
        y_mode_combo = ttk.Combobox(ctrl, textvariable=y_mode_var,
                                     values=["Auto", "Manual"],
                                     state="readonly", width=7)
        y_mode_combo.pack(side=tk.LEFT, padx=(0, 5))

        # Y min/max entries (initially hidden)
        y_min_var = tk.StringVar(
            value=str(spn_info.minimum) if spn_info else "0")
        y_max_var = tk.StringVar(
            value=str(spn_info.maximum) if spn_info else "100")

        y_min_lbl = ttk.Label(ctrl, text="Min:", style="Medium.TLabel")
        y_min_entry = ttk.Entry(ctrl, textvariable=y_min_var, width=8)
        y_max_lbl = ttk.Label(ctrl, text="Max:", style="Medium.TLabel")
        y_max_entry = ttk.Entry(ctrl, textvariable=y_max_var, width=8)

        def _on_y_mode(e, ml=y_min_lbl, me=y_min_entry,
                       xl=y_max_lbl, xe=y_max_entry, mv=y_mode_var):
            if mv.get() == "Manual":
                ml.pack(side=tk.LEFT, padx=(0, 2))
                me.pack(side=tk.LEFT, padx=(0, 5))
                xl.pack(side=tk.LEFT, padx=(0, 2))
                xe.pack(side=tk.LEFT, padx=(0, 5))
            else:
                ml.pack_forget(); me.pack_forget()
                xl.pack_forget(); xe.pack_forget()
        y_mode_combo.bind("<<ComboboxSelected>>", _on_y_mode)

        # Time window
        ttk.Label(ctrl, text="Window:", style="Medium.TLabel").pack(
            side=tk.LEFT, padx=(10, 3))
        tw_var = tk.StringVar(value="30s")
        tw_combo = ttk.Combobox(ctrl, textvariable=tw_var,
                                 values=["5s", "10s", "30s", "60s", "All"],
                                 state="readonly", width=5)
        tw_combo.pack(side=tk.LEFT, padx=(0, 10))

        # Remove button (✕)
        def _remove(k=spn_key):
            self._pv_remove_graph(k)
            if k in self._pv_tree_items:
                tid = self._pv_tree_items[k]
                txt = self._pv_tree.item(tid, "text")
                self._pv_tree.item(tid,
                                    text=txt.replace("☑", "☐", 1),
                                    tags=("spn",))
            n2 = len(self._pv_selected_graph_spns)
            self._pv_sel_var.set(f"Graphing: {n2}/5 SPNs")

        ttk.Button(ctrl, text="✕", command=_remove,
                   style="Error.TButton", width=3).pack(side=tk.RIGHT)

        # Pause / Resume
        running_var = tk.BooleanVar(value=True)
        pause_btn = ttk.Button(ctrl, text="⏸", width=3)
        def _toggle(rv=running_var, btn=pause_btn):
            rv.set(not rv.get())
            btn.configure(text="⏸" if rv.get() else "▶")
        pause_btn.configure(command=_toggle)
        pause_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # Canvas
        canvas = tk.Canvas(gf, bg=COLORS["bg_dark"],
                           highlightthickness=0, height=100)
        canvas.pack(fill=tk.BOTH, expand=True)

        slot = {
            "spn_key": spn_key,
            "frame": gf,
            "canvas": canvas,
            "value_var": value_var,
            "y_mode_var": y_mode_var,
            "y_min_var": y_min_var,
            "y_max_var": y_max_var,
            "tw_var": tw_var,
            "running_var": running_var,
            "spn_info": spn_info,
            "color": color,
        }
        self._pv_graph_slots.append(slot)
        self._pv_selected_graph_spns.append(spn_key)

    def _pv_remove_graph(self, spn_key: str):
        """Remove a graph slot."""
        for slot in self._pv_graph_slots:
            if slot["spn_key"] == spn_key:
                slot["frame"].destroy()
                self._pv_graph_slots.remove(slot)
                break
        if spn_key in self._pv_selected_graph_spns:
            self._pv_selected_graph_spns.remove(spn_key)

        # Show placeholder if no graphs remain
        if not self._pv_graph_slots:
            self._pv_placeholder.pack(fill=tk.BOTH, expand=True, pady=50)

    # --- Parsed Viewer: Frame Decoding ---

    def _pv_process_frames(self, frames: List[CANFrame]):
        """Decode incoming CAN frames — RX-data-driven PGN discovery."""
        tree_dirty = False

        for frame in frames:
            can_id = frame.can_id

            # Determine PGN number
            if frame.is_extended:
                pgn_num = extract_j1939_pgn(can_id)
            else:
                pgn_num = can_id

            # --- Register new PGN on first sight ---
            if pgn_num not in self._pv_rx_pgns:
                # Try to find DBC definition
                msg = self._pv_msg_by_id.get(can_id)
                if msg is None and frame.is_extended:
                    msg = self._pv_msg_by_pgn.get(pgn_num)

                self._pv_rx_pgns[pgn_num] = {
                    "name": msg.name if msg else "Unknown",
                    "msg": msg,
                    "is_known": msg is not None,
                    "last_data": frame.data,
                    "last_ts": frame.timestamp,
                    "count": 1,
                }
                tree_dirty = True
            else:
                self._pv_rx_pgns[pgn_num]["last_data"] = frame.data
                self._pv_rx_pgns[pgn_num]["last_ts"] = frame.timestamp
                self._pv_rx_pgns[pgn_num]["count"] += 1

            # --- Decode known messages ---
            pgn_info = self._pv_rx_pgns[pgn_num]
            if pgn_info["is_known"]:
                msg = pgn_info["msg"]
                try:
                    decoded = msg.decode(
                        frame.data, scaling=True, decode_choices=False)
                    for sig_name, value in decoded.items():
                        spn_key = f"{msg.name}.{sig_name}"
                        fval = float(value)
                        self._pv_latest_values[spn_key] = (
                            frame.timestamp, fval)
                        if spn_key not in self._pv_spn_history:
                            self._pv_spn_history[spn_key] = deque(
                                maxlen=5000)
                        self._pv_spn_history[spn_key].append(
                            (frame.timestamp, fval))
                except Exception:
                    pass

        # Rebuild tree only when new PGNs discovered
        if tree_dirty:
            self._pv_populate_tree()

    # --- Parsed Viewer: Tree Value Updates ---

    def _pv_update_tree_values(self):
        """Update the value column in the SPN tree with latest data."""
        # Update decoded SPN values
        for spn_key, (_, val) in self._pv_latest_values.items():
            tid = self._pv_tree_items.get(spn_key)
            if tid:
                try:
                    self._pv_tree.set(tid, "value", f"{val:.4g}")
                except tk.TclError:
                    pass

        # Update PGN frame counts and raw data for unknown PGNs
        for pgn_num, info in self._pv_rx_pgns.items():
            tid = self._pv_pgn_tree_items.get(pgn_num)
            if not tid:
                continue
            try:
                if info["is_known"]:
                    self._pv_tree.set(tid, "value",
                                      f"{info['count']} frames")
                else:
                    raw_hex = (info["last_data"].hex(' ').upper()
                               if info.get("last_data") else "--")
                    self._pv_tree.set(tid, "value", raw_hex)
                    self._pv_tree.set(tid, "unit",
                                      f"{info['count']} frm")
            except tk.TclError:
                pass

    # --- Parsed Viewer: Graph Drawing ---

    def _pv_draw_all_graphs(self):
        """Redraw all active parsed-viewer graphs (called periodically)."""
        now = time.time()
        if now - self._pv_last_draw < 0.200:  # 5 Hz max
            return
        self._pv_last_draw = now

        for slot in self._pv_graph_slots:
            if slot["running_var"].get():
                self._pv_draw_graph(slot)

        # Also refresh tree values at the same rate
        self._pv_update_tree_values()

    def _pv_draw_graph(self, slot: Dict):
        """Draw a single parsed-data graph."""
        canvas = slot["canvas"]
        canvas.delete("all")

        spn_key = slot["spn_key"]
        history = list(self._pv_spn_history.get(spn_key, []))

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 60 or height < 40:
            return

        ml, mr, mt, mb = 65, 15, 10, 22
        gw = width - ml - mr
        gh = height - mt - mb
        if gw <= 0 or gh <= 0:
            return

        color = slot["color"]

        # --- Apply time window ---
        tw_str = slot["tw_var"].get()
        if tw_str != "All" and history:
            try:
                window_s = float(tw_str.replace("s", ""))
            except ValueError:
                window_s = 30.0
            cutoff = history[-1][0] - window_s
            history = [(t, v) for t, v in history if t >= cutoff]

        # --- Y range ---
        y_mode = slot["y_mode_var"].get()
        if y_mode == "Manual":
            try:
                y_min = float(slot["y_min_var"].get())
                y_max = float(slot["y_max_var"].get())
            except ValueError:
                y_min, y_max = 0.0, 100.0
        else:
            # Auto
            if history:
                vals = [v for _, v in history]
                y_min = min(vals)
                y_max = max(vals)
                pad = (y_max - y_min) * 0.1 or 1.0
                y_min -= pad
                y_max += pad
            else:
                si = slot["spn_info"]
                y_min = si.minimum if si else 0.0
                y_max = si.maximum if si else 100.0

        if y_max <= y_min:
            y_max = y_min + 1.0
        y_span = y_max - y_min

        # --- Grid ---
        # Horizontal lines (5)
        for i in range(5):
            ly = mt + (i / 4) * gh
            canvas.create_line(ml, ly, ml + gw, ly,
                               fill=COLORS["bg_light"], dash=(2, 4))
            # Y labels
            y_val = y_max - (i / 4) * y_span
            canvas.create_text(ml - 5, ly, text=f"{y_val:.3g}",
                               fill=COLORS["fg_secondary"],
                               font=("Consolas", 8), anchor=tk.E)
        # Vertical lines (10)
        for i in range(11):
            lx = ml + (i / 10) * gw
            canvas.create_line(lx, mt, lx, mt + gh,
                               fill=COLORS["bg_light"], dash=(2, 4))
        # Border
        canvas.create_rectangle(ml, mt, ml + gw, mt + gh,
                                outline=COLORS["fg_secondary"])

        # --- Data line ---
        if len(history) >= 2:
            t_min = history[0][0]
            t_max = history[-1][0]
            if t_max <= t_min:
                t_max = t_min + 0.001
            t_span = t_max - t_min

            points = []
            for t, v in history:
                x = ml + ((t - t_min) / t_span) * gw
                y = mt + gh - ((v - y_min) / y_span) * gh
                y = max(mt, min(mt + gh, y))
                points.extend([x, y])

            if len(points) >= 4:
                canvas.create_line(points, fill=color, width=2, smooth=True)

            # Time labels
            canvas.create_text(
                ml, mt + gh + 13,
                text=f"{t_min:.1f}s", fill=COLORS["fg_secondary"],
                font=("Consolas", 8), anchor=tk.NW)
            canvas.create_text(
                ml + gw, mt + gh + 13,
                text=f"{t_max:.1f}s", fill=COLORS["fg_secondary"],
                font=("Consolas", 8), anchor=tk.NE)
        else:
            canvas.create_text(
                ml + gw // 2, mt + gh // 2,
                text="Waiting for data…",
                fill=COLORS["fg_secondary"], font=("Segoe UI", 10))

        # Update current value label
        if history:
            slot["value_var"].set(f"{history[-1][1]:.4g}")

    # ========================================================================
    # CAN Simulator Tab
    # ========================================================================

    def _create_simulator_tab(self, parent):
        """Create the CAN Simulator tab with DBC loading and SPN selection."""
        # Scrollable container for the whole tab
        sim_canvas = tk.Canvas(parent, bg=COLORS["bg_dark"], highlightthickness=0)
        sim_scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=sim_canvas.yview)
        sim_canvas.configure(yscrollcommand=sim_scrollbar.set)
        sim_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        sim_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sim_inner = ttk.Frame(sim_canvas, style="Dark.TFrame")
        sim_canvas.create_window((0, 0), window=sim_inner, anchor=tk.NW)

        def _on_sim_configure(event):
            sim_canvas.configure(scrollregion=sim_canvas.bbox("all"))
            # Ensure inner frame fills canvas width
            sim_canvas.itemconfig(sim_canvas.find_withtag("all")[0], width=sim_canvas.winfo_width())

        sim_inner.bind("<Configure>", _on_sim_configure)
        sim_canvas.bind("<Configure>",
                        lambda e: sim_canvas.itemconfig(
                            sim_canvas.find_withtag("all")[0], width=e.width))

        # === DBC File Loading Section ===
        dbc_frame = ttk.LabelFrame(sim_inner, text="📄 DBC File", padding=8)
        dbc_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        # File selection row
        file_row = ttk.Frame(dbc_frame, style="Medium.TFrame")
        file_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(file_row, text="File:", style="Medium.TLabel").pack(side=tk.LEFT, padx=(0, 5))

        self.dbc_path_var = tk.StringVar(value="No file loaded")
        dbc_path_entry = ttk.Entry(file_row, textvariable=self.dbc_path_var, width=70,
                                   state="readonly")
        dbc_path_entry.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)

        ttk.Button(file_row, text="📂 Load DBC", command=self._load_dbc_file,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(5, 0))

        # === DBC Configuration Display ===
        dbc_config_inner = ttk.Frame(dbc_frame, style="Medium.TFrame")
        dbc_config_inner.pack(fill=tk.X)

        # Config grid - populated when DBC is loaded
        self._dbc_config_labels: Dict[str, ttk.Label] = {}
        config_items = [
            ("file", "File:"),
            ("version", "Version:"),
            ("messages", "Messages:"),
            ("signals", "Signals:"),
            ("frame_type", "Frame Type:"),
            ("byte_order", "Byte Order:"),
            ("value_type", "Value Types:"),
            ("nodes", "Nodes:"),
        ]

        for i, (key, label_text) in enumerate(config_items):
            row = i // 2
            col = (i % 2) * 2

            lbl = ttk.Label(dbc_config_inner, text=label_text, style="Medium.TLabel",
                            font=("Segoe UI", 9, "bold"))
            lbl.grid(row=row, column=col, sticky=tk.W, padx=(0, 5), pady=2)

            val_lbl = ttk.Label(dbc_config_inner, text="—", style="Medium.TLabel")
            val_lbl.grid(row=row, column=col + 1, sticky=tk.W, padx=(0, 30), pady=2)
            self._dbc_config_labels[key] = val_lbl

        # Configure grid weights
        dbc_config_inner.columnconfigure(1, weight=1)
        dbc_config_inner.columnconfigure(3, weight=1)

        # === PGN / SPN Selection Section ===
        spn_frame = ttk.LabelFrame(sim_inner, text="📋 PGN / SPN Selection", padding=8)
        spn_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # Search and selection controls
        controls_row = ttk.Frame(spn_frame, style="Medium.TFrame")
        controls_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(controls_row, text="🔍 Search:", style="Medium.TLabel").pack(
            side=tk.LEFT, padx=(0, 5))

        self.spn_search_var = tk.StringVar()
        self.spn_search_var.trace_add("write", self._on_spn_search_changed)
        spn_search_entry = ttk.Entry(controls_row, textvariable=self.spn_search_var, width=30)
        spn_search_entry.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(controls_row, text="✕",
                   command=lambda: self.spn_search_var.set(""),
                   style="Small.TButton", width=3).pack(side=tk.LEFT, padx=(0, 15))

        # Select / Deselect buttons
        ttk.Button(controls_row, text="Select All Visible",
                   command=self._select_all_visible_spns,
                   style="Small.TButton").pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(controls_row, text="Deselect All",
                   command=self._deselect_all_spns,
                   style="Small.TButton").pack(side=tk.LEFT, padx=(0, 15))

        # Selection count label
        self.sim_selection_var = tk.StringVar(value="Selected: 0 SPNs from 0 PGNs")
        ttk.Label(controls_row, textvariable=self.sim_selection_var,
                  style="Status.TLabel").pack(side=tk.RIGHT, padx=5)

        # === SPN Treeview ===
        tree_container = ttk.Frame(spn_frame, style="Medium.TFrame")
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("pgn_id", "bits", "byte_order", "type",
                   "factor", "offset", "unit", "range")
        self.spn_tree = ttk.Treeview(tree_container, columns=columns,
                                     show="tree headings", selectmode="none",
                                     height=20)

        # Column headings
        self.spn_tree.heading("#0", text="PGN / SPN Name", anchor=tk.W)
        self.spn_tree.heading("pgn_id", text="PGN / Bit Position")
        self.spn_tree.heading("bits", text="Size")
        self.spn_tree.heading("byte_order", text="Byte Order")
        self.spn_tree.heading("type", text="Type")
        self.spn_tree.heading("factor", text="Factor")
        self.spn_tree.heading("offset", text="Offset")
        self.spn_tree.heading("unit", text="Unit")
        self.spn_tree.heading("range", text="Range")

        # Column widths
        self.spn_tree.column("#0", width=260, minwidth=180)
        self.spn_tree.column("pgn_id", width=160, anchor=tk.CENTER)
        self.spn_tree.column("bits", width=65, anchor=tk.CENTER)
        self.spn_tree.column("byte_order", width=95, anchor=tk.CENTER)
        self.spn_tree.column("type", width=75, anchor=tk.CENTER)
        self.spn_tree.column("factor", width=75, anchor=tk.CENTER)
        self.spn_tree.column("offset", width=60, anchor=tk.CENTER)
        self.spn_tree.column("unit", width=70, anchor=tk.CENTER)
        self.spn_tree.column("range", width=130, anchor=tk.CENTER)

        # Scrollbars
        tree_vsb = ttk.Scrollbar(tree_container, orient=tk.VERTICAL,
                                 command=self.spn_tree.yview)
        tree_hsb = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL,
                                 command=self.spn_tree.xview)
        self.spn_tree.configure(yscrollcommand=tree_vsb.set,
                                xscrollcommand=tree_hsb.set)

        self.spn_tree.grid(row=0, column=0, sticky="nsew")
        tree_vsb.grid(row=0, column=1, sticky="ns")
        tree_hsb.grid(row=1, column=0, sticky="ew")

        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        # Tags for styling PGN / SPN rows
        self.spn_tree.tag_configure("pgn",
                                    font=("Segoe UI", 10, "bold"),
                                    foreground=COLORS["accent"])
        self.spn_tree.tag_configure("spn",
                                    foreground=COLORS["fg_primary"])
        self.spn_tree.tag_configure("spn_selected",
                                    foreground=COLORS["success"],
                                    font=("Segoe UI", 10, "bold"))

        # Bind click for checkbox toggling
        self.spn_tree.bind("<ButtonRelease-1>", self._on_spn_tree_click)

        # === Signal Generation Section ===
        gen_outer = ttk.LabelFrame(sim_inner, text="🎯 Signal Generation", padding=8)
        gen_outer.pack(fill=tk.X, padx=5, pady=(0, 5))

        # Controls row: Start/Stop + status
        gen_controls = ttk.Frame(gen_outer, style="Medium.TFrame")
        gen_controls.pack(fill=tk.X, pady=(0, 8))

        self.sim_start_btn = ttk.Button(gen_controls, text="▶ Start Simulation",
                                         command=self._start_simulation,
                                         style="Success.TButton", width=16)
        self.sim_start_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.sim_stop_btn = ttk.Button(gen_controls, text="⏹ Stop Simulation",
                                        command=self._stop_simulation,
                                        style="Error.TButton",
                                        state=tk.DISABLED, width=16)
        self.sim_stop_btn.pack(side=tk.LEFT, padx=(0, 15))

        self.sim_gen_status_var = tk.StringVar(value="Stopped")
        ttk.Label(gen_controls, textvariable=self.sim_gen_status_var,
                  style="Status.TLabel").pack(side=tk.RIGHT, padx=5)

        # Table for signal generation parameters
        self._sim_gen_table = ttk.Frame(gen_outer, style="Medium.TFrame")
        self._sim_gen_table.pack(fill=tk.X)
        # Click on empty table space releases entry focus
        self._sim_gen_table.bind("<Button-1>",
                                lambda e: self._sim_gen_table.focus_set())

        # Header row
        gen_headers = [("#", 3), ("SPN Name", 22), ("PGN", 16), ("Type", 9),
                       ("Min / Value", 14), ("Max", 14), ("Step", 10),
                       ("Tics/s", 10), ("Unit", 8)]
        for col, (text, width) in enumerate(gen_headers):
            lbl = ttk.Label(self._sim_gen_table, text=text, style="Medium.TLabel",
                           font=("Segoe UI", 9, "bold"), width=width, anchor=tk.W)
            lbl.grid(row=0, column=col, sticky="w", padx=2, pady=2)

        sep = ttk.Separator(self._sim_gen_table, orient="horizontal")
        sep.grid(row=1, column=0, columnspan=len(gen_headers), sticky="ew", pady=2)

        # Empty state label
        self._sim_gen_empty_label = ttk.Label(
            self._sim_gen_table,
            text="Select SPNs above to configure signal generation (max 20)",
            style="Status.TLabel")
        self._sim_gen_empty_label.grid(row=2, column=0, columnspan=len(gen_headers), pady=20)

    # --- DBC Loading ---

    def _load_dbc_file(self):
        """Open file dialog and load a DBC file."""
        # Default to the DBCs folder next to this script
        # Start from last DBC's directory, fallback to DBCs folder
        last_dbc = self.settings.get("last_dbc_path", "")
        if last_dbc and os.path.isdir(os.path.dirname(last_dbc)):
            initial_dir = os.path.dirname(last_dbc)
        else:
            initial_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DBCs")
            if not os.path.isdir(initial_dir):
                initial_dir = os.path.expanduser("~")

        filepath = filedialog.askopenfilename(
            title="Select DBC File",
            filetypes=[("DBC Files", "*.dbc"), ("All Files", "*.*")],
            initialdir=initial_dir
        )

        if not filepath:
            return

        try:
            if not DBCHandler.is_available():
                messagebox.showerror(
                    "Missing Library",
                    "cantools library is required for DBC file support.\n\n"
                    "Install with:\n  pip install cantools"
                )
                return

            config = self._dbc_handler.load(filepath)
            self.dbc_path_var.set(filepath)
            self.settings["last_dbc_path"] = filepath
            self.settings.save()
            self._update_dbc_config_display(config)

            # Clear previous selection state
            self._sim_selected_spns.clear()

            # Populate the PGN/SPN tree
            self._populate_spn_tree()
            self._update_signal_gen_table()

        except Exception as e:
            messagebox.showerror("DBC Load Error",
                                 f"Failed to load DBC file:\n\n{e}")

    def _update_dbc_config_display(self, config: DBCConfig):
        """Update the DBC configuration display labels."""
        self._dbc_config_labels["file"].configure(text=config.filename)
        self._dbc_config_labels["version"].configure(
            text=config.version if config.version else "(none)")
        self._dbc_config_labels["messages"].configure(text=str(config.num_messages))
        self._dbc_config_labels["signals"].configure(text=str(config.num_signals))
        self._dbc_config_labels["frame_type"].configure(text=config.frame_types_str)
        self._dbc_config_labels["byte_order"].configure(text=config.byte_orders_str)
        self._dbc_config_labels["value_type"].configure(text=config.value_types_str)
        self._dbc_config_labels["nodes"].configure(text=config.nodes_summary)

    # --- SPN Tree Population ---

    def _populate_spn_tree(self, filter_text: str = ""):
        """
        Populate the SPN treeview with loaded DBC data.
        Respects the current search filter and preserves selection state.
        Sorted by PGN number+name, then by SPN name within each PGN.
        """
        # Clear tree
        for item in self.spn_tree.get_children():
            self.spn_tree.delete(item)

        self._sim_spn_tree_items.clear()
        self._sim_tree_item_to_key.clear()
        self._sim_pgn_tree_items.clear()

        if not self._dbc_handler.is_loaded:
            return

        filter_lower = filter_text.strip().lower()

        for pgn in self._dbc_handler.pgns:
            # Check PGN-level match
            pgn_name_match = (filter_lower in pgn.name.lower()) if filter_lower else True
            pgn_id_match = (filter_lower in pgn.pgn_hex.lower() or
                            filter_lower in str(pgn.pgn_decimal)) if filter_lower else True
            pgn_level_match = pgn_name_match or pgn_id_match

            # Determine which SPNs match the filter
            if filter_lower:
                matching_spns = [
                    spn for spn in pgn.signals
                    if (pgn_level_match
                        or filter_lower in spn.name.lower()
                        or filter_lower in (spn.unit or '').lower()
                        or filter_lower in (spn.comment or '').lower())
                ]
            else:
                matching_spns = list(pgn.signals)

            # Skip PGN entirely if no matching signals and PGN itself doesn't match
            if not matching_spns:
                continue

            # Insert PGN parent node
            pgn_text = f"\U0001F4E6 {pgn.name}"
            pgn_item = self.spn_tree.insert(
                "", tk.END, text=pgn_text,
                values=(
                    f"PGN {pgn.pgn_hex} ({pgn.pgn_decimal})",
                    f"{pgn.dlc} bytes",
                    "",
                    pgn.frame_type_str,
                    "",
                    "",
                    pgn.sender,
                    f"{len(pgn.signals)} signals"
                ),
                tags=("pgn",),
                open=bool(filter_lower)  # Auto-expand when filtering
            )

            self._sim_pgn_tree_items[pgn.name] = pgn_item

            # Insert SPN child nodes (already sorted by name in dbc_handler)
            for spn in matching_spns:
                spn_key = f"{pgn.name}.{spn.name}"
                is_selected = spn_key in self._sim_selected_spns
                checkbox = "\u2611" if is_selected else "\u2610"
                spn_text = f"{checkbox} {spn.name}"
                tag = "spn_selected" if is_selected else "spn"

                spn_item = self.spn_tree.insert(
                    pgn_item, tk.END, text=spn_text,
                    values=(
                        f"Bit {spn.start_bit}:{spn.length}",
                        f"{spn.length} bits",
                        spn.byte_order_short,
                        spn.type_str,
                        f"{spn.factor}",
                        f"{spn.offset}",
                        spn.unit,
                        spn.range_str
                    ),
                    tags=(tag,)
                )

                self._sim_spn_tree_items[spn_key] = spn_item
                self._sim_tree_item_to_key[spn_item] = spn_key

        self._update_sim_selection_count()

    # --- SPN Tree Event Handlers ---

    def _on_spn_tree_click(self, event):
        """Handle click on the SPN treeview — toggle SPN selection."""
        item_id = self.spn_tree.identify_row(event.y)
        if not item_id:
            return

        # Only toggle SPN items (children), not PGN items (parents)
        parent = self.spn_tree.parent(item_id)
        if not parent:
            # Clicked a PGN row — just let expand/collapse work
            return

        spn_key = self._sim_tree_item_to_key.get(item_id)
        if not spn_key:
            return

        current_text = self.spn_tree.item(item_id, 'text')

        if spn_key in self._sim_selected_spns:
            # Deselect
            self._sim_selected_spns.discard(spn_key)
            new_text = current_text.replace("\u2611", "\u2610", 1)
            self.spn_tree.item(item_id, text=new_text, tags=("spn",))
        else:
            # Enforce max 20 selected SPNs
            if len(self._sim_selected_spns) >= 20:
                messagebox.showwarning(
                    "Selection Limit",
                    "Maximum 20 SPNs can be selected for simulation.")
                return
            # Select
            self._sim_selected_spns.add(spn_key)
            new_text = current_text.replace("\u2610", "\u2611", 1)
            self.spn_tree.item(item_id, text=new_text, tags=("spn_selected",))

        self._update_sim_selection_count()
        self._update_signal_gen_table()
        self._save_sim_config()

    def _on_spn_search_changed(self, *args):
        """Handle search entry change — debounced tree filtering."""
        if hasattr(self, '_spn_filter_after_id'):
            self.root.after_cancel(self._spn_filter_after_id)
        self._spn_filter_after_id = self.root.after(
            300, lambda: self._populate_spn_tree(
                filter_text=self.spn_search_var.get()))

    def _select_all_visible_spns(self):
        """Select all currently visible (filtered) SPNs, up to 20 total."""
        for spn_key, spn_item in self._sim_spn_tree_items.items():
            if len(self._sim_selected_spns) >= 20:
                messagebox.showwarning(
                    "Selection Limit",
                    "Maximum 20 SPNs can be selected for simulation.")
                break
            if spn_key not in self._sim_selected_spns:
                self._sim_selected_spns.add(spn_key)
                current_text = self.spn_tree.item(spn_item, 'text')
                new_text = current_text.replace("\u2610", "\u2611", 1)
                self.spn_tree.item(spn_item, text=new_text, tags=("spn_selected",))
        self._update_sim_selection_count()
        self._update_signal_gen_table()
        self._save_sim_config()

    def _deselect_all_spns(self):
        """Deselect all SPNs (including those not currently visible)."""
        self._sim_selected_spns.clear()
        self._sim_spn_configs.clear()
        # Re-populate to refresh checkboxes
        self._populate_spn_tree(filter_text=self.spn_search_var.get())
        self._update_signal_gen_table()
        self._save_sim_config()

    def _update_sim_selection_count(self):
        """Update the selection count label."""
        num_spns = len(self._sim_selected_spns)
        # Count unique PGNs
        pgn_names = set()
        for key in self._sim_selected_spns:
            pgn_name = key.split(".", 1)[0]
            pgn_names.add(pgn_name)
        num_pgns = len(pgn_names)
        self.sim_selection_var.set(
            f"Selected: {num_spns} SPN{'s' if num_spns != 1 else ''} "
            f"from {num_pgns} PGN{'s' if num_pgns != 1 else ''}"
        )

    # --- Signal Generation Table ---

    def _get_entry_actual_value(self, entry) -> str:
        """Get the typed value from a placeholder entry, '' if still placeholder."""
        if getattr(entry, '_is_placeholder', True):
            return ""
        return entry.get()

    def _set_entry_actual_value(self, entry, value: str):
        """Set a real value on a placeholder entry, clearing placeholder state."""
        if not value:
            return  # keep placeholder
        entry.delete(0, tk.END)
        entry.insert(0, value)
        entry.configure(fg=COLORS["fg_primary"])
        entry._is_placeholder = False

    def _capture_sim_gen_values(self):
        """Capture current signal gen widget values into _sim_spn_configs."""
        for spn_key, info in self._sim_gen_widgets.items():
            self._sim_spn_configs[spn_key] = {
                "mode": info["mode_var"].get(),
                "const": self._get_entry_actual_value(info["const_entry"]),
                "sweep_min": self._get_entry_actual_value(info["sweep_min_entry"]),
                "sweep_max": self._get_entry_actual_value(info["sweep_max_entry"]),
                "step": self._get_entry_actual_value(info["sweep_diff_entry"]),
                "freq": self._get_entry_actual_value(info["sweep_freq_entry"]),
            }

    def _save_sim_config(self):
        """Capture widget values and persist sim config to settings."""
        self._capture_sim_gen_values()
        self.settings["sim_selected_spns"] = list(self._sim_selected_spns)
        self.settings["sim_spn_configs"] = self._sim_spn_configs
        self.settings.save()

    def _create_placeholder_entry(self, parent, placeholder="", width=12):
        """Create a tk.Entry with grey placeholder text showing allowed range."""
        entry = tk.Entry(parent, width=width,
                        bg=COLORS["bg_dark"],
                        fg="#666666",
                        insertbackground=COLORS["fg_primary"],
                        font=("Consolas", 9),
                        relief=tk.FLAT,
                        highlightthickness=1,
                        highlightbackground=COLORS["bg_light"],
                        highlightcolor=COLORS["accent"])
        entry.insert(0, placeholder)
        entry._placeholder = placeholder
        entry._is_placeholder = True

        def on_focus_in(e):
            if entry._is_placeholder:
                entry.delete(0, tk.END)
                entry.configure(fg=COLORS["fg_primary"])
                entry._is_placeholder = False

        def on_focus_out(e):
            if not entry.get():
                entry.insert(0, entry._placeholder)
                entry.configure(fg="#666666")
                entry._is_placeholder = True

        def on_return(e):
            # Move focus to parent so the entry "releases"
            parent.focus_set()

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        entry.bind("<Return>", on_return)
        entry.bind("<KP_Enter>", on_return)
        entry.bind("<Escape>", on_return)
        return entry

    @staticmethod
    def _safe_float(text: str, default: float) -> float:
        """Parse a string to float – safe to call from any thread."""
        try:
            return float(text) if text else default
        except (ValueError, TypeError):
            return default

    def _get_entry_float(self, entry, default: float) -> float:
        """Get float value from a placeholder entry, returning default if placeholder."""
        try:
            if getattr(entry, '_is_placeholder', True):
                return default
            val = entry.get()
            return float(val) if val else default
        except Exception:
            return default

    def _update_signal_gen_table(self):
        """Rebuild the signal generation table from selected SPNs."""
        # Capture current values BEFORE destroying widgets
        self._capture_sim_gen_values()

        # Destroy all existing row widgets
        for widget_dict in self._sim_gen_widgets.values():
            for w in widget_dict.get("all_widgets", []):
                try:
                    w.destroy()
                except Exception:
                    pass
        self._sim_gen_widgets.clear()

        if not self._sim_selected_spns:
            self._sim_gen_empty_label.grid(row=2, column=0, columnspan=8, pady=20)
            return

        self._sim_gen_empty_label.grid_forget()

        # Get SPN info for selected ones
        selected_info = self._dbc_handler.get_selected_spn_info(self._sim_selected_spns)

        for i, (pgn, spn) in enumerate(selected_info):
            row_idx = i + 2  # row 0 = header, row 1 = separator
            spn_key = f"{pgn.name}.{spn.name}"
            all_widgets = []

            # # column
            num_lbl = ttk.Label(self._sim_gen_table, text=str(i + 1),
                               style="Medium.TLabel", width=3, anchor=tk.W)
            num_lbl.grid(row=row_idx, column=0, padx=2, pady=1, sticky="w")
            all_widgets.append(num_lbl)

            # SPN Name
            name_lbl = ttk.Label(self._sim_gen_table, text=spn.name,
                                style="Medium.TLabel", width=22,
                                font=("Consolas", 9), anchor=tk.W)
            name_lbl.grid(row=row_idx, column=1, padx=2, pady=1, sticky="w")
            all_widgets.append(name_lbl)

            # PGN
            pgn_lbl = ttk.Label(self._sim_gen_table, text=pgn.name,
                               style="Medium.TLabel", width=16,
                               font=("Consolas", 9), anchor=tk.W)
            pgn_lbl.grid(row=row_idx, column=2, padx=2, pady=1, sticky="w")
            all_widgets.append(pgn_lbl)

            # Type combobox
            mode_var = tk.StringVar(value="Const")
            mode_combo = ttk.Combobox(self._sim_gen_table, textvariable=mode_var,
                                      values=["Sweep", "Const"],
                                      state="readonly", width=7)
            mode_combo.grid(row=row_idx, column=3, padx=2, pady=1, sticky="w")
            all_widgets.append(mode_combo)

            range_min = spn.minimum
            range_max = spn.maximum

            # Const mode entry (column 4, spans cols 4-6)
            const_ph = f"{range_min} ... {range_max}"
            const_entry = self._create_placeholder_entry(
                self._sim_gen_table, placeholder=const_ph, width=40)
            all_widgets.append(const_entry)

            # Sweep mode entries
            sweep_min_entry = self._create_placeholder_entry(
                self._sim_gen_table, placeholder=str(range_min), width=12)
            all_widgets.append(sweep_min_entry)

            sweep_max_entry = self._create_placeholder_entry(
                self._sim_gen_table, placeholder=str(range_max), width=12)
            all_widgets.append(sweep_max_entry)

            step_ph = str(spn.factor) if spn.factor else "1.0"
            sweep_diff_entry = self._create_placeholder_entry(
                self._sim_gen_table, placeholder=step_ph, width=10)
            all_widgets.append(sweep_diff_entry)

            # Freq (Hz) entry for sweep mode
            sweep_freq_entry = self._create_placeholder_entry(
                self._sim_gen_table, placeholder="1.0", width=10)
            all_widgets.append(sweep_freq_entry)

            # Unit
            unit_lbl = ttk.Label(self._sim_gen_table, text=spn.unit or "",
                                style="Medium.TLabel", width=8,
                                font=("Consolas", 9), anchor=tk.W)
            unit_lbl.grid(row=row_idx, column=8, padx=2, pady=1, sticky="w")
            all_widgets.append(unit_lbl)

            # Auto-save on FocusOut of every entry
            for ent in (const_entry, sweep_min_entry, sweep_max_entry,
                        sweep_diff_entry, sweep_freq_entry):
                ent.bind("<FocusOut>",
                         lambda e: self._save_sim_config(), add="+")

            # Bind mode change
            mode_combo.bind('<<ComboboxSelected>>',
                           lambda e, k=spn_key: self._on_gen_mode_change(k))

            self._sim_gen_widgets[spn_key] = {
                "all_widgets": all_widgets,
                "mode_var": mode_var,
                "const_entry": const_entry,
                "sweep_min_entry": sweep_min_entry,
                "sweep_max_entry": sweep_max_entry,
                "sweep_diff_entry": sweep_diff_entry,
                "sweep_freq_entry": sweep_freq_entry,
                "spn_info": spn,
                "pgn_info": pgn,
                "row": row_idx,
            }

            # Restore saved config or default to Const mode
            saved = self._sim_spn_configs.get(spn_key)
            if saved:
                mode_var.set(saved.get("mode", "Const"))
                self._on_gen_mode_change(spn_key)
                self._set_entry_actual_value(const_entry, saved.get("const", ""))
                self._set_entry_actual_value(sweep_min_entry, saved.get("sweep_min", ""))
                self._set_entry_actual_value(sweep_max_entry, saved.get("sweep_max", ""))
                self._set_entry_actual_value(sweep_diff_entry, saved.get("step", ""))
                self._set_entry_actual_value(sweep_freq_entry, saved.get("freq", ""))
            else:
                self._on_gen_mode_change(spn_key)

    def _on_gen_mode_change(self, spn_key: str):
        """Handle signal type change between Sweep and Const."""
        info = self._sim_gen_widgets.get(spn_key)
        if not info:
            return
        row = info["row"]
        mode = info["mode_var"].get()

        if mode == "Sweep":
            info["const_entry"].grid_remove()
            info["sweep_min_entry"].grid(row=row, column=4, padx=2, pady=1, sticky="w")
            info["sweep_max_entry"].grid(row=row, column=5, padx=2, pady=1, sticky="w")
            info["sweep_diff_entry"].grid(row=row, column=6, padx=2, pady=1, sticky="w")
            info["sweep_freq_entry"].grid(row=row, column=7, padx=2, pady=1, sticky="w")
        else:
            info["sweep_min_entry"].grid_remove()
            info["sweep_max_entry"].grid_remove()
            info["sweep_diff_entry"].grid_remove()
            info["sweep_freq_entry"].grid_remove()
            info["const_entry"].grid(row=row, column=4, columnspan=4,
                                     padx=2, pady=1, sticky="w")

        # Auto-save after mode change
        self._save_sim_config()

    # --- Simulation Control ---

    def _start_simulation(self):
        """Start the CAN simulation using the main connected device."""
        if not self.can_interface.is_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to a device first using the "
                                   "connection bar at the top.")
            return

        if not self._sim_selected_spns:
            messagebox.showwarning("No SPNs Selected",
                                   "Select at least one SPN to simulate.")
            return

        if not self._dbc_handler.is_loaded:
            messagebox.showwarning("No DBC Loaded",
                                   "Load a DBC file first.")
            return

        # Snapshot every entry value into _sim_spn_configs so the
        # background thread never has to touch tkinter widgets.
        self._capture_sim_gen_values()

        self._sim_running_flag = True
        self._sim_sweep_values.clear()
        self._sim_tx_count = 0
        self._sim_error_count = 0
        self._sim_start_time = time.time()

        # Initialize sweep values to min (from snapshot, not widgets)
        for spn_key, info in self._sim_gen_widgets.items():
            cfg = self._sim_spn_configs.get(spn_key, {})
            sweep_min = self._safe_float(
                cfg.get("sweep_min", ""), info["spn_info"].minimum)
            self._sim_sweep_values[spn_key] = sweep_min

        self._sim_thread = threading.Thread(target=self._simulation_loop,
                                            daemon=True)
        self._sim_thread.start()

        self.sim_start_btn.configure(state=tk.DISABLED)
        self.sim_stop_btn.configure(state=tk.NORMAL)
        self.sim_gen_status_var.set("▶ Running...")
        self._update_sim_status()

    def _stop_simulation(self):
        """Stop the CAN simulation."""
        self._sim_running_flag = False
        if self._sim_thread:
            self._sim_thread.join(timeout=2.0)
            self._sim_thread = None

        self.sim_start_btn.configure(state=tk.NORMAL)
        self.sim_stop_btn.configure(state=tk.DISABLED)
        self.sim_gen_status_var.set("⏹ Stopped")
    
    def _on_sim_device_lost(self):
        """Called on main thread when simulation detects device is gone."""
        self.sim_start_btn.configure(state=tk.NORMAL)
        self.sim_stop_btn.configure(state=tk.DISABLED)
        elapsed = time.time() - self._sim_start_time if self._sim_start_time else 0.0
        self.sim_gen_status_var.set(
            f"⚠ Device lost | TX: {self._sim_tx_count} | "
            f"Errors: {self._sim_error_count} | {elapsed:.1f}s")

    def _simulation_loop(self):
        """Background thread: generate and send CAN frames.

        IMPORTANT: This thread must NEVER call tkinter widget methods
        (entry.get(), mode_var.get(), etc.) – that is not thread-safe and
        silently fails on many platforms.  All user-entered values are read
        from the ``_sim_spn_configs`` dict which is populated on the main
        thread (captured before start and refreshed by _update_sim_status).
        """
        interval_s = 0.100  # 100ms tick rate (10 Hz)

        while self._sim_running_flag:
            # Bail out immediately if device is gone
            if not self.can_interface.is_connected:
                self._sim_running_flag = False
                self.root.after(0, lambda: self._on_sim_device_lost())
                break

            # Group signals by PGN
            pgn_signals: Dict[str, Dict[str, float]] = defaultdict(dict)

            for spn_key, info in list(self._sim_gen_widgets.items()):
                pgn_name = info["pgn_info"].name
                spn_name = info["spn_info"].name
                spn = info["spn_info"]

                # ── Read everything from the config snapshot (plain dict) ──
                cfg = self._sim_spn_configs.get(spn_key, {})
                mode = cfg.get("mode", "Const")

                if mode == "Const":
                    value = self._safe_float(
                        cfg.get("const", ""), spn.minimum)
                else:
                    current = self._sim_sweep_values.get(spn_key, spn.minimum)
                    value = current
                    s_min = self._safe_float(
                        cfg.get("sweep_min", ""), spn.minimum)
                    s_max = self._safe_float(
                        cfg.get("sweep_max", ""), spn.maximum)

                    # Step  = value to add/subtract per tic
                    # Tics/s = how many tics (steps) per second
                    step_val = self._safe_float(
                        cfg.get("step", ""), spn.factor or 1.0)
                    tics_per_s = self._safe_float(
                        cfg.get("freq", ""), 1.0)

                    # diff per loop-tick = step * tics_per_s * interval_s
                    # Example: step=10, tics/s=5, loop=10Hz →
                    #   diff = 10 * 5 * 0.1 = 5.0 per loop-tick
                    #   → 50/s  (= step * tics_per_s)
                    diff = step_val * tics_per_s * interval_s

                    next_val = current + diff
                    if diff >= 0 and next_val > s_max:
                        next_val = s_min
                    elif diff < 0 and next_val < s_min:
                        next_val = s_max
                    self._sim_sweep_values[spn_key] = next_val

                pgn_signals[pgn_name][spn_name] = value

            # Encode and send each PGN via the main CAN interface
            for pgn_name, signals in pgn_signals.items():
                # Re-check connection before each send
                if not self.can_interface.is_connected:
                    self._sim_running_flag = False
                    self.root.after(0, lambda: self._on_sim_device_lost())
                    break
                try:
                    msg = self._dbc_handler.db.get_message_by_name(pgn_name)
                    # Build defaults for ALL signals so encode doesn't
                    # KeyError on signals the user didn't select
                    all_signals: Dict[str, float] = {}
                    for sig in msg.signals:
                        if sig.initial is not None:
                            all_signals[sig.name] = sig.initial
                        elif sig.minimum is not None:
                            all_signals[sig.name] = sig.minimum
                        else:
                            all_signals[sig.name] = 0
                    # Override with user-selected values
                    all_signals.update(signals)
                    data = msg.encode(all_signals, scaling=True, padding=True,
                                     strict=False)
                    if self.can_interface.send(
                            msg.frame_id, data,
                            extended=getattr(msg, 'is_extended_frame', False)):
                        self._sim_tx_count += 1
                    else:
                        self._sim_error_count += 1
                except Exception as e:
                    self._sim_error_count += 1
                    print(f"[Sim] Error {pgn_name}: {e}")
            else:
                # Only sleep if the inner for-loop wasn't broken out of
                time.sleep(interval_s)
                continue
            # Inner loop was broken (device lost), exit outer loop too
            break

    def _update_sim_status(self):
        """Periodically update simulation status in the UI."""
        if not self._sim_running_flag:
            return

        # Re-snapshot entry values on the main thread so the background
        # sim loop picks up any changes the user made while running.
        self._capture_sim_gen_values()

        elapsed = time.time() - self._sim_start_time if self._sim_start_time else 0.0
        self.sim_gen_status_var.set(
            f"▶ Running | TX: {self._sim_tx_count} | "
            f"Errors: {self._sim_error_count} | {elapsed:.1f}s")
        self.root.after(500, self._update_sim_status)

    def _bind_events(self):
        """Bind keyboard and window events."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<F5>", lambda e: self._scan_devices())
        self.root.bind("<Delete>", lambda e: self._clear_data())
        
    def _scan_devices(self):
        """Scan for CAN devices."""
        if self.can_interface.is_connected:
            return  # Don't scan while connected
        self.scan_btn.configure(state=tk.DISABLED)
        self.conn_status_var.set("\u25CF Scanning...")
        self.root.update_idletasks()
        
        try:
            self.devices = CANInterface.scan_devices()
            
            device_names = [str(d) for d in self.devices]
            
            if self.devices:
                self.device_combo["values"] = device_names
                self.device_combo.current(0)
                self.conn_status_var.set(f"\u25CF Found {len(self.devices)} device(s)")
            else:
                self.device_combo["values"] = []
                self.device_var.set("")
                self.conn_status_var.set("\u25CF No devices found")
                messagebox.showwarning("No Devices", 
                    "No candleLight devices found.\n\n"
                    "Make sure:\n"
                    "1. Device is plugged in\n"
                    "2. WinUSB driver is installed (use Zadig)\n"
                    "3. candleLight firmware is flashed")
        except Exception as e:
            self.conn_status_var.set("\u25CF Scan error")
            messagebox.showerror("Scan Error", str(e))
        finally:
            self.scan_btn.configure(state=tk.NORMAL)
    
    def _connect(self):
        """Connect to selected device."""
        if not self.devices:
            messagebox.showwarning("No Device", "Please scan for devices first.")
            return
        
        idx = self.device_combo.current()
        if idx < 0:
            return
        
        device = self.devices[idx]
        bitrate = int(self.bitrate_var.get())
        
        self.conn_status_var.set("● Connecting...")
        self.root.update_idletasks()
        
        # Set callbacks
        self.can_interface.set_frame_callback(self._on_frame_received)
        self.can_interface.set_disconnect_callback(self._on_device_disconnected)
        
        if self.can_interface.connect(device, bitrate):
            self.conn_status_var.set(
                f"● Connected: {device} @ {bitrate//1000}k")
            self.connect_btn.configure(state=tk.DISABLED)
            self.disconnect_btn.configure(state=tk.NORMAL)
            self.device_combo.configure(state=tk.DISABLED)
            self.scan_btn.configure(state=tk.DISABLED)
        else:
            self.conn_status_var.set("● Connection failed")
            messagebox.showerror("Connection Failed", 
                "Could not connect to the device.\nTry unplugging and replugging.")
    
    def _disconnect(self):
        """Disconnect from device."""
        # Stop simulation if running
        if self._sim_running_flag:
            self._stop_simulation()
        self.can_interface.disconnect()
        self._reset_connection_ui("● Disconnected")
    
    def _reset_connection_ui(self, status_text: str = "● Disconnected"):
        """Reset all connection-related UI elements to disconnected state."""
        self.conn_status_var.set(status_text)
        self.connect_btn.configure(state=tk.NORMAL)
        self.disconnect_btn.configure(state=tk.DISABLED)
        self.device_combo.configure(state="readonly")
        self.scan_btn.configure(state=tk.NORMAL)
    
    def _on_device_disconnected(self, reason: str):
        """Called from CAN RX thread when device unexpectedly disconnects."""
        # Schedule UI update on the main (Tk) thread
        self.root.after(0, lambda: self._handle_unexpected_disconnect(reason))
    
    def _handle_unexpected_disconnect(self, reason: str):
        """Handle unexpected device disconnection on main thread."""
        # Stop simulation if running
        if self._sim_running_flag:
            self._stop_simulation()
        
        # Reset UI
        self._reset_connection_ui("⚠ Device lost")
        
        # Clear stale device list since the HW is gone
        self.devices.clear()
        self.device_combo["values"] = []
        self.device_var.set("")
        
        messagebox.showwarning("Device Disconnected", reason)
    
    def _on_frame_received(self, frame: CANFrame):
        """Callback when a CAN frame is received (called from CAN thread)."""
        # Queue frame for UI update (thread-safe)
        self.frame_queue.put(frame)
        
        # Log if enabled
        if self.logger.is_logging:
            self.logger.log_frame(frame)
    
    def _schedule_update(self):
        """Schedule periodic UI update."""
        self._update_ui()
        # Redraw parsed-viewer graphs (throttled internally)
        if self._pv_graph_slots:
            self._pv_draw_all_graphs()
        self.root.after(DATA_VIEWER_UPDATE_MS, self._schedule_update)
    
    def _update_ui(self):
        """Update UI with queued frames."""
        frames_to_add = []
        
        # Get all queued frames
        while True:
            try:
                frame = self.frame_queue.get_nowait()
                frames_to_add.append(frame)
                
                # Update counters
                self._frame_count += 1
                if frame.direction == FrameDirection.RX:
                    self._rx_count += 1
                else:
                    self._tx_count += 1
                
                # Track CAN IDs for raw data view
                self._can_id_data[frame.can_id] = frame
                self._can_id_counts[frame.can_id] += 1
                
                # Update byte history for selected ID
                if self._graph_running and frame.can_id == self._selected_can_id:
                    for i in range(min(8, len(frame.data))):
                        self._byte_history[i].append((frame.timestamp, frame.data[i]))
                    
            except queue.Empty:
                break
        
        # Decode frames for the Parsed Data Viewer
        if frames_to_add:
            self._pv_process_frames(frames_to_add)
        
        # Add frames to treeview
        for frame in frames_to_add:
            tag = "rx" if frame.direction == FrameDirection.RX else "tx"
            
            self.tree.insert("", tk.END, values=(
                self._frame_count,
                f"{frame.timestamp:.3f}",
                frame.direction.value,
                frame.id_hex,
                frame.dlc,
                frame.data_hex,
                frame.data_ascii
            ), tags=(tag,))
        
        # Limit rows
        children = self.tree.get_children()
        if len(children) > DATA_VIEWER_MAX_ROWS:
            for item in children[:len(children) - DATA_VIEWER_MAX_ROWS]:
                self.tree.delete(item)
        
        # Auto-scroll to bottom
        if frames_to_add and self.autoscroll_var.get():
            self.tree.yview_moveto(1.0)
        
        # Update counter display
        self.counter_var.set(f"RX: {self._rx_count} | TX: {self._tx_count} | Total: {self._frame_count}")
        
        # Update CAN ID list
        if frames_to_add:
            self._update_canid_list()
        
        # Update raw data view for selected ID
        if self._selected_can_id is not None and self._selected_can_id in self._can_id_data:
            frame = self._can_id_data[self._selected_can_id]
            self._draw_bit_grid(frame.data)
            self._maybe_draw_graph()
        
        # Update log status
        if self.logger.is_logging:
            size = self.logger.current_file_size_mb
            count = self.logger.frames_logged
            part = self.logger.part_number
            part_str = f" (part {part})" if part > 0 else ""
            self.log_status_var.set(f"Logging{part_str}: {count} frames | {size:.2f} MB")
    
    def _update_canid_list(self):
        """Update the CAN ID listbox."""
        # Remember selection
        selection = self.canid_listbox.curselection()
        selected_idx = selection[0] if selection else None
        
        # Get sorted CAN IDs
        sorted_ids = sorted(self._can_id_counts.keys())
        
        # Update list
        self.canid_listbox.delete(0, tk.END)
        for can_id in sorted_ids:
            count = self._can_id_counts[can_id]
            self.canid_listbox.insert(tk.END, f"0x{can_id:03X}  ({count} frames)")
        
        # Restore selection
        if selected_idx is not None and selected_idx < self.canid_listbox.size():
            self.canid_listbox.selection_set(selected_idx)
    
    def _clear_data(self):
        """Clear the data viewer."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._frame_count = 0
        self._rx_count = 0
        self._tx_count = 0
        self.counter_var.set("RX: 0 | TX: 0 | Total: 0")
    
    def _browse_log_dir(self):
        """Browse for log directory."""
        dir_path = filedialog.askdirectory(initialdir=self.log_dir_var.get())
        if dir_path:
            self.log_dir_var.set(dir_path)
    
    def _start_logging(self):
        """Start logging CAN data."""
        try:
            self.logger.log_dir = self.log_dir_var.get()
            self.logger.base_filename = self.log_filename_var.get()
            self.logger.max_size_bytes = int(float(self.max_size_var.get()) * 1024 * 1024)
            
            file_path = self.logger.start()
            self.log_status_var.set(f"Logging: {file_path}")
            
            self.log_start_btn.configure(state=tk.DISABLED)
            self.log_stop_btn.configure(state=tk.NORMAL)
            
        except Exception as e:
            messagebox.showerror("Logging Error", str(e))
    
    def _stop_logging(self):
        """Stop logging CAN data."""
        stats = self.logger.stop()
        self.log_status_var.set(
            f"Stopped. {stats['frames_logged']} frames, "
            f"{stats['files_created']} file(s)"
        )
        
        self.log_start_btn.configure(state=tk.NORMAL)
        self.log_stop_btn.configure(state=tk.DISABLED)
    
    def _on_close(self):
        """Handle window close."""
        # Save settings before closing
        self._save_settings()
        
        # Stop simulation if running
        if self._sim_running_flag:
            self._stop_simulation()
        
        if self.can_interface.is_connected:
            self.can_interface.disconnect()
        if self.logger.is_logging:
            self.logger.stop()
        self.root.destroy()
    
    def run(self):
        """Run the application."""
        # Initial device scan
        self.root.after(500, self._scan_devices)
        
        # Start main loop
        self.root.mainloop()


def main():
    """Application entry point."""
    app = YonaCanApp()
    app.run()


if __name__ == "__main__":
    main()
