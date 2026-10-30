"""스킬 창 실행기: pythonw launch.py <명령>

AutoCAD 명령(bc_autocad.lsp의 startapp)과 MCP(open_skill)가 이 파일로 창을 띄운다.
- 바로 찍는 명령(kind=lisp): 설정 창
- 창 명령(kind=window): skills/windows/<명령>.py 의 main(), MPL은 skills/multi_plot
"""

import importlib
import os
import sys

sys.dont_write_bytecode = True  # 패키지 폴더(동기화 폴더일 수 있음)에 __pycache__를 만들지 않는다
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skills import registry  # noqa: E402
from skills.common import ui  # noqa: E402


ON, OFF = "☑", "☐"


class HelpWindow(ui.BaseWindow):
    """BCHELP: 명령 목록. 두 번 누르면 그 명령의 창(바로 찍는 명령은 설정 창)을 연다.
    명령은 기본으로 BC를 붙인 이름(BCFE)만 쓴다. 첫 칸을 누르면 BC 없는 짧은 이름(FE)을 켜고 끈다.
    켤 때 이 PC에서 같은 이름을 이미 쓰고 있으면(단축키 파일·프로그램 명령·다른 리습) 먼저 묻는다."""

    def __init__(self):
        import tkinter as tk
        from tkinter import ttk
        from skills.common import settings as S
        from skills.common.acad import Acad
        super().__init__("BCHELP", "명령 목록", size="900x660")
        self.S = S
        self.acad = Acad()
        self.short = [n for n in S.load_short() if n in registry.COMMANDS]
        top = tk.Frame(self, bg=ui.BG)
        top.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(top, text="첫 칸 ☑: 단축 이름(FE)도 함께 사용합니다. 기본값은 BC 접두어 이름(BCFE)만 사용합니다.", bg=ui.BG, fg=ui.FG,
                 font=ui.FONT).pack(side="left")
        tk.Button(top, text="모두 해제 (BC 이름만)", command=self.all_off, bg="#383A3E", fg="#FFFFFF",
                  relief="flat").pack(side="right", padx=4)
        tk.Button(top, text="모두 활성화 (단축 이름 포함)", command=self.all_on, bg="#3E5879", fg="#FFFFFF",
                  relief="flat").pack(side="right", padx=4)
        frame = tk.Frame(self, bg=ui.PANEL)
        frame.pack(fill="both", expand=True, padx=10, pady=8)
        cols = ("short", "cmd", "title", "kind", "desc")
        self.tree = tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, t, w in (("short", "단축 이름", 70), ("cmd", "명령", 80), ("title", "이름", 190), ("kind", "방식", 70),
                        ("desc", "설명", 460)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center" if c == "short" else "w", stretch=(c == "desc"))
        group = None
        for k, v in registry.COMMANDS.items():
            if v["group"] != group:
                group = v["group"]
                tree.insert("", "end", values=("", "", "── " + group, "", ""))
            tree.insert("", "end", iid=k, values=(self.mark(k), "BC" + k, v["title"],
                                                  "대화상자" if v["kind"] == "window" else "도면 선택", v["desc"]))
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.bind("<Button-1>", self.on_click)
        tree.bind("<Double-1>", lambda e: None if tree.identify_column(e.x) == "#1" else self.open_cmd(tree.focus()))
        self.status("AutoCAD 명령줄에 BCFE처럼 BC를 붙여 입력합니다. 단축 이름을 활성화한 명령은 FE로도 실행됩니다. "
                    "더블 클릭하면 해당 명령의 대화상자 또는 설정이 열립니다. 전체 해제는 AutoCAD에서 BCOFF 명령으로도 가능합니다.")

    def mark(self, k):
        return ON if k in self.short else OFF

    def on_click(self, e):
        k = self.tree.identify_row(e.y)
        if self.tree.identify_column(e.x) == "#1" and k in registry.COMMANDS:
            self.change([n for n in self.short if n != k] if k in self.short else self.short + [k])

    def all_on(self):
        self.change(list(registry.COMMANDS))

    def all_off(self):
        self.change([])

    def change(self, new):
        """짧은 이름 목록을 new로 바꾼다. 새로 켜는 이름이 이 PC에서 이미 쓰이면 한 번 묻는다.
        저장한 뒤 지금 AutoCAD 도면에 바로 적용한다(이미 열린 다른 도면은 다시 열 때)."""
        from tkinter import messagebox
        new = [k for k in registry.COMMANDS if k in new]  # 목록 순서로
        added = [k for k in new if k not in self.short]
        cad_ok = True
        if added:
            try:
                rows = self.acad.lisp('(foreach _p (bc:short-conflicts (list %s)) (write-line (strcat (car _p) _d'
                                      ' (cadr _p) _d (caddr _p)) _fp))' % " ".join('"%s"' % k for k in added), 60)
            except Exception as e:  # noqa: BLE001 — 연결 실패·리습 오류 모두 사람에게 묻는다
                cad_ok, rows = False, []
                if not messagebox.askyesno(self.cmd, "AutoCAD에 연결하지 못해 이름 중복 여부를 확인하지 못했습니다.\n(%s)\n\n"
                                           "계속 활성화하시겠습니까? 활성화하면 AutoCAD에서 도면을 다시 열 때 적용됩니다." % e,
                                           parent=self):
                    return
            if rows:
                hits = [r.split("\t") for r in rows]
                lines = "\n".join("  %s — %s" % (h[1], h[2]) for h in hits[:15])
                more = "\n  … 외 %d개" % (len(hits) - 15) if len(hits) > 15 else ""
                if not messagebox.askyesno(
                        self.cmd, "다음 이름은 이 PC에서 이미 사용 중입니다:\n%s%s\n\n활성화하면 기존 명령 대신 이 패키지의 "
                                  "명령이 실행됩니다. 계속 활성화하시겠습니까?\n(해제하면 기존 명령이 복원됩니다. 모두 해제: BCOFF)"
                                  % (lines, more), parent=self):
                    return
        self.S.save_short(new)
        self.short = new
        for k in registry.COMMANDS:
            self.tree.set(k, "short", self.mark(k))
        msg = "단축 이름 %d개가 활성화되었습니다. " % len(new)
        if cad_ok:
            try:
                self.acad.lisp('(bc:short-apply) (write-line "ok" _fp)', 60)
                msg += "현재 도면에 적용했습니다(이미 열려 있는 다른 도면은 다시 열 때 적용됩니다)."
            except Exception as e:  # noqa: BLE001
                msg += "AutoCAD에 적용하지 못했습니다. 도면을 다시 열면 적용됩니다. (%s)" % e
        else:
            msg += "AutoCAD에서 도면을 다시 열면 적용됩니다."
        self.status(msg)

    def open_cmd(self, cmd):
        import subprocess
        info = registry.COMMANDS.get(cmd)
        if not info or (info["kind"] == "lisp" and not info.get("fields")):
            return
        subprocess.Popen([sys.executable, os.path.abspath(__file__), cmd])


def main(argv):
    if len(argv) < 2:
        print("사용법: launch.py <명령>  (예: FE, CEX, MPL)")
        return 2
    cmd = argv[1].upper()
    if cmd == "BCHELP":
        ui.setup_logging("skill_BCHELP")
        HelpWindow().mainloop()
        return 0
    info = registry.COMMANDS.get(cmd)
    if not info:
        print("알 수 없는 명령: %s" % cmd)
        return 2
    ui.setup_logging("skill_" + cmd)
    if info["kind"] == "lisp":
        if not info.get("fields"):
            return 0
        ui.SettingsWindow(cmd, info, registry.defaults(cmd)).mainloop()
        return 0
    mod = "skills.multi_plot.multi_plot" if cmd == "MPL" else "skills.windows." + cmd.lower()
    importlib.import_module(mod).main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
