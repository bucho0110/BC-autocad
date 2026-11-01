# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""EWT 토적표 블록 값 엑셀로 모으기 — 횡단면마다 붙은 토적표 블록에서 측점·토공 항목 값을 모아 엑셀 표로 낸다.

토적표는 블록이어야 한다(선만 블록이고 문자는 따로여도 된다).
- 일반 블록: 토적표 하나에서 측점 칸·항목 칸 영역을 등록하면, 같은 이름의 모든 블록에서 그 영역(블록 기준 좌표) 안 문자를 읽는다.
  블록마다 축척·회전이 달라도 블록 기준으로 바꿔 읽는다.
- 속성 블록: 측점 태그와 항목 태그를 등록한다.
등록은 설정 파일에 남아 다음에도 쓴다. collect()·to_rows()는 창 없이도 쓴다(MCP skill_run).
"""

import json
import math
import tkinter as tk
from tkinter import simpledialog

from skills.common import acad as A
from skills.common import coords as C
from skills.common import excel as X
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "EWT"
FIELDS = [
    ("측점구분", "측점 정렬용 구분", "choice", "Station", ["Station", "Number"]),
    ("측점간격", "Number 측점 간격 (m)", "real", 20.0, None),
    ("숫자로", "숫자로 읽히는 값은 숫자로 내보내기", "bool", True, None),
    ("누가거리열", "측점 옆에 누가거리 열 추가", "bool", True, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
REG_KEY = "EWT_REG"


def load_reg():
    try:
        return json.loads(S.load(REG_KEY, {"json": ""})["json"] or "{}")
    except ValueError:
        return {}


def save_reg(reg):
    S.save(REG_KEY, {"json": json.dumps(reg, ensure_ascii=False)})


def dump_lisp(block):
    """같은 이름 블록마다 I<탭>핸들<탭>x<탭>y<탭>sx<탭>sy<탭>회전, 속성 A<탭>태그<탭>값, 모형 공간 문자 T<탭>x<탭>y<탭>내용."""
    return ('(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "INSERT") (cons 2 "%s") (cons 410 "Model"))))'
            ' (setq _ed (entget _e) _ip (trans (cdr (assoc 10 _ed)) _e 0))'
            ' (write-line (strcat "I" _d (cdr (assoc 5 _ed)) _d (bc:rtos (car _ip) 2 8) _d (bc:rtos (cadr _ip) 2 8) _d'
            '  (bc:rtos (cdr (assoc 41 _ed)) 2 8) _d (bc:rtos (cdr (assoc 42 _ed)) 2 8) _d (bc:rtos (cdr (assoc 50 _ed)) 2 10)) _fp)'
            ' (setq _a (entnext _e)) (while (and _a (= (cdr (assoc 0 (entget _a))) "ATTRIB"))'
            '  (write-line (strcat "A" _d (cdr (assoc 2 (entget _a))) _d (vl-string-translate "\\t\\n\\r" "   "'
            '   (cdr (assoc 1 (entget _a))))) _fp) (setq _a (entnext _a))))'
            '(foreach _e (bc:ss-list (ssget "_X" (list (cons 0 "TEXT,MTEXT") (cons 410 "Model"))))'
            ' (setq _p (bc:obj-center _e)) (write-line (strcat "T" _d (bc:rtos (car _p) 2 8) _d (bc:rtos (cadr _p) 2 8) _d'
            '  (vl-string-translate "\\t\\n\\r" "   " (bc:text-of _e))) _fp))' % ls(block))


def to_local(ins, x, y):
    dx, dy = x - ins["x"], y - ins["y"]
    c, s = math.cos(-ins["rot"]), math.sin(-ins["rot"])
    return (dx * c - dy * s) / (ins["sx"] or 1.0), (dx * s + dy * c) / (ins["sy"] or 1.0)


def parse(rows):
    ins, texts = [], []
    for r in rows:
        c = r.split("\t")
        if c[0] == "I":
            ins.append({"handle": c[1], "x": float(c[2]), "y": float(c[3]), "sx": float(c[4]), "sy": float(c[5]),
                        "rot": float(c[6]), "att": {}})
        elif c[0] == "A" and ins:
            ins[-1]["att"][c[1].upper()] = c[2].strip() if len(c) > 2 else ""
        elif c[0] == "T":
            texts.append((float(c[1]), float(c[2]), c[3].strip() if len(c) > 3 else ""))
    return ins, texts


def _in(box, p):
    x0, y0, x1, y1 = box
    return min(x0, x1) <= p[0] <= max(x0, x1) and min(y0, y1) <= p[1] <= max(y0, y1)


def collect(ins, texts, reg):
    """→ [{station, values {항목: 값}}]. reg: {"mode": "box"|"attr", "station": 상자|태그, "items": [[이름, 상자|태그]]}."""
    import bisect
    out = []
    texts = sorted(texts)
    tx = [t[0] for t in texts]
    boxes = [] if reg.get("mode") == "attr" else [reg["station"]] + [b for _n, b in reg["items"]]
    reach = max([abs(v) for bx in boxes for v in bx] or [0.0])
    for b in ins:
        if reg.get("mode") == "attr":
            st = b["att"].get(str(reg["station"]).upper(), "")
            vals = {n: b["att"].get(str(t).upper(), "") for n, t in reg["items"]}
        else:
            # 블록 근처 문자만(블록 기준 상자가 닿는 거리 안) — 블록 기준 좌표로 바꿔 상자 안인지 본다
            R = reach * max(abs(b["sx"]), abs(b["sy"]), 1e-9) * 1.5
            i0, i1 = bisect.bisect_left(tx, b["x"] - R), bisect.bisect_right(tx, b["x"] + R)
            loc = [(to_local(b, x, y), t) for x, y, t in texts[i0:i1] if abs(y - b["y"]) <= R]
            pick = lambda box: " ".join(t for p, t in sorted(loc, key=lambda i: (-i[0][1], i[0][0])) if _in(box, p))  # noqa: E731
            st = pick(reg["station"])
            vals = {n: pick(box) for n, box in reg["items"]}
        out.append({"station": st, "values": vals, "handle": b["handle"]})
    return out


def to_rows(items, reg, cfg):
    names = [n for n, _b in reg["items"]]
    head = ["측점"] + (["누가거리"] if cfg["누가거리열"] else []) + names
    rows = []
    for it in items:
        d = C.station_to_dist(it["station"].replace("STA.", "").replace("STA", "").strip(), cfg["측점구분"],
                              float(cfg["측점간격"])) if it["station"] else None
        r = [it["station"]] + ([C.fmt(d, 3) if d is not None else ""] if cfg["누가거리열"] else [])
        for n in names:
            v = it["values"].get(n, "")
            f = X.to_float(v) if cfg["숫자로"] else None
            r.append(f if f is not None else v)
        rows.append((d if d is not None else float("inf"), r))
    rows.sort(key=lambda t: t[0])
    return [head] + [r for _d, r in rows]


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "토적표 블록 값 엑셀로 모으기", size="540x560")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        self.var_reg = tk.StringVar()
        tk.Label(body, textvariable=self.var_reg, bg=ui.PANEL, fg=ui.ACCENT, font=ui.FONT, anchor="w",
                 justify="left", wraplength=500).pack(fill="x", pady=4)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=2)
        for t, fn in (("토적표 블록 등록", self.reg_block), ("항목 추가", self.add_items), ("등록 지우기", self.clear)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat").pack(
                side="left", expand=True, fill="x", padx=1)
        tk.Button(self, text="엑셀로 내보내기 (엑셀에서 쓸 첫 칸을 먼저 고르세요)", command=self.run, bg="#3E5879",
                  fg="#FFFFFF", relief="flat", height=2).pack(fill="x", padx=10, pady=4)
        self.reg = load_reg()
        self.show()

    def show(self):
        r = self.reg
        if not r:
            self.var_reg.set("등록 없음 — [토적표 블록 등록]부터 하세요.")
        else:
            self.var_reg.set("블록 %s (%s) · 항목: %s" % (r.get("block"), "속성" if r.get("mode") == "attr" else "영역",
                                                    ", ".join(n for n, _b in r.get("items", [])) or "없음"))

    def clear(self):
        self.reg = {}
        save_reg(self.reg)
        self.show()

    def _box(self, msg):
        rows = self.in_cad(self.acad.lisp, '(setq _a (getpoint "\\n%s 첫 모서리: ")) (if _a (progn'
                           ' (setq _b (getcorner _a "\\n반대 모서리: ")) (if _b (progn (setq _a (trans _a 1 0) _b (trans _b 1 0))'
                           ' (write-line (strcat (bc:rtos (car _a) 2 10) _d (bc:rtos (cadr _a) 2 10) _d (bc:rtos (car _b) 2 10)'
                           ' _d (bc:rtos (cadr _b) 2 10)) _fp)))))' % msg, A.PICK_TIMEOUT)
        return [float(v) for v in rows[0].split("\t")] if rows else None

    def _local_box(self, box):
        i = self.reg["ins"]
        a, b = to_local(i, box[0], box[1]), to_local(i, box[2], box[3])
        return [a[0], a[1], b[0], b[1]]

    def reg_block(self):
        rows = self.in_cad(self.acad.lisp, '(setq _s (entsel "\\n토적표 블록 선택: ")) (if _s (progn (setq _e (car _s) _ed (entget _e))'
                           ' (if (= (cdr (assoc 0 _ed)) "INSERT") (progn (setq _ip (trans (cdr (assoc 10 _ed)) _e 0))'
                           ' (write-line (strcat "I" _d (cdr (assoc 2 _ed)) _d (bc:rtos (car _ip) 2 8) _d (bc:rtos (cadr _ip) 2 8) _d'
                           ' (bc:rtos (cdr (assoc 41 _ed)) 2 8) _d (bc:rtos (cdr (assoc 42 _ed)) 2 8) _d (bc:rtos (cdr (assoc 50 _ed)) 2 10)) _fp)'
                           ' (setq _a (entnext _e)) (while (and _a (= (cdr (assoc 0 (entget _a))) "ATTRIB"))'
                           ' (write-line (strcat "A" _d (cdr (assoc 2 (entget _a))) _d (cdr (assoc 1 (entget _a)))) _fp)'
                           ' (setq _a (entnext _a)))))))', A.PICK_TIMEOUT)
        i = [r.split("\t") for r in rows or [] if r.startswith("I\t")]
        if not i:
            return
        c = i[0]
        ins = {"x": float(c[2]), "y": float(c[3]), "sx": float(c[4]), "sy": float(c[5]), "rot": float(c[6])}
        tags = [r.split("\t")[1] for r in rows if r.startswith("A\t")]
        if tags:
            st = simpledialog.askstring(CMD, "속성 블록입니다. 측점 태그를 적으세요:\n" + ", ".join(tags), parent=self)
            if not st:
                return
            self.reg = {"block": c[1], "mode": "attr", "station": st,
                        "items": [[t, t] for t in tags if t.upper() != st.upper()]}
        else:
            self.reg = {"block": c[1], "mode": "box", "ins": ins, "station": None, "items": []}
            box = self._box("측점 값 영역")
            if not box:
                return
            self.reg["station"] = self._local_box(box)
        save_reg(self.reg)
        self.show()
        if self.reg["mode"] == "box":
            self.add_items()

    def add_items(self):
        if not self.reg or self.reg.get("mode") != "box":
            self.error("일반 블록 토적표를 먼저 등록하세요(속성 블록은 태그가 곧 항목입니다).")
            return
        while True:
            box = self._box("토공 항목 값 영역(끝내려면 엔터)")
            if not box:
                break
            name = simpledialog.askstring(CMD, "항목 이름 (예: 깎기토사):", parent=self)
            if not name:
                break
            self.reg["items"].append([name, self._local_box(box)])
            save_reg(self.reg)
            self.show()

    def run(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        if not self.reg or not self.reg.get("items"):
            self.error("토적표 블록과 항목을 먼저 등록하세요.")
            return
        rows = self.in_cad(self.acad.lisp, dump_lisp(self.reg["block"]), 180)
        if rows is None:
            return
        ins, texts = parse(rows)
        items = collect(ins, texts, self.reg)
        try:
            ws, r0, c0 = X.active_cell()
            X.write_rows(ws, r0, c0, to_rows(items, self.reg, cfg))
        except X.ExcelNotReady as e:
            self.error(str(e))
            return
        self.status("토적표 %d개를 내보냈습니다." % len(items))


def main():
    Window().mainloop()
