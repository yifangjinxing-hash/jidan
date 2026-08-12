from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from ninelights_demo import NineLightsHost


LEVEL_LABELS = {
    "十字 · 入门": "cross",
    "双角 · 进阶": "corners",
    "满灯 · 挑战": "full",
}
LEVEL_NAMES = {level_id: label for label, level_id in LEVEL_LABELS.items()}
SOLUTIONS = {
    "cross": (4,),
    "corners": (0, 8),
    "full": (0, 2, 4, 6, 8),
}


def bundled_asset(name: str) -> Path:
    """Resolve a checked-in asset both from source and a PyInstaller bundle."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root) / name
    return Path(__file__).resolve().parents[1] / "docs" / "assets" / name


def run_self_test() -> int:
    """Exercise all fixed solutions without importing Tkinter or creating a window."""

    host = NineLightsHost()
    completed: list[dict[str, Any]] = []
    expected_receipts = 0
    try:
        for level_id, moves in SOLUTIONS.items():
            state = host.start(level_id)
            expected_receipts += 1
            for cell in moves:
                state = host.press(state, cell)
                expected_receipts += 1
            summary = host.summary(state)
            if state["status"] != "won":
                raise AssertionError(f"{level_id} did not reach won")
            if state["cells"] != [0] * 9:
                raise AssertionError(f"{level_id} did not turn every light off")
            if state["moveCount"] != len(moves):
                raise AssertionError(
                    f"{level_id} expected {len(moves)} moves, "
                    f"got {state['moveCount']}"
                )
            if summary["receiptCount"] != expected_receipts:
                raise AssertionError(
                    f"{level_id} expected {expected_receipts} receipts, "
                    f"got {summary['receiptCount']}"
                )
            if not summary["receiptChainVerified"]:
                raise AssertionError(f"{level_id} receipt chain did not verify")
            last_hash = summary["lastReceiptHash"]
            if not isinstance(last_hash, str) or len(last_hash) != 64:
                raise AssertionError(f"{level_id} did not produce a receipt hash")
            completed.append(
                {
                    "levelId": level_id,
                    "moves": len(moves),
                    "status": state["status"],
                }
            )
    except Exception as exc:
        print(f"Nine Lights GUI self-test failed: {exc}", file=sys.stderr)
        return 1

    receipts = host.runtime.receipts.all()
    if any(
        receipt["status"] != "succeeded" or receipt["effect"] != "read"
        for receipt in receipts
    ):
        print("Nine Lights GUI self-test failed: invalid receipt", file=sys.stderr)
        return 1

    final_summary = host.summary(state)
    print(
        json.dumps(
            {
                "ok": True,
                "host": "NineLightsHost",
                "runtimePath": "TaskPlan -> Grant -> Runtime -> Receipt",
                "levels": completed,
                "receiptCount": final_summary["receiptCount"],
                "receiptChainVerified": final_summary["receiptChainVerified"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


class NineLightsApp:
    """Windows-friendly Tkinter surface over the existing trusted game Host."""

    BACKGROUND = "#0b1518"
    PANEL = "#142226"
    PANEL_LIGHT = "#1d3035"
    TEXT = "#f7f3e6"
    MUTED = "#9eb0b3"
    ACCENT = "#6ee7c2"
    LIGHT_ON = "#ffd15c"
    LIGHT_ON_ACTIVE = "#ffe196"
    LIGHT_OFF = "#2a3b40"
    LIGHT_OFF_ACTIVE = "#344a50"

    def __init__(self) -> None:
        # Delayed imports keep --self-test usable on headless/minimal Python builds.
        import tkinter as tk
        from tkinter import messagebox, ttk

        self.tk = tk
        self.messagebox = messagebox
        self.ttk = ttk
        self.host = NineLightsHost()
        self.state: Mapping[str, Any] | None = None

        self.root = tk.Tk()
        self.root.title("九灯")
        try:
            self.root.iconbitmap(default=str(bundled_asset("ninelights-icon.ico")))
        except tk.TclError:
            # A missing/unreadable icon must never prevent the game from opening.
            pass
        self.root.configure(background=self.BACKGROUND)
        window_width = min(680, max(520, self.root.winfo_screenwidth() - 48))
        window_height = min(720, max(620, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(520, 620)

        self.level_var = tk.StringVar(value=LEVEL_NAMES["cross"])
        self.move_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="准备中")
        self.receipt_var = tk.StringVar(value="操作记录准备中")
        self.capability_var = tk.StringVar(value="完全离线运行 · 不联网 · 不上传数据")
        self.cell_buttons: list[Any] = []

        self._configure_styles()
        self._build_ui()
        self.root.bind_all("<KeyPress>", self._on_keypress)
        self._start_level("cross")

    def _configure_styles(self) -> None:
        style = self.ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self.tk.TclError:
            pass
        style.configure(
            "NineLights.TCombobox",
            foreground=self.TEXT,
            fieldbackground=self.PANEL_LIGHT,
            background=self.PANEL_LIGHT,
            bordercolor=self.PANEL_LIGHT,
            arrowcolor=self.TEXT,
            padding=8,
        )
        style.map(
            "NineLights.TCombobox",
            fieldbackground=[("readonly", self.PANEL_LIGHT)],
            foreground=[("readonly", self.TEXT)],
            selectbackground=[("readonly", self.PANEL_LIGHT)],
            selectforeground=[("readonly", self.TEXT)],
        )

    def _build_ui(self) -> None:
        tk = self.tk
        outer = tk.Frame(self.root, bg=self.BACKGROUND, padx=26, pady=14)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="离线小游戏 · NINE LIGHTS",
            bg=self.BACKGROUND,
            fg=self.ACCENT,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            outer,
            text="九灯",
            bg=self.BACKGROUND,
            fg=self.TEXT,
            font=("Microsoft YaHei UI", 30, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            outer,
            text="按下一格会翻转它自己和上下左右的灯。让九盏灯全部熄灭即可获胜。",
            bg=self.BACKGROUND,
            fg=self.MUTED,
            justify="left",
            wraplength=610,
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(0, 10))

        control_panel = tk.Frame(outer, bg=self.PANEL, padx=14, pady=10)
        control_panel.pack(fill="x", pady=(0, 10))
        control_panel.columnconfigure(0, weight=1)

        tk.Label(
            control_panel,
            text="选择关卡",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.level_select = self.ttk.Combobox(
            control_panel,
            state="readonly",
            values=tuple(LEVEL_LABELS),
            textvariable=self.level_var,
            style="NineLights.TCombobox",
            font=("Microsoft YaHei UI", 10),
        )
        self.level_select.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.level_select.bind("<<ComboboxSelected>>", self._on_level_selected)

        restart = tk.Button(
            control_panel,
            text="重新开始",
            command=self._restart,
            bg=self.PANEL_LIGHT,
            activebackground="#294148",
            fg=self.TEXT,
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            padx=18,
            pady=7,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        restart.grid(row=1, column=1, sticky="e")

        board = tk.Frame(outer, bg=self.BACKGROUND)
        board.pack(fill="both", expand=True)
        for row in range(3):
            board.rowconfigure(row, weight=1, uniform="board")
            board.columnconfigure(row, weight=1, uniform="board")
        for cell in range(9):
            button = tk.Button(
                board,
                command=lambda selected=cell: self._press(selected),
                text=str(cell + 1),
                bg=self.LIGHT_OFF,
                activebackground=self.LIGHT_OFF_ACTIVE,
                fg=self.MUTED,
                activeforeground=self.TEXT,
                disabledforeground="#5d6a6d",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Microsoft YaHei UI", 20, "bold"),
                takefocus=True,
            )
            row, column = divmod(cell, 3)
            button.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            self.cell_buttons.append(button)

        summary = tk.Frame(outer, bg=self.PANEL, padx=14, pady=10)
        summary.pack(fill="x", pady=(10, 0))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)

        self._metric(summary, "步数", self.move_var, 0, "w")
        self._metric(summary, "状态", self.status_var, 1, "e")
        tk.Label(
            summary,
            textvariable=self.receipt_var,
            bg=self.PANEL,
            fg=self.ACCENT,
            anchor="w",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 3))
        tk.Label(
            summary,
            textvariable=self.capability_var,
            bg=self.PANEL,
            fg=self.MUTED,
            anchor="w",
            justify="left",
            wraplength=590,
            font=("Consolas", 8),
        ).grid(row=3, column=0, columnspan=2, sticky="ew")

        tk.Label(
            outer,
            text="鼠标点击，或用键盘 1–9 翻灯。游戏完全离线，每次操作只在本机处理。",
            bg=self.BACKGROUND,
            fg=self.MUTED,
            justify="left",
            wraplength=610,
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(8, 0))

    def _metric(self, parent: Any, title: str, variable: Any, column: int, anchor: str) -> None:
        tk = self.tk
        frame = tk.Frame(parent, bg=self.PANEL)
        frame.grid(row=0, column=column, sticky="ew")
        tk.Label(
            frame,
            text=title,
            bg=self.PANEL,
            fg=self.MUTED,
            anchor=anchor,
            font=("Microsoft YaHei UI", 8),
        ).pack(fill="x")
        tk.Label(
            frame,
            textvariable=variable,
            bg=self.PANEL,
            fg=self.TEXT,
            anchor=anchor,
            font=("Microsoft YaHei UI", 15, "bold"),
        ).pack(fill="x")

    def _on_level_selected(self, _event: Any = None) -> None:
        self._start_level(LEVEL_LABELS[self.level_var.get()])

    def _restart(self) -> None:
        self._start_level(LEVEL_LABELS[self.level_var.get()])

    def _start_level(self, level_id: str) -> None:
        try:
            self.state = self.host.start(level_id)
        except Exception as exc:
            self._show_error(exc)
            return
        self.level_var.set(LEVEL_NAMES[level_id])
        self.capability_var.set("本地游戏已开始")
        self._render()

    def _press(self, cell: int) -> None:
        if self.state is None or self.state["status"] == "won":
            return
        try:
            self.state = self.host.press(self.state, cell)
        except Exception as exc:
            self._show_error(exc)
            return
        self.capability_var.set(f"已记录第 {cell + 1} 格操作")
        self._render()
        if self.state["status"] == "won":
            winning_move_count = self.state["moveCount"]
            self.root.after(
                80,
                lambda moves=winning_move_count: self.messagebox.showinfo(
                    "过关啦！",
                    f"九盏灯已经全部熄灭。\n你用了 {moves} 步。",
                    parent=self.root,
                ),
            )

    def _render(self) -> None:
        if self.state is None:
            return
        won = self.state["status"] == "won"
        for cell, value in enumerate(self.state["cells"]):
            button = self.cell_buttons[cell]
            if value:
                button.configure(
                    text=f"●  {cell + 1}",
                    bg=self.LIGHT_ON,
                    activebackground=self.LIGHT_ON_ACTIVE,
                    fg="#352400",
                    activeforeground="#352400",
                )
            else:
                button.configure(
                    text=f"○  {cell + 1}",
                    bg=self.LIGHT_OFF,
                    activebackground=self.LIGHT_OFF_ACTIVE,
                    fg=self.MUTED,
                    activeforeground=self.TEXT,
                )
            button.configure(state="disabled" if won else "normal")

        self.move_var.set(str(self.state["moveCount"]))
        self.status_var.set("已完成" if won else "进行中")
        summary = self.host.summary(self.state)
        chain_text = "本次游戏记录正常" if summary["receiptChainVerified"] else "本次游戏记录异常"
        hash_prefix = summary["lastReceiptHash"][:12] if summary["lastReceiptHash"] else "无"
        self.receipt_var.set(
            f"{chain_text} · {summary['receiptCount']} 条 · {hash_prefix}…"
        )

    def _on_keypress(self, event: Any) -> None:
        if event.char in "123456789":
            self._press(int(event.char) - 1)

    def _show_error(self, exc: Exception) -> None:
        self.status_var.set("动作被拒绝")
        self.messagebox.showerror(
            "这一步没成功",
            f"请重新开始本关后再试。\n\n详细信息：{exc}",
            parent=self.root,
        )

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Play Nine Lights through JCL Runtime in a local Tkinter window."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="solve all fixed levels without creating a GUI window",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test()

    try:
        app = NineLightsApp()
    except Exception as exc:
        print(f"Unable to start Nine Lights GUI: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
