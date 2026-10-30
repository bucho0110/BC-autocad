"""AutoLISP 실행기 — (load) 없이 파일 eval로 실행하고 결과 줄을 돌려받는다.

AutoCAD 2023 실측(2026-10-28)에 근거한 방식:
- 외부 프로세스의 SendCommand는 동기다. LISP가 끝나야 돌아온다(M2).
- 인라인으로 약 7.5KB를 넘기면 SendCommand가 돌아오지 않는다(M21).
  그래서 LISP 전체를 한 줄 UTF-8 파일로 쓰고, 짧은 인라인 식이 그 줄을 읽어
  (eval (read ...)) 한다. 210KB까지 0.43초, 한글 정상(M22).
- (load)를 쓰지 않으므로 SECURELOAD·신뢰 경로 보안창과 무관하다.
- 닫히지 않은 LISP나 입력 대기 함수는 SendCommand를 붙잡는다. 이때 AutoCAD GUI
  스레드의 입력 포커스 창에 WM_CHAR ESC를 보내면 풀린다(주 창에 보내면 효과 없음, M22-B).
"""

import atexit
import ctypes
import ctypes.wintypes as wt
import logging
import os
import shutil
import tempfile
import threading
import time
from typing import List, Optional

try:
    from .validators import check_parens, one_line
except ImportError:
    from validators import check_parens, one_line

logger = logging.getLogger("lisp_runner")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_WM_CHAR = 0x0102
_VK_ESCAPE = 0x1B
# 64비트 HWND를 c_int로 넘기다 넘치지 않게 인자 형식을 박아 둔다.
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_user32.GetWindowThreadProcessId.restype = wt.DWORD
_user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
_user32.GetAncestor.restype = wt.HWND
_user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.PostMessageW.restype = wt.BOOL
_user32.IsWindowVisible.argtypes = [wt.HWND]
_ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumWindows.argtypes = [_ENUMPROC, wt.LPARAM]


def find_acad_hwnd() -> int:
    """COM 없이 AutoCAD 주 창을 찾는다(서버가 아직 COM으로 붙기 전이거나 COM 스레드가 막혔을 때)."""
    found = []

    def cb(h, _):
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(h, buf, 256)
        cls = buf.value
        _user32.GetWindowTextW(h, buf, 256)
        if cls.startswith("AfxMDIFrame") and buf.value.startswith("Autodesk AutoCAD") and _user32.IsWindowVisible(h):
            found.append(int(h))
        return True
    _user32.EnumWindows(_ENUMPROC(cb), 0)
    return found[0] if found else 0


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


def focus_window(main_hwnd: int) -> dict:
    """AutoCAD GUI 스레드의 입력 포커스 창과 그 최상위 창(클래스·제목)을 알려 준다."""
    out = {"hwnd": None, "root_class": "", "root_title": ""}
    if not main_hwnd:
        return out
    pid = wt.DWORD()
    tid = _user32.GetWindowThreadProcessId(wt.HWND(main_hwnd), ctypes.byref(pid))
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(_GUITHREADINFO)
    if not (tid and _user32.GetGUIThreadInfo(tid, ctypes.byref(info))):
        return out
    target = info.hwndFocus or info.hwndActive
    if not target:
        return out
    root = _user32.GetAncestor(wt.HWND(target), 2) or target  # GA_ROOT
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(root, buf, 256)
    out["root_class"] = buf.value
    _user32.GetWindowTextW(root, buf, 256)
    out["root_title"] = buf.value
    out["hwnd"] = int(target)
    return out


def is_dialog(info: dict) -> bool:
    """포커스가 대화창(#32770) 안에 있는가. 이때는 ESC로 함부로 닫지 않는다(사람이 보고 판단할 창)."""
    return info.get("root_class") == "#32770"


def post_escape(main_hwnd: int, times: int = 2, allow_dialog: bool = False) -> dict:
    """AutoCAD GUI 스레드의 입력 포커스 창에 ESC를 보낸다. 포커스를 빼앗지 않는다(PostMessage).
    COM을 쓰지 않으므로 COM 스레드가 막혀 있어도 다른 스레드에서 부를 수 있다.
    포커스가 대화창 안이면 allow_dialog=True일 때만 보낸다.
    반환: focus_window 정보 + sent(보냈는지)."""
    info = focus_window(main_hwnd)
    info["sent"] = False
    if not info["hwnd"] or (is_dialog(info) and not allow_dialog):
        return info
    for _ in range(times):
        _user32.PostMessageW(info["hwnd"], _WM_CHAR, _VK_ESCAPE, 0)
    info["sent"] = True
    return info


class LispError(RuntimeError):
    """LISP 실행 중 런타임 오류(*error* 처리기가 잡은 것)."""


class LispCancelled(RuntimeError):
    """제한시간 안에 안 끝나 ESC로 취소했다. 효과가 이미 들어갔을 수 있다 — 재실행 금지."""


