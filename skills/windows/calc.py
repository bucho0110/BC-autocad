# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""CALC CAD 계산기 — 문자·치수 값, 객체 길이, 두 점 거리, 면적, 체적을 사칙연산하고 결과를 도면에 쓰거나 문자를 고친다.

산출식 칸에 직접 식을 넣어 계산기처럼 쓸 수도 있다(삼각함수는 도 단위, ^·²·³·√·π 인식).
evaluate()·values_lisp()·expression()은 창 없이도 쓴다(MCP skill_run).
"""

import ast
import math
import operator
import re
import tkinter as tk

from skills.common import acad as A
from skills.common import coords as C
from skills.common import settings as S
from skills.common import ui
from skills.windows import tte
from skills.windows.ttp import num_in_text
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "CALC"
TARGETS = ["문자", "치수", "객체 길이", "거리", "수평 거리", "수직 거리", "수식", "면적(객체)", "체적"]
OPS = ["+", "-", "×", "÷", "평균"]
SCALED = {"객체 길이": 1, "거리": 1, "수평 거리": 1, "수직 거리": 1, "면적(객체)": 2, "체적": 3}  # 축척 차수
JUST = {"왼쪽": "L", "중심": "C", "중앙 중심": "MC", "오른쪽": "R"}
FIELDS = [
    ("대상", "계산 대상", "choice", TARGETS[0], TARGETS),
    ("방식", "계산 방식", "choice", OPS[0], OPS),
    ("축척", "축척 (1000=m 도면, 1=mm 도면 — 길이·거리·면적·체적)", "real", 1000.0, None),
    ("소수", "결과 소수 자리", "int", 3, None),
    ("식소수", "산출식 값 소수 자리", "int", 3, None),
    ("이전식삭제", "새로 고를 때 이전 산출식 지우기", "bool", True, None),
    ("높이", "결과 문자 높이 (도면 단위)", "real", 2.5, None),
    ("DIMSCALE적용", "문자 높이에 DIMSCALE 곱하기", "bool", False, None),
    ("레이어", "결과 문자 레이어 (비우면 현재 레이어)", "str", "", None),
    ("정렬", "결과 문자 정렬", "choice", "왼쪽", list(JUST)),
    ("각도", "결과 문자 각도 (도)", "real", 0.0, None),
    ("천단위", "천 단위 쉼표", "bool", False, None),
    ("머리말", "결과 머리말 (예: L=)", "str", "", None),
    ("꼬리말", "결과 꼬리말 (예: m)", "str", "", None),
    ("식포함", "도면에 산출식도 함께 쓰기", "bool", False, None),
    ("연산자공백", "산출식 연산자 앞뒤 공백 수", "int", 1, None),
    ("수정색", "문자 수정 시 바꿀 색 (ACI, 0=안 바꿈)", "int", 0, None),
    ("클립보드", "계산 후 클립보드에 복사", "choice", "복사 안 함", ["복사 안 함", "결과값", "산출식"]),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

# ---------------------------------------------------------------- 식 계산

_RAD = math.radians
_FUN = {
    "sin": lambda d: math.sin(_RAD(d)), "cos": lambda d: math.cos(_RAD(d)), "tan": lambda d: math.tan(_RAD(d)),
    "cot": lambda d: 1.0 / math.tan(_RAD(d)),
    "arcsin": lambda v: math.degrees(math.asin(v)), "arccos": lambda v: math.degrees(math.acos(v)),
    "arctan": lambda v: math.degrees(math.atan(v)), "arccot": lambda v: math.degrees(math.atan(1.0 / v)),
    "sqrt": math.sqrt, "abs": abs,
}
_CONST = {"pi": math.pi}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow}
_TOKEN = re.compile(r"\d+(?:\.\d*)?|\.\d+|\*\*|[-+*/()]|[A-Za-z]+")


def clean(expr: str) -> str:
    """도면 문자·사람 입력 → 파이썬 식. 모르는 글자(한글 설명, '=' 등)는 버린다."""
    s = str(expr)
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)  # 천 단위 쉼표
    for a, b in (("×", "*"), ("÷", "/"), ("√", "sqrt"), ("π", "pi"), ("^", "**"),
                 ("²", "**2"), ("³", "**3"), ("⁴", "**4"), ("−", "-")):
        s = s.replace(a, b)
    s = re.sub(r"(?<=[\d)\s])[xX](?=\s*[\d(.])", "*", s)  # 5.0x2.0 · 5 X 2
    out = []
    for t in _TOKEN.findall(s):
        if t[0].isalpha() and t.lower() not in _FUN and t.lower() not in _CONST:
            continue
        out.append(t.lower() if t[0].isalpha() else t)
    return " ".join(out)


def _ev(n):
    if isinstance(n, ast.Expression):
        return _ev(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return float(n.value)
    if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and abs(b) > 100:
            raise ValueError("지수가 너무 큽니다")
        return _BIN[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _ev(n.operand)
        return -v if isinstance(n.op, ast.USub) else v
    if isinstance(n, ast.Name) and n.id in _CONST:
        return _CONST[n.id]
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUN and len(n.args) == 1:
        return float(_FUN[n.func.id](_ev(n.args[0])))
    raise ValueError("계산할 수 없는 식입니다")


def evaluate(expr: str) -> float:
    s = clean(expr)
    if not s:
        raise ValueError("식에 숫자가 없습니다")
    try:
        return _ev(ast.parse(s, mode="eval"))
    except SyntaxError:
        raise ValueError("식 모양이 맞지 않습니다: %s" % s)
    except ZeroDivisionError:
        raise ValueError("0으로 나눌 수 없습니다")


# ---------------------------------------------------------------- 도면 값

PICK_TYPES = {"문자": "TEXT,MTEXT", "치수": "DIMENSION", "수식": "TEXT,MTEXT",
              "객체 길이": "LINE,LWPOLYLINE,POLYLINE,SPLINE,ARC,CIRCLE,ELLIPSE",
              "면적(객체)": "LWPOLYLINE,POLYLINE,CIRCLE,ELLIPSE,SPLINE,HATCH,REGION", "체적": "3DSOLID"}


def values_lisp(target: str) -> str:
    """선택 집합 _ss의 값 → 'V<탭>핸들<탭>값(문자는 내용)' 줄."""
    if target in ("문자", "수식"):
        val = "(bc:text-of _en)"
    elif target == "치수":
        return tte.dump_lisp({"문자기준": "삽입점", "속성태그": ""})
    elif target == "객체 길이":
        val = "(bc:rtos (vlax-curve-getDistAtParam _en (vlax-curve-getEndParam _en)) 2 10)"
    elif target == "면적(객체)":
        val = ('(if (not (vl-catch-all-error-p (setq _v (vl-catch-all-apply (quote vla-get-Area)'
               ' (list (vlax-ename->vla-object _en)))))) (bc:rtos _v 2 10))')
    else:
        val = ('(if (not (vl-catch-all-error-p (setq _v (vl-catch-all-apply (quote vla-get-Volume)'
               ' (list (vlax-ename->vla-object _en)))))) (bc:rtos _v 2 10))')
    return ('(if _ss (progn (setq _i 0) (while (< _i (sslength _ss)) (setq _en (ssname _ss _i) _i (1+ _i))'
            ' (if (setq _t %s) (write-line (strcat "V" _d (cdr (assoc 5 (entget _en))) _d'
            ' (vl-string-translate "\\t\\n\\r" "   " _t)) _fp)))))' % val)


def parse_values(rows, target):
    """values_lisp 결과 → [숫자] (숫자가 없는 문자는 건너뛴다). 수식은 [문자 그대로]."""
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "T" and len(c) == 5:  # 치수(tte 덤프 형식)
            c = ["V", c[1], c[4]]
        if c[0] != "V" or len(c) < 3:
            continue
        if target == "수식":
            out.append(c[2])
        elif target in ("문자", "치수"):
            v = num_in_text(c[2])
            if v is not None:
                out.append(v)
        else:
            out.append(float(c[2]))
    return out


DIST_LISP = ('(setq _p (getpoint "\\n첫 점 지정: "))'
             ' (while (and _p (setq _q (getpoint _p "\\n다음 점 지정 (끝내려면 엔터): ")))'
             ' (setq _a (trans _p 1 0) _b (trans _q 1 0))'
             ' (write-line (strcat "D" _d (bc:rtos (car _a) 2 10) _d (bc:rtos (cadr _a) 2 10) _d'
             ' (bc:rtos (car _b) 2 10) _d (bc:rtos (cadr _b) 2 10)) _fp) (setq _p _q))')


def distances(pairs, target):
    """[(x1,y1,x2,y2)] → 거리 목록(수평은 X 차, 수직은 Y 차)."""
    out = []
    for x1, y1, x2, y2 in pairs:
        out.append(abs(x2 - x1) if target == "수평 거리" else abs(y2 - y1) if target == "수직 거리"
                   else math.hypot(x2 - x1, y2 - y1))
    return out


def parse_dist(rows):
    return [tuple(float(v) for v in r.split("\t")[1:5]) for r in rows if r.startswith("D\t")]


def scaled(vals, target, scale):
    """도면 단위 → m(축척 1000 = 1m가 도면 1). 길이 1차, 면적 2차, 체적 3차."""
    k = SCALED.get(target, 0)
    if not k:
        return vals
    u = 1000.0 / (scale if scale and scale > 0 else 1000.0)
    return [v / u ** k for v in vals]


def expression(vals, op, dec, spaces=1) -> str:
    """값 목록 → 산출식. 평균은 (a + b) / n."""
    if not vals:
        return ""
    sym = {"+": "+", "-": "-", "×": "*", "÷": "/", "평균": "+"}[op]
    sp = " " * max(0, int(spaces))
    body = (sp + sym + sp).join(("(%s)" % C.fmt(v, dec)) if v < 0 else C.fmt(v, dec) for v in vals)
    return "(%s)%s/%s%d" % (body, sp, sp, len(vals)) if op == "평균" and len(vals) > 1 else body


def result_text(expr, value, cfg) -> str:
    v = C.fmt(value, cfg["소수"])
    if cfg["천단위"]:
        neg = v.startswith("-")
        ip, _, fp = v.lstrip("-").partition(".")
        v = ("-" if neg else "") + "{:,}".format(int(ip)) + ("." + fp if fp else "")
    s = cfg["머리말"] + v + cfg["꼬리말"]
    return "%s = %s" % (expr, s) if cfg["식포함"] and expr else s


def write_lisp(pt_expr, text, cfg) -> str:
    """결과 문자 쓰기. pt_expr는 WCS 점 LISP 식."""
    h = "(* %.6f (getvar \"DIMSCALE\"))" % cfg["높이"] if cfg["DIMSCALE적용"] else "%.6f" % cfg["높이"]
    return ('(bc:text %s "%s" %s "%s" "%s" %.10f)'
            % (pt_expr, ls(text), h, ls(cfg["레이어"]), JUST[cfg["정렬"]], math.radians(cfg["각도"])))


def replace_lisp(en_expr, text, cfg) -> str:
    """문자 내용 바꾸기(MTEXT 긴 내용 조각 3은 지운다). 바꾸면 OK 줄."""
    col = int(cfg["수정색"])
    c = ("(setq _e (if (assoc 62 _e) (subst (cons 62 %d) (assoc 62 _e) _e) (append _e (list (cons 62 %d)))))"
         % (col, col)) if col > 0 else ""
    return ('(setq _e (entget %s)) (if (member (cdr (assoc 0 _e)) (quote ("TEXT" "MTEXT"))) (progn'
            ' (setq _e (vl-remove-if (quote (lambda (x) (= (car x) 3))) _e) _e (subst (cons 1 "%s") (assoc 1 _e) _e)) %s'
            ' (if (entmod _e) (write-line "OK" _fp))))' % (en_expr, ls(text), c))


def compute(target, vals, cfg):
    """(산출식, 결과값). 수식 대상은 고른 문자 식들을 방식으로 잇는다."""
    if target == "수식":
        sym = {"+": "+", "-": "-", "×": "*", "÷": "/", "평균": "+"}[cfg["방식"]]
        sp = " " * max(0, int(cfg["연산자공백"]))
        expr = (sp + sym + sp).join("(%s)" % clean(v) for v in vals) if len(vals) > 1 else (vals[0] if vals else "")
        if cfg["방식"] == "평균" and len(vals) > 1:
            expr = "(%s)%s/%s%d" % (expr, sp, sp, len(vals))
    else:
        expr = expression(scaled(vals, target, cfg["축척"]), cfg["방식"], cfg["식소수"], cfg["연산자공백"])
    return expr, evaluate(expr)


def run_mcp(ctl, doc, lib, a, t1, merged_cfg, lq, draw):
    """skill_run CALC: expression(직접 식) 또는 settings.대상 + handles(문자·치수·길이·면적·체적)/points(거리).
    write_point [x,y]면 결과 문자 쓰기, replace_handle이면 그 문자 내용 바꾸기."""
    cfg = merged_cfg(CMD, DEFAULTS, a.get("settings"))
    target = cfg["대상"]
    if a.get("expression"):
        expr = str(a["expression"])
        value = evaluate(expr)
    else:
        if target in ("거리", "수평 거리", "수직 거리"):
            pts = a.get("points") or []
            if len(pts) < 2:
                raise ValueError("거리는 points [[x,y], …] 두 점 이상이 필요합니다(이어진 점 사이 거리).")
            vals = distances([(p[0], p[1], q[0], q[1]) for p, q in zip(pts, pts[1:])], target)
        else:
            if not a.get("handles"):
                raise ValueError("handles(계산할 객체)나 expression이 필요합니다.")
            sel = ('(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                   % " ".join(lq(h) for h in a["handles"]))
            vals = parse_values(ctl.lisp(lib + sel + values_lisp(target), doc=doc, timeout_s=t1), target)
        if not vals:
            raise ValueError("고른 객체에서 값을 얻지 못했습니다(대상 %s)." % target)
        expr, value = compute(target, vals, cfg)
    text = result_text(expr, value, cfg)
    res = {"drawing": doc.Name, "expression": expr, "result": float(C.fmt(value, cfg["소수"])), "text": text}
    if a.get("write_point"):
        p = list(a["write_point"]) + [0.0]
        draw("(setq _r %s)" % write_lisp("(list %.10f %.10f 0.0)" % (p[0], p[1]), text, cfg))
        res["written"] = True
    if a.get("replace_handle"):
        res["replaced"] = bool(ctl.lisp(lib + replace_lisp("(handent %s)" % lq(a["replace_handle"]), text, cfg),
                                        doc=doc, timeout_s=t1))
    return res


# ---------------------------------------------------------------- 창

class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "CAD 계산기", size="560x900")
        self.acad = A.Acad()
        self.ans = None
        self.value = None
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        vals = S.load(CMD, DEFAULTS)
        self.form = self.form_section(body, "계산·문자 설정", FIELDS, vals)

        self.section(body, "산출식 (직접 입력 후 엔터도 됨)")
        self.var_expr = tk.StringVar()
        ent = tk.Entry(body, textvariable=self.var_expr, font=ui.FONT)
        ent.pack(fill="x", pady=2)
        ent.bind("<Return>", lambda _e: self.calc())
        self.var_res = tk.StringVar(value="결과: -")
        tk.Label(body, textvariable=self.var_res, bg=ui.PANEL, fg=ui.ACCENT, font=ui.FONT_B, anchor="w").pack(fill="x")
        row = tk.Frame(body, bg=ui.PANEL)
        row.pack(fill="x", pady=3)
        for t, fn in (("도면에서 선택", self.pick), ("=", self.calc), ("ANS", self.put_ans), ("AC", self.clear),
                      ("문자 쓰기", self.write), ("문자 수정", self.replace)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat").pack(
                side="left", expand=True, fill="x", padx=1)
        self.section(body, "지난 계산 (고르면 다시 계산)")
        self.hist = tk.Listbox(body, height=5, font=ui.FONT)
        self.hist.pack(fill="both", expand=True)
        self.hist.bind("<<ListboxSelect>>", self.from_hist)

    def _cfg(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        return cfg

    def _show(self, expr, value, cfg):
        self.value, self.ans = value, value
        self.var_expr.set(expr)
        self.var_res.set("결과: " + result_text("", value, dict(cfg, 식포함=False)))
        self.hist.insert(0, expr)
        clip = cfg["클립보드"]
        if clip != "복사 안 함":
            self.clipboard_clear()
            self.clipboard_append(C.fmt(value, cfg["소수"]) if clip == "결과값" else expr)

    def pick(self):
        try:
            cfg = self._cfg()
        except ValueError as e:
            self.error(str(e))
            return
        target = cfg["대상"]
        if target in ("거리", "수평 거리", "수직 거리"):
            rows = self.in_cad(self.acad.lisp, DIST_LISP, A.PICK_TIMEOUT)
            vals = distances(parse_dist(rows), target) if rows else []
        else:
            body = ('(princ "\\n%s 객체 선택: ") (setq _ss (ssget (list (cons 0 "%s")))) %s'
                    % (target, PICK_TYPES[target], values_lisp(target)))
            rows = self.in_cad(self.acad.lisp, body, A.PICK_TIMEOUT)
            vals = parse_values(rows, target) if rows else []
        if not vals:
            self.status("값을 얻지 못했습니다.")
            return
        try:
            expr, _v = compute(target, vals, cfg)
            old = self.var_expr.get().strip()
            if not cfg["이전식삭제"] and old:
                sym = {"평균": "+", "×": "*", "÷": "/"}.get(cfg["방식"], cfg["방식"])
                expr = "%s %s %s" % (old, sym, expr)
            self._show(expr, evaluate(expr), cfg)
            self.status("%s %d개를 계산했습니다." % (target, len(vals)))
        except ValueError as e:
            self.error(str(e))

    def calc(self):
        try:
            cfg = self._cfg()
            expr = self.var_expr.get()
            self._show(expr, evaluate(expr), cfg)
        except ValueError as e:
            self.error(str(e))

    def put_ans(self):
        if self.ans is not None:
            self.var_expr.set(self.var_expr.get() + repr(self.ans))

    def clear(self):
        self.var_expr.set("")
        self.var_res.set("결과: -")
        self.value = None

    def from_hist(self, _e=None):
        sel = self.hist.curselection()
        if sel:
            self.var_expr.set(self.hist.get(sel[0]))
            try:
                cfg = self._cfg()
                self.value = evaluate(self.var_expr.get())
                self.var_res.set("결과: " + result_text("", self.value, dict(cfg, 식포함=False)))
            except ValueError as e:
                self.error(str(e))

    def write(self):
        if self.value is None:
            self.error("먼저 계산하세요.")
            return
        cfg = self._cfg()
        text = result_text(self.var_expr.get(), self.value, cfg)
        body = '(setq _p (getpoint "\\n결과 문자 위치: ")) (if _p (progn %s (write-line "OK" _fp)))' % write_lisp(
            "(trans _p 1 0)", text, cfg)
        if self.in_cad(self.acad.lisp_undo, body, A.PICK_TIMEOUT):
            self.status("도면에 썼습니다: " + text)

    def replace(self):
        if self.value is None:
            self.error("먼저 계산하세요.")
            return
        cfg = self._cfg()
        text = result_text(self.var_expr.get(), self.value, cfg)
        body = '(setq _s (entsel "\\n내용을 바꿀 문자 선택: ")) (if _s (progn %s))' % replace_lisp("(car _s)", text, cfg)
        if self.in_cad(self.acad.lisp_undo, body, A.PICK_TIMEOUT):
            self.status("문자를 바꿨습니다: " + text)


def main():
    Window().mainloop()
