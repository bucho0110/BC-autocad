"""RCE 순번 좌표 내보내기 — 점을 찍을 때마다 엑셀에 [순번, X, Y(, Z)]를 한 줄씩 쌓고 도면에 순번을 쓴다."""

import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "RCE"
FIELDS = [
    ("좌표", "좌표계", "choice", "토목", ["토목", "수학"]),
    ("소수", "좌표 소수 자리", "int", 4, None),
    ("엑셀순번", "엑셀에 순번 넣기", "bool", True, None),
    ("Z표기", "Z 값도", "bool", False, None),
    ("Z소수", "Z 소수 자리", "int", 4, None),
    ("순번시작", "순번 시작 값", "int", 1, None),
    ("증분", "순번 증분", "int", 1, None),
    ("자리", "자리 수 (0 채움, 1=안 채움)", "int", 1, None),
    ("머리말", "순번 머리말", "str", "", None),
    ("꼬리말", "순번 꼬리말", "str", "", None),
    ("점표기", "지정 점에 Point", "bool", False, None),
    ("도면순번", "도면에 순번 쓰기", "bool", True, None),
    ("높이", "순번 문자 높이", "real", 2.5, None),
    ("원", "순번에 원 두르기", "bool", False, None),
    ("레이어", "레이어 (비우면 현재)", "str", "", None),
    ("X이격", "순번 X 이격", "real", 0.0, None),
    ("Y이격", "순번 Y 이격", "real", 3.0, None),
    ("전체축척", "전체 축척 (높이·원·이격에 곱함)", "real", 1.0, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def pick_and_mark_lisp(label, cfg) -> str:
    """점 하나를 받고(엔터=끝) 설정대로 표기, 좌표를 결과로 쓴다."""
    k = float(cfg["전체축척"])
    h, dx, dy = float(cfg["높이"]) * k, float(cfg["X이격"]) * k, float(cfg["Y이격"]) * k
    lay = ls(cfg["레이어"])
    s = ['(setq _p (getpoint "\\n좌표 내보낼 점 지정 [%s] (엔터=끝): "))' % ls(label),
         "(if _p (progn (setq _p (trans _p 1 0))",
         '(write-line (strcat "P\\t" (bc:rtos (car _p) 2 10) "\\t" (bc:rtos (cadr _p) 2 10) "\\t" (bc:rtos (caddr _p) 2 10)) _fp)']
    if cfg["점표기"]:
        s.append('(bc:point _p "%s")' % lay)
    if cfg["도면순번"]:
        s.append('(setq _q (list (+ (car _p) %.6f) (+ (cadr _p) %.6f) 0.0))' % (dx, dy))
        s.append('(bc:text _q "%s" %.6f "%s" "MC" 0.0)' % (ls(label), h, lay))
        if cfg["원"]:
            s.append('(bc:circle _q %.6f "%s")' % (h * 0.9, lay))
    s.append("))")
    return "".join(s)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "순번 좌표 내보내기", size="560x760")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="시작 (엑셀에서 첫 셀 선택 후 누르기)", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            S.save(CMD, cfg)
            ws, row, col = X.active_cell()
        except (ValueError, X.ExcelNotReady) as e:
            self.error(str(e))
            return
        n = int(cfg["순번시작"])
        count = 0
        self.iconify()
        self.acad.activate()
        try:
            while True:
                lab = "%s%s%s" % (cfg["머리말"], str(n).zfill(max(1, int(cfg["자리"]))), cfg["꼬리말"])
                rows = self.acad.lisp_undo(pick_and_mark_lisp(lab, cfg), A.PICK_TIMEOUT)
                pts = [r for r in rows if r.startswith("P\t")]
                if not pts:
                    break
                _t, x, y, z = pts[0].split("\t")
                a, b, zz = C.civil((float(x), float(y), float(z)), cfg["좌표"])
                line = ([lab] if cfg["엑셀순번"] else []) + [C.fmt(a, cfg["소수"]), C.fmt(b, cfg["소수"])]
                if cfg["Z표기"]:
                    line.append(C.fmt(zz, cfg["Z소수"]))
                X.write_rows(ws, row + count, col, [line])  # 줄마다 열 너비를 맞춘다(뒤 줄 값이 더 길 수 있다)
                count += 1
                n += int(cfg["증분"])
        except Exception as e:  # noqa: BLE001
            self.error("%s: %s" % (type(e).__name__, e))
        finally:
            self.deiconify()
            self.lift()
        self.status("점 %d개를 내보냈습니다(엑셀 %s!%d행부터)." % (count, ws.Name, row))


def main():
    Window().mainloop()
