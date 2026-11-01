# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""개발용: registry로 skills/lisp/bc_windows.lsp·bc_00_guard.lsp·bc_zz_alias.lsp를 만든다(명령을 더하거나 고친 뒤 실행).

창 명령(kind=window)은 AutoCAD에서 치면 창을 띄운다. 도움말 명령 BCHELP도 여기서 만든다.
명령 이름: 기본은 BC를 붙인 이름(BCFE…)만 쓴다. BC 없는 짧은 이름(FE…)은 사람이 BCHELP 창에서 체크한 명령만 켠다
(설정 %LOCALAPPDATA%/bc-autocad/settings/shortnames.txt). 상황에 따라 저절로 켜거나 끄지 않는다.
bc_00_guard.lsp(명령 파일보다 먼저)는 같은 이름을 먼저 쓰던 다른 리습 명령을 기억하고,
bc_zz_alias.lsp(맨 뒤)는 짧은 이름을 원래대로 돌려놓은 뒤 BC 이름을 만들고 체크된 짧은 이름만 켠다.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True

from skills import registry  # noqa: E402

OUT = os.path.join(ROOT, "skills", "lisp", "bc_windows.lsp")
COPYRIGHT = ";;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)"
ALIASES = {"MPL": ["MPLOT"]}


def main():
    lines = [COPYRIGHT, ";;; bc_windows.lsp — 창 명령과 도움말 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)", ""]
    for cmd, info in registry.COMMANDS.items():
        if info["kind"] != "window":
            continue
        lines.append('(defun c:%s () (bc:open-window "%s") (princ))  ; %s' % (cmd, cmd, info["title"]))
        for a in ALIASES.get(cmd, []):
            lines.append("(defun c:%s () (bc:fn-%s))" % (a, cmd))
    lines += ["", ";; BCHELP: 명령 목록 창을 띄우고, 명령줄 기록(F2)에도 목록을 남긴다",
              "(defun c:BCHELP ()", '  (bc:open-window "BCHELP")', '  (princ "\\n[BC] 명령 목록 (F2로 전체 보기)")']
    group = None
    for cmd, info in registry.COMMANDS.items():
        if info["group"] != group:
            group = info["group"]
            lines.append('  (princ "\\n  ── %s")' % group)
        lines.append('  (princ "\\n  %-7s %s%s")' % ("BC" + cmd, info["title"], " (대화상자)" if info["kind"] == "window" else ""))
    lines += ['  (princ "\\n  ※ 명령은 BC를 붙여 입력합니다(FE → BCFE). 단축 이름은 BCHELP 대화상자에서 활성화합니다.")',
              '  (if bc:*short* (progn (princ "\\n  ※ 활성화된 단축 이름:") (foreach _k bc:*short* (princ (strcat " " _k)))'
              ' (princ "  (모두 켜기: BCON, 모두 해제: BCOFF)")))',
              "  (princ))", ""]
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("만듦:", OUT)
    write_guard()
    write_alias()


GUARD_OUT = os.path.join(ROOT, "skills", "lisp", "bc_00_guard.lsp")
ALIAS_OUT = os.path.join(ROOT, "skills", "lisp", "bc_zz_alias.lsp")


def _names():
    """우리가 정의하는 명령 이름 전부(별명 MPLOT 포함)."""
    out = list(registry.COMMANDS)
    for cmd in registry.COMMANDS:
        out += ALIASES.get(cmd, [])
    return out


def write_guard():
    """bc_core 다음, 명령 파일들보다 먼저 불러와진다(이름순으로 bc_00이 맨 앞).
    우리 명령을 정의하기 전에, 같은 이름을 이미 쓰던 다른 리습 명령을 기억해 둔다(짧은 이름이 꺼져 있으면 되돌린다).
    지난번에 우리가 만든 것(bc:fn-이름과 같은 함수, 짧은 이름 감싸개)은 기억하지 않는다."""
    lits = " ".join('"%s"' % c for c in _names())
    cmds = " ".join('"%s"' % c for c in registry.COMMANDS)
    body = [COPYRIGHT, ";;; bc_00_guard.lsp — 먼저 있던 같은 이름 명령 기억 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)",
            ";;; 우리 명령을 정의하기 전에, 같은 이름을 이미 쓰던 다른 리습 명령을 기억해 둔다.",
            "(setq bc:*names* (quote (%s)))" % lits,
            "(setq bc:*cmds* (quote (%s)))" % cmds,
            "(setq bc:*prior* nil)",
            "(foreach _n bc:*names*",
            "  (setq _f (eval (read (strcat \"c:\" _n))))",
            "  (if (and _f (not (eq _f (eval (read (strcat \"bc:fn-\" _n)))))",
            "           (not (eq _f (eval (read (strcat \"bc:sw-\" _n))))))",
            "    (setq bc:*prior* (cons (cons _n _f) bc:*prior*))))",
            "(setq _n nil _f nil)", ""]
    with open(GUARD_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(body))
    print("만듦:", GUARD_OUT)


