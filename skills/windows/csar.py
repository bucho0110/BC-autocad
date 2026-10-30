# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CSAR 도곽에 횡단 배치 — 흩어진 횡단면을 도곽(블록) 사본마다 X×Y 칸에 순서대로 옮겨 붙인다.

순서: 견본 중심선 → 견본 단면의 선택 범위(두 구석) → 배치할 중심선들 → 도곽 블록 → 도곽 안 배치 영역(두 구석)
→ (선택) 도곽과 함께 복사할 객체 → 첫 도곽 삽입점.
단면마다 '중심선 아래 끝 기준 같은 범위'에 걸치는 모든 객체를 복사한다(외곽 상자로 판정 — 화면 밖도 잡는다).
원본은 그대로 두고 복사본을 만든다. plan()은 창 없이도 쓴다(MCP run_skill).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui

CMD = "CSAR"
ORDERS = ["아래→위 열 우선", "위→아래 행 우선", "위→아래 열 우선"]
SRC_ORDERS = ["아래→위", "위→아래", "왼→오른", "오른→왼"]
FIELDS = [
    ("원래순서", "도면의 횡단을 가져올 순서", "choice", "아래→위", SRC_ORDERS),
    ("칸순서", "도곽 안 칸 채우는 순서", "choice", "아래→위 열 우선", ORDERS),
    ("X개수", "한 도곽 가로 개수", "int", 1, None),
    ("Y개수", "한 도곽 세로 개수", "int", 3, None),
    ("도곽배치", "도곽 배치", "choice", "행", ["행", "열"]),
    ("줄당도곽", "한 줄 도곽 수", "int", 5, None),
    ("도곽간격", "도곽 사이 간격 (도면 단위)", "real", 10.0, None),
    ("함께복사", "도곽과 함께 복사할 객체 고르기", "bool", False, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}


def cell_order(n, X, Y, mode):
    """한 도곽의 칸 순서 [(열, 행)] — 행 0이 아래."""
    out = []
    if mode == "위→아래 행 우선":
        for r in range(Y - 1, -1, -1):
            for c in range(X):
                out.append((c, r))
    elif mode == "위→아래 열 우선":
        for c in range(X):
            for r in range(Y - 1, -1, -1):
                out.append((c, r))
    else:
        for c in range(X):
            for r in range(Y):
                out.append((c, r))
    return out


def frame_offsets(n, mode, per, fw, fh, gap):
    """도곽 n개의 첫 도곽 기준 위치 [(dx, dy)]. 행 = 오른쪽으로 per개 → 아래 줄, 열 = 아래로 per개 → 오른쪽 줄."""
    per = max(1, int(per))
    out = []
    for i in range(n):
        if mode == "열":
            col, row = i // per, i % per
        else:
            col, row = i % per, i // per
        out.append((col * (fw + gap) * 1.0, -row * (fh + gap) * 1.0))
    return out


def sort_sections(cs, how):
    key = {"아래→위": lambda c: (c[1], c[0]), "위→아래": lambda c: (-c[1], c[0]),
           "왼→오른": lambda c: (c[0], c[1]), "오른→왼": lambda c: (-c[0], c[1])}[how]
    return sorted(cs, key=key)


def plan(centers, win, frame, area, cfg, boxes):
    """centers [(x, y아래끝)], win (dx0, dy0, dx1, dy1) 중심선 아래 끝 기준 범위, frame (ins x, y, minx, miny, maxx, maxy),
    area (ax0, ay0, ax1, ay1) 도곽 삽입점 기준, boxes {핸들: (minx, miny, maxx, maxy)}.
    반환: [(도곽 이동 dx, dy, [(핸들목록, dx, dy) 단면별])]"""
    X, Y = max(1, int(cfg["X개수"])), max(1, int(cfg["Y개수"]))
    per = X * Y
    cs = sort_sections(centers, cfg["원래순서"])
    nf = int(math.ceil(len(cs) / float(per))) if cs else 0
    fw, fh = frame[4] - frame[2], frame[5] - frame[3]
    offs = frame_offsets(nf, cfg["도곽배치"], cfg["줄당도곽"], fw, fh, float(cfg["도곽간격"]))
    order = cell_order(per, X, Y, cfg["칸순서"])
    ax0, ay0, ax1, ay1 = min(area[0], area[2]), min(area[1], area[3]), max(area[0], area[2]), max(area[1], area[3])
    cw, ch = (ax1 - ax0) / X, (ay1 - ay0) / Y
    wx0, wy0, wx1, wy1 = min(win[0], win[2]), min(win[1], win[3]), max(win[0], win[2]), max(win[1], win[3])
    out = []
    base = cfg["_base"]
    for f in range(nf):
        fdx = base[0] + offs[f][0] - frame[0]
        fdy = base[1] + offs[f][1] - frame[1]
        secs = []
        for k, (cx, cy) in enumerate(cs[f * per:(f + 1) * per]):
            col, row = order[k]
            # 칸 가운데 = 도곽 사본의 배치 영역 안
            tx = base[0] + offs[f][0] + ax0 + (col + 0.5) * cw
            ty = base[1] + offs[f][1] + ay0 + (row + 0.5) * ch
            # 단면 범위 가운데를 칸 가운데로
            sx, sy = cx + (wx0 + wx1) / 2.0, cy + (wy0 + wy1) / 2.0
            x0, y0, x1, y1 = cx + wx0, cy + wy0, cx + wx1, cy + wy1
            hs = [h for h, b in boxes.items() if b[0] <= x1 and b[2] >= x0 and b[1] <= y1 and b[3] >= y0]
            secs.append((hs, tx - sx, ty - sy))
        out.append((fdx, fdy, secs))
    return out


def copy_lisp(handles, dx, dy) -> str:
    if not handles:
        return ""
    return '(bc:copy-move (list %s) %.10f %.10f)' % (" ".join('"%s"' % h for h in handles), dx, dy)


PICK_BODY = (
    '(setq _c (entsel "\\n견본 단면의 중심선(세로선) 선택: "))'
    # 중심선은 LINE이나 꼭짓점 2개짜리 폴리선(횡단면도의 '중심바') 둘 다
    ' (if (and _c (setq _vb (bc:vbar (car _c)))) (progn (setq _ce (entget (car _c)) _p0 (car _vb) _p1 (cadr _vb))'
    '  (write-line (strcat "C" _d (cdr (assoc 8 _ce)) _d (bc:rtos (- (cadr _p1) (cadr _p0)) 2 8)) _fp)'
    '  (setq _a (getpoint "\\n견본 단면의 선택 범위 첫 구석: "))'
    '  (setq _b (if _a (getcorner _a "\\n반대 구석: ")))'
    '  (if _b (progn (setq _a (trans _a 1 0) _b (trans _b 1 0))'
    '   (write-line (strcat "W" _d (bc:rtos (- (car _a) (car _p0)) 2 8) _d (bc:rtos (- (cadr _a) (cadr _p0)) 2 8) _d'
    '    (bc:rtos (- (car _b) (car _p0)) 2 8) _d (bc:rtos (- (cadr _b) (cadr _p0)) 2 8)) _fp)'
    '   (princ "\\n배치할 횡단의 중심선들 선택: ")'
    '   (setq _ss (ssget (list (cons 0 "LINE,LWPOLYLINE") (cons 8 (bc:wild-esc (cdr (assoc 8 _ce)))))) _i 0)'
    '   (if _ss (while (< _i (sslength _ss)) (setq _vb (bc:vbar (ssname _ss _i)) _q0 (car _vb) _q1 (cadr _vb))'
    '    (if (and _vb (equal (- (cadr _q1) (cadr _q0)) (- (cadr _p1) (cadr _p0)) (* 0.01 (- (cadr _p1) (cadr _p0)))))'
    '     (write-line (strcat "S" _d (bc:rtos (car _q0) 2 8) _d (bc:rtos (min (cadr _q0) (cadr _q1)) 2 8)) _fp))'
    '    (setq _i (1+ _i))))'
    '   (setq _f (entsel "\\n도곽 블록 선택: "))'
    '   (if (and _f (= (cdr (assoc 0 (entget (car _f)))) "INSERT")) (progn'
    '    (setq _fi (cdr (assoc 10 (entget (car _f)))) _fb (bc:bbox (car _f)))'
    '    (write-line (strcat "F" _d (cdr (assoc 5 (entget (car _f)))) _d (bc:rtos (car _fi) 2 8) _d (bc:rtos (cadr _fi) 2 8)'
    '     _d (bc:rtos (car _fb) 2 8) _d (bc:rtos (cadr _fb) 2 8) _d (bc:rtos (caddr _fb) 2 8) _d (bc:rtos (cadddr _fb) 2 8)) _fp)'
    '    (setq _a (getpoint "\\n도곽 안 횡단 배치 영역 첫 구석: ")) (setq _b (if _a (getcorner _a "\\n반대 구석: ")))'
    '    (if _b (progn (setq _a (trans _a 1 0) _b (trans _b 1 0))'
    '     (write-line (strcat "A" _d (bc:rtos (- (car _a) (car _fi)) 2 8) _d (bc:rtos (- (cadr _a) (cadr _fi)) 2 8) _d'
    '      (bc:rtos (- (car _b) (car _fi)) 2 8) _d (bc:rtos (- (cadr _b) (cadr _fi)) 2 8)) _fp)'
    '     %EXTRA%'
    '     (setq _bp (getpoint "\\n배치할 첫 도곽 삽입점 지정: "))'
    '     (if _bp (progn (setq _bp (trans _bp 1 0)) (write-line (strcat "P" _d (bc:rtos (car _bp) 2 8) _d (bc:rtos (cadr _bp) 2 8)) _fp)))))))))))'
)
EXTRA = ('(princ "\\n도곽과 함께 복사할 객체 선택(없으면 엔터): ") (setq _xs (ssget) _i 0)'
         ' (if _xs (while (< _i (sslength _xs)) (write-line (strcat "X" _d (cdr (assoc 5 (entget (ssname _xs _i))))) _fp) (setq _i (1+ _i))))')


def parse_pick(rows):
    d = {"S": [], "X": []}
    for r in rows:
        c = r.split("\t")
        if c[0] in ("S", "X"):
            d[c[0]].append(c[1:])
        else:
            d[c[0]] = c[1:]
    if not all(k in d for k in ("C", "W", "F", "A", "P")):
        return None
    f = d["F"]
    return {"center_layer": d["C"][0], "win": [float(v) for v in d["W"]],
            "centers": [(float(x), float(y)) for x, y in d["S"]],
            "frame_handle": f[0], "frame": [float(v) for v in f[1:]], "area": [float(v) for v in d["A"]],
            "extra": [x[0] for x in d["X"]], "base": [float(v) for v in d["P"]]}


def boxes_from(rows):
    out = {}
    for r in rows:
        c = r.split("\t")
        if c[0] == "B":
            out[c[1]] = tuple(float(v) for v in c[2:6])
    return out


def run_plan(lisp, lisp_group, pick, cfg):
    """pick(parse_pick 결과)로 실제 복사. lisp(body)·lisp_group(bodies) 은 실행 함수. 반환 (도곽 수, 단면 수)."""
    rows = lisp('(bc:dump-bbox (ssget "_X" (list (cons 410 "Model"))) _fp)')
    boxes = boxes_from(rows)
    boxes.pop(pick["frame_handle"], None)
    cfg = dict(cfg, _base=pick["base"])
    p = plan(pick["centers"], pick["win"], pick["frame"], pick["area"], cfg, boxes)
    bodies = []
    for fdx, fdy, secs in p:
        b = [copy_lisp([pick["frame_handle"]] + pick["extra"], fdx, fdy)]
        b += [copy_lisp(hs, dx, dy) for hs, dx, dy in secs]
        bodies.append("".join(b))
    lisp_group(bodies)
    return len(p), sum(len(s) for _f, _g, s in p)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "도곽에 횡단 배치", size="560x520")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="실행 (CAD에서 차례로 고르기)", command=self.run, bg="#3E5879", fg="#FFFFFF", relief="flat",
                  height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        body = PICK_BODY.replace("%EXTRA%", EXTRA if cfg["함께복사"] else "")
        pick = parse_pick(self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT) or [])
        if not pick or not pick["centers"]:
            self.status("취소했거나 고른 중심선이 없습니다.")
            return

        def group(bodies):
            with self.acad.undo_group():
                for b in bodies:
                    self.acad.lisp(b, 120)
            return True

        res = self.in_cad(run_plan, lambda b: self.acad.lisp(b, 120), group, pick, cfg)
        if res:
            self.status("도곽 %d장에 횡단 %d개를 배치했습니다(원본은 그대로)." % res)


def main():
    Window().mainloop()
