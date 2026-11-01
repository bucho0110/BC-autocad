# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""INN ? 자리 일련번호 매기기 — 문자 내용 중 '?' 자리를 숫자(또는 알파벳·16진수)로 늘려 가며 새로 쓰거나 기존 문자를 고친다.

예: '횡 단 면 도 (?/6)', 시작 1, 증분 1 → 횡 단 면 도 (1/6), (2/6) …
기존 문자 고치기는 블록 안 문자·속성 문자도 된다(nentsel).
values()·pattern_text()는 창 없이도 쓴다(MCP skill_run).
"""

import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "INN"
FIELDS = [
    ("내용", "문자 내용 (증가할 자리에 ?)", "str", "", None),
    ("시작값", "시작 값 (숫자, 알파벳 A·a, 16진수)", "str", "1", None),
    ("증분", "증분 값", "str", "1", None),
    ("자리수", "자리 수 (앞을 0으로 채움, 1=채우지 않음)", "int", 1, None),
    ("소수", "소수 자리", "int", 0, None),
    ("천단위", "천 단위 구분 기호", "bool", False, None),
    ("16진수", "16진수로 증가", "bool", False, None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}
MAX_N = 500


def _col(s):
    """엑셀 열 이름 → 번호(A=1, Z=26, AA=27)."""
    n = 0
    for ch in s.upper():
        n = n * 26 + ord(ch) - 64
    return n


def _col_name(n, lower):
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out.lower() if lower else out


def value(k, cfg):
    """k번째(0부터) 값 문자."""
    start, step = str(cfg["시작값"]).strip(), str(cfg["증분"]).strip() or "1"
    if cfg["16진수"]:
        v = int(start or "0", 16) + k * int(step, 16)
        s = format(v, "X")
        return s.lower() if start and start == start.lower() and any(c.isalpha() for c in start) else s
    if start.isalpha() and start.isascii():
        return _col_name(_col(start) + k * int(float(step)), start == start.lower())
    v = float(start or "0") + k * float(step)
    dec = max(0, int(cfg["소수"]))
    s = "%.*f" % (dec, v)
    neg = s.startswith("-")
    ip, _, fp = s.lstrip("-").partition(".")
    ip = ip.zfill(max(1, int(cfg["자리수"])))
    if cfg["천단위"]:
        ip = "{:,}".format(int(ip)) if len(ip) > 3 and not ip.startswith("0") else ip
    return ("-" if neg else "") + ip + ("." + fp if fp else "")


def pattern_text(k, cfg):
    return str(cfg["내용"]).replace("?", value(k, cfg))


def values(cfg, n):
    if "?" not in str(cfg["내용"]):
        raise ValueError("문자 내용에 증가할 자리(?)가 없습니다.")
    return [pattern_text(k, cfg) for k in range(n)]


def copy_lisp(src_expr, vals, base, points) -> str:
    """원본 문자를 base→각 점으로 옮긴 자리에 vals 내용으로 복사한다. 점은 WCS LISP 식 목록."""
    out = ['(setq _src (vlax-ename->vla-object %s) _bp %s)' % (src_expr, base)]
    for v, p in zip(vals, points):
        out.append('(setq _c (vla-Copy _src)) (vla-Move _c (vlax-3d-point _bp) (vlax-3d-point %s))'
                   ' (vla-put-TextString _c "%s")' % (p, ls(v)))
    return "".join(out)


def modify_lisp(vals_expr) -> str:
    """사람이 고르는 문자마다 다음 값으로 바꾼다(블록 안·속성 포함). 엔터로 끝."""
    return ('(setq _vals %s _k 0)'
            '(while (and (< _k (length _vals))'
            ' (setq _s (nentsel (strcat "\\n바꿀 문자 선택 → " (nth _k _vals) " (끝내려면 엔터): "))))'
            ' (setq _e (car _s) _ed (entget _e))'
            ' (if (member (cdr (assoc 0 _ed)) (quote ("TEXT" "MTEXT" "ATTRIB")))'
            '  (progn (vla-put-TextString (vlax-ename->vla-object _e) (nth _k _vals))'
            '   (if (cadddr _s) (foreach _b (cadddr _s) (entupd _b)))'
            '   (entupd _e) (setq _k (1+ _k)) (write-line (nth (1- _k) _vals) _fp))'
            '  (princ "\\n문자가 아닙니다.")))' % vals_expr)


def lisp_list(vals):
    return "(list %s)" % " ".join('"%s"' % ls(v) for v in vals)


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "? 자리 일련번호 매기기", size="500x470")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        self.var_prev = tk.StringVar(value="")
        tk.Label(body, textvariable=self.var_prev, bg=ui.PANEL, fg=ui.ACCENT, font=ui.FONT, anchor="w",
                 justify="left").pack(fill="x", pady=4)
        row = tk.Frame(self, bg=ui.BG)
        row.pack(fill="x", padx=10, pady=4)
        for t, fn in (("문자 내용 가져오기", self.pick), ("미리보기", self.preview),
                      ("선택 문자 복사", self.copy), ("기존 문자 수정", self.modify)):
            tk.Button(row, text=t, command=fn, bg="#3E5879", fg="#FFFFFF", relief="flat").pack(
                side="left", expand=True, fill="x", padx=1)
        self.src = None
        for var, _t, _d in self.form.vars.values():  # 바꾸는 즉시 미리보기
            var.trace_add("write", lambda *_a: self.after_idle(self.preview))
        self.preview()

    def _cfg(self):
        cfg = self.form.values()
        S.save(CMD, cfg)
        return cfg

    def preview(self):
        try:
            v = values(self._cfg(), 2)
            self.var_prev.set("미리보기: %s\n             %s" % (v[0], v[1]))
        except ValueError as e:
            self.var_prev.set("미리보기: %s" % e)

    def pick(self):
        rows = self.in_cad(self.acad.lisp, '(setq _s (entsel "\\n증가시킬 문자 선택: ")) (if _s (progn'
                           ' (setq _e (car _s)) (if (bc:text-of _e) (write-line (strcat (cdr (assoc 5 (entget _e))) _d'
                           ' (bc:text-of _e)) _fp))))', A.PICK_TIMEOUT)
        if rows:
            h, txt = rows[0].split("\t", 1)
            self.src = h
            self.form.vars["내용"][0].set(txt)
            self.status("가져왔습니다: %s — 증가할 자리를 ?로 바꾸세요." % txt)

    def copy(self):
        if not self.src:
            self.error("먼저 [문자 내용 가져오기]로 복사할 문자를 고르세요.")
            return
        try:
            vals = values(self._cfg(), MAX_N)
        except ValueError as e:
            self.error(str(e))
            return
        body = ('(setq _src (vlax-ename->vla-object (handent "%s")) _vals %s _k 0'
                ' _bp (getpoint "\\n복사 기준점 지정: "))'
                ' (while (and _bp (< _k (length _vals))'
                '  (setq _p (getpoint _bp (strcat "\\n" (nth _k _vals) " 쓸 점 지정 (끝내려면 엔터): "))))'
                '  (setq _c (vla-Copy _src)) (vla-Move _c (vlax-3d-point (trans _bp 1 0)) (vlax-3d-point (trans _p 1 0)))'
                '  (vla-put-TextString _c (nth _k _vals)) (write-line (nth _k _vals) _fp) (setq _k (1+ _k)))'
                % (ls(self.src), lisp_list(vals)))
        done = self.in_cad(self.acad.lisp_undo, body, A.PICK_TIMEOUT)
        if done is not None:
            self.status("%d개를 썼습니다%s" % (len(done), (" (마지막: %s)" % done[-1]) if done else ""))

    def modify(self):
        try:
            vals = values(self._cfg(), MAX_N)
        except ValueError as e:
            self.error(str(e))
            return
        done = self.in_cad(self.acad.lisp_undo, modify_lisp(lisp_list(vals)), A.PICK_TIMEOUT)
        if done is not None:
            self.status("%d개를 고쳤습니다%s" % (len(done), (" (마지막: %s)" % done[-1]) if done else ""))


def main():
    Window().mainloop()
