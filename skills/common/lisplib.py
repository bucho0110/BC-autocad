# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""BC 명령 LISP 라이브러리(skills/lisp/*.lsp)를 MCP·창에서 쓸 수 있게 한 줄 파일로 만든다.

AutoCAD 명령(FE·XY…)은 시작 시 (load)로 원본 .lsp를 불러 정의된다(install이 만든 bc_autocad.lsp).
MCP와 창은 (load)를 쓰지 않는다 — 한 줄로 바꾼 사본을 PC별 작업 폴더에 써 두고,
도면에 같은 판이 아직 없을 때만 그 파일을 읽어 eval한다. 판 표시는 원본 내용의 해시다.
"""

import glob
import hashlib
import os

from .paths import LISP_DIR, WORK, lisp_path
from validators import _lisp_tokens, one_line  # src: 한 줄 만들기·괄호 세기가 같은 규칙을 쓴다

# 불러오는 순서(core가 먼저). 목록에 없는 파일은 이름순으로 뒤에 붙는다.
ORDER = ["bc_core.lsp"]

_cache = {"key": None, "expr": None}


def sources():
    files = sorted(glob.glob(os.path.join(LISP_DIR, "*.lsp")))
    first = [os.path.join(LISP_DIR, n) for n in ORDER if os.path.join(LISP_DIR, n) in files]
    return first + [f for f in files if f not in first]


class LispSourceError(ValueError):
    pass


def split_forms(body: str, limit: int = 100000):
    """그리기 LISP를 맨 바깥 식 경계에서 limit 글자 남짓씩 나눈다. 한 번에 너무 긴 식은 AutoCAD가 끝까지 못 읽는다
    (실제 하천 도면 292단면 DCEM 1.4MB — END 없음, 실측 2026-10-29). 나눈 조각은 차례로 같은 LISP 세션에서 돈다.
    문자열·주석(; 줄 주석, ;| |; 블록 주석) 안의 괄호는 세지 않는다(MCP의 LISP 읽기 규칙 _lisp_tokens와 같다)."""
    if len(body) <= limit:
        return [body]
    out, start, depth, pos = [], 0, 0, 0
    for kind, txt in _lisp_tokens(body):
        pos += len(txt)
        if kind == "(":
            depth += 1
        elif kind == ")":
            depth -= 1
            if depth == 0 and pos - start >= limit:
                out.append(body[start:pos])
                start = pos
    if body[start:].strip():
        out.append(body[start:])
    return out


def check_depth(text: str, name: str):
    """파일 하나의 괄호 깊이: 문자열·주석을 건너뛰고 세어, 음수가 되는 줄과 끝 깊이를 잡는다.
    전체 개수만 맞는 검사는 '여기서 하나 더 닫고 저기서 하나 덜 닫은' 경우를 놓친다 — 그러면
    한 줄로 합친 라이브러리가 중간에서 끝나 뒤 정의가 조용히 빠진다(실측 2026-10-29).
    주석 규칙은 한 줄로 합칠 때 쓰는 one_line(_lisp_tokens)과 같다(; 줄 주석, ;| |; 블록 주석, CR 단독 줄바꿈)."""
    depth, line = 0, 1
    for kind, txt in _lisp_tokens(text):
        if kind == "(":
            depth += 1
        elif kind == ")":
            depth -= 1
            if depth < 0:
                raise LispSourceError("%s %d줄: 닫는 괄호가 남습니다." % (name, line))
        elif kind == "open_str":
            raise LispSourceError("%s %d줄: 문자열이 닫히지 않았습니다." % (name, line))
        elif kind == "open_block":
            raise LispSourceError("%s %d줄: 블록 주석(;| … |;)이 닫히지 않았습니다." % (name, line))
        line += txt.count("\n") + (txt.count("\r") - txt.count("\r\n"))
    if depth != 0:
        raise LispSourceError("%s: 끝에서 괄호 %d개가 안 닫혔습니다." % (name, depth))


def _read_all():
    parts = []
    for f in sources():
        with open(f, "r", encoding="utf-8-sig") as fh:
            t = fh.read()
        check_depth(t, os.path.basename(f))
        parts.append(t)
    return "\n".join(parts)


def build():
    """(판, 한 줄 파일 경로). 원본이 바뀌면 새 판을 만든다."""
    text = _read_all()
    ver = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    path = os.path.join(WORK, "bc_lib_%s.lsp.txt" % ver)
    if not os.path.exists(path):
        code = one_line("(progn " + text + "\n (setq bc:libver \"" + ver + "\") (princ))")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(code)
        os.replace(tmp, path)
    return ver, path


def ensure_expr() -> str:
    """도면에 같은 판이 없을 때만 라이브러리를 eval. 창을 띄우는 데 쓰는 *bc-root*·*bc-pyw*도
    AutoCAD 시작 때 불러오기 파일이 정하지 않았으면 여기서 정한다."""
    from .paths import ROOT, pythonw
    ver, path = build()
    return ('(if (null *bc-root*) (setq *bc-root* "%s" *bc-pyw* "%s"))'
            '(if (/= (vl-princ-to-string bc:libver) "%s") (progn (setq _bcf (open "%s" "r" "utf8")'
            ' _bcs (read-line _bcf)) (close _bcf) (setq _bcf nil) (eval (read _bcs)) (setq _bcs nil)))'
            % (lisp_path(ROOT), lisp_path(pythonw()), ver, lisp_path(path)))
