# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""FTF 누락 글꼴 대체 — 이 PC에 없는 글꼴(SHX·트루타입·큰 글꼴)을 쓰는 문자 스타일을 고른 글꼴로 바꾼다.

글꼴이 없으면 문자가 ? 로 보이거나 다른 글꼴로 대신 그려진다. '모든 스타일'이면 있는 글꼴도 모두 바꾼다.
SHX는 AutoCAD 지원 경로(findfile), 트루타입은 윈도우 글꼴 폴더(사용자 글꼴 포함)에서 찾는다. 지금 도면에만 한다.
missing()은 창 없이도 쓴다(MCP skill_run).
"""

import os
import tkinter as tk

from skills.common import acad as A
from skills.common import settings as S
from skills.common import ui
from validators import lisp_str as ls  # src: LISP 문자열 이스케이프(역슬래시·따옴표)

CMD = "FTF"
MODES = ["없는 글꼴 스타일만", "모든 스타일"]
FIELDS = [
    ("방식", "바꿀 스타일", "choice", MODES[0], MODES),
    ("글꼴", "바꿀 글꼴 파일 (예 malgun.ttf, romans.shx)", "str", "malgun.ttf", None),
    ("큰글꼴", "큰 글꼴 (SHX 글꼴일 때, 예 whgtxt.shx — 트루타입이면 비움)", "str", "", None),
]
DEFAULTS = {k: d for k, _l, _t, d, _c in FIELDS}

# S<탭>이름<탭>글꼴<탭>큰글꼴<탭>글꼴 찾음(경로)<탭>큰글꼴 찾음
DUMP_LISP = (
    '(defun _ftf-find (f) (cond ((or (not f) (= f "")) "-") ((findfile f)) ((findfile (strcat f ".shx"))) (T "")))'
    '(setq _s (tblnext "STYLE" T)) (while _s'
    ' (if (and (/= (cdr (assoc 2 _s)) "") (zerop (logand 1 (cdr (assoc 70 _s)))))'
    '  (write-line (strcat "S" _d (cdr (assoc 2 _s)) _d (cdr (assoc 3 _s)) _d (if (assoc 4 _s) (cdr (assoc 4 _s)) "") _d'
    '   (_ftf-find (cdr (assoc 3 _s))) _d (_ftf-find (cdr (assoc 4 _s)))) _fp))'
    ' (setq _s (tblnext "STYLE")))')


def _font_dirs():
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    la = os.environ.get("LOCALAPPDATA")
    if la:
        dirs.append(os.path.join(la, "Microsoft", "Windows", "Fonts"))
    return dirs


def font_exists(name, found):
    """LISP findfile 결과(found)와 윈도우 글꼴 폴더로 판단."""
    if not name:
        return True
    if found and found != "-":
        return True
    base = os.path.basename(name.replace("/", os.sep))
    if os.path.splitext(base)[1].lower() in (".ttf", ".ttc", ".otf"):
        return any(os.path.isfile(os.path.join(d, base)) for d in _font_dirs())
    return False


def parse(rows):
    out = []
    for r in rows:
        c = r.split("\t")
        if c[0] == "S" and len(c) >= 6:
            out.append({"style": c[1], "font": c[2], "bigfont": c[3], "font_ok": font_exists(c[2], c[4]),
                        "big_ok": font_exists(c[3], c[5])})
    return out


def targets(styles, cfg):
    if cfg["방식"] == MODES[1]:
        return [s["style"] for s in styles]
    return [s["style"] for s in styles if not (s["font_ok"] and s["big_ok"])]


def font_path(name):
    """트루타입은 윈도우 글꼴 폴더 전체 경로(파일 이름만 주면 AutoCAD가 '파일러 오류'로 거절한다)."""
    base = os.path.basename(name)
    if os.path.splitext(base)[1].lower() in (".ttf", ".ttc", ".otf"):
        for d in _font_dirs():
            if os.path.isfile(os.path.join(d, base)):
                return os.path.join(d, base)
        raise ValueError("이 PC에 글꼴 %s가 없습니다." % base)
    return None


def fix_lisp(names, cfg):
    """글꼴은 전체 경로로 넣는다. 큰 글꼴을 비우면 스타일 표의 4번 값을 지운다(빈 값은 BigFontFile로 못 넣음)."""
    big = str(cfg["큰글꼴"]).strip()
    ttf = os.path.splitext(str(cfg["글꼴"]))[1].lower() in (".ttf", ".ttc", ".otf")
    fp = font_path(str(cfg["글꼴"]).strip())
    font = '"%s"' % ls(fp) if fp else '(cond ((findfile "%s")) ((findfile "%s.shx")) (T nil))' % (ls(cfg["글꼴"]), ls(cfg["글꼴"]))
    bigx = '(cond ((findfile "%s")) (T nil))' % ls(big) if big and not ttf else "nil"
    return ('(setq _sts (vla-get-TextStyles (vla-get-ActiveDocument (vlax-get-acad-object))) _ff %s _bf %s)'
            '(if (not _ff) (write-line (strcat "ERR" _d "글꼴 파일을 찾지 못했습니다: %s") _fp)'
            ' (progn (foreach _n (list %s) (setq _st (vla-Item _sts _n)) (vla-put-fontFile _st _ff)'
            '  (if _bf (vla-put-BigFontFile _st _bf)'
            '   (progn (setq _e (entget (tblobjname "STYLE" _n)))'
            '    (if (and (assoc 4 _e) (/= (cdr (assoc 4 _e)) "")) (entmod (subst (cons 4 "") (assoc 4 _e) _e))))))'
            ' (vla-Regen (vla-get-ActiveDocument (vlax-get-acad-object)) acAllViewports)))'
            % (font, bigx, ls(cfg["글꼴"]), " ".join('"%s"' % ls(n) for n in names)))


class Window(ui.BaseWindow):
    def __init__(self):
        super().__init__(CMD, "누락 글꼴 대체", size="500x300")
        self.acad = A.Acad()
        body = tk.Frame(self, bg=ui.PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=6)
        self.form = self.form_section(body, "설정", FIELDS, S.load(CMD, DEFAULTS))
        tk.Button(self, text="지금 도면 스타일 글꼴 고치기", command=self.run, bg="#3E5879", fg="#FFFFFF",
                  relief="flat", height=2).pack(fill="x", padx=10, pady=4)

    def run(self):
        try:
            cfg = self.form.values()
        except ValueError as e:
            self.error(str(e))
            return
        S.save(CMD, cfg)
        rows = self.in_cad(self.acad.lisp, DUMP_LISP, 30)
        if rows is None:
            return
        names = targets(parse(rows), cfg)
        if names:
            try:
                code = fix_lisp(names, cfg)
            except ValueError as e:
                self.error(str(e))
                return
            out = self.in_cad(self.acad.lisp_undo, code, 60)
            if out is None:
                return
            err = [r.split("\t", 1)[1] for r in out if r.startswith("ERR\t")]
            if err:
                self.error(err[0])
                return
        self.status("스타일 %d개를 %s(으)로 바꿨습니다%s" % (len(names), cfg["글꼴"], (": " + ", ".join(names[:8])) if names else ""))


def main():
    Window().mainloop()
