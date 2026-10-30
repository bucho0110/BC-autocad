# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CEX 좌표 내보내기 — 고른 객체의 좌표를 엑셀 화면(선택 셀부터) 또는 텍스트 파일로.

build_rows()는 창 없이도 쓴다(MCP run_skill).
"""

import os
import tkinter as tk
from tkinter import filedialog

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CEX"
FIELDS = [
    ("대상선", "선·폴리선 (정점)", "bool", True, None),
    ("대상문자", "문자 (삽입점)", "bool", True, None),
    ("대상점", "점", "bool", True, None),
    ("대상블록", "블록 (삽입점)", "bool", True, None),
    ("대상원호", "원·도넛·호 (중심)", "bool", True, None),
    ("좌표", "좌표계", "choice", "토목", ["토목", "수학"]),
    ("출력", "내보낼 곳", "choice", "엑셀", ["엑셀", "텍스트"]),
    ("구분", "텍스트 구분 문자 (쉼표 / 빈칸 / 직접 입력)", "str", ",", None),
    ("소수", "X·Y 소수 자리", "int", 4, None),
    ("Z포함", "Z 좌표 포함", "bool", False, None),
    ("Z소수", "Z 소수 자리", "int", 4, None),
    ("레이어포함", "객체 레이어 포함", "bool", False, None),
    ("문자내용", "문자: 내용 포함(맨 뒤)", "bool", True, None),
    ("정렬점", "문자: 정렬점 좌표로", "bool", False, None),
    ("중복제외", "중복 좌표 제외", "bool", False, None),
    ("정렬", "좌표 정렬", "choice", "안 함", C.SORTS),
    ("객체별빈줄", "객체별 한 줄 띄우기", "bool", False, None),
    ("순번", "순번 표기 (엑셀·도면)", "bool", False, None),
    ("순번시작", "순번 시작 값", "int", 1, None),
    ("순번자리", "순번 자리 수 (0 채움, 1=안 채움)", "int", 1, None),
    ("순번머리", "순번 머리말", "str", "", None),
    ("순번꼬리", "순번 꼬리말", "str", "", None),
    ("도면순번", "도면에도 순번 쓰기", "bool", False, None),
    ("순번높이", "도면 순번 문자 높이", "real", 2.5, None),
    ("순번원", "순번에 원 두르기", "bool", False, None),
    ("순번레이어", "도면 순번 레이어 (비우면 현재)", "str", "", None),
    ("순번X", "순번 X 이격", "real", 0.0, None),
    ("순번Y", "순번 Y 이격", "real", 3.0, None),
    ("열너비맞춤", "엑셀 열 너비 자동 맞춤", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def type_filter(cfg) -> str:
    keys = [("대상선", "선"), ("대상문자", "문자"), ("대상점", "점"), ("대상블록", "블록"), ("대상원호", "원호")]
    return ",".join(C.TYPE_GROUPS[g] for k, g in keys if cfg.get(k))


def label(n, cfg):
    s = str(n).zfill(max(1, int(cfg["순번자리"])))
    return "%s%s%s" % (cfg["순번머리"], s, cfg["순번꼬리"])


def build_rows(ents, cfg):
    """덤프 객체 → (행 목록, 순번 표기할 [(라벨, CAD점)])"""
    pts = []  # (객체 순번, 객체, 점)
    for oi, e in enumerate(ents):
        for p in e["points"]:
            pts.append((oi, e, p))
    if cfg["중복제외"]:
        seen, uniq = set(), []
        for t in pts:
            k = (round(t[2][0], 6), round(t[2][1], 6), round(t[2][2], 6))
            if k not in seen:
                seen.add(k)
                uniq.append(t)
        pts = uniq
    how = cfg["정렬"]
    if how in ("내용 오름차순", "내용 내림차순"):
        pts.sort(key=lambda t: t[1]["text"], reverse=(how == "내용 내림차순"))
    elif cfg["객체별빈줄"]:
        # 객체 단위로 첫 좌표 기준 정렬, 좌표 순서는 유지
        order = C.sort_points(list(range(len(ents))), how, key=lambda i: ents[i]["points"][0] if ents[i]["points"] else (0, 0, 0))
        rank = {oi: r for r, oi in enumerate(order)}
        pts.sort(key=lambda t: rank.get(t[0], 0))
    else:
        pts = C.sort_points(pts, how, key=lambda t: t[2])
    rows, marks = [], []
    n = int(cfg["순번시작"])
    last = None
    for oi, e, p in pts:
        if cfg["객체별빈줄"] and last is not None and oi != last:
            rows.append([])
        last = oi
        a, b, z = C.civil(p, cfg["좌표"])
        r = []
        if cfg["순번"]:
            r.append(label(n, cfg))
            marks.append((label(n, cfg), p))
            n += 1
        r += [C.fmt(a, cfg["소수"]), C.fmt(b, cfg["소수"])]
        if cfg["Z포함"]:
            r.append(C.fmt(z, cfg["Z소수"]))
        if cfg["레이어포함"]:
            r.append(e["layer"])
        if cfg["문자내용"] and e["type"] in ("TEXT", "MTEXT"):
            r.append(e["text"])
        rows.append(r)
    return rows, marks


def marks_lisp(marks, cfg) -> str:
    """도면 순번 문자(+원)를 그리는 LISP 본문."""
    h = float(cfg["순번높이"])
    lay = ls(cfg["순번레이어"])
    out = []
    for lab, p in marks:
        q = (p[0] + float(cfg["순번X"]), p[1] + float(cfg["순번Y"]), 0.0)
        out.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "MC" 0.0)' % (q[0], q[1], ls(lab), h, lay))
        if cfg["순번원"]:
            out.append('(bc:circle (list %.10f %.10f 0.0) %.6f "%s")' % (q[0], q[1], h * 0.9, lay))
    return "".join(out)


def write_text(path, rows, sep):
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        for r in rows:
            f.write(sep.join(str(x) for x in r) + "\n")


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "좌표 내보내기", size="600x800")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        canvas = tk.Canvas(body, bg=ui.PANEL, highlightthickness=0)
        sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=ui.PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.form = self.form_section(inner, "설정", FIELDS, S.load(CMD, DEFAULTS))
        btn = tk.Frame(self, bg=ui.BG)
        btn.pack(fill="x", padx=10, pady=4)
        tk.Button(btn, text="도면에서 객체 선택 → 내보내기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x")
        self.status("엑셀로 낼 때는 엑셀에서 첫 셀을 먼저 선택해 두세요.")

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        flt = type_filter(cfg)
        if not flt:
            self.error("내보낼 대상을 하나 이상 고르세요.")
            return
        body = ('(princ "\\n좌표 내보낼 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s"))))'
                ' (bc:dump-ss _ss %s _fp)' % (flt, "T" if cfg["정렬점"] else "nil"))
        rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
        if rows is None:
            return
        ents = C.parse_dump(rows)
        if not ents:
            self.status("고른 객체가 없습니다.")
            return
        out, marks = build_rows(ents, cfg)
        try:
            if cfg["출력"] == "엑셀":
                ws, r, c = X.active_cell()
                X.write_rows(ws, r, c, out, cfg["열너비맞춤"])
                where = "엑셀 %s!%s행 %s열부터" % (ws.Name, r, c)
            else:
                path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt",
                                                    filetypes=[("텍스트", "*.txt"), ("CSV", "*.csv")])
                if not path:
                    return
                sep = {"빈칸": " ", "쉼표": ","}.get(cfg["구분"], cfg["구분"] or ",")
                write_text(path, out, sep)
                where = path
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        if cfg["순번"] and cfg["도면순번"] and marks:
            self.in_cad(self.acad.lisp_undo, marks_lisp(marks, cfg))
        self.status("객체 %d개, 좌표 %d줄을 내보냈습니다 → %s" % (len(ents), sum(1 for r in out if r), where))


def main():
    Window().mainloop()
