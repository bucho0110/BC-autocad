# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""ADD 문자 속 숫자 사칙연산 — 고른 문자(치수 문자 포함)의 숫자에 같은 값을 더하고 빼고 곱하고 나눈다.

글자가 섞여 있으면 맨 뒤 숫자(또는 맨 앞 숫자)만 바꾼다: EL=123.45 → EL=124.05, GL-100 + 200 → GL100(+ 기호 켜면 GL+100).
측점 인식을 켜면 1+250·0K120 같은 측점을 거리로 읽어 증감하고 같은 형식으로 쓴다.
치수는 측정값(또는 재지정 문자)에 계산해 재지정 문자로 넣는다. new_text()는 창 없이도 쓴다(MCP skill_run).
"""

import re
import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "ADD"
OPS = ["+/-", "×", "÷"]
FIELDS = [
    ("값", "증감 숫자 (빼기는 -10)", "str", "1", None),
    ("계산", "계산 방식", "choice", OPS[0], OPS),
    ("자리수", "자리 수 (앞을 0으로, 1 = 채우지 않음)", "int", 1, None),
    ("소수", "소수 자리 (-1 = 원래 문자 따름)", "int", -1, None),
    ("천단위", "천 단위 구분 기호", "bool", False, None),
    ("부호", "양수에 + 기호", "bool", False, None),
    ("16진수", "16진수로 계산", "bool", False, None),
    ("위치", "바꿀 숫자", "choice", "맨 뒤 숫자", ["맨 뒤 숫자", "맨 앞 숫자"]),
    ("측점", "측점(1+250·0K120) 인식", "bool", False, None),
    ("km구분", "측점 km 구분 문자", "str", "+", None),
    ("치수", "치수 문자도 바꾸기", "bool", True, None),
    ("색변경", "바꾼 문자 색 바꾸기", "bool", False, None),
    ("색", "바꿀 색 (ACI)", "int", 1, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
_NUM = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?|[-+]?\.\d+")
_HEX = re.compile(r"[0-9A-Fa-f]+")

# X<탭>핸들<탭>종류<탭>내용(문자 그대로, MTEXT 서식 포함)<탭>측정값(치수)<탭>재지정
DUMP_LISP = (
    '(foreach _en (bc:ss-list _ss) (setq _ed (entget _en) _ty (cdr (assoc 0 _ed)))'
    ' (write-line (strcat "X" _d (cdr (assoc 5 _ed)) _d _ty _d'
    '  (vl-string-translate "\\t\\n\\r" "   " (if (member _ty (list "TEXT" "MTEXT")) (vla-get-TextString (vlax-ename->vla-object _en)) ""))'
    '  _d (if (wcmatch _ty "*DIMENSION") (bc:rtos (vla-get-Measurement (vlax-ename->vla-object _en)) 2 10) "")'
    '  _d (if (wcmatch _ty "*DIMENSION") (vl-string-translate "\\t\\n\\r" "   " (cdr (assoc 1 _ed))) "")) _fp))')


def _calc(v, cfg):
    k = float(cfg["값"])
    return v + k if cfg["계산"] == OPS[0] else v * k if cfg["계산"] == OPS[1] else v / k


def _fmt(v, dec, cfg, keep_sign_char=False, comma=False):
    s = "%.*f" % (max(0, dec), v)
    neg = s.startswith("-")
    ip, _, fp = s.lstrip("-").partition(".")
    ip = ip.zfill(max(1, int(cfg["자리수"])))
    if (cfg["천단위"] or comma) and len(ip) > 3:
        ip = "{:,}".format(int(ip))
    sign = "-" if neg else ("+" if (cfg["부호"] or keep_sign_char) and v > 0 else "")
    return sign + ip + ("." + fp if fp else "")


def new_number(tok, cfg):
    """숫자 글자 하나 → 바꾼 글자."""
    if cfg["16진수"]:
        v = int(tok, 16) + int(str(cfg["값"]), 16) * (1 if cfg["계산"] == OPS[0] else 0)
        if cfg["계산"] == OPS[1]:
            v = int(tok, 16) * int(str(cfg["값"]), 16)
        elif cfg["계산"] == OPS[2]:
            v = int(tok, 16) // int(str(cfg["값"]), 16)
        s = format(v, "X")
        return s.lower() if tok == tok.lower() and any(c.isalpha() for c in tok) else s
    clean = tok.replace(",", "")
    dec = int(cfg["소수"]) if int(cfg["소수"]) >= 0 else len(clean.partition(".")[2])
    return _fmt(_calc(float(clean), cfg), dec, cfg, keep_sign_char=tok.startswith("+"), comma="," in tok)


def new_text(s, cfg):
    """문자 내용 → 바꾼 내용(숫자가 없으면 None)."""
    if cfg["측점"]:
        sep = re.escape(str(cfg["km구분"]) or "+")
        m = list(re.finditer(r"(\d+)%s(\d+(?:\.\d+)?)" % sep, s))
        if m:
            m = m[-1] if cfg["위치"] == "맨 뒤 숫자" else m[0]
            km, rest = m.group(1), m.group(2)
            dec = int(cfg["소수"]) if int(cfg["소수"]) >= 0 else len(rest.partition(".")[2])
            d = _calc(int(km) * 1000 + float(rest), cfg)
            k = int(d // 1000)
            r = "%0*.*f" % (len(rest.partition(".")[0]) + (dec + 1 if dec else 0), dec, d - k * 1000)
            return s[:m.start()] + "%d%s%s" % (k, cfg["km구분"] or "+", r) + s[m.end():]
    ms = list((_HEX if cfg["16진수"] else _NUM).finditer(s))
    if not ms:
        return None
    m = ms[-1] if cfg["위치"] == "맨 뒤 숫자" else ms[0]
    tok = m.group(0)
    start = m.start()
    if not cfg["16진수"] and tok[0] in "+-" and start > 0 and (s[start - 1].isdigit()):
        tok, start = tok[1:], start + 1  # 1-2 처럼 앞 글자가 숫자면 - 는 빼기 기호가 아니라 구분
    return s[:start] + new_number(tok, cfg) + s[start + len(tok):]


def plan(items, cfg):
    """items [{handle, type, text, measure, override}] → [(핸들, 새 문자, 치수 여부)]."""
    out = []
    for it in items:
        if "DIMENSION" in it["type"]:
            if not cfg["치수"]:
                continue
            ov = it["override"]
            base = ov.replace("<>", it["measure"]) if ov and ov != " " else it["measure"]
            t = new_text(base, cfg)
            if t is not None:
                out.append((it["handle"], t, True))
        else:
            t = new_text(it["text"], cfg)
            if t is not None and t != it["text"]:
                out.append((it["handle"], t, False))
    return out


def parse(rows):
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "X" and len(c) >= 6:
            out.append({"handle": c[1], "type": c[2], "text": c[3], "measure": c[4], "override": c[5]})
    return out


def apply_lisp(changes, cfg):
    out = []
    for h, t, dim in changes:
        o = '(vlax-ename->vla-object (handent "%s"))' % h
        out.append('(vla-put-%s %s "%s")' % ("TextOverride" if dim else "TextString", o, ls(t)))
        if cfg["색변경"]:
            out.append('(vla-put-Color %s %d)' % (o, int(cfg["색"])))
    return "".join(out)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "문자 속 숫자 사칙연산", size="500x620")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="문자·치수 선택 → 숫자 증감", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
            float(cfg["값"]) if not cfg["16진수"] else int(str(cfg["값"]), 16)
        except ValueError as e:
            self.error("증감 숫자를 확인하세요: %s" % e)
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, '(princ "\\n바꿀 문자 선택: ") (setq _ss (ssget (list (cons 0 "TEXT,MTEXT%s")))) %s'
                           % (",DIMENSION" if cfg["치수"] else "", DUMP_LISP), A.PICK_TIMEOUT)
        if rows is None:
            return
        ch = plan(parse(rows), cfg)
        if ch and self.in_cad(self.acad.lisp_undo, apply_lisp(ch, cfg), 60) is None:
            return
        self.status("%d개를 바꿨습니다%s" % (len(ch), (" (예: %s)" % ch[0][1]) if ch else ""))


def main():
    Window().mainloop()
