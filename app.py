"""
app.py
Scientific Calculator -- desktop app (CustomTkinter).

Every calculation is performed by evaluator.py / decimal100.py / bignum100.py
using base-100 arbitrary-precision arithmetic from scratch (no floats used
for the actual math -- see decimal100.py header for the one documented
exception: cheap integer bookkeeping during range reduction).

Run:
    pip install customtkinter
    python app.py

Build a Windows/Mac/Linux .exe (run ON that OS, with internet access):
    pip install pyinstaller
    pyinstaller --onefile --windowed app.py
"""

import time
import threading
import traceback

import customtkinter as ctk

import bignum100
from decimal100 import Decimal100, PI, E
from evaluator import evaluate, EvalError

# ---------------------------------------------------------------- constants
PHI = Decimal100.from_string("1.6180339887498948482045868343656381177203091798057628621354486227052604628189")
G = Decimal100.from_string("0.0000000000667430")
C_LIGHT = Decimal100.from_string("299792458")
PLANCK = Decimal100.from_string("0.000000000000000000000000000000000662607015")
AVOGADRO = Decimal100.from_string("602214076000000000000000")
GAS_R = Decimal100.from_string("8.314462618")

CONSTANT_TABLE = [
    ("\u03c0", "Pi", PI.to_string(14)),
    ("e", "Euler's number", E.to_string(14)),
    ("\u03c6", "Golden ratio", PHI.to_string(14)),
    ("G", "Gravitational constant", "6.67430\u00d710\u207b\u00b9\u00b9"),
    ("c", "Speed of light", "2.99792458\u00d710\u2078"),
    ("h", "Planck's constant", "6.62607015\u00d710\u207b\u00b3\u2074"),
    ("N\u2090", "Avogadro's number", "6.02214076\u00d710\u00b2\u00b3"),
    ("R", "Gas constant", GAS_R.to_string(10)),
]

DARK_BG = "#0b1220"
PANEL_BG = "#101a2c"
CARD_BG = "#16233a"
KEY_BG = "#1c2b46"
KEY_HOVER = "#233457"
ACCENT_BLUE = "#3b82f6"
ACCENT_BLUE_HOVER = "#2f6fd8"
ACCENT_ORANGE = "#f2994a"
ACCENT_ORANGE_HOVER = "#d9822f"
TEXT_MAIN = "#f1f5f9"
TEXT_DIM = "#8896ab"