class _Scratch:
    """이 서버 프로세스 전용 임시 폴더. 처음 쓸 때 만들고 프로세스가 끝나면 통째로 지운다."""

    def __init__(self):
        self._dir = None
        self._lock = threading.Lock()
        self._serial = 0

    def path(self, stem: str, ext: str) -> str:
        """호출마다 새 파일 이름. LISP 문자열에 넣으므로 / 로 잇는다."""
        with self._lock:
            if self._dir is None:
                self._dir = tempfile.mkdtemp(prefix="bc_autocad_")
                atexit.register(shutil.rmtree, self._dir, True)
            self._serial += 1
            name = "%s_%d_%d%s" % (stem, os.getpid(), self._serial, ext)
        return os.path.join(self._dir, name).replace(chr(92), "/")


_scratch = _Scratch()
DONE = "BC-DONE"  # 결과 파일 마지막 줄 — 이 줄이 있어야 본문이 끝까지 돈 것이다
_KIDS = '(quote ("ATTRIB" "VERTEX" "SEQEND"))'  # 주 개체에 딸린 하위 개체(주 개체와 같이 지워진다)

# 본문이 쓰는 이름을 함수 지역으로 묶는다 — 끝나면 선택 집합이 풀린다(AutoCAD 동시 선택 집합 한도 128).
_LOCALS = ("_d _fp _bc_olderr _bc_mark _bc_blank _bc_cur _bc_next _bc_undone"
           " _ss _t _m _e _en _i _n _k _c _bb _h _ob _r _nw _p0 _p1 _cr _base _lay _ok _why _ed _bf _el _pt"
           " _co _vi _tx _tc _ip _a _bbof _spc")


def _wrap(body: str, out_path: str) -> str:
    """본문을 함수 bc:job 하나로 감싼다(매번 다시 정의).

    - _fp: 결과 파일(UTF-8), _d: 탭. 본문은 (write-line ... _fp)로 결과를 쓰고, 끝나면 DONE 줄을 붙인다.
    - 시작 전 마지막 개체(entlast)를 표시해 두고, 오류가 나면 그 뒤에 새로 생긴 개체만 지운다.
      * 표시가 속성 블록·옛 POLYLINE이면 (entnext)가 그 하위 개체를 내주므로 표시를 SEQEND까지 옮겨 두고,
        지울 때도 하위 개체는 건너뛴다(주 개체를 지우면 같이 지워진다).
      * 표시가 nil이면 도면이 정말 비어 있었을 때(entnext도 nil)만 첫 개체부터 지운다 — 아니면 기존 개체까지
        지울 수 있다. 빈 도면은 실측.
    """
    tab = '"' + chr(92) + 't"'
    return (
        "(progn"
        " (defun bc:job ( / " + _LOCALS + ")"
        "  (setq _d " + tab + " _fp (open \"" + out_path + "\" \"w\" \"utf8\"))"
        "  (setq _bc_mark (entlast) _bc_blank (not (or _bc_mark (entnext))))"
        "  (while (and _bc_mark (setq _bc_next (entnext _bc_mark))"
        "              (member (cdr (assoc 0 (entget _bc_next))) " + _KIDS + "))"
        "   (setq _bc_mark _bc_next))"
        "  (setq _bc_olderr *error*)"
        "  (defun *error* (msg)"
        "   (setq _bc_undone 0"
        "         _bc_cur (if _bc_mark (entnext _bc_mark) (if _bc_blank (entnext))))"
        "   (while _bc_cur"
        "    (setq _bc_next (entnext _bc_cur))"
        "    (if (and (entget _bc_cur) (not (member (cdr (assoc 0 (entget _bc_cur))) " + _KIDS + ")))"
        "     (progn (entdel _bc_cur) (setq _bc_undone (1+ _bc_undone))))"
        "    (setq _bc_cur _bc_next))"
        # 탭은 _d 대신 (chr 9) — 본문이 _d를 다른 값으로 덮어써도 오류 보고는 남게
        "   (write-line (strcat \"LISPERROR\" (chr 9) (if (= (type msg) (quote STR)) msg \"\") (chr 9) (itoa _bc_undone)) _fp)"
        "   (write-line \"" + DONE + "\" _fp) (close _fp) (setq *error* _bc_olderr) (princ))"
        "  " + body + "\n"  # 본문 끝의 ; 주석이 아래 마무리까지 삼키지 않게 줄을 바꾼다
        "  (write-line \"" + DONE + "\" _fp) (close _fp) (setq *error* _bc_olderr) (princ))"
        " (bc:job))"
    )


def _bootstrap(src_path: str) -> str:
    """SendCommand로 보내는 짧은 식: 파일의 한 줄을 읽어 eval한다."""
    return ('(progn (setq _bcin (open "%s" "r" "utf8") _bcsrc (read-line _bcin)) (close _bcin)'
            ' (setq _bcin nil) (eval (read _bcsrc)) (setq _bcsrc nil) (princ))\n' % src_path)


