"""
YonaCan - Main Application GUI
Modern CAN bus analyzer for candleLight devices.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from datetime import datetime
from typing import Optional, List, Dict, Tuple
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
        
    def _bind_events(self):
        """Bind keyboard and window events."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<F5>", lambda e: self._scan_devices())
        self.root.bind("<Delete>", lambda e: self._clear_data())
        
    def _scan_devices(self):
        """Scan for CAN devices."""
        self.scan_btn.configure(state=tk.DISABLED)
        self.conn_status_var.set("● Scanning...")
        self.root.update_idletasks()
        
        try:
            self.devices = CANInterface.scan_devices()
            
            if self.devices:
                device_names = [str(d) for d in self.devices]
                self.device_combo["values"] = device_names
                self.device_combo.current(0)
                self.conn_status_var.set(f"● Found {len(self.devices)} device(s)")
            else:
                self.device_combo["values"] = []
                self.device_var.set("")
                self.conn_status_var.set("● No devices found")
                messagebox.showwarning("No Devices", 
                    "No candleLight devices found.\n\n"
                    "Make sure:\n"
                    "1. Device is plugged in\n"
                    "2. WinUSB driver is installed (use Zadig)\n"
                    "3. candleLight firmware is flashed")
        except Exception as e:
            self.conn_status_var.set(f"● Scan error")
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
        
        # Set frame callback
        self.can_interface.set_frame_callback(self._on_frame_received)
        
        if self.can_interface.connect(device, bitrate):
            self.conn_status_var.set(f"● Connected @ {bitrate//1000}k")
            self.connect_btn.configure(state=tk.DISABLED)
            self.disconnect_btn.configure(state=tk.NORMAL)
            self.device_combo.configure(state=tk.DISABLED)
        else:
            self.conn_status_var.set("● Connection failed")
            messagebox.showerror("Connection Failed", 
                "Could not connect to the device.\nTry unplugging and replugging.")
    
    def _disconnect(self):
        """Disconnect from device."""
        self.can_interface.disconnect()
        self.conn_status_var.set("● Disconnected")
        self.connect_btn.configure(state=tk.NORMAL)
        self.disconnect_btn.configure(state=tk.DISABLED)
        self.device_combo.configure(state="readonly")
    
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
        
        # Auto-scroll
        if frames_to_add and self.autoscroll_var.get():
            children = self.tree.get_children()
            if children:
                self.tree.see(children[-1])
        
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