class ScientificCalculator(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Scientific Calculator")
        self.geometry("1150x700")
        self.minsize(860, 560)
        self.resizable(True, True)
        self.configure(fg_color=DARK_BG)

        ctk.set_appearance_mode("dark")

        # ---------------- state ----------------
        # (expression text now lives in self.expr_var, created in _build_display)
        self.angle_mode = "deg"       # "deg" or "rad"
        self.hyperbolic = True   # matches default ON switch state below
        self.memory_value = Decimal100.zero()
        self.memory_active = False
        self.last_answer = Decimal100.zero()
        self.log_base_value = "10"    # for the Logarithm tab base dropdown

        self._build_display()
        self._build_tabs()
        self._setup_keyboard_shortcuts()

    def _setup_keyboard_shortcuts(self):
        # The expression field is a real Entry, so typing digits, operators
        # (+ - * / ^ % . ( ) ! , letters for sin/cos/etc.) already works
        # natively the moment it has keyboard focus. These add the few
        # things a plain Entry doesn't give you for free:
        self.bind_all("<Return>", lambda e: self._equals())
        self.bind_all("<KP_Enter>", lambda e: self._equals())
        self.bind_all("<Escape>", lambda e: self._all_clear())
        # start with keyboard focus in the expression field
        self.after(100, self.expr_entry.focus_set)

    # ================================================================
    # DISPLAY
    # ================================================================
    def _build_display(self):
        frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=14)
        frame.pack(fill="x", padx=16, pady=(16, 8))

        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(10, 0))

        self.mode_label = ctk.CTkLabel(
            top_row, text=self._mode_text(), font=ctk.CTkFont(size=12),
            text_color=TEXT_DIM, anchor="w",
        )
        self.mode_label.pack(side="left")

        self.cancel_button = ctk.CTkButton(
            top_row, text="Cancel", width=64, height=22,
            fg_color=ACCENT_ORANGE, hover_color=ACCENT_ORANGE_HOVER,
            text_color="#ffffff", corner_radius=6,
            font=ctk.CTkFont(size=11), command=self._cancel_calculation,
        )
        # only shown while a calculation is running; not packed yet

        self.timing_label = ctk.CTkLabel(
            top_row, text="", font=ctk.CTkFont(size=12),
            text_color=TEXT_DIM, anchor="e",
        )
        self.timing_label.pack(side="right")

        # ---- expression line: a real, editable, pasteable Entry ----
        self.expr_var = ctk.StringVar(value="")
        self.expr_entry = ctk.CTkEntry(
            frame, textvariable=self.expr_var,
            font=ctk.CTkFont(size=18), justify="right",
            fg_color="transparent", border_width=0,
            text_color=TEXT_DIM,
        )
        self.expr_entry.pack(fill="x", padx=16, pady=(6, 0))
        # (Enter/Escape are wired globally in _setup_keyboard_shortcuts)

        # ---- main display: one expanded, scrollable box holding both the
        # full-precision number and its scientific notation. Font size
        # shrinks automatically for very long numbers; a scrollbar (built
        # into CTkTextbox) appears on its own if content still overflows. ----
        self.result_box = ctk.CTkTextbox(
            frame, height=150, wrap="char",
            fg_color="transparent", text_color=TEXT_MAIN,
            corner_radius=0, border_width=0,
        )
        self.result_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self._init_result_tags()
        self._show_result_text("0", "")

    def _init_result_tags(self):
        """Configure the Text-widget tags used to size/color sections of
        the main display differently. Wrapped in try/except: CTkTextbox
        forwards to the underlying tkinter Text widget, but tag options
        are set defensively in case of version differences."""
        box = self.result_box
        try:
            box.tag_config("main", font=ctk.CTkFont(size=40, weight="bold"))
            box.tag_config("label", font=ctk.CTkFont(size=12), foreground=TEXT_DIM)
            box.tag_config("sci", font=ctk.CTkFont(size=16), foreground=TEXT_MAIN)
            box.tag_config("err", font=ctk.CTkFont(size=22, weight="bold"), foreground=ACCENT_ORANGE)
        except Exception:
            pass

    @staticmethod
    def _pick_main_font_size(digit_count):
        # more digits -> smaller font, so long numbers stay on screen
        # as long as possible before the scrollbar has to take over
        if digit_count <= 12:
            return 40
        if digit_count <= 20:
            return 32
        if digit_count <= 30:
            return 24
        if digit_count <= 45:
            return 18
        if digit_count <= 70:
            return 14
        return 11

    def _show_result_text(self, main_text, sci_text, is_error=False):
        box = self.result_box
        box.configure(state="normal")
        box.delete("1.0", "end")

        if is_error:
            box.insert("end", main_text, "err")
            box.configure(state="normal")
            return

        digit_count = sum(ch.isdigit() for ch in main_text)
        size = self._pick_main_font_size(digit_count)
        try:
            box.tag_config("main", font=ctk.CTkFont(size=size, weight="bold"))
        except Exception:
            pass

        box.insert("end", main_text, "main")
        if sci_text:
            box.insert("end", "\n\nScientific notation:\n", "label")
            box.insert("end", sci_text, "sci")
        box.see("1.0")
        # left as state="normal" (not "disabled") so the text stays
        # selectable/copyable on every platform.

    def _mode_text(self):
        mode = "DEG" if self.angle_mode == "deg" else "RAD"
        mem = "  |  M" if self.memory_active else ""
        return f"{mode}{mem}"

    def _refresh_display(self):
        self.mode_label.configure(text=self._mode_text())

    # ================================================================
    # TABS
    # ================================================================
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self, fg_color=PANEL_BG, segmented_button_fg_color=PANEL_BG,
            segmented_button_selected_color=ACCENT_BLUE,
            segmented_button_selected_hover_color=ACCENT_BLUE_HOVER,
            segmented_button_unselected_color=CARD_BG,
            corner_radius=14,
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        self.tabview.add("Basic")
        self.tabview.add("Trigonometric")
        self.tabview.add("Logarithm")
        self.tabview.add("Constants & Memory")

        self._build_basic_tab(self.tabview.tab("Basic"))
        self._build_trig_tab(self.tabview.tab("Trigonometric"))
        self._build_log_tab(self.tabview.tab("Logarithm"))
        self._build_const_mem_tab(self.tabview.tab("Constants & Memory"))

    # ---------------------------------------------------------- key factory
    def _make_key(self, master, text, command, kind="normal"):
        colors = {
            "normal": (KEY_BG, KEY_HOVER, TEXT_MAIN),
            "accent": (ACCENT_BLUE, ACCENT_BLUE_HOVER, "#ffffff"),
            "warn": (ACCENT_ORANGE, ACCENT_ORANGE_HOVER, "#ffffff"),
            "dim": ("#26314a", "#31405f", TEXT_DIM),
        }
        fg, hover, txt = colors.get(kind, colors["normal"])
        btn = ctk.CTkButton(
            master, text=text, command=command,
            fg_color=fg, hover_color=hover, text_color=txt,
            corner_radius=10, font=ctk.CTkFont(size=15),
            height=44,
        )
        return btn

    def _grid_keys(self, master, layout, start_row=0):
        """layout: list of rows, each row a list of (label, command, kind).
        Returns a dict mapping label text -> created button widget."""
        created = {}
        n_cols = max(len(row) for row in layout)
        for c in range(n_cols):
            master.grid_columnconfigure(c, weight=1, uniform="col")
        for r, row in enumerate(layout):
            master.grid_rowconfigure(start_row + r, weight=1, uniform="row")
            for c, spec in enumerate(row):
                if spec is None:
                    continue
                label, command, kind = spec
                btn = self._make_key(master, label, command, kind)
                btn.grid(row=start_row + r, column=c, sticky="nsew", padx=5, pady=5)
                created[label] = btn
        return created

    # ================================================================
    # BASIC TAB
    # ================================================================
    def _build_basic_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        grid = ctk.CTkFrame(tab, fg_color="transparent")
        grid.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        A = self._append   # shorthand: append text to expression
        layout = [
            [("2nd", self._noop, "dim"), ("\u03c0", lambda: A("pi"), "normal"),
             ("e", lambda: A("e"), "normal"), ("(", lambda: A("("), "normal"),
             (")", lambda: A(")"), "normal"), ("%", lambda: A("%"), "normal"),
             ("\u232b", self._backspace, "normal")],

            [("sin", lambda: A("sin("), "normal"), ("cos", lambda: A("cos("), "normal"),
             ("tan", lambda: A("tan("), "normal"), ("sin\u207b\u00b9", lambda: A("asin("), "normal"),
             ("cos\u207b\u00b9", lambda: A("acos("), "normal"), ("tan\u207b\u00b9", lambda: A("atan("), "normal"),
             (self._angle_btn_label(), self._toggle_angle_mode, "dim")],

            [("log", lambda: A("log("), "normal"), ("ln", lambda: A("ln("), "normal"),
             ("10\u02e3", lambda: A("10^"), "normal"), ("e\u02e3", lambda: A("exp("), "normal"),
             ("x\u00b2", lambda: A("^2"), "normal"), ("x\u02b8", lambda: A("^"), "normal"),
             ("\u221a", lambda: A("sqrt("), "normal")],

            [("\u00b3\u221a", lambda: A("cbrt("), "normal"), ("1/x", self._reciprocal, "normal"),
             ("|x|", lambda: A("abs("), "normal"), ("n!", lambda: A("!"), "normal"),
             ("(\u2212)", self._toggle_sign, "normal"), ("C", self._clear_entry, "dim"),
             ("AC", self._all_clear, "warn")],

            [("7", lambda: A("7"), "normal"), ("8", lambda: A("8"), "normal"),
             ("9", lambda: A("9"), "normal"), ("\u00f7", lambda: A("/"), "normal"),
             ("\u00d7", lambda: A("*"), "normal"), ("MC", self._mem_clear, "dim"), None],

            [("4", lambda: A("4"), "normal"), ("5", lambda: A("5"), "normal"),
             ("6", lambda: A("6"), "normal"), ("\u2212", lambda: A("-"), "normal"),
             ("+", lambda: A("+"), "normal"), ("MR", self._mem_recall, "dim"), None],

            [("1", lambda: A("1"), "normal"), ("2", lambda: A("2"), "normal"),
             ("3", lambda: A("3"), "normal"), ("=", self._equals, "accent"),
             ("M\u2212", self._mem_subtract, "dim"), ("M+", self._mem_add, "dim"), None],

            [("0", lambda: A("0"), "normal"), (".", lambda: A("."), "normal"),
             ("+/\u2212", self._toggle_sign, "normal"), None,
             ("MS", self._mem_store, "dim"), None, None],
        ]
        created_buttons = self._grid_keys(grid, layout)
        self.equals_button = created_buttons.get("=")

    def _angle_btn_label(self):
        return "Deg \u25be" if self.angle_mode == "deg" else "Rad \u25be"

    def _toggle_angle_mode(self):
        self.angle_mode = "rad" if self.angle_mode == "deg" else "deg"
        self._refresh_display()

    # ================================================================
    # TRIGONOMETRIC TAB
    # ================================================================
    def _build_trig_tab(self, tab):
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 8), pady=4)
        ctk.CTkLabel(left, text="Trigonometric Functions", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))

        grid = ctk.CTkFrame(left, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=12, pady=8)

        A = self._append
        base_rows = [
            [("sin", lambda: A("sin("), "normal"), ("cos", lambda: A("cos("), "normal"), ("tan", lambda: A("tan("), "normal")],
            [("sin\u207b\u00b9", lambda: A("asin("), "normal"), ("cos\u207b\u00b9", lambda: A("acos("), "normal"), ("tan\u207b\u00b9", lambda: A("atan("), "normal")],
        ]
        hyp_rows = [
            [("sinh", lambda: A("sinh("), "normal"), ("cosh", lambda: A("cosh("), "normal"), ("tanh", lambda: A("tanh("), "normal")],
            [("sinh\u207b\u00b9", lambda: A("asinh("), "normal"), ("cosh\u207b\u00b9", lambda: A("acosh("), "normal"), ("tanh\u207b\u00b9", lambda: A("atanh("), "normal")],
        ]
        self._grid_keys(grid, base_rows + hyp_rows)

        right = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 4), pady=4)

        ctk.CTkLabel(right, text="Angle Unit", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 4))
        self.angle_menu = ctk.CTkOptionMenu(
            right, values=["Degrees (DEG)", "Radians (RAD)"],
            command=self._on_angle_menu, fg_color=KEY_BG,
            button_color=KEY_BG, button_hover_color=KEY_HOVER,
        )
        self.angle_menu.pack(fill="x", padx=16, pady=(0, 14))

        hyp_row = ctk.CTkFrame(right, fg_color="transparent")
        hyp_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(hyp_row, text="Hyperbolic", text_color=TEXT_MAIN).pack(side="left")
        self.hyp_switch = ctk.CTkSwitch(hyp_row, text="", command=self._toggle_hyperbolic,
                                         progress_color=ACCENT_BLUE)
        self.hyp_switch.pack(side="right")
        self.hyp_switch.select()  # matches screenshot default (on)

        ctk.CTkLabel(right, text="Other", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(4, 4))
        other_grid = ctk.CTkFrame(right, fg_color="transparent")
        other_grid.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        other_rows = [
            [("\u03c0", lambda: A("pi"), "normal"), ("\u03c0/2", lambda: A("(pi/2)"), "normal")],
            [("\u03c0/3", lambda: A("(pi/3)"), "normal"), ("\u03c0/4", lambda: A("(pi/4)"), "normal")],
        ]
        self._grid_keys(other_grid, other_rows)

    def _on_angle_menu(self, choice):
        self.angle_mode = "deg" if "DEG" in choice else "rad"
        self._refresh_display()

    def _toggle_hyperbolic(self):
        self.hyperbolic = bool(self.hyp_switch.get())

    # ================================================================
    # LOGARITHM TAB
    # ================================================================
    def _build_log_tab(self, tab):
        tab.grid_columnconfigure(0, weight=3)
        tab.grid_columnconfigure(1, weight=2)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 8), pady=4)
        ctk.CTkLabel(left, text="Logarithm Functions", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))
        grid = ctk.CTkFrame(left, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=12, pady=8)

        A = self._append
        rows = [
            [("log", lambda: A("log("), "normal"), ("ln", lambda: A("ln("), "normal"),
             ("10\u02e3", lambda: A("10^"), "normal"), ("e\u02e3", lambda: A("exp("), "normal")],
            [("log\u2081\u2080( )", lambda: A("log("), "normal"), ("ln( )", lambda: A("ln("), "normal"),
             ("10\u02e3( )", lambda: A("10^("), "normal"), ("e\u02e3( )", lambda: A("exp("), "normal")],
        ]
        self._grid_keys(grid, rows)
        ctk.CTkLabel(left, text="Use log(x, base) for a custom-base logarithm, e.g. log(8,2)",
                     text_color=TEXT_DIM, font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(0, 12))

        right = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 4), pady=4)
        ctk.CTkLabel(right, text="Additional", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))
        add_grid = ctk.CTkFrame(right, fg_color="transparent")
        add_grid.pack(fill="both", expand=False, padx=12, pady=(0, 8))
        add_rows = [
            [("x\u02b8", lambda: A("^"), "normal"), ("x\u00b2", lambda: A("^2"), "normal"), ("x\u00b3", lambda: A("^3"), "normal")],
            [("\u00b3\u221a", lambda: A("cbrt("), "normal"), ("\u221a", lambda: A("sqrt("), "normal"), ("\u207f\u221a", lambda: A("^(1/"), "normal")],
        ]
        self._grid_keys(add_grid, add_rows)

        ctk.CTkLabel(right, text="Base", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(12, 4))
        self.base_menu = ctk.CTkOptionMenu(
            right, values=["10 (Common Log)", "2 (Binary Log)", "e (Natural Log)"],
            command=self._on_base_menu, fg_color=KEY_BG,
            button_color=KEY_BG, button_hover_color=KEY_HOVER,
        )
        self.base_menu.pack(fill="x", padx=16, pady=(0, 16))

    def _on_base_menu(self, choice):
        self.log_base_value = choice.split()[0]

    # ================================================================
    # CONSTANTS & MEMORY TAB
    # ================================================================
    def _build_const_mem_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_columnconfigure(2, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        # ---- Memory Functions ----
        mem_frame = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        mem_frame.grid(row=0, column=0, sticky="nsew", padx=(4, 6), pady=4)
        ctk.CTkLabel(mem_frame, text="Memory Functions", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))
        mem_buttons = [
            ("MC", "Clear Memory", self._mem_clear),
            ("MR", "Recall Memory", self._mem_recall),
            ("M+", "Add to Memory", self._mem_add),
            ("M\u2212", "Subtract from Memory", self._mem_subtract),
            ("MS", "Store in Memory", self._mem_store),
        ]
        for code, label, cmd in mem_buttons:
            row = ctk.CTkFrame(mem_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=4)
            btn = ctk.CTkButton(row, text=code, width=50, command=cmd,
                                 fg_color=KEY_BG, hover_color=KEY_HOVER, text_color=TEXT_MAIN,
                                 corner_radius=8)
            btn.pack(side="left")
            ctk.CTkLabel(row, text=label, text_color=TEXT_DIM).pack(side="left", padx=10)

        # ---- Constants (table) ----
        const_frame = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        const_frame.grid(row=0, column=1, sticky="nsew", padx=6, pady=4)
        ctk.CTkLabel(const_frame, text="Constants", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))
        for sym, name, val in CONSTANT_TABLE:
            row = ctk.CTkFrame(const_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=sym, width=28, text_color=ACCENT_BLUE,
                         font=ctk.CTkFont(weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=name, text_color=TEXT_DIM, anchor="w").pack(side="left", padx=6)
            ctk.CTkLabel(row, text=val, text_color=TEXT_MAIN, anchor="e").pack(side="right")

        # ---- Common Constants (quick insert) ----
        quick_frame = ctk.CTkFrame(tab, fg_color=CARD_BG, corner_radius=12)
        quick_frame.grid(row=0, column=2, sticky="nsew", padx=(6, 4), pady=4)
        ctk.CTkLabel(quick_frame, text="Common Constants", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_MAIN).pack(anchor="w", padx=16, pady=(14, 8))
        quick_items = [
            ("\u03c0", "Pi", lambda: self._append("pi")),
            ("e", "Euler's number", lambda: self._append("e")),
            ("\u03c6", "Golden ratio", lambda: self._append(PHI.to_string(20))),
            ("c", "Speed of light", lambda: self._append(C_LIGHT.to_string(20))),
            ("G", "Gravitational constant", lambda: self._append(G.to_string(20))),
        ]
        for sym, name, cmd in quick_items:
            btn = ctk.CTkButton(quick_frame, text=f"{sym}   {name}", command=cmd,
                                 fg_color=KEY_BG, hover_color=KEY_HOVER, text_color=TEXT_MAIN,
                                 corner_radius=8, anchor="w")
            btn.pack(fill="x", padx=12, pady=4)

    # ================================================================
    # INPUT HANDLING
    # ================================================================
    def _append(self, text):
        # insert at the current cursor position, like a real text field
        self.expr_entry.insert("insert", text)
        self.expr_entry.focus_set()

    def _backspace(self):
        pos = self.expr_entry.index("insert")
        if pos > 0:
            self.expr_entry.delete(pos - 1, pos)

    def _clear_entry(self):
        self.expr_var.set("")

    def _all_clear(self):
        self.expr_var.set("")
        self.timing_label.configure(text="")
        self._show_result_text("0", "")

    def _toggle_sign(self):
        current = self.expr_var.get()
        if current.startswith("-"):
            self.expr_var.set(current[1:])
        else:
            self.expr_var.set("-" + current)

    def _reciprocal(self):
        current = self.expr_var.get()
        if current:
            self.expr_var.set(f"1/({current})")

    def _noop(self):
        pass

    # ---------------- evaluation (background thread, cancellable) --------
    def _equals(self):
        expr_text = self.expr_var.get()
        if not expr_text.strip():
            return
        if getattr(self, "_calc_thread", None) and self._calc_thread.is_alive():
            return  # a calculation is already running

        bignum100.CANCEL_EVENT.clear()
        self._calc_result = {}
        self._set_processing_ui(True)

        def worker():
            try:
                start = time.perf_counter()
                result = evaluate(expr_text, angle_mode=self.angle_mode)
                elapsed = time.perf_counter() - start
                self._calc_result["result"] = result
                self._calc_result["elapsed"] = elapsed
            except bignum100.CalculationCancelled:
                self._calc_result["cancelled"] = True
            except (EvalError, ZeroDivisionError, ValueError) as e:
                self._calc_result["error"] = str(e)
            except Exception:
                self._calc_result["error"] = "Unexpected error"
                traceback.print_exc()

        self._calc_thread = threading.Thread(target=worker, daemon=True)
        self._calc_thread.start()
        self.after(30, self._poll_calc_thread)

    def _poll_calc_thread(self):
        if self._calc_thread.is_alive():
            self.after(30, self._poll_calc_thread)
            return

        self._set_processing_ui(False)
        data = self._calc_result

        if "cancelled" in data:
            self.timing_label.configure(text="Calculation cancelled")
            self._show_result_text("Cancelled", "", is_error=True)
        elif "error" in data:
            self.timing_label.configure(text=data["error"])
            self._show_result_text("Error", "", is_error=True)
        else:
            result = data["result"]
            elapsed = data["elapsed"]
            self.last_answer = result
            full_text = result.to_string(30)
            sci_text = result.to_scientific(20)
            self.timing_label.configure(text=f"Computed in {elapsed * 1000:.3f} ms")
            self._show_result_text(full_text, sci_text)

    def _cancel_calculation(self):
        bignum100.CANCEL_EVENT.set()

    def _set_processing_ui(self, processing):
        if processing:
            self.timing_label.configure(text="Processing...")
            self.cancel_button.pack(side="right", padx=(0, 10))
            if hasattr(self, "equals_button"):
                self.equals_button.configure(state="disabled")
        else:
            self.cancel_button.pack_forget()
            if hasattr(self, "equals_button"):
                self.equals_button.configure(state="normal")

    # ---------------- memory ----------------
    def _current_value_or_answer(self):
        """Try to evaluate the current expression; fall back to last answer."""
        expr_text = self.expr_var.get()
        if expr_text.strip():
            try:
                return evaluate(expr_text, angle_mode=self.angle_mode)
            except Exception:
                pass
        return self.last_answer

    def _mem_store(self):
        self.memory_value = self._current_value_or_answer()
        self.memory_active = True
        self._refresh_display()

    def _mem_recall(self):
        self.expr_entry.insert("insert", self.memory_value.to_string(15))

    def _mem_clear(self):
        self.memory_value = Decimal100.zero()
        self.memory_active = False
        self._refresh_display()

    def _mem_add(self):
        self.memory_value = self.memory_value.add(self._current_value_or_answer())
        self.memory_active = True
        self._refresh_display()

    def _mem_subtract(self):
        self.memory_value = self.memory_value.sub(self._current_value_or_answer())
        self.memory_active = True
        self._refresh_display()


def main():
    app = ScientificCalculator()
    app.mainloop()


if __name__ == "__main__":
    main()
