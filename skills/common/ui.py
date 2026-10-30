# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""스킬 창 공통 부품 — BC_TOOL 표준(작업표시줄 아이콘·AppID), 어두운 색, 설정 입력 폼.

창마다 AppUserModelID를 다르게 해 작업표시줄에서 섞이지 않게 한다.
"""

import base64
import ctypes
import logging
import os
import tkinter as tk
from tkinter import ttk, messagebox

from .icon_b64 import ICON_B64
from .paths import DATA, LOGS
from . import settings as S

VERSION_NUM = "0.2.0"  # 패키지 버전(install.py의 플러그인 AppVersion과 같게). 사용자 시험 전이라 0.x
VERSION = "BC." + VERSION_NUM

BG = "#1E1F22"
PANEL = "#25262A"
HEAD = "#313338"
FG = "#E8EAED"
ACCENT = "#F2C94C"
STATUS = "#A8C7FA"
ENTRY = "#2B2D30"
FONT = ("맑은 고딕", 9)
FONT_B = ("맑은 고딕", 9, "bold")


def setup_logging(name: str):
    logging.basicConfig(filename=os.path.join(LOGS, name + ".log"), level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8")


def app_id(name: str):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BC.%s.%s" % (name, VERSION_NUM))
    except Exception:
        pass


def apply_icon(win):
    """제목표시줄·작업표시줄 아이콘(다중 해상도 .ico를 Win32로 직접 붙인다)."""
    try:
        # PC별 폴더에 한 번만 쓰고 다시 쓴다(창마다 %TEMP%에 쌓이지 않게 —)
        path = os.path.join(DATA, "bc_icon.ico")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(base64.b64decode(ICON_B64))
        win.update_idletasks()
        u = ctypes.windll.user32
        hwnd = u.GetParent(win.winfo_id()) or win.winfo_id()
        hs = u.LoadImageW(0, path, 1, u.GetSystemMetrics(49), u.GetSystemMetrics(50), 0x10)
        hl = u.LoadImageW(0, path, 1, u.GetSystemMetrics(11), u.GetSystemMetrics(12), 0x10)
        if hs:
            u.SendMessageW(hwnd, 0x0080, 0, hs)
        if hl:
            u.SendMessageW(hwnd, 0x0080, 1, hl)
    except Exception as e:
        logging.warning("아이콘 적용 실패: %s", e)


def styles(win):
    st = ttk.Style(win)
    st.theme_use("clam")
    st.configure("TCombobox", fieldbackground=ENTRY, background="#383A3E", foreground="#FFFFFF")
    st.configure("Treeview", background=ENTRY, foreground=FG, fieldbackground=ENTRY, rowheight=24, font=FONT)
    st.configure("Treeview.Heading", background="#383A3E", foreground=ACCENT, font=FONT_B)


class BaseWindow(tk.Tk):
    """명령 창의 틀: 제목, 아이콘, 상태줄."""

    def __init__(self, cmd: str, title: str, size="520x600"):
        app_id("BC_" + cmd)
        super().__init__()
        self.cmd = cmd
        # 버전은 BCHELP 창 제목에만 쓴다(명령 창마다 쓰지 않음)
        self.title("%s  %s - %s" % (cmd, title, VERSION) if cmd == "BCHELP" else "%s  %s" % (cmd, title))
        self.geometry(size)
        self.configure(bg=BG)
        styles(self)
        apply_icon(self)
        self.var_status = tk.StringVar(value="")
        bar = tk.Frame(self, bg="#18191C")
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, textvariable=self.var_status, bg="#18191C", fg=STATUS, font=FONT, anchor="w").pack(
            fill="x", padx=8, pady=4)
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))

    def status(self, msg: str):
        self.var_status.set(msg)
        self.update_idletasks()

    def section(self, parent, text):
        hdr = tk.Frame(parent, bg=HEAD)
        hdr.pack(fill="x", pady=(8, 3))
        tk.Label(hdr, text="  " + text, bg=HEAD, fg=ACCENT, font=FONT_B, anchor="w").pack(fill="x", pady=3)

    def error(self, msg):
        logging.error(msg)
        messagebox.showerror(self.cmd, msg, parent=self)

    def in_cad(self, fn, *args, **kw):
        """CAD에서 사람이 고르게 할 때: 창을 내리고 AutoCAD를 앞으로, 끝나면 창을 다시 올린다.
        오류는 창에 보여 주고 None을 돌려준다."""
        from .acad import CadNotReady
        self.iconify()
        try:
            if getattr(self, "acad", None) is not None:
                self.acad.activate()
            return fn(*args, **kw)
        except CadNotReady as e:
            self.error(str(e))
        except Exception as e:  # noqa: BLE001 — 사람이 볼 창이므로 원문을 보인다
            logging.exception("CAD 작업 오류")
            self.error("%s: %s" % (type(e).__name__, e))
        finally:
            self.deiconify()
            self.lift()
        return None

    def form_section(self, parent, title, fields, values):
        self.section(parent, title)
        f = FieldForm(parent, fields, values)
        f.pack(fill="x")
        return f


class FieldForm(tk.Frame):
    """registry 설정 항목으로 입력 폼을 만든다. values()로 형식에 맞춘 값을 돌려준다."""

    def __init__(self, parent, fields, values):
        super().__init__(parent, bg=PANEL)
        self.fields = fields
        self.vars = {}
        for r, (k, label, typ, d, choices) in enumerate(fields):
            tk.Label(self, text=label, bg=PANEL, fg=FG, font=FONT, anchor="w", wraplength=260, justify="left").grid(
                row=r, column=0, sticky="w", padx=(8, 6), pady=2)
            v = values.get(k, d)
            if typ == "bool":
                var = tk.BooleanVar(value=bool(v))
                tk.Checkbutton(self, variable=var, bg=PANEL, activebackground=PANEL, selectcolor=ENTRY).grid(
                    row=r, column=1, sticky="w")
            elif typ == "choice":
                var = tk.StringVar(value=str(v))
                ttk.Combobox(self, textvariable=var, values=[str(c) for c in choices], state="readonly", width=16,
                             font=FONT).grid(row=r, column=1, sticky="w", pady=2)
            else:
                var = tk.StringVar(value=str(v))
                tk.Entry(self, textvariable=var, bg=ENTRY, fg="#FFFFFF", insertbackground="#FFFFFF", width=18,
                         font=FONT, relief="flat").grid(row=r, column=1, sticky="w", pady=2)
            self.vars[k] = (var, typ, d)
        self.columnconfigure(0, weight=1)

    def values(self) -> dict:
        out = {}
        for k, (var, typ, d) in self.vars.items():
            v = var.get()
            try:
                if typ == "bool":
                    out[k] = bool(v)
                elif typ == "int":
                    out[k] = int(float(v))
                elif typ == "real":
                    out[k] = float(v)
                elif typ == "choice":
                    out[k] = type(d)(v) if isinstance(d, (int, float)) and not isinstance(d, bool) else v
                else:
                    out[k] = v
            except ValueError:
                raise ValueError("'%s' 값이 숫자가 아닙니다: %s" % (k, v))
        return out


class SettingsWindow(BaseWindow):
    """LISP 명령의 설정(S) 창. 저장하면 같은 설정 파일을 LISP가 다음 실행 때 읽는다."""

    def __init__(self, cmd: str, info: dict, defaults: dict):
        super().__init__(cmd, info["title"] + " — 설정", size="560x%d" % min(860, 140 + 30 * len(info["fields"])))
        self.body = body = tk.Frame(self, bg=PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        tk.Label(body, text=info["desc"], bg=PANEL, fg=FG, font=FONT, wraplength=520, justify="left").pack(
            fill="x", padx=8, pady=(6, 2))
        self.form = FieldForm(body, info["fields"], S.load(cmd, defaults))
        self.form.pack(fill="both", expand=True, pady=4)
        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=10, pady=(0, 6))
        tk.Button(btns, text="저장", width=10, command=self.save, bg="#3E5879", fg="#FFFFFF", relief="flat").pack(
            side="right", padx=4)
        tk.Button(btns, text="기본값", width=10, command=lambda: self.reset(info, defaults), bg="#383A3E",
                  fg="#FFFFFF", relief="flat").pack(side="right", padx=4)
        self.status("저장한 뒤 AutoCAD에서 %s를 다시 실행하세요." % cmd)

    def save(self):
        try:
            p = S.save(self.cmd, self.form.values())
        except ValueError as e:
            self.error(str(e))
            return
        self.status("저장했습니다: %s" % p)
        self.after(600, self.destroy)

    def reset(self, info, defaults):
        self.form.destroy()
        self.form = FieldForm(self.body, info["fields"], defaults)
        self.form.pack(fill="both", expand=True, pady=4)
