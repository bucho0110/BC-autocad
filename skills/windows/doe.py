# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""DOE 겹친 객체 삭제 — 긴 객체 밑에 완전히 겹쳐 있는 짧은 선·폴리선·호·원을 지운다.

객체 A의 모든 구간(직선·호)이 다른 한 객체 B의 구간 위에 놓이고 A가 B보다 짧으면 A를 지운다.
완전히 같은 객체(중복)는 설정에 따라 먼저 만든 하나만 남긴다. 일직선 위에서 겹치거나 맞닿은 선(LINE)은 하나로 합칠 수 있다.
겹침 판단은 허용오차(소수 자리)로 한다. plan()은 창 없이도 쓴다(MCP skill_run).
"""

import math
import tkinter as tk

from skills.common import acad as A
from skills.common import geo as G
from skills.common import settings as S
from skills.common import ui
from skills.windows.dde import each_lisp
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "DOE"
FIELDS = [
    ("소수", "겹침 판단 소수 자리", "int", 4, None),
    ("같은레이어만", "레이어가 같을 때만", "bool", True, None),
    ("같은색만", "색이 같을 때만", "bool", False, None),
    ("중복삭제", "완전히 같은 객체도 하나만 남기기", "bool", True, None),
    ("결합", "일직선 위 겹치거나 맞닿은 선(LINE) 합치기", "bool", False, None),
    ("옮기기", "지우지 않고 레이어만 옮기기", "bool", False, None),
    ("옮길레이어", "옮길 레이어", "str", "겹친객체", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
TYPES = "LINE,LWPOLYLINE,ARC,CIRCLE"


def _line_key(p, q):
    """직선(무한)의 정규 방향·법선 거리."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    if ux < -1e-12 or (abs(ux) <= 1e-12 and uy < 0):
        ux, uy = -ux, -uy
    return ux, uy, -uy * p[0] + ux * p[1]


def _merge(iv, tol):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + tol:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _covered(iv, a, b, tol):
    return any(x <= a + tol and y >= b - tol for x, y in iv)


def _angle_iv(a0, th):
    """호 각 구간 → [0, 2π) 안 구간 목록(넘어가면 둘로)."""
    s, e = (a0, a0 + th) if th > 0 else (a0 + th, a0)
    s %= 2 * math.pi
    e = s + abs(th)
    if e <= 2 * math.pi + 1e-12:
        return [(s, e)]
    return [(s, 2 * math.pi), (0.0, e - 2 * math.pi)]


class Shape:
    def __init__(self, e, tol):
        self.e = e
        self.lines, self.arcs = {}, {}
        for p, q, b in e["pieces"]:
            if math.hypot(q[0] - p[0], q[1] - p[1]) <= tol:
                continue
            if abs(b) < 1e-12:
                ux, uy, d = _line_key(p, q)
                t1, t2 = sorted((p[0] * ux + p[1] * uy, q[0] * ux + q[1] * uy))
                self.lines.setdefault((ux, uy, d), []).append((t1, t2))
            else:
                c, r, a0, th = G.arc_of(p, q, b)
                self.arcs.setdefault((c[0], c[1], r), []).extend(_angle_iv(a0, th))
        pts = G.polygon(e["pieces"], 10.0) + [q for _p, q, _b in e["pieces"]]
        xs, ys = [p[0] for p in pts] or [0], [p[1] for p in pts] or [0]
        self.box = (min(xs), min(ys), max(xs), max(ys))

    def find_line(self, key, tol, atol):
        for k, iv in self.lines.items():
            if abs(k[0] - key[0]) <= atol and abs(k[1] - key[1]) <= atol and abs(k[2] - key[2]) <= tol:
                yield iv

    def covers(self, other, tol):
        atol = max(tol * 1e-3, 1e-9)
        for key, ivs in other.lines.items():
            mine = [x for iv in self.find_line(key, tol, atol) for x in iv]
            m = _merge(mine, tol)
            if not all(_covered(m, a, b, tol) for a, b in ivs):
                return False
        for (cx, cy, r), ivs in other.arcs.items():
            mine = [x for (x0, y0, r0), iv in self.arcs.items()
                    if abs(x0 - cx) <= tol and abs(y0 - cy) <= tol and abs(r0 - r) <= tol for x in iv]
            m = _merge(mine, max(tol / max(r, 1e-9), 1e-9))
            if not all(_covered(m, a, b, max(tol / max(r, 1e-9), 1e-9)) for a, b in ivs):
                return False
        return True