def _read_result(out_path: str) -> Optional[List[str]]:
    """결과 파일의 마지막 줄이 DONE일 때만 줄 목록(DONE 제외)을 준다."""
    if not os.path.exists(out_path):
        return None
    try:
        with open(out_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [ln.rstrip("\r\n") for ln in f]
    except OSError:
        return None
    if not lines or lines[-1].strip() != DONE:
        return None
    return lines[:-1]


def run(doc, main_hwnd: int, body: str, timeout_s: float = 60.0) -> List[str]:
    """body를 실행하고 결과 줄(빈 줄 제외)을 돌려준다. COM 스레드에서 부른다.

    doc: 활성 문서(SendCommand 대상). main_hwnd: AutoCAD 주 창 핸들(ESC 감시용).
    호출 전에 사용자가 명령 중이 아닌지(CMDACTIVE=0)는 호출부가 확인한다.
    """
    check_parens(body)
    out_path = _scratch.path("out", ".txt")
    src_path = _scratch.path("src", ".lsp.txt")
    code = one_line(_wrap(body, out_path))
    with open(src_path, "w", encoding="utf-8", newline="") as f:
        f.write(code)

    cancelled = {"at": None, "info": None}

    def on_timeout():
        cancelled["at"] = time.time()
        cancelled["info"] = post_escape(main_hwnd)
        logger.warning("LISP 제한시간 %.1fs 초과 — 포커스 창 ESC: %s", timeout_s, cancelled["info"])

    timer = threading.Timer(timeout_s, on_timeout)
    timer.daemon = True
    timer.start()
    try:
        doc.SendCommand(_bootstrap(src_path))
    finally:
        timer.cancel()
    try:
        lines = _read_result(out_path)
        info = cancelled["info"] or {}
        if cancelled["at"] and not info.get("sent"):
            why = ("대화창(%s)이 떠 있어" % info.get("root_title", "") if is_dialog(info)
                   else "입력 포커스 창을 찾지 못해")
            how = "취소하지 않았습니다" if lines is None else "취소하지 않았는데 나중에 끝났습니다"
            raise LispCancelled("LISP가 %.0f초를 넘겼지만 %s ESC를 보내지 않았고 %s. 효과가 들어갔을 수 있으니 "
                                "다시 실행하기 전에 AutoCAD 화면과 도면을 확인하세요." % (timeout_s, why, how))
        if lines is None:
            # 동기 SendCommand가 돌아왔는데 END가 없다: 부트스트랩 자체가 실패했거나
            # (파일 열기 실패 등) 취소로 *error*도 못 거친 경우다.
            if cancelled["at"]:
                raise LispCancelled("LISP가 %.0f초 안에 끝나지 않아 ESC로 취소했습니다. 결과를 "
                                    "확인할 수 없고 일부 효과가 이미 들어갔을 수 있습니다 — "
                                    "다시 실행하기 전에 도면을 확인하세요." % timeout_s)
            raise LispError("LISP 결과 파일이 완성되지 않았습니다(끝 표시 없음). AutoCAD 명령줄을 확인하세요.")
        rows = [ln for ln in lines if ln.strip() != ""]
        # *error*는 결과를 몇 줄 쓴 뒤에도 불릴 수 있다 — 첫 줄만 보면 오류가 성공으로 둔갑한다.
        err = next((r for r in reversed(rows) if r.startswith("LISPERROR\t")), None)
        if err is not None:
            parts = err.split("\t")
            msg = parts[1] if len(parts) > 1 else ""
            rolled = parts[2] if len(parts) > 2 else "?"
            done = len(rows) - 1
            if cancelled["at"]:
                raise LispCancelled("LISP가 %.0f초 안에 끝나지 않아 ESC로 취소했습니다(%s, 그 전까지 결과 %d줄). "
                                    "이번 호출이 새로 만든 개체 %s개를 지웠지만 기존 개체에 가한 변경은 되돌리지 "
                                    "않았습니다 — 다시 실행하기 전에 도면을 확인하세요."
                                    % (timeout_s, msg, done, rolled))
            raise LispError("LISP 실행 오류: %s (그 전까지 결과 %d줄, 이번 호출이 새로 만든 개체 %s개를 지움, "
                            "기존 개체 변경은 되돌리지 않음)" % (msg, done, rolled))
        if cancelled["at"]:
            raise LispCancelled("LISP가 %.0f초를 넘겨 ESC를 보낸 뒤에 끝났습니다. 효과가 이미 들어갔으니 "
                                "다시 실행하지 말고 도면을 확인하세요." % timeout_s)
        return rows
    finally:
        for p in (out_path, src_path):
            try:
                os.remove(p)
            except OSError:
                pass
