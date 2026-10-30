"""CIM 좌표 가져오기 — 엑셀 선택 범위나 텍스트 파일의 좌표로 폴리선·점·번호·Z 문자·블록을 그린다.

build_lisp()는 창 없이도 쓴다(MCP run_skill).
"""

import tkinter as tk
from tkinter import filedialog

from skills.common import acad as A
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui

CMD = "CIM"
LAYOUTS = ["X,Y", "X,Y,Z", "번호,X,Y", "번호,X,Y,Z", "번호,X,Y,Z,코드"]
FIELDS = [
    ("원본", "좌표 가져올 곳", "choice", "엑셀", ["엑셀", "텍스트"]),
    ("구분", "텍스트 구분 문자 (쉼표 / 빈칸 / 직접 입력)", "str", ",", None),
    ("열", "열 순서", "choice", "번호,X,Y", LAYOUTS),
    ("좌표", "좌표계 (토목: X=북쪽)", "choice", "토목", ["토목", "수학"]),
    ("폴리선", "폴리선 그리기", "bool", True, None),
    ("닫기", "폴리선 닫기", "bool", False, None),
    ("3D", "Z 있으면 3D 폴리선", "bool", False, None),
    ("점", "각 좌표에 Point", "bool", False, None),
    ("번호문자", "번호 문자 쓰기", "bool", True, None),
    ("Z문자", "Z 값 문자 쓰기", "bool", False, None),
    ("Z소수", "Z 문자 소수 자리", "int", 3, None),
    ("높이", "문자 높이", "real", 2.5, None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
    ("코드블록", "코드별 블록 (예: MH=맨홀,TR=수목)", "str", "", None),
    ("블록축척", "블록 축척", "real", 1.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def parse_rows(rows, cfg):
    """2차원 값 → [(번호, x, y, z, 코드)] (CAD 좌표). 숫자가 아닌 행(머리글)은 건너뛴다."""
    cols = cfg["열"].split(",")
    out = []
    for r in rows:
        r = list(r) + [None] * (len(cols) - len(r))
        d = dict(zip(cols, r))
        a, b = X.to_float(d.get("X")), X.to_float(d.get("Y"))
        if a is None or b is None:
            continue
        z = X.to_float(d.get("Z")) if "Z" in d else 0.0
        x, y = (b, a) if cfg["좌표"] == "토목" else (a, b)
        no = d.get("번호")
        if isinstance(no, float) and no.is_integer():
            no = int(no)
        out.append((str(no) if no is not None else "", x, y, z or 0.0, str(d.get("코드") or "")))
    return out


def read_text(path, sep):
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(line.split() if sep == " " else [c.strip() for c in line.split(sep)])
    return rows


def _q(s):
    """LISP 문자열 리터럴 안에 넣을 값(역슬래시·따옴표 이스케이프,)."""
    from validators import lisp_str
    return lisp_str(s)


def build_lisp(pts, cfg) -> str:
    lay = _q(cfg["레이어"])
    h = float(cfg["높이"])
    s = []
    if cfg["폴리선"] and len(pts) > 1:
        if cfg["3D"] and "Z" in cfg["열"]:
            s.append('(entmake (list (quote (0 . "POLYLINE")) (cons 8 (bc:layer "%s")) (quote (66 . 1)) (cons 70 %d) (quote (10 0.0 0.0 0.0))))'
                     % (lay, 8 | (1 if cfg["닫기"] else 0)))
            for _n, x, y, z, _c in pts:
                s.append('(entmake (list (quote (0 . "VERTEX")) (cons 8 (bc:layer "%s")) (list 10 %.10f %.10f %.10f) (quote (70 . 32))))' % (lay, x, y, z))
            s.append('(entmake (quote ((0 . "SEQEND"))))')
        else:
            s.append("(bc:pline (list %s) %s \"%s\")" % (" ".join("(list %.10f %.10f)" % (x, y) for _n, x, y, _z, _c in pts),
                                                          "T" if cfg["닫기"] else "nil", lay))
    blocks = {}
    for item in (cfg["코드블록"] or "").split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            blocks[k.strip()] = v.strip()
    for n, x, y, z, code in pts:
        if cfg["점"]:
            s.append('(bc:point (list %.10f %.10f %.10f) "%s")' % (x, y, z, lay))
        if cfg["번호문자"] and n:
            s.append('(bc:text (list %.10f %.10f 0.0) "%s" %.6f "%s" "BL" 0.0)' % (x + h * 0.4, y + h * 0.4, _q(n), h, lay))
        if cfg["Z문자"]:
            s.append('(bc:text (list %.10f %.10f 0.0) (bc:rtos %.10f 2 %d) %.6f "%s" "TL" 0.0)'
                     % (x + h * 0.4, y - h * 0.4, z, int(cfg["Z소수"]), h, lay))
        if code and code in blocks:
            s.append('(if (tblsearch "BLOCK" "%s") (vla-InsertBlock (vla-get-ModelSpace (vla-get-ActiveDocument (vlax-get-acad-object)))'
                     ' (vlax-3d-point (list %.10f %.10f %.10f)) "%s" %.6f %.6f %.6f 0.0))'
                     % (_q(blocks[code]), x, y, z, _q(blocks[code]), cfg["블록축척"], cfg["블록축척"], cfg["블록축척"]))
    s.append('(write-line (strcat "N\\t" (itoa %d)) _fp)' % len(pts))
    return "".join(s)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "좌표 가져오기", size="560x720")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="가져와서 그리기 (엑셀은 범위를 먼저 선택)", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            if cfg["원본"] == "엑셀":
                rows = X.selection_values()
            else:
                path = filedialog.askopenfilename(parent=self, filetypes=[("텍스트", "*.txt *.csv"), ("모든 파일", "*.*")])
                if not path:
                    return
                rows = read_text(path, {"빈칸": " ", "쉼표": ","}.get(cfg["구분"], cfg["구분"] or ","))
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        pts = parse_rows(rows, cfg)
        if not pts:
            self.error("좌표로 읽을 수 있는 행이 없습니다. 열 순서 설정을 확인하세요.")
            return
        res = self.in_cad(self.acad.lisp_undo, build_lisp(pts, cfg), 120)
        if res is not None:
            self.status("좌표 %d개로 그렸습니다." % len(pts))


def main():
    Window().mainloop()
