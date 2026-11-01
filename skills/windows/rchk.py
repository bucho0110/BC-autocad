# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""RCHK 구조도·상세도 철근 대조 — 구조도의 철근 번호 표시와 철근 상세를 번호·직경으로 대조한다.

구조도: 원(또는 철근 번호 블록) 안 번호 + 원 근처 문자의 직경(H22·D13@250 …).
상세도: RET과 같은 인식(원 안 번호, 밑줄 위 직경·L=·N=).
결과: 직경 다름 · 상세도 누락(구조도에만) · 상세도만 있음 · 상세도 중복. 표시를 켜면 구조도 쪽 문제 번호에 빨간 원,
직경 다름은 구조도 번호와 상세를 잇는 선을 '철근-검사' 레이어에 그린다. compare()는 창 없이도 쓴다(MCP skill_run).
"""

import math
import re
import tkinter as tk

from skills.common import acad as A
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.windows import ret

CMD = "RCHK"
FIELDS = [
    ("목록", "목록에 넣을 것", "choice", "다른 것만", ["다른 것만", "모두"]),
    ("구분문자", "철근 구분 문자 (쉼표)", "str", "D,H,S,U", None),
    ("원미만", "이 지름 미만 원은 검색 안 함 (0 = 제한 없음)", "real", 0.0, None),
    ("원초과", "이 지름 초과 원은 검색 안 함 (0 = 제한 없음)", "real", 0.0, None),
    ("직경거리", "구조도 번호 원에서 직경 문자를 찾을 거리 (원 반지름 배수)", "real", 6.0, None),
    ("표시", "문제 철근을 도면에 표시", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def marks(circles, texts, cfg):
    """구조도 철근 표시 → [{no, dia(문자)|None, x, y, r}]."""
    grades = [g.strip().upper() for g in str(cfg["구분문자"]).split(",") if g.strip()]
    re_d = re.compile(r"(%s)\s*(\d+)" % "|".join(re.escape(g) for g in grades), re.I) if grades else None
    dmin, dmax = float(cfg["원미만"]), float(cfg["원초과"])
    out = []
    for c in circles:
        d = 2 * c["r"]
        if (dmin > 0 and d < dmin) or (dmax > 0 and d > dmax):
            continue
        if c.get("no"):
            no, dia = c["no"], c.get("dia_text") or None
        else:
            inner = sorted((t for t in texts if math.hypot(t["x"] - c["x"], t["y"] - c["y"]) < c["r"]), key=lambda t: -t["y"])
            if not inner:
                continue
            no, dia = "".join(t["text"] for t in inner).replace(" ", ""), None
        if dia is None and re_d:
            near = sorted((math.hypot(t["x"] - c["x"], t["y"] - c["y"]), t) for t in texts
                          if c["r"] <= math.hypot(t["x"] - c["x"], t["y"] - c["y"]) <= float(cfg["직경거리"]) * c["r"])
            for _dd, t in near:
                m = re_d.search(t["text"].replace(" ", ""))
                if m:
                    dia = "%s%s" % (m.group(1).upper(), m.group(2))
                    break
        out.append({"no": no, "dia": dia, "x": c["x"], "y": c["y"], "r": c["r"]})
    return out


def compare(struct_rows, detail_rows, cfg):
    """→ (목록 행 [[번호, 구조도 직경, 상세도 직경, 비고]], 구조도 표시, 상세 목록)."""
    rcfg = dict(ret.DEFAULTS, 구분문자=cfg["구분문자"], 원미만=cfg["원미만"], 원초과=cfg["원초과"])
    sm = marks(*ret.parse_dump(struct_rows)[:2], cfg)
    details, _bad = ret.recognize(*ret.parse_dump(detail_rows), rcfg)
    dmap = {}
    for d in details:
        dmap.setdefault(d["no"], []).append(d)
    smap = {}
    for m in sm:
        smap.setdefault(m["no"], []).append(m)
    rows, probs = [], []
    for no in sorted(set(smap) | set(dmap), key=ret._natural):
        sd = sorted({m["dia"] for m in smap.get(no, []) if m["dia"]})
        dd = sorted({"%s%d" % (d["grade"], d["dia"]) for d in dmap.get(no, [])})
        note = []
        if no in smap and no not in dmap:
            note.append("상세도 누락")
        if no in dmap and no not in smap:
            note.append("상세도만 있음")
        if len(dmap.get(no, [])) > 1:
            note.append("상세도 중복")
        if sd and dd and set(sd) != set(dd):
            note.append("직경 다름")
        if note or cfg["목록"] == "모두":
            rows.append([no, ",".join(sd), ",".join(dd), ", ".join(note)])
        if note:
            probs.append((no, note, smap.get(no, []), dmap.get(no, [])))
    return rows, probs


def mark_lisp(probs):
    out = ['(bc:ensure-layer "철근-검사" 1)']
    for _no, note, ms, ds in probs:
        for m in ms:
            out.append('(bc:circle (list %.6f %.6f 0.0) %.6f "철근-검사")' % (m["x"], m["y"], m["r"] * 1.6))
            if "직경 다름" in note:
                for d in ds:
                    out.append('(bc:line (list %.6f %.6f 0.0) (list %.6f %.6f 0.0) "철근-검사")' % (m["x"], m["y"], d["x"], d["y"]))
        if not ms:
            for d in ds:
                out.append('(bc:circle (list %.6f %.6f 0.0) %.6f "철근-검사")' % (d["x"], d["y"], 6.0))
    return "".join(out)


SEL = ('(princ "\\n%s 선택: ") (setq _ss (ssget (list (cons 0 "CIRCLE,INSERT,TEXT,MTEXT,LINE,LWPOLYLINE"))))'
       ' (if _ss (progn %s (write-line "END" _fp)))')


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "구조도·상세도 철근 대조", size="560x560")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        from tkinter import ttk
        self.tree = ttk.Treeview(body, columns=("no", "s", "d", "note"), show="headings", height=8)
        for c, t, w in (("no", "번호", 70), ("s", "구조도 직경", 90), ("d", "상세도 직경", 90), ("note", "비고", 220)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True, pady=4)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        for t, fn in (("구조도 선택 → 상세도 선택 → 검사", self.run), ("목록 엑셀로", self.to_excel)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat", height=2).pack(
                side="left", expand=True, fill="x", padx=1)
        self.rows = []

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        a = self.in_cad(self.acad.lisp, SEL % ("구조도", ret.DUMP_LISP), A.PICK_TIMEOUT)
        if not a:
            return
        b = self.in_cad(self.acad.lisp, SEL % ("상세도", ret.DUMP_LISP), A.PICK_TIMEOUT)
        if not b:
            return
        self.rows, probs = compare(a, b, cfg)
        self.tree.delete(*self.tree.get_children())
        for r in self.rows:
            self.tree.insert("", "end", values=r)
        if cfg["표시"] and probs:
            self.in_cad(self.acad.lisp_undo, mark_lisp(probs), 60)
        self.status("문제 %d건 (목록 %d줄)" % (len(probs), len(self.rows)))

    def to_excel(self):
        try:
            ws, r, c = X.active_cell()
            X.write_rows(ws, r, c, [["번호", "구조도 직경", "상세도 직경", "비고"]] + self.rows)
        except X.ExcelNotReady as e:
            self.error(str(e))


def main():
    Window().mainloop()
