# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""백그라운드 작도: 화면 없는 AutoCAD(accoreconsole.exe)로 도면 파일(DWG)을 만든다.

켜져 있는 AutoCAD 화면·도면·키보드는 건드리지 않는다(AutoCAD가 꺼져 있어도 된다. 설치만 되어 있으면 된다).
- LISP 본문을 UTF-8 한 줄 파일로 써 두고, 스크립트(.scr)는 그 파일을 읽어 eval만 한다(한글 그대로).
- 백그라운드에는 객체 스냅·대화창이 없어 (command ...)도 쓸 수 있다(OSMODE 0으로 시작).
- 토목 명령 함수(skills/lisp)를 먼저 불러 둘 수 있다(use_skills).
- 끝나면 DWG(2018 형식)로 저장하고, 결과 파일의 마지막 줄 DONE으로 끝까지 돌았는지 확인한다.
실측(AutoCAD 2023): 새 도면 작도·저장 약 2.4초, 한글 파일 이름·문자 정상, 스크립트가 끝나면 스스로 종료.
"""

import glob
import os
import re
import shutil
import subprocess
import tempfile
import time

try:
    from . import validators as V
except ImportError:
    import validators as V

DONE = "BC_BG_DONE"
_YEAR = re.compile(r"AutoCAD (\d{4})")


def find_console() -> str:
    """accoreconsole.exe 경로. 환경 변수 BC_ACCORECONSOLE이 있으면 그것, 없으면 설치된 AutoCAD 2021 이상 중 가장 새 판."""
    env = os.environ.get("BC_ACCORECONSOLE", "")
    if env and os.path.isfile(env):
        return env
    found = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")):
        if not base:
            continue
        for p in glob.glob(os.path.join(base, "Autodesk", "AutoCAD *", "accoreconsole.exe")):
            m = _YEAR.search(p)
            if m and int(m.group(1)) >= 2021:
                found.append((int(m.group(1)), p))
    if not found:
        raise FileNotFoundError("화면 없는 AutoCAD(accoreconsole.exe)를 찾지 못했습니다. AutoCAD 2021 이상이 설치되어 "
                                "있어야 합니다. 다른 위치에 있으면 환경 변수 BC_ACCORECONSOLE에 경로를 지정하세요.")
    return sorted(found)[-1][1]


def _slash(p: str) -> str:
    return os.path.abspath(p).replace(chr(92), "/")


def _skills_lib():
    """토목 명령 함수 묶음(한 줄 파일) 경로. skills 패키지를 처음 쓸 때만 불러온다."""
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from skills.common import lisplib
    return lisplib.build()[1]


PREVIEW_DIR = os.path.join(tempfile.gettempdir(), "bc_bg_preview")


def _plot_lisp(png: str) -> str:
    """모형 공간 전체를 PNG로 출력(PublishToWeb PNG.pc3, 기본 용지 1600×1280 픽셀, 색은 acad.ctb 그대로).
    한국어판은 용지 이름이 한글이라 용지는 빈 입력(기본값)으로 받는다(실측). 실패해도 작도·저장은 그대로 둔다."""
    p = _slash(png)
    return ('(if (and (> _bccount 0) (setq _bcok (vl-catch-all-apply (function (lambda () (command "_.ZOOM" "_E")'
            ' (command "_.-PLOT" "_Y" "Model" "PublishToWeb PNG.pc3" "" "_L" "_N" "_E" "_F" "_C" "_Y" "acad.ctb" "_Y" "_A"'
            ' "%s" "_N" "_Y")))))) (princ))'
            ' (write-line (strcat "BC_BG_PNG" (chr 9) (if (findfile "%s") "1" "0")) _fp)') % (p, p)


def build(code: str, output_path: str, base_drawing: str = "", overwrite: bool = False, use_skills: bool = True,
          timeout_s: float = 300.0, preview: bool = True) -> dict:
    """code(LISP)를 화면 없는 AutoCAD에서 실행하고 output_path(.dwg)로 저장한다.
    base_drawing을 주면 그 도면을 열어 시작한다(원본은 그대로, 결과는 output_path에만 저장).
    결과는 code가 (write-line "..." _fp)로 쓴 줄을 lines로 돌려준다.
    preview면 저장한 뒤 모형 공간 전체를 PNG로 출력해 preview(임시 폴더 경로)로 돌려준다 — 화면 없이 결과를 눈으로 확인할 때."""
    V.check_parens(code)
    out = os.path.abspath(output_path)
    if not out.lower().endswith(".dwg"):
        raise ValueError("output_path는 .dwg 파일이어야 합니다: %s" % output_path)
    if not os.path.isdir(os.path.dirname(out)):
        raise FileNotFoundError("저장할 폴더가 없습니다: %s" % os.path.dirname(out))
    base = os.path.abspath(base_drawing) if base_drawing else ""
    if base and not os.path.isfile(base):
        raise FileNotFoundError("base_drawing 도면이 없습니다: %s" % base_drawing)
    if base and os.path.normcase(base) == os.path.normcase(out):
        raise ValueError("base_drawing과 output_path가 같습니다. 원본을 지키기 위해 다른 이름으로 저장하세요.")
    if os.path.exists(out):
        if not overwrite:
            raise FileExistsError("이미 있는 파일입니다: %s (덮어쓰려면 overwrite=true)" % out)
        os.remove(out)
    if timeout_s <= 0 or timeout_s > 3600:
        raise ValueError("timeout_s는 1~3600초입니다.")

    acc = find_console()
    work = tempfile.mkdtemp(prefix="bc_bg_")
    try:
        res = os.path.join(work, "result.txt")
        lib = ('(progn (setq _bcl (open "%s" "r" "utf8") _bcs (read-line _bcl)) (close _bcl) (eval (read _bcs)) '
               '(setq _bcl nil _bcs nil))' % _slash(_skills_lib())) if use_skills else ""
        png = ""
        if preview:
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            png = os.path.join(PREVIEW_DIR, "%s_%s.png" % (os.path.splitext(os.path.basename(out))[0],
                                                           time.strftime("%Y%m%d_%H%M%S")))
        body = (
            '(progn (setq _fp (open "%s" "w" "utf8") _d (chr 9))'
            ' (defun *error* (msg) (write-line (strcat "LISPERROR" (chr 9) (if (= (type msg) (quote STR)) msg "")) _fp)'
            '  (write-line "%s" _fp) (close _fp) (princ))'
            ' (setvar "OSMODE" 0) (setvar "CMDECHO" 0) %s\n%s\n'
            ' (setq _bccount (if (setq _bcss (ssget "_X")) (sslength _bcss) 0))'
            ' (write-line (strcat "BC_BG_COUNT" (chr 9) (itoa _bccount)) _fp)'
            ' (command "_.SAVEAS" "2018" "%s")'
            ' (write-line (strcat "BC_BG_SAVED" (chr 9) (if (findfile "%s") "1" "0")) _fp)'
            ' %s'
            ' (write-line "%s" _fp) (close _fp) (princ))'
        ) % (_slash(res), DONE, lib, code, _slash(out), _slash(out), _plot_lisp(png) if png else "", DONE)
        src = os.path.join(work, "code.lsp.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write(V.one_line(body))
        scr = os.path.join(work, "run.scr")
        with open(scr, "w", encoding="ascii") as f:
            f.write('(progn (setq _in (open "%s" "r" "utf8") _s (read-line _in)) (close _in) (eval (read _s)) (princ))\n'
                    % _slash(src))
        args = [acc] + (["/i", base] if base else []) + ["/s", scr]
        if os.path.isdir(os.path.join(os.path.dirname(acc), "ko-KR")):
            args += ["/l", "ko-KR"]
        t0 = time.time()
        try:
            # MCP 서버(stdio)에서 부르면 TEMP·TMP가 빠진 환경일 수 있다 — 그러면 콘솔이 드라이브 맨 위에 임시 파일을
            # 만들려다 "Can't redirect stdout (errno=13)"로 멈춘다(실측). 작업 폴더를 임시 폴더로 넘기고 입력은 막는다.
            env = dict(os.environ, TEMP=work, TMP=work)
            proc = subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout_s, cwd=work,
                                  env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise TimeoutError("백그라운드 작업이 %d초 안에 끝나지 않아 중단했습니다." % timeout_s)
        sec = round(time.time() - t0, 1)
        lines = []
        if os.path.exists(res):
            with open(res, "r", encoding="utf-8-sig", errors="replace") as f:
                lines = [ln.rstrip("\r\n") for ln in f if ln.strip()]
        tail = proc.stdout.decode("utf-16-le", errors="replace")[-800:].strip()
        err = [ln.split("\t", 1)[-1] for ln in lines if ln.startswith("LISPERROR")]
        if err:
            raise RuntimeError("LISP 오류: %s (저장하지 않았습니다)" % err[0])
        if not lines or lines[-1] != DONE:
            raise RuntimeError("백그라운드 작업이 끝까지 돌지 않았습니다(종료 코드 %s). 화면 없는 AutoCAD 출력 끝부분:\n%s"
                               % (proc.returncode, tail))
        info = dict(ln.split("\t", 1) for ln in lines if ln.startswith("BC_BG_") and "\t" in ln)
        if info.get("BC_BG_SAVED") != "1" or not os.path.isfile(out):
            raise RuntimeError("도면을 저장하지 못했습니다: %s" % out)
        user = [ln for ln in lines[:-1] if not ln.startswith("BC_BG_")]
        result = {"output": out, "entities": int(info.get("BC_BG_COUNT", "0")), "seconds": sec,
                  "bytes": os.path.getsize(out), "lines": user, "console": os.path.basename(os.path.dirname(acc))}
        if preview:
            ok = info.get("BC_BG_PNG") == "1" and os.path.isfile(png)
            result["preview"] = png if ok else None
            if not ok:
                result["preview_note"] = ("빈 도면이라 출력하지 않았습니다." if result["entities"] == 0 else
                                          "PNG 출력에 실패했습니다(도면은 저장됨). open_drawing 후 capture_view로 확인하세요.")
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)