def write_alias():
    """BC 이름과 짧은 이름. 맨 뒤에 불러와진다.
    - 우리 함수는 bc:fn-이름에 잡아 두고, 짧은 이름(c:FE…)은 일단 원래대로(먼저 있던 다른 리습 또는 없음) 돌려놓는다.
    - BC 이름(BCFE…)은 항상 만든다. 불러온 그때의 우리 함수(bc:fn-FE)를 부르므로 나중에 다른 리습이 c:FE를 다시
      정의해도 BCFE는 우리 것이다. BC 이름이 이미 다른 것(단축키·프로그램 명령·우리가 만들지 않은 리습 함수)이면 만들지 않는다.
    - 짧은 이름은 설정 파일(shortnames.txt)에 적힌 명령만 켠다(bc:short-apply). 켜고 끄기는 BCHELP 창, 모두 켜기는 BCON(겹치는 이름 제외), 모두 끄기는 BCOFF.
      리습 명령은 같은 이름의 단축키(acad.pgp)보다 먼저 실행되므로, 켤 때 창이 bc:short-conflicts로 겹침을 경고한다.
    MCP(skill_run)는 명령 이름을 거치지 않으므로 영향이 없다."""
    extra = " ".join('("%s" %s)' % (c, " ".join('"%s"' % a for a in al)) for c, al in ALIASES.items())
    body = [COPYRIGHT, ";;; bc_zz_alias.lsp — BC 이름(BCFE…)과 짧은 이름(FE…) (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)",
            ";;; 기본은 BC 이름만. 짧은 이름은 BCHELP 창에서 체크한 명령만 켠다(모두 켜기: BCON, 모두 끄기: BCOFF).",
            "(setq bc:*short-extra* (quote (%s)))" % extra,
            ";; 단축키 파일의 이름 목록. 주석·빈 줄과 이름 글자(영문·숫자·_·-)가 아닌 것(파일 앞 BOM 등)은 뺀다",
            "(defun bc:pgp-names (p / f l i n out)",
            "  (if (and p (setq f (open p \"r\")))",
            "    (progn",
            "      (while (setq l (read-line f))",
            "        (setq l (vl-string-trim \" \\t\" l))",
            "        (if (and (/= l \"\") (/= (substr l 1 1) \";\") (setq i (vl-string-search \",\" l))",
            "                 (/= (setq n (strcase (vl-string-trim \" \\t\" (substr l 1 i)))) \"\")",
            "                 (not (wcmatch n \"*[~A-Z0-9_`-]*\")))",
            "          (setq out (cons n out))))",
            "      (close f)))",
            "  out)",
            ";; 짧은 이름 설정 파일: 켠 명령 이름을 한 줄에 하나",
            "(defun bc:short-path () (strcat (getenv \"LOCALAPPDATA\") \"\\\\bc-autocad\\\\settings\\\\shortnames.txt\"))",
            "(defun bc:short-read (/ f l out)",
            "  (if (and (findfile (bc:short-path)) (setq f (open (bc:short-path) \"r\" \"utf8\")))",
            "    (progn",
            "      (while (setq l (read-line f))",
            "        (setq l (strcase (vl-string-trim \" \\t\\r\" l)))",
            "        (if (and (member l bc:*cmds*) (not (member l out))) (setq out (cons l out))))",
            "      (close f)))",
            "  (reverse out))",
            "(defun bc:short-write (names / d f)",
            "  (setq d (strcat (getenv \"LOCALAPPDATA\") \"\\\\bc-autocad\"))",
            "  (vl-mkdir d) (vl-mkdir (strcat d \"\\\\settings\"))",
            "  (if (setq f (open (bc:short-path) \"w\" \"utf8\"))",
            "    (progn (foreach n names (write-line n f)) (close f) T)))",
            ";; 명령 하나의 짧은 이름들(MPL이면 MPLOT까지)",
            "(defun bc:short-names (n) (cons n (cdr (assoc n bc:*short-extra*))))",
            ";; 짧은 이름으로 실행하면 어느 명령이 돌았는지 한 줄 남긴다",
            "(defun bc:run-short (n s) (princ (strcat \"\\n[BC] BC\" n)) (eval (list (read (strcat \"bc:fn-\" s)))))",
            "(defun bc:short-on (n)",
            "  (foreach s (bc:short-names n)",
            "    (if (null (eval (read (strcat \"bc:sw-\" s))))",
            "      (eval (read (strcat \"(defun bc:sw-\" s \" () (bc:run-short \\\"\" n \"\\\" \\\"\" s \"\\\"))\"))))",
            "    (set (read (strcat \"c:\" s)) (eval (read (strcat \"bc:sw-\" s))))",
            "    (vl-acad-defun (read (strcat \"c:\" s)))))",
            ";; 끄면 먼저 있던 다른 리습 명령으로 되돌리거나(없으면) 지운다 — 같은 이름의 단축키·프로그램 명령이 다시 산다.",
            ";; 없을 때는 명령 등록까지 풀어야 한다 — 값만 nil로 두면 등록이 남아 CL(중심선) 같은 acad.pgp 단축키가",
            ";; 'no function definition: C:CL'로 막힌다(2026-11-01)",
            "(defun bc:short-off (n / p)",
            "  (foreach s (bc:short-names n)",
            "    (set (read (strcat \"c:\" s)) (setq p (cdr (assoc s bc:*prior*))))",
            "    (if (null p) (vl-acad-undefun (read (strcat \"c:\" s))))))",
            ";; 설정 파일대로 이 도면에 켜고 끈다. 켠 목록을 bc:*short*에 둔다",
            "(defun bc:short-apply ()",
            "  (setq bc:*short* (bc:short-read))",
            "  (foreach n bc:*cmds* (if (member n bc:*short*) (bc:short-on n) (bc:short-off n)))",
            "  bc:*short*)",
            ";; 이 PC에서 이미 쓰는 이름: ((이름 . 무엇) ...) — 켜기 전에 창이 경고용으로 부른다",
            "(defun bc:short-conflicts (names / pgp out)",
            "  (setq pgp (bc:pgp-names (findfile \"acad.pgp\")))",
            "  (foreach n names",
            "    (foreach s (bc:short-names n)",
            "      (cond ((member s pgp) (setq out (cons (list n s \"단축키 파일(acad.pgp)\") out)))",
            "            ((getcname s) (setq out (cons (list n s \"프로그램 명령\") out)))",
            "            ((assoc s bc:*prior*) (setq out (cons (list n s \"다른 리습\") out))))))",
            "  (reverse out))",
            "(defun c:BCOFF ()",
            "  (bc:short-write nil) (bc:short-apply)",
            "  (princ \"\\n[BC] 단축 이름(FE 등)을 모두 해제했습니다. 이후에는 BCFE처럼 접두어 BC를 붙여 입력하십시오.\")",
            "  (princ \"\\n     이미 열려 있는 다른 도면은 다시 열 때 해제됩니다.\")",
            "  (princ))",
            ";; 모두 켜기: 이 PC에서 이미 쓰는 이름(acad.pgp 단축키·프로그램 명령·다른 리습)과 겹치는 것은 건너뛴다.",
            ";; 겹치는 이름을 덮어쓰면 CL(중심선) 같은 원래 명령이 사라지므로, 그런 것은 BCHELP 창에서 경고를 보고 하나씩 켠다.",
            ";; 이미 켜 둔 이름은 겹쳐도 그대로 둔다",
            "(defun c:BCON (/ skip on)",
            "  (setq skip (bc:short-conflicts (vl-remove-if (function (lambda (n) (member n bc:*short*))) bc:*cmds*)))",
            "  (setq on (vl-remove-if (function (lambda (n) (assoc n skip))) bc:*cmds*))",
            "  (bc:short-write on) (bc:short-apply)",
            "  (princ (strcat \"\n[BC] 단축 이름 \" (itoa (length bc:*short*)) \"개를 활성화했습니다(모두 해제: BCOFF).\"))",
            "  (if skip",
            "    (progn",
            "      (princ \"\n[BC] 이 PC에서 이미 쓰는 이름이라 건너뛰었습니다:\")",
            "      (foreach p skip (princ (strcat \"\n       \" (cadr p) \" — \" (caddr p))))",
            "      (princ \"\n     이 이름을 쓰려면 BCHELP 대화상자에서 해당 명령을 활성화하십시오. BC를 붙인 이름(BCCL 등)은 언제든 쓸 수 있습니다.\")))",
            "  (princ \"\n     이미 열려 있는 다른 도면은 다시 열 때 적용됩니다.\")",
            "  (princ))",
            ";; 우리 함수를 잡아 두고 짧은 이름은 일단 원래대로",
            "(foreach _n bc:*names*",
            "  (set (read (strcat \"bc:fn-\" _n)) (eval (read (strcat \"c:\" _n))))",
            "  (set (read (strcat \"c:\" _n)) (cdr (assoc _n bc:*prior*))))",
            ";; BC 이름은 항상",
            "(setq _pgp (bc:pgp-names (findfile \"acad.pgp\")))",
            "(foreach _n bc:*cmds*",
            "  (setq _a (strcat \"BC\" _n))",
            "  (if (and (eval (read (strcat \"bc:fn-\" _n)))",
            "           (not (getcname _a)) (not (member _a _pgp))",
            "           (or (null (eval (read (strcat \"c:\" _a)))) (member _a bc:*aliases*)))",
            "    (progn",
            "      (eval (read (strcat \"(defun c:\" _a \" () (bc:fn-\" _n \"))\")))",
            "      (if (not (member _a bc:*aliases*)) (setq bc:*aliases* (cons _a bc:*aliases*))))))",
            ";; 체크해 둔 짧은 이름만 켠다",
            "(if (bc:short-apply)",
            "  (princ (strcat \"\\n[BC] 단축 이름 \" (itoa (length bc:*short*)) \"개가 활성화되어 있습니다(해제: BCOFF).\")))",
            "(setq _n nil _a nil _pgp nil)", ""]
    with open(ALIAS_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(body))
    print("만듦:", ALIAS_OUT)


if __name__ == "__main__":
    main()