def plan(ents, cfg):
    """→ (지울 핸들 [], 합칠 선 [(남길 핸들, 새 시작, 새 끝, 지울 핸들들)])."""
    tol = 10.0 ** -int(cfg["소수"])
    shapes = [Shape(e, tol) for e in ents if e["pieces"]]
    shapes.sort(key=lambda s: (-s.e["length"], int(s.e["handle"], 16)))
    gone = set()
    for i, a in enumerate(shapes):
        if a.e["handle"] in gone:
            continue
        for b in shapes[i + 1:]:
            if b.e["handle"] in gone:
                continue
            if cfg["같은레이어만"] and a.e["layer"] != b.e["layer"]:
                continue
            if cfg["같은색만"] and a.e["color"] != b.e["color"]:
                continue
            ab, bb = a.box, b.box
            if bb[0] < ab[0] - tol or bb[1] < ab[1] - tol or bb[2] > ab[2] + tol or bb[3] > ab[3] + tol:
                continue
            same = abs(a.e["length"] - b.e["length"]) <= tol
            if same and not cfg["중복삭제"]:
                continue
            if a.covers(b, tol):
                gone.add(b.e["handle"])
    merges = []
    if cfg["결합"]:
        groups = {}
        for s in shapes:
            if s.e["type"] != "LINE" or s.e["handle"] in gone or not s.lines:
                continue
            (key, iv), = s.lines.items()
            k = next((g for g in groups if abs(g[0][0] - key[0]) <= 1e-9 and abs(g[0][1] - key[1]) <= 1e-9
                      and abs(g[0][2] - key[2]) <= tol and g[1] == (s.e["layer"] if cfg["같은레이어만"] else "")), None)
            if k is None:
                k = (key, s.e["layer"] if cfg["같은레이어만"] else "")
                groups[k] = []
            groups[k].append((iv[0][0], iv[0][1], s.e["handle"]))
        for (key, _ly), items in groups.items():
            items.sort()
            cur = [items[0]]
            for it in items[1:] + [None]:
                if it is not None and it[0] <= max(c[1] for c in cur) + tol:
                    cur.append(it)
                    continue
                if len(cur) > 1:
                    ux, uy, d = key
                    t0, t1 = min(c[0] for c in cur), max(c[1] for c in cur)
                    nx, ny = -uy * d, ux * d
                    keep = min(cur, key=lambda c: int(c[2], 16))[2]
                    merges.append((keep, (nx + ux * t0, ny + uy * t0), (nx + ux * t1, ny + uy * t1),
                                   [c[2] for c in cur if c[2] != keep]))
                cur = [it] if it is not None else []
    return sorted(gone), merges


def apply_lisp(gone, merges, cfg):
    out = []
    if gone:
        out.append(each_lisp(gone, '(vla-put-Layer _o "%s")' % ls(cfg["옮길레이어"]) if cfg["옮기기"] else "(vla-Delete _o)",
                             ('(bc:ensure-layer "%s" 1)' % ls(cfg["옮길레이어"])) if cfg["옮기기"] else ""))
    for keep, p, q, drop in merges:
        out.append('(setq _e (handent "%s") _ed (entget _e)) (setq _ed (subst (list 10 %.10f %.10f (cadddr (assoc 10 _ed))) (assoc 10 _ed) _ed))'
                   ' (setq _ed (subst (list 11 %.10f %.10f (cadddr (assoc 11 _ed))) (assoc 11 _ed) _ed)) (entmod _ed)'
                   % (keep, p[0], p[1], q[0], q[1]))
        out.append(each_lisp(drop, "(vla-Delete _o)"))
    return "".join(out)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "겹친 객체 삭제", size="500x420")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="객체 선택 → 겹친 객체 삭제", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n검사할 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s'
                           % (TYPES, G.GEO_LISP), A.PICK_TIMEOUT)
        if rows is None:
            return
        gone, merges = plan(G.parse(rows), cfg)
        code = apply_lisp(gone, merges, cfg)
        if code and self.in_cad(self.acad.lisp_undo, code, 120) is None:
            return
        self.status("겹친 객체 %d개 %s, 합친 선 묶음 %d개" % (len(gone), "옮김" if cfg["옮기기"] else "삭제", len(merges)))


def main():
    Window().mainloop()
