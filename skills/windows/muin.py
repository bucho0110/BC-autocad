# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""MUIN 여러 도면 원래 좌표로 불러오기 — DWG·DXF 여러 개를 지금 도면에 원래 좌표 그대로 한 번에 넣는다.

- 각 도면을 화면 없는 AutoCAD(src/background.py)로 열어 기준점(INSBASE)을 읽고 고유한 이름의 임시 DWG로 저장한다
  (DXF도 이때 DWG가 된다. 사용자의 AutoCAD 화면은 그대로). 지금 도면에 같은 이름 블록이 있어도 섞이지 않는다.
- 그 기준점에 넣어 원래 좌표를 맞추고, 단위 자동 축척이 끼지 않게 INSUNITS를 잠깐 0으로 둔다.
- 폭파(기본): 넣은 뒤 풀어 원래 객체로 남기고 임시 블록 정의는 지운다. 폭파하지 않으면 파일 이름 블록으로 남긴다.
"""

import os
import shutil
import tempfile
import time
import tkinter as tk
from tkinter import filedialog

from skills.common import acad as A
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "MUIN"
EXTS = (".dwg", ".dxf")


def prepare(files, work):
    """[(원본 경로, 넣을 임시 DWG, 블록 이름 후보, 원래 기준점)] — 화면 없는 AutoCAD로 각 도면을 열어 기준점(INSBASE)을
    읽고 고유한 이름의 DWG로 저장한다(DXF도 이때 DWG가 된다). 파일 하나에 약 3초."""
    import background  # src
    out = []
    stamp = time.strftime("%Y%m%d%H%M%S")
    for f in files:
        if not os.path.isfile(f):
            raise FileNotFoundError("파일이 없습니다: %s" % f)
        if os.path.splitext(f)[1].lower() not in EXTS:
            raise ValueError("DWG·DXF만 불러올 수 있습니다: %s" % f)
    for i, f in enumerate(files):
        f = os.path.abspath(f)
        tmp = os.path.join(work, "BC_MUIN_%s_%d.dwg" % (stamp, i))
        r = background.build('(setq _ib (getvar "INSBASE")) (write-line (strcat "IB" _d (rtos (car _ib) 2 10) _d'
                             ' (rtos (cadr _ib) 2 10) _d (rtos (caddr _ib) 2 10)) _fp)',
                             tmp, base_drawing=f, use_skills=False, preview=False)
        ib = [float(v) for v in next(ln for ln in r["lines"] if ln.startswith("IB\t")).split("\t")[1:]]
        out.append((f, tmp, os.path.splitext(os.path.basename(f))[0], ib))
    return out


def insert_lisp(items, explode=True) -> str:
    """지금 도면에 items를 원래 좌표로 넣는 LISP. 결과 줄: F<탭>원본 파일<탭>넣은 객체 수(폭파 안 하면 1)."""
    s = ['(setq _doc (vla-get-ActiveDocument (vlax-get-acad-object)) _ms (vla-get-ModelSpace _doc)'
         ' _blks (vla-get-Blocks _doc) _iu (getvar "INSUNITS"))',
         '(setvar "INSUNITS" 0)']
    for src, tmp, stem, ib in items:
        # 파일을 블록으로 넣으면 객체가 원래 기준점(INSBASE) 기준으로 들어가므로 그 점에 넣어야 원래 좌표가 된다(실측).
        # InsertBlock은 경로 구분자로 역슬래시만 받는다 — 슬래시면 "키를 찾을 수 없음" 오류(실측). ls가 역슬래시를 이스케이프한다
        s.append('(setq _last (entlast) _ins (vla-InsertBlock _ms (vlax-3d-point %.10f %.10f %.10f) "%s" 1.0 1.0 1.0 0.0)'
                 ' _blk (vla-Item _blks (vla-get-Name _ins)))' % (ib[0], ib[1], ib[2], ls(os.path.abspath(tmp))))
        if explode:
            s.append('(vla-Explode _ins) (vla-Delete _ins) (vl-catch-all-apply (quote vla-Delete) (list _blk))'
                     ' (setq _n 0 _e _last) (while (setq _e (if _e (entnext _e) (entnext))) (setq _n (1+ _n)))')
        else:
            s.append('(if (not (tblsearch "BLOCK" "%s")) (vla-put-Name _blk "%s")) (setq _n 1)' % (ls(stem), ls(stem)))
        s.append('(write-line (strcat "F" _d "%s" _d (itoa _n)) _fp)' % ls(src))
    s.append('(setvar "INSUNITS" _iu)')
    return "\n".join(s)


def parse(rows):
    return [{"file": r.split("\t")[1], "entities": int(r.split("\t")[2])} for r in rows if r.startswith("F\t")]


def run_mcp(ctl, doc, lib, a, timeout_s):
    """skill_run("MUIN", files=[...], explode=true)"""
    files = a.get("files") or []
    if not files:
        raise ValueError("MUIN: files(불러올 DWG·DXF 경로 목록)가 필요합니다")
    work = tempfile.mkdtemp(prefix="bc_muin_")
    try:
        items = prepare(files, work)
        with ctl._undo_group(doc):
            rows = ctl.lisp(lib + insert_lisp(items, a.get("explode", True)), doc=doc, timeout_s=timeout_s)
        got = parse(rows)
        return {"drawing": doc.Name, "files": got, "entities": sum(g["entities"] for g in got)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "여러 도면 원래 좌표로 불러오기", size="620x520")
        self.acad = A.Acad()
        self.files = []
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.section(body, "불러올 도면 (DWG·DXF)")
        self.lst = tk.Listbox(body, bg=ui.ENTRY, fg="#FFFFFF", font=ui.FONT, relief="flat", height=12)
        self.lst.pack(fill="both", expand=True, padx=4, pady=4)
        row = tk.Frame(body, bg=ui.PANEL)
        row.pack(fill="x")
        tk.Button(row, text="파일 추가", command=self.add, bg="#383A3E", fg="#FFFFFF", relief="flat").pack(side="left", padx=4)
        tk.Button(row, text="목록 비우기", command=self.clear, bg="#383A3E", fg="#FFFFFF", relief="flat").pack(side="left", padx=4)
        self.var_exp = tk.BooleanVar(value=True)
        tk.Checkbutton(body, text="불러온 뒤 폭파해 원래 객체로 (끄면 파일 이름 블록으로 남김)", variable=self.var_exp,
                       bg=ui.PANEL, fg=ui.FG, selectcolor=ui.ENTRY, activebackground=ui.PANEL, font=ui.FONT).pack(anchor="w", pady=4)
        tk.Button(self, text="불러오기 (원래 좌표 그대로)", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
                  height=2).pack(fill="x", padx=10, pady=4)
        self.status("DWG·DXF를 여러 개 골라 지금 도면에 원래 좌표 그대로 넣습니다. DXF는 뒤에서 DWG로 바꿔 넣습니다.")

    def add(self):
        got = filedialog.askopenfilenames(parent=self, title="불러올 도면",
                                          filetypes=[("도면", "*.dwg *.dxf"), ("DWG", "*.dwg"), ("DXF", "*.dxf")])
        for f in got:
            if f not in self.files:
                self.files.append(f)
                self.lst.insert("end", f)
        self.status("%d개 도면" % len(self.files))

    def clear(self):
        self.files = []
        self.lst.delete(0, "end")

    def run(self):
        if not self.files:
            self.error("불러올 도면을 먼저 추가하세요.")
            return
        work = tempfile.mkdtemp(prefix="bc_muin_")
        try:
            self.status("준비 중… (DXF는 DWG로 바꾸는 중)")
            items = prepare(self.files, work)
            self.status("지금 도면에 넣는 중…")
            got = parse(self.acad.lisp_undo(insert_lisp(items, self.var_exp.get()), 600))
            self.status("도면 %d개, 객체 %d개를 원래 좌표로 넣었습니다(UNDO 한 번으로 취소)." %
                        (len(got), sum(g["entities"] for g in got)))
        except Exception as e:  # noqa: BLE001 — 사람이 볼 창이므로 원문을 보인다
            self.error("%s: %s" % (type(e).__name__, e))
        finally:
            shutil.rmtree(work, ignore_errors=True)


def main():
    Window().mainloop()
