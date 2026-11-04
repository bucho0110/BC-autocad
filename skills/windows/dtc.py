# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DTC 도면 목록표 만들기 — 도곽마다 도면번호·도면명(과 기타 항목)을 읽어 도면 목록표를 엑셀로 내거나 도면에 그린다.

도곽 등록은 MPTE와 같다(같은 등록을 쓴다). 설정의 번호항목·제목항목에 등록한 항목 이름을 적는다.
한 도면에 도곽이 여럿이어도, 모형·배치에 섞여 있어도, 도곽 축척이 달라도 된다. 여러 파일도 한 표로 모은다.
to_rows()·draw_lisp()는 창 없이도 쓴다(MCP skill_run).
"""

import re
import tkinter as tk

from skills.common import acad as A
from skills.common import cadtable as TB
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from skills.windows import mpte as M

CMD = "DTC"
FIELDS = [
    ("번호항목", "도면번호 항목 이름 (MPTE 등록 이름)", "str", "도면번호", None),
    ("제목항목", "도면명 항목 이름", "str", "도면명", None),
    ("기타항목", "기타 열 항목 이름 (쉼표로 4개까지, 비우면 없음)", "str", "", None),
    ("공간", "읽을 공간", "choice", "모형+배치", ["모형+배치", "모형", "배치"]),
    ("정렬", "목록 순서", "choice", "도면번호", ["도면번호", "도곽 순서"]),
    ("빈번호제외", "도면번호가 빈 도곽은 빼기", "bool", True, None),
    ("문자높이", "도면에 그릴 때 문자 높이", "real", 3.0, None),
    ("문자레이어", "문자 레이어", "str", "표_문자", None),
    ("선레이어", "선 레이어", "str", "표_선", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def extras(cfg):
    return [e.strip() for e in str(cfg["기타항목"]).split(",") if e.strip()][:4]


def _natural(s):
    """도면번호 자연 정렬(2 < 10, 'C-2' < 'C-10')."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", s) if t]


def to_rows(read, cfg):
    """read(MPTE gather 결과) → [머리, [순번, 도면번호, 도면명, 기타…]…]."""
    ex = extras(cfg)
    items = []
    for _path, frames in read:
        for it in frames:
            no = it["values"].get(cfg["번호항목"], "")
            if cfg["빈번호제외"] and not no:
                continue
            items.append([no, it["values"].get(cfg["제목항목"], "")] + [it["values"].get(e, "") for e in ex])
    if cfg["정렬"] == "도면번호":
        items.sort(key=lambda r: _natural(r[0]))
    return [["순번", "도면번호", "도면명"] + ex] + [[i + 1] + r for i, r in enumerate(items)]


def _width(s, h):
    """글자 폭 어림(한글 1.0h, 그 밖 0.7h) + 양옆 여백."""
    return sum(h if ord(c) > 0x2E7F else 0.7 * h for c in str(s)) + 2 * h


def draw_lisp(rows, origin, cfg):
    """origin = 표 왼쪽 위. → (LISP, 너비, 높이)."""
    h = float(cfg["문자높이"])
    rows = [[str(v) for v in r] for r in rows]
    widths = [max(_width(r[j], h) for r in rows if j < len(r)) for j in range(len(rows[0]))]
    return TB.table_lisp(rows, origin, widths, 2.2 * h, h, cfg["문자레이어"], cfg["선레이어"])


font_warning = TB.font_warning  # 표는 지금 문자 스타일로 그린다 — 한글 글꼴이 없으면 알린다


class Window(M.Window):
    CMD, TITLE, FIELDS_, DEFAULTS_ = CMD, "도면 목록표 만들기", FIELDS, DEFAULTS

    def buttons(self):
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        tk.Button(row, text="엑셀로 (첫 칸을 먼저 고르세요)", command=self.to_excel, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(row, text="지금 도면에 표 그리기", command=self.to_drawing, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(side="left", expand=True, fill="x", padx=2)

    def _rows(self):
        cfg = self.form.values()
        S.save(self.CMD, cfg)
        names = M.item_names(self.reg)
        if cfg["번호항목"] not in names:
            self.error("번호항목 '%s'이(가) 등록한 항목에 없습니다. 등록 항목: %s" % (cfg["번호항목"], ", ".join(names) or "없음"))
            return None, cfg
        read = self._read(dict(M.DEFAULTS, 공간=cfg["공간"], 정렬="위→아래"))
        return (to_rows(read, cfg) if read is not None else None), cfg

    def to_excel(self):
        rows, _cfg = self._rows()
        if rows is None:
            return
        try:
            ws, r0, c0 = X.active_cell()
            M.write_text_rows(ws, r0, c0, rows)
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        self.status("도면 %d장 목록을 내보냈습니다." % (len(rows) - 1))

    def to_drawing(self):
        rows, cfg = self._rows()
        if rows is None:
            return
        got = self.in_cad(self.acad.lisp, '(setq _p (getpoint "\\n표 왼쪽 위: ")) (if _p (progn (setq _p (trans _p 1 0))'
                          ' (write-line (strcat (bc:rtos (car _p) 2 10) _d (bc:rtos (cadr _p) 2 10)) _fp)))', A.PICK_TIMEOUT)
        if not got:
            return
        p = [float(v) for v in got[0].split("\t")]
        code = draw_lisp(rows, p, cfg)[0]
        if self.in_cad(self.acad.lisp_undo, code, 600) is not None:
            warn = font_warning(lambda c: self.acad.lisp(c, 60), rows)
            self.status("도면 %d장 목록표를 그렸습니다(UNDO 한 번으로 취소).%s" % (len(rows) - 1, " " + warn if warn else ""))


def main():
    Window().mainloop()
