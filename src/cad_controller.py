# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""AutoCAD COM 제어 계층(AutoCAD 2023에서 실측).

- 모든 COM 호출은 전용 STA 스레드 하나(ComWorker)에서 차례로 실행한다.
- 호출 하나하나를 재시도로 감싼다(ComProxy). AutoCAD가 바쁠 때 거절된 호출은
  실행되지 않은 것이므로 다시 보내도 같은 작업이 두 번 되지 않는다.
  작업 전체를 다시 돌리면 앞부분이 두 번 그려질 수 있어 하지 않는다.
- 문서는 매번 ActiveDocument를 읽는다(고정 변수를 두면 사용자가 탭을 바꾼 뒤 엉뚱한 도면에 그린다).
- LISP는 lisp_runner(파일 eval)로 실행한다. 근거는 AutoCAD 2023 실측(README 9장).
"""

import asyncio
import concurrent.futures
import ctypes
import ctypes.wintypes as wt
import logging
import math
import os
import queue
import tempfile
import threading
import time
import types
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import pythoncom
import win32com.client
import win32com.client.dynamic

try:
    from . import geom_query
    from . import lisp_runner
    from . import validators as V
except ImportError:
    import geom_query
    import lisp_runner
    import validators as V

logger = logging.getLogger("cad_controller")

# ---------------------------------------------------------------- COM 재시도

_RPC_E_CALL_REJECTED = -2147418111       # 0x80010001 바쁨 — 실행 안 됨, 재시도 안전
_RPC_E_SERVERCALL_RETRYLATER = -2147417846  # 0x8001010A
_ACAD_SAVE_TRANSIENT = -2145320861       # 저장·열기 중 SaveAs 일시 오류
# 연결이 죽은 경우 — 재시도 무의미, 다음 호출에서 다시 붙는다.
_CONNECTION_LOST = frozenset((
    -2147417848,  # RPC_E_DISCONNECTED
    -2147418105,  # RPC_E_SERVER_DIED
    -2147418094,  # RPC_E_SERVER_DIED_DNE
    -2147023174,  # RPC_S_SERVER_UNAVAILABLE
    -2147023170,  # RPC_S_CALL_FAILED
    -2147221021,  # MK_E_UNAVAILABLE
    -2147220995,  # CO_E_OBJNOTCONNECTED
))

_on_dead = []  # 연결이 죽었음을 알릴 콜백


def _is_retryable(e, attr: Optional[str]) -> bool:
    hr = getattr(e, "hresult", None)
    if hr in (_RPC_E_CALL_REJECTED, _RPC_E_SERVERCALL_RETRYLATER):
        return True
    if _ACAD_SAVE_TRANSIENT in tuple(getattr(e, "excepinfo", None) or ()):
        return True
    # pywin32 동적 디스패치는 "멤버 찾기 거절"을 AttributeError로 바꿔 hresult를 잃는다.
    # 새 도면 직후 실제로 겪었다(실측: Documents.Add 직후 'Add.Name').
    if attr and isinstance(e, AttributeError):
        msg = str(e)
        return msg.endswith("." + attr) or msg.endswith("attribute '%s'" % attr)
    return False


def com_retry(fn, attr: Optional[str] = None, retries: int = 70, delay: float = 0.3):
    """fn()을 실행하고, AutoCAD가 바빠 거절하면 최대 약 20초까지 다시 보낸다.
    (도구 전수 시험 중 UNDO 직후 9초 넘게 거절된 적이 있다.)"""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if getattr(e, "hresult", None) in _CONNECTION_LOST:
                for cb in _on_dead:
                    cb()
                raise
            if _is_retryable(e, attr) and attempt < retries - 1:
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("unreachable")


def unwrap(v):
    """ComProxy를 원래 COM 객체로 되돌린다(다른 COM 호출의 인자로 넘길 때)."""
    if isinstance(v, ComProxy):
        return object.__getattribute__(v, "_o")
    if isinstance(v, (list, tuple)):
        return type(v)(unwrap(x) for x in v)
    return v


def wrap(v):
    if isinstance(v, win32com.client.dynamic.CDispatch):
        return ComProxy(v)
    if isinstance(v, tuple) and v and any(isinstance(x, win32com.client.dynamic.CDispatch) for x in v):
        return tuple(wrap(x) for x in v)
    return v


class ComProxy:
    """속성 읽기·쓰기·메서드 호출마다 com_retry를 거는 얇은 감싸개."""
    __slots__ = ("_o",)

    def __init__(self, o):
        object.__setattr__(self, "_o", o)

    def __getattr__(self, name):
        o = object.__getattribute__(self, "_o")
        v = com_retry(lambda: getattr(o, name), attr=name)
        if isinstance(v, win32com.client.dynamic.CDispatch):
            return ComProxy(v)
        if isinstance(v, types.MethodType):
            def call(*args):
                a = tuple(unwrap(x) for x in args)
                return wrap(com_retry(lambda: v(*a), attr=name))
            return call
        return wrap(v)

    def __setattr__(self, name, value):
        o = object.__getattribute__(self, "_o")
        value = unwrap(value)
        com_retry(lambda: setattr(o, name, value), attr=name)

    def __call__(self, *args):
        """형식 정보를 못 받은 객체에서는 메서드가 호출 가능한 CDispatch로 올 수 있다."""
        o = object.__getattribute__(self, "_o")
        a = tuple(unwrap(x) for x in args)
        return wrap(com_retry(lambda: o(*a)))

    def __repr__(self):
        return "<ComProxy>"


# ---------------------------------------------------------------- COM 전용 스레드

class CadBusy(RuntimeError):
    """앞선 작업이 아직 AutoCAD 안에서 끝나지 않았다."""


class _Job:
    __slots__ = ("fn", "args", "kwargs", "future", "label", "limit")

    def __init__(self, fn, args, kwargs, limit=None):
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.future = concurrent.futures.Future()
        self.label = getattr(fn, "__name__", "?")
        self.limit = limit  # 부른 쪽이 기다리기로 한 시간(초). 모르면 None


class ComWorker(threading.Thread):
    """AutoCAD COM은 한 STA 스레드에서만 만진다. 일감(_Job)을 받은 순서대로 이 스레드에서 처리한다.

    SendCommand는 LISP가 끝나야 돌아온다(README 9장). 그 사이 일감을 계속 쌓으면 AutoCAD가 막혔을 때
    모든 도구가 하염없이 기다리므로, 지금 일감이 BUSY_FAST_FAIL초를 넘겼으면 새 일감은 받지 않고 바로 알린다.
    daemon 스레드라 AutoCAD가 멈춰 있어도 서버 프로세스는 끝날 수 있다.
    """
    BUSY_FAST_FAIL = 5.0

    def __init__(self, diagnose=None):
        super().__init__(name="cad-com", daemon=True)
        self._inbox: "queue.SimpleQueue[_Job]" = queue.SimpleQueue()
        self._now = None          # (시작 시각, 일감 이름, 제한 초) — 처리 중일 때만
        self._diagnose = diagnose  # COM 없이 AutoCAD 화면 상태(대화창 등)를 한 줄로 알려 주는 함수
        self.start()

    def run(self):  # threading.Thread의 본문
        pythoncom.CoInitialize()
        while True:
            job = self._inbox.get()
            if job.future.cancelled() or not job.future.set_running_or_notify_cancel():
                continue  # 기다리던 쪽이 이미 포기했다
            self._now = (time.monotonic(), job.label, job.limit)
            try:
                job.future.set_result(job.fn(*job.args, **job.kwargs))
            except BaseException as err:  # noqa: BLE001 — 부른 쪽에서 다시 던진다
                job.future.set_exception(err)
            finally:
                self._now = None

    def _hint(self) -> str:
        try:
            return self._diagnose() if self._diagnose else ""
        except Exception:
            return ""

    def busy_info(self) -> Optional[dict]:
        now = self._now
        if not now:
            return None
        return {"task": now[1], "seconds": round(time.monotonic() - now[0], 1), "limit": now[2] or 120.0}

    def _enqueue(self, fn, args, kwargs, limit=None) -> "concurrent.futures.Future":
        job = _Job(fn, args, kwargs, limit)
        self._inbox.put(job)
        return job.future

    def submit(self, fn, *args, **kwargs):
        """끝날 때까지 기다려 결과를 돌려준다. 이 스레드 안에서 부르면 줄 서지 않고 바로 실행."""
        if threading.current_thread() is self:
            return fn(*args, **kwargs)
        return self._enqueue(fn, args, kwargs).result()

    async def call(self, fn, *args, timeout: float = 60.0, **kwargs):
        now = self._now
        if now and time.monotonic() - now[0] > self.BUSY_FAST_FAIL:
            spent = time.monotonic() - now[0]
            limit = now[2] or 120.0
            if spent < limit:
                # 정상적으로 오래 걸리는 작업(큰 조회·일괄 작도·플롯)일 수 있다 — 끊으라고 하지 않는다
                raise CadBusy("앞선 작업(%s)이 %.0f초째 실행 중입니다(그 작업의 제한 %.0f초). 끝난 뒤 다시 부르세요."
                              % (now[1], spent, limit))
            raise CadBusy("앞선 작업(%s)이 %.0f초째 AutoCAD 안에서 끝나지 않았습니다(제한 %.0f초 넘김).%s AutoCAD 화면"
                          "(대화창·명령줄)을 확인하거나 cancel_command를 부르세요." % (now[1], spent, limit, self._hint()))
        fut = self._enqueue(fn, args, kwargs, timeout)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(fut), timeout)
        except asyncio.TimeoutError:
            fut.cancel()  # 아직 차례가 안 왔으면 실행되지 않는다
            raise CadBusy("AutoCAD가 %.0f초 안에 응답하지 않았습니다.%s 작업이 실행 중이었다면 효과가 "
                          "들어갔을 수 있으니 다시 실행하기 전에 도면을 확인하세요." % (timeout, self._hint()))


# ---------------------------------------------------------------- 캡처 보조

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def grab_window(hwnd):
    """창 내용을 그림(PIL)으로 — 앞으로 끌어오지 않고, 다른 창에 가려져 있어도 된다(PrintWindow 전체 그리기).
    순수 ctypes GDI로 32비트 위→아래 DIB를 받아 만든다. 크기가 0이거나 실패하거나 전부 검정이면 None."""
    from PIL import Image

    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    for f in (u32.GetWindowDC, g32.CreateCompatibleDC, g32.CreateCompatibleBitmap, g32.SelectObject):
        f.restype = ctypes.c_void_p
    u32.GetWindowDC.argtypes = [wt.HWND]
    u32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
    u32.PrintWindow.argtypes = [wt.HWND, ctypes.c_void_p, wt.UINT]
    g32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
    g32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    g32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    g32.DeleteObject.argtypes = [ctypes.c_void_p]
    g32.DeleteDC.argtypes = [ctypes.c_void_p]
    g32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT, wt.UINT, ctypes.c_void_p,
                              ctypes.c_void_p, wt.UINT]

    rc = wt.RECT()
    if not u32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rc)):  # HWND로 감싸 64비트 값도 넘친 없이
        return None
    width, height = rc.right - rc.left, rc.bottom - rc.top
    if width <= 0 or height <= 0:
        return None
    screen = u32.GetWindowDC(hwnd)
    if not screen:
        return None
    mem = bitmap = old = None
    try:
        mem = g32.CreateCompatibleDC(screen)
        bitmap = g32.CreateCompatibleBitmap(screen, width, height)
        old = g32.SelectObject(mem, bitmap)
        if not u32.PrintWindow(hwnd, mem, 2):  # 2 = PW_RENDERFULLCONTENT(하드웨어 가속 창도)
            return None
        head = _BITMAPINFOHEADER()
        head.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        head.biWidth, head.biHeight = width, -height  # 음수 = 위에서 아래로
        head.biPlanes, head.biBitCount, head.biCompression = 1, 32, 0  # BI_RGB
        pixels = ctypes.create_string_buffer(width * height * 4)
        g32.SelectObject(mem, old)  # GetDIBits 전에 비트맵을 DC에서 떼어 낸다
        old = None
        if g32.GetDIBits(mem, bitmap, 0, height, pixels, ctypes.byref(head), 0) != height:  # DIB_RGB_COLORS
            return None
        pic = Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1)
        return None if pic.convert("L").getextrema()[1] == 0 else pic
    finally:
        if old:
            g32.SelectObject(mem, old)
        if bitmap:
            g32.DeleteObject(bitmap)
        if mem:
            g32.DeleteDC(mem)
        u32.ReleaseDC(hwnd, screen)


def _child_rect(hwnd, class_name):
    """보이는 자식 창 중 class_name인 가장 큰 것의 화면 좌표 사각형."""
    user32 = ctypes.windll.user32
    best = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _):
        buf = ctypes.create_unicode_buffer(128)
        hw = wt.HWND(h)  # 자식 창 핸들도 HWND로 감싼다(64비트 값에서 넘치지 않게)
        user32.GetClassNameW(hw, buf, 128)
        if buf.value == class_name and user32.IsWindowVisible(hw):
            r = wt.RECT()
            user32.GetWindowRect(hw, ctypes.byref(r))
            best.append((r.right - r.left) * (r.bottom - r.top) and (r.left, r.top, r.right, r.bottom))
        return True
    user32.EnumChildWindows(wt.HWND(hwnd), PROC(cb), 0)
    best = [b for b in best if b]
    return max(best, key=lambda r: (r[2] - r[0]) * (r[3] - r[1])) if best else None


# ---------------------------------------------------------------- 상수

_LINEWEIGHTS = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211]
_BYLAYER_LW, _BYBLOCK_LW, _DEFAULT_LW = -1, -2, -3

# ObjectName → DXF 이름 (get_entity 등 COM 경로의 type 표기를 LISP 조회와 맞춘다)
_OBJ_TO_DXF = {
    "AcDbLine": "LINE", "AcDbPolyline": "LWPOLYLINE", "AcDb2dPolyline": "POLYLINE",
    "AcDb3dPolyline": "POLYLINE", "AcDbCircle": "CIRCLE", "AcDbArc": "ARC",
    "AcDbEllipse": "ELLIPSE", "AcDbText": "TEXT", "AcDbMText": "MTEXT",
    "AcDbBlockReference": "INSERT", "AcDbHatch": "HATCH", "AcDbPoint": "POINT",
    "AcDbSpline": "SPLINE", "AcDbAttributeDefinition": "ATTDEF",
    "AcDbAlignedDimension": "DIMENSION", "AcDbRotatedDimension": "DIMENSION",
    "AcDbLeader": "LEADER", "AcDbMLeader": "MULTILEADER", "AcDbTrace": "SOLID",
}

_HANDLE_HINT = ("삭제되었거나, 다른 도면의 핸들이거나, 형식이 잘못된 핸들입니다. 핸들은 도면 안에서만 "
                "유효하므로 활성 도면이 바뀌었는지 확인하고 get_entities·ssget_query로 다시 조회하세요.")

# 조회 응답 한 페이지의 직렬화 상한(대화창 부담 기준).
PAGE_BUDGET_BYTES = 256 * 1024


def _row_bytes(row) -> int:
    import json
    return len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1


def fit_page(rows: list, count: int, offset: int, key: str) -> dict:
    """조회 결과 한 쪽: 앞에서부터 PAGE_BUDGET_BYTES 안에 드는 행까지만 싣고, 남으면 truncated·next_offset을 붙인다.
    맨 첫 행부터 상한을 넘으면 쪽을 나눠도 소용없으므로 그 개체를 따로 읽으라고 알린다."""
    take, total = 0, 0
    for row in rows:
        size = _row_bytes(row)
        if total + size > PAGE_BUDGET_BYTES:
            if take == 0:
                raise ValueError("개체 %s 한 건의 응답이 %d B라 한 페이지 상한(%d B)을 넘습니다. run_lisp로 그 개체만 "
                                 "따로 읽으세요." % (row.get("handle", "?"), size - 1, PAGE_BUDGET_BYTES))
            break
        total += size
        take += 1
    shown = rows[:take]
    more = offset + take < count  # offset을 더해야 마지막 쪽에서 멈춘다
    page = {"count": count, "returned": take, "truncated": more, key: shown}
    if more:
        page["next_offset"] = offset + take
    return page


# 개체 한 줄(탭 구분) 열 순서 — LISP bcq:row와 _parse_rows가 같이 쓴다.
ROW_COLUMNS = ("index", "handle", "type", "layer", "color", "visible", "x1", "y1", "x2", "y2", "ipx", "ipy",
               "truecolor", "text")
TOTAL_TAG = "TOTAL"  # 조회 본문이 마지막에 쓰는 전체 개수 줄: TOTAL<탭>n

# 본문 앞에 붙는 조회 함수들(매 호출 다시 정의 — 재정의 허용).
#   bcq:box  개체 외곽 (x1 y1 x2 y2). GetBoundingBox가 안 되는 개체는 10·11 정의점의 최소·최대로
#            (XLINE·RAY의 11은 방향 벡터라 10만 쓴다).
#   bcq:text 문자 내용 전체. 250자 넘는 MTEXT는 앞부분이 3번 그룹 여러 개에 나뉘어 있다.
#            줄바꿈은 결과 파일 한 줄을 깨므로 빈칸으로.
#   bcq:row  index·entget 목록·ename → ROW_COLUMNS 순서의 한 줄. 좌표는 소수 8자리(1mm 정밀 규칙).
#            영역 조회가 방금 구한 외곽(_bb, _bbof = 그 개체)이 있으면 다시 구하지 않는다. 비어 있는 그룹은 ""로.
_BBOX_DEFUN = (
    "(vl-load-com)"
    "(defun bcq:box (en / ob lo hi r xs ys pts)"
    " (setq ob (vlax-ename->vla-object en)"
    "  r (vl-catch-all-apply (function vla-GetBoundingBox) (list ob (quote lo) (quote hi))))"
    " (if (and (not (vl-catch-all-error-p r)) lo hi)"
    "  (progn (setq lo (vlax-safearray->list lo) hi (vlax-safearray->list hi))"
    "   (list (car lo) (cadr lo) (car hi) (cadr hi)))"
    "  (progn"
    "   (setq pts (if (member (cdr (assoc 0 (entget en))) (quote (\"XLINE\" \"RAY\"))) (quote (10)) (quote (10 11))))"
    "   (foreach g (entget en)"
    "    (if (and (member (car g) pts) (listp (cdr g)))"
    "     (setq xs (cons (cadr g) xs) ys (cons (caddr g) ys))))"
    "   (if xs (list (apply (function min) xs) (apply (function min) ys)"
    "               (apply (function max) xs) (apply (function max) ys))))))"
    "(defun bcq:text (e / s)"
    " (setq s (apply (function strcat) (mapcar (function cdr)"
    "  (vl-remove-if-not (function (lambda (g) (= (car g) 3))) e))))"
    " (if (assoc 1 e) (setq s (strcat s (cdr (assoc 1 e)))))"
    " (vl-string-translate \"\\r\\n\" \"  \" s))"
    "(defun bcq:num (v) (rtos v 2 8))"
    "(defun bcq:row (i e en / g bb ip tc)"
    " (setq bb (if (and _bbof (eq _bbof en)) _bb (bcq:box en)) ip (cdr (assoc 10 e)) tc (cdr (assoc 420 e)))"
    " (bcq:tabs (list (itoa i) (cdr (assoc 5 e)) (cdr (assoc 0 e)) (cdr (assoc 8 e))"
    "  (if (setq g (assoc 62 e)) (itoa (cdr g)) \"256\")"
    "  (if (and (setq g (assoc 60 e)) (/= (cdr g) 0)) \"0\" \"1\")"
    "  (if bb (bcq:num (nth 0 bb)) \"\") (if bb (bcq:num (nth 1 bb)) \"\")"
    "  (if bb (bcq:num (nth 2 bb)) \"\") (if bb (bcq:num (nth 3 bb)) \"\")"
    "  (if (and ip (listp ip)) (bcq:num (car ip)) \"\") (if (and ip (listp ip)) (bcq:num (cadr ip)) \"\")"
    "  (if tc (itoa tc) \"\") (bcq:text e))))"
    "(defun bcq:tabs (lst / out) (setq out (car lst))"
    " (foreach x (cdr lst) (setq out (strcat out _d (if x x \"\")))) out)"
)
_ENT_EMIT = "(write-line (bcq:row _i _e _en) _fp)"


def _total_line(lines: List[str]):
    for ln in lines:
        if ln.startswith(TOTAL_TAG + "	"):
            return int(ln.split("	", 1)[1].strip() or 0)
    return None


def _parse_rows(lines: List[str]) -> tuple:
    """bcq:row 줄들 → (전체 개수, [행]). TOTAL 줄이 없으면 받은 행 수가 전체."""
    out = []
    for ln in lines:
        cells = ln.split("	", len(ROW_COLUMNS) - 1)
        if cells[0] == TOTAL_TAG or len(cells) < len(ROW_COLUMNS) - 1:
            continue
        v = dict(zip(ROW_COLUMNS, cells + [""] * (len(ROW_COLUMNS) - len(cells))))
        try:
            row = {"index": int(v["index"]), "handle": v["handle"], "type": v["type"], "layer": v["layer"],
                   "color": int(v["color"]), "visible": v["visible"] == "1"}
        except ValueError:
            continue
        if v["x1"]:
            row["bbox_min"] = [float(v["x1"]), float(v["y1"])]
            row["bbox_max"] = [float(v["x2"]), float(v["y2"])]
        if v["ipx"]:
            row["insertion_point"] = [float(v["ipx"]), float(v["ipy"])]
        if v["truecolor"]:
            t = int(v["truecolor"])
            row["true_color"] = "%d,%d,%d" % (t >> 16 & 255, t >> 8 & 255, t & 255)
        if v["text"] or v["type"] in ("TEXT", "MTEXT", "ATTDEF"):
            row["text"] = v["text"]
        out.append(row)
    total = _total_line(lines)
    return (len(out) if total is None else total), out


# ================================================================ 제어기

class AcadControl:
    """AutoCAD에 붙어 도구가 요청한 일을 한다. 메서드는 모두 COM 스레드에서 실행된다."""

    def __init__(self):
        self.executor = ComWorker(diagnose=self._diagnose)
        self.app = None   # ComProxy
        self.hwnd = 0     # 주 창 핸들(ESC 감시용, COM 없이 쓴다)
        _on_dead.append(self._reset)

    def main_hwnd(self) -> int:
        """주 창 핸들. COM으로 붙기 전이면 창 목록에서 찾는다(COM 스레드가 막혀도 쓸 수 있게)."""
        return self.hwnd or lisp_runner.find_acad_hwnd()

    def _diagnose(self) -> str:
        """COM 없이 화면 상태 한마디(대화창이 떠 있으면 그 제목)."""
        fw = lisp_runner.focus_window(self.main_hwnd())
        if lisp_runner.is_dialog(fw):
            return " AutoCAD에 대화창 '%s'이(가) 떠 있습니다 — 화면에서 직접 확인하세요." % fw["root_title"]
        return ""

    # ------------------------------------------------------------ 연결

    def _reset(self):
        logger.warning("AutoCAD 연결이 끊어졌습니다 — 다음 호출에서 다시 붙습니다")
        self.app = None
        self.hwnd = 0

    def connect(self):
        """켜져 있는 AutoCAD에만 붙는다(자동 실행하지 않음)."""
        if self.app is not None:
            return self.app
        pythoncom.CoInitialize()
        try:
            raw = win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception as e:
            raise RuntimeError("실행 중인 AutoCAD를 찾지 못했습니다. AutoCAD를 먼저 켜 주세요. (%s)" % e)
        self.app = ComProxy(win32com.client.dynamic.Dispatch(raw._oleobj_))
        self.hwnd = int(self.app.HWND)
        logger.info("AutoCAD에 연결: %s", self.app.Version)
        return self.app

    @property
    def doc(self):
        app = self.connect()
        try:
            return app.ActiveDocument
        except Exception as e:
            raise RuntimeError("활성 도면이 없습니다. 도면을 열거나 new_drawing을 부르세요. (%s)" % e)

    def _require_idle(self, doc=None):
        """사용자가 명령 중이거나 AutoCAD가 유휴가 아니면 거절한다. MCP가 사람의 명령을 끊지 않는다."""
        doc = doc or self.doc
        active = int(doc.GetVariable("CMDACTIVE"))
        quiet = True
        try:
            quiet = bool(self.app.GetAcadState().IsQuiescent)
        except Exception:
            pass
        if active or not quiet:
            names = ""
            try:
                names = str(doc.GetVariable("CMDNAMES"))
            except Exception:
                pass
            raise CadBusy("AutoCAD가 명령 실행 중입니다(CMDACTIVE=%d, 명령=%s, 유휴=%s). 사람이 쓰는 중일 수 "
                          "있어 건드리지 않았습니다. 명령을 끝낸 뒤 다시 부르거나, MCP가 남긴 것이면 "
                          "cancel_command를 부르세요." % (active, names or "-", quiet))
        return doc

    def lisp(self, body: str, timeout_s: float = 45.0, doc=None) -> List[str]:
        """유휴 확인과 SendCommand를 한 작업 안에서 연속 실행한다(사이에 다른 호출이 끼지 않게).
        doc을 주면 호출부가 같은 작업 안에서 이미 _require_idle로 확인한 것으로 본다.
        timeout_s는 server._run의 바깥 제한시간보다 짧아야 ESC 복구가 먼저 돈다."""
        if doc is None:
            doc = self._require_idle()
        return lisp_runner.run(doc, self.hwnd, _BBOX_DEFUN + body, timeout_s)

    @contextmanager
    def _undo_group(self, doc):
        """이번 도구 작업 전체를 UNDO 한 번에 되돌릴 묶음으로. LISP 작업도 같이 묶인다(실측)."""
        doc.StartUndoMark()
        try:
            yield
        finally:
            try:
                doc.EndUndoMark()
            except Exception:
                logger.warning("EndUndoMark 실패(도면 전환 등)")

    def _resolve(self, doc, handle: str):
        h = (handle or "").strip()
        if not h:
            raise LookupError("핸들이 비어 있습니다. get_entities·ssget_query로 먼저 조회하세요.")
        try:
            return doc.HandleToObject(h)
        except Exception as e:
            raise LookupError("핸들 '%s'을(를) 현재 도면(%s)에서 찾을 수 없습니다. %s"
                              % (h, doc.Name, _HANDLE_HINT)) from e

    @staticmethod
    def _vpt(x, y, z=0.0):
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)])

    @staticmethod
    def _varr(vals):
        return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in vals])

    # ------------------------------------------------------------ 정보·진단

    def ping(self) -> dict:
        return {"status": "pong", "drawing": self.doc.Name}

    def get_cad_info(self) -> dict:
        app = self.connect()
        d = self.doc
        return {"application": app.Caption, "version": app.Version, "drawing": d.Name,
                "path": d.Path, "full_name": d.FullName}

    def health_check(self) -> dict:
        out = {"connected": False}
        try:
            app = self.connect()
            # AutoCAD를 껐다 켠 뒤면 붙어 있던 연결이 죽어 있다 — 재시도 없이 한 번 찔러 보고, 죽었으면 새로 붙는다
            # (아래에서 예외를 삼키는 진단 함수라 바깥의 '죽은 연결이면 다시 보내기'가 돌지 않는다)
            try:
                unwrap(app).HWND  # 연결할 때 이미 읽은 속성이라 죽은 연결이면 hresult가 붙은 오류가 난다
            except Exception as e:  # noqa: BLE001 — 바쁨(대화창) 같은 다른 오류는 아래 진단이 다룬다
                if getattr(e, "hresult", None) in _CONNECTION_LOST:
                    self._reset()
                    app = self.connect()
        except Exception as e:
            out["connect_error"] = str(e)
            return out
        out.update(connected=True, hwnd=self.hwnd)
        # 대화창이 떠 있으면 COM 호출이 거절되며 재시도로 20초 넘게 걸린다 — 창 상태(COM 없음)부터 보고 바로 돌려준다
        fw = lisp_runner.focus_window(self.hwnd)
        out["focus_root"] = {"class": fw["root_class"], "title": fw["root_title"]}
        out["dialog_open"] = lisp_runner.is_dialog(fw)
        if out["dialog_open"]:
            out["responsive"] = False
            out["error"] = "AutoCAD에 대화창이 떠 있습니다: %s" % fw["root_title"]
            return out
        try:
            out["version"] = app.Version
            out["caption"] = app.Caption
            out["documents_count"] = app.Documents.Count
            t0 = time.perf_counter()
            d = app.ActiveDocument
            out["active_document"] = d.Name
            out["active_document_path"] = d.FullName
            out["ping_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            out["cmdactive"] = int(d.GetVariable("CMDACTIVE"))
            out["quiescent"] = bool(app.GetAcadState().IsQuiescent)
            out["responsive"] = True
        except Exception as e:
            out["responsive"] = False
            out["error"] = "%s: %s" % (type(e).__name__, e)
        return out

    # ------------------------------------------------------------ 문서

    def list_documents(self) -> list:
        app = self.connect()
        docs = app.Documents
        active = app.ActiveDocument.Name  # 열린 도면 이름은 세션 안에서 유일(저장 안 한 도면은 FullName이 빈 값)
        out = []
        for i in range(docs.Count):
            d = docs.Item(i)
            out.append({"index": i, "name": d.Name, "full_name": d.FullName, "active": d.Name == active})
        return out

    def _wait_active(self, name_check, seconds=20.0):
        """새로 열거나 만든 도면이 활성이 되고 호출을 받을 때까지 기다린다(실측: 직후 잠깐 거절)."""
        deadline = time.time() + seconds
        last = None
        while time.time() < deadline:
            try:
                d = self.app.ActiveDocument
                if name_check(d):
                    _ = d.ModelSpace.Count
                    return d
            except Exception as e:
                last = e
            time.sleep(0.3)
        raise RuntimeError("도면이 %d초 안에 준비되지 않았습니다 (%s)" % (seconds, last))

    def activate_document(self, name: str) -> dict:
        app = self.connect()
        docs = app.Documents
        key = name.lower()
        for i in range(docs.Count):
            d = docs.Item(i)
            if key in d.Name.lower() or key in d.FullName.lower():
                d.Activate()
                full = d.FullName or d.Name
                self._wait_active(lambda x: (x.FullName or x.Name) == full)
                return {"activated": full}
        raise ValueError("도면을 찾을 수 없습니다: %s (list_documents로 확인)" % name)

    def open_drawing(self, path: str, read_only: bool = False) -> dict:
        app = self.connect()
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError("파일이 없습니다: %s" % path)
        docs = app.Documents
        norm = os.path.normcase(path)
        for i in range(docs.Count):
            d = docs.Item(i)
            if d.FullName and os.path.normcase(d.FullName) == norm:
                d.Activate()
                self._wait_active(lambda x: os.path.normcase(x.FullName or "") == norm)
                return {"opened": d.FullName, "already_open": True}
        docs.Open(path, bool(read_only))
        d = self._wait_active(lambda x: os.path.normcase(x.FullName or "") == norm, 60.0)
        return {"opened": d.FullName, "read_only": bool(read_only)}

    def _check_target_free(self, path: str, current) -> None:
        """다른 열린 도면이 잡고 있는 파일로 SaveAs하면 계속 실패한다(실측) — 미리 막는다."""
        norm = os.path.normcase(path)
        docs = self.app.Documents
        for i in range(docs.Count):
            d = docs.Item(i)
            if d.FullName and os.path.normcase(d.FullName) == norm and d.Name != current.Name:
                raise ValueError("대상 파일이 다른 열린 도면에서 쓰이고 있어 덮어쓸 수 없습니다: %s" % path)

    def save_drawing(self, path: str = "") -> dict:
        d = self._require_idle()
        if path:
            path = os.path.abspath(path)
            if os.path.splitext(path)[1].lower() not in (".dwg", ".dxf"):
                raise ValueError("저장 경로는 .dwg 또는 .dxf여야 합니다: %s" % path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._check_target_free(path, d)
            d.SaveAs(path)
        else:
            if not int(d.GetVariable("DWGTITLED")):
                raise ValueError("저장된 적 없는 새 도면입니다(%s). path를 지정하세요." % d.Name)
            if d.ReadOnly:
                raise ValueError("읽기 전용으로 연 도면입니다. 다른 path로 저장하세요.")
            d.Save()
        return {"saved": d.FullName}

    def close_drawing(self, save: bool = True) -> dict:
        d = self._require_idle()
        name = d.FullName or d.Name
        if save:
            if not int(d.GetVariable("DWGTITLED")):
                raise ValueError("저장된 적 없는 새 도면이라 그대로 저장할 수 없습니다. save_drawing(path=...)로 "
                                 "먼저 저장하거나 save=false로 닫으세요.")
            if d.ReadOnly:
                raise ValueError("읽기 전용으로 연 도면이라 저장할 수 없습니다. 다른 path로 save_drawing 하거나 "
                                 "save=false로 닫으세요.")
            d.Save()
        d.Close(False)  # 이미 저장했거나 버리기로 했다 — 저장 여부를 묻는 대화창을 띄우지 않는다
        return {"closed": name, "saved": bool(save)}

    def new_drawing(self) -> dict:
        app = self.connect()
        before = {app.Documents.Item(i).Name for i in range(app.Documents.Count)}
        app.Documents.Add()
        d = self._wait_active(lambda x: x.Name not in before)
        return {"created": d.Name}

    def get_drawing_info(self) -> dict:
        d = self.doc
        out = {"name": d.Name, "path": d.Path, "full_name": d.FullName, "saved": bool(d.Saved),
               "read_only": bool(d.ReadOnly), "titled": bool(int(d.GetVariable("DWGTITLED")))}
        try:
            mn, mx = d.GetVariable("EXTMIN"), d.GetVariable("EXTMAX")
            out["extents"] = {"min": [mn[0], mn[1]], "max": [mx[0], mx[1]]}
        except Exception:
            pass
        try:
            mn, mx = d.GetVariable("LIMMIN"), d.GetVariable("LIMMAX")
            out["limits"] = {"lower_left": [mn[0], mn[1]], "upper_right": [mx[0], mx[1]]}
        except Exception:
            out["limits"] = "unavailable"
        out["modelspace_count"] = d.ModelSpace.Count
        out["current_layer"] = d.ActiveLayer.Name
        out["insunits"] = int(d.GetVariable("INSUNITS"))
        return out

    # ------------------------------------------------------------ 색·선종류·스타일

    @staticmethod
    def _color_of(obj) -> dict:
        """{"color": ACI(256=ByLayer, 0=ByBlock), "true_color": "r,g,b"(트루컬러일 때만)}"""
        out = {}
        try:
            tc = obj.TrueColor
            method = int(tc.ColorMethod)
            if method == 192:      # acColorMethodByLayer
                out["color"] = 256
            elif method == 193:    # acColorMethodByBlock
                out["color"] = 0
            else:
                out["color"] = int(tc.ColorIndex)
                if method == 194:  # acColorMethodByRGB
                    out["true_color"] = "%d,%d,%d" % (tc.Red, tc.Green, tc.Blue)
        except Exception:
            try:
                out["color"] = int(obj.Color)
            except Exception:
                out["color"] = None
        return out

    @staticmethod
    def _set_color(obj, color=None, true_color=None):
        if true_color:
            r, g, b = V.rgb(true_color)
            tc = obj.TrueColor
            tc.SetRGB(r, g, b)
            obj.TrueColor = tc
        elif color is not None:
            obj.Color = V.aci(color)

    def _ensure_linetype(self, doc, name: str) -> str:
        """선종류가 도면에 없으면 표준 .lin에서 불러온다(set_layer·작도·modify 공통)."""
        if name.upper() in ("BYLAYER", "BYBLOCK", "CONTINUOUS"):
            return name
        lts = doc.Linetypes
        for i in range(lts.Count):
            lt = lts.Item(i)
            if lt.Name.casefold() == name.casefold():
                return lt.Name
        lin = "acadiso.lin" if int(doc.GetVariable("MEASUREMENT")) == 1 else "acad.lin"
        try:
            lts.Load(name, lin)
        except Exception as e:
            raise ValueError("선종류 '%s'를 %s에서 불러오지 못했습니다(이름 확인): %s" % (name, lin, e))
        return name

    def _ensure_layer(self, doc, name: str):
        """레이어가 없으면 만든다. 현재 레이어는 바꾸지 않는다."""
        layers = doc.Layers
        for i in range(layers.Count):
            la = layers.Item(i)
            if la.Name.casefold() == name.casefold():
                return la
        return layers.Add(name)

    def _apply_style(self, doc, ent, layer="", color=-1, true_color="", linetype="", lineweight=-1):
        if layer:
            ent.Layer = self._ensure_layer(doc, layer).Name
        if true_color:
            self._set_color(ent, true_color=true_color)
        elif color is not None and color >= 0:
            self._set_color(ent, color=color)
        if linetype:
            ent.Linetype = self._ensure_linetype(doc, linetype)
        if lineweight is not None and lineweight != -1:
            lw = int(lineweight)
            if lw not in _LINEWEIGHTS + [_BYLAYER_LW, _BYBLOCK_LW, _DEFAULT_LW]:
                raise ValueError("lineweight는 %s 중 하나(1/100mm) 또는 -1(ByLayer)·-2(ByBlock)·-3(기본)이어야 "
                                 "합니다: %r" % (_LINEWEIGHTS, lineweight))
            ent.Lineweight = lw

    def _create(self, what: str, make, style: dict, extra=None) -> dict:
        """개체 하나를 만들고 스타일을 입힌다. 도중에 실패하면 이번에 만든 개체만 지우고 원인을 올린다."""
        d = self._require_idle()
        with self._undo_group(d):
            ms = d.ModelSpace
            ent = make(ms)
            try:
                if extra:
                    extra(ent)
                self._apply_style(d, ent, **style)
                ent.Update()
            except Exception as e:
                cleanup = "삭제함"
                try:
                    ent.Delete()
                except Exception as e2:
                    cleanup = "삭제 실패: %s" % e2
                raise RuntimeError("%s 생성 중 속성 지정 실패: %s (만든 개체 %s)" % (what, e, cleanup)) from e
            return {"handle": ent.Handle, "type": _OBJ_TO_DXF.get(ent.ObjectName, ent.ObjectName),
                    "drawing": d.Name}

    # ------------------------------------------------------------ 레이어

    def get_layers(self) -> list:
        d = self.doc
        layers = d.Layers
        cur = d.ActiveLayer.Name
        out = []
        for i in range(layers.Count):
            la = layers.Item(i)
            row = {"name": la.Name, "on": bool(la.LayerOn), "frozen": bool(la.Freeze), "locked": bool(la.Lock),
                   "linetype": la.Linetype, "lineweight": int(la.Lineweight), "current": la.Name == cur}
            row.update(self._color_of(la))
            out.append(row)
        return out

    def set_layer(self, name: str, color: int = -1, on=None, locked=None, linetype: str = "",
                  true_color: str = "", lineweight: int = -1) -> dict:
        if not name or not name.strip():
            raise ValueError("레이어 이름이 비어 있습니다")
        # 입력 검사를 모두 먼저 한다 — 레이어를 만들고 일부만 바꾼 채 오류로 끝나지 않게.
        rgb = V.rgb(true_color) if true_color else None
        c = None
        if not rgb and color is not None and color >= 0:
            c = V.aci(color)
            if c in (0, 256):
                raise ValueError("레이어 색은 1~255여야 합니다(ByLayer/ByBlock 불가): %r" % color)
        lw = None
        if lineweight is not None and lineweight != -1:
            lw = int(lineweight)
            if lw not in _LINEWEIGHTS + [_DEFAULT_LW]:
                raise ValueError("레이어 lineweight는 %s 또는 -3(기본)이어야 합니다: %r" % (_LINEWEIGHTS, lineweight))
        d = self._require_idle()
        lt = self._ensure_linetype(d, linetype) if linetype else None
        with self._undo_group(d):
            layers = d.Layers
            existing = None
            for i in range(layers.Count):
                la = layers.Item(i)
                if la.Name.casefold() == name.casefold():
                    existing = la
                    break
            la = existing or layers.Add(name)
            changed = []
            if rgb:
                self._set_color(la, true_color=true_color)
                changed.append("true_color")
            elif c is not None:
                la.Color = c
                changed.append("color")
            if on is not None:
                la.LayerOn = bool(on)
                changed.append("on")
            if locked is not None:
                la.Lock = bool(locked)
                changed.append("locked")
            if lt:
                la.Linetype = lt
                changed.append("linetype")
            if lw is not None:
                la.Lineweight = lw
                changed.append("lineweight")
        return {"layer": la.Name, "action": "set" if existing else "created", "changed": changed,
                "drawing": d.Name}

    def set_active_layer(self, name: str) -> dict:
        d = self._require_idle()
        layers = d.Layers
        for i in range(layers.Count):
            la = layers.Item(i)
            if la.Name.casefold() == name.casefold():
                if la.Freeze:
                    raise ValueError("동결된 레이어는 현재 레이어로 만들 수 없습니다: %s" % la.Name)
                d.ActiveLayer = la
                return {"active_layer": la.Name, "drawing": d.Name}
        raise ValueError("레이어가 없습니다: %s (set_layer로 먼저 만드세요)" % name)

    # ------------------------------------------------------------ 조회 (LISP ssget)

    @staticmethod
    def _filter(entity_type="", layer="", text_like="", color=None) -> str:
        f = ["(cons 67 0)"]  # 모형 공간만
        if entity_type:
            f.append('(cons 0 "%s")' % V.lisp_str(V.dxf_type(entity_type)))
        if layer:
            f.append('(cons 8 "%s")' % V.lisp_str(V.wild_escape(layer)))
        if text_like:
            f.append('(cons 1 "%s")' % V.lisp_str(text_like))
        if color is not None and color >= 0:
            f.append("(cons 62 %d)" % V.aci(color))
        return "(list " + " ".join(f) + ")"

    def _query(self, flist: str, area, limit: int, offset: int, handles_only: bool = False) -> dict:
        """ssget "_X"로 고르고 영역은 외곽 겹침으로 직접 거른다(_C는 화면 밖을 놓친다, 실측)."""
        limit, offset = int(limit), int(offset)
        if limit < 1 or offset < 0:
            raise ValueError("limit은 1 이상, offset은 0 이상이어야 합니다")
        if area:
            x1, y1, x2, y2 = area
            keep = ("(setq _bb (bcq:box _en) _bbof _en)"
                    " (and _bb (<= (nth 0 _bb) %.8f) (>= (nth 2 _bb) %.8f) (<= (nth 1 _bb) %.8f) (>= (nth 3 _bb) %.8f))"
                    % (x2, x1, y2, y1))
        else:
            keep = "T"
        if handles_only:
            emit = ('(write-line (strcat (itoa _i) _d (cdr (assoc 5 _e)) _d (cdr (assoc 0 _e)) _d'
                    ' (cdr (assoc 8 _e))) _fp)')
        else:
            emit = _ENT_EMIT
        body = (
            '(setq _ss (ssget "_X" ' + flist + ') _m 0 _i 0 _c 0)'
            "(if _ss (progn (setq _n (sslength _ss) _k 0)"
            " (while (< _k _n)"
            "  (setq _en (ssname _ss _k) _k (1+ _k))"
            "  (if (progn " + keep + ")"
            "   (progn (if (and (>= _m %d) (< _c %d))"
            "     (progn (setq _e (entget _en) _i _m) " + emit + " (setq _c (1+ _c))))"
            "    (setq _m (1+ _m)))))))"
            '(write-line (strcat "TOTAL" _d (itoa _m)) _fp)'
        ) % (offset, limit)
        lines = self.lisp(body, timeout_s=120.0)
        if handles_only:
            count = _total_line(lines) or 0
            rows = []
            for ln in lines:
                c = ln.split("\t", 3)
                if len(c) == 4 and c[0] != TOTAL_TAG:
                    rows.append({"index": int(c[0]), "handle": c[1], "type": c[2], "layer": c[3]})
        else:
            count, rows = _parse_rows(lines)
        return fit_page(rows, count, offset, "entities")

    def get_entities(self, layer="", entity_type="", limit=100, offset=0, bbox=None) -> dict:
        return self._query(self._filter(entity_type, layer), bbox, limit, offset)

    def ssget_query(self, entity_type="", layer="", text_like="", color=-1, area=None,
                    limit=2000, offset=0, fields="full") -> dict:
        if fields not in ("full", "handles"):
            raise ValueError('fields는 "full" 또는 "handles"여야 합니다: %r' % fields)
        return self._query(self._filter(entity_type, layer, text_like, color), area, limit, offset,
                           handles_only=fields == "handles")

    def count_entities(self, layer="", entity_type="") -> dict:
        flist = self._filter(entity_type, layer)
        body = ('(setq _t (ssget "_X" (list (cons 67 0))) _m (ssget "_X" ' + flist + '))'
                '(write-line (strcat (if _t (itoa (sslength _t)) "0") "," (if _m (itoa (sslength _m)) "0")) _fp)')
        line = self.lisp(body)
        total, matched = (int(x) for x in line[0].split(",", 1))
        return {"total": total, "matched": matched}

    def entget_by_handles(self, handles: List[str]) -> dict:
        if not handles:
            return {"count": 0, "returned": 0, "truncated": False, "entities": []}
        lits = " ".join('"%s"' % V.lisp_str(h) for h in handles)
        body = ("(setq _i 0)"
                "(foreach _h (list " + lits + ")"
                # 도형만(레이어 8번이 있는 것) — 표·사전 같은 비도형 핸들은 없는 것으로 센다
                " (if (and (setq _en (handent _h)) (setq _e (entget _en)) (assoc 8 _e)) (progn " + _ENT_EMIT + "))"
                " (setq _i (1+ _i)))")
        _, rows = _parse_rows(self.lisp(body, timeout_s=120.0))
        page = fit_page(rows, len(rows), 0, "entities")
        page["requested"] = len(handles)
        if page.pop("next_offset", None) is not None:
            page["next_index"] = page["entities"][-1]["index"] + 1  # index = 입력 handles 위치
        page["missing"] = len(handles) - len(rows) if not page["truncated"] else None
        return page

    def find_text(self, keyword: str, limit=2000, offset=0) -> dict:
        if not keyword:
            raise ValueError("keyword가 비어 있습니다")
        limit, offset = int(limit), int(offset)
        if limit < 1 or offset < 0:
            raise ValueError("limit은 1 이상, offset은 0 이상이어야 합니다")
        # ssget의 (cons 1 ...)은 1번 그룹만 본다 — 250자 넘는 MTEXT의 앞부분(3번 그룹)을 놓친다.
        # 그래서 TEXT·MTEXT를 모두 고른 뒤 전체 내용을 wcmatch(대소문자 무시)로 맞춘다.
        # keyword는 글자 그대로 찾는다(D16@200, 1,234, [좌안]) — 와일드카드 조회는 ssget_query(text_like)
        pat = V.lisp_str("*" + V.wild_escape(keyword) + "*")
        body = (
            '(setq _ss (ssget "_X" (list (cons 67 0) (cons 0 "TEXT,MTEXT"))) _m 0 _c 0)'
            "(if _ss (progn (setq _n (sslength _ss) _k 0)"
            "  (while (< _k _n)"
            "   (setq _e (entget (ssname _ss _k)) _k (1+ _k) _tx (bcq:text _e))"
            '   (if (wcmatch (strcase _tx) (strcase "' + pat + '"))'
            "    (progn (if (and (>= _m %d) (< _c %d) (setq _pt (cdr (assoc 10 _e))))" % (offset, limit) +
            "      (progn (write-line (strcat (rtos (car _pt) 2 8) _d (rtos (cadr _pt) 2 8) _d"
            "        (cdr (assoc 5 _e)) _d (cdr (assoc 8 _e)) _d _tx) _fp) (setq _c (1+ _c))))"
            "     (setq _m (1+ _m)))))))"
            '(write-line (strcat "TOTAL" _d (itoa _m)) _fp)'
        )
        lines = self.lisp(body, timeout_s=120.0)
        count = _total_line(lines) or 0
        results = []
        for ln in lines:
            p = ln.split("\t", 4)
            if len(p) < 4 or p[0] == TOTAL_TAG:
                continue
            results.append({"x": float(p[0]), "y": float(p[1]), "handle": p[2], "layer": p[3],
                            "text": p[4] if len(p) > 4 else ""})
        page = fit_page(results, count, offset, "results")
        page["found"] = page.pop("count")
        return page

    def get_entity(self, handle: str) -> dict:
        d = self.doc
        ent = self._resolve(d, handle)
        obj = ent.ObjectName
        info = {"handle": ent.Handle, "type": _OBJ_TO_DXF.get(obj, obj), "object_name": obj,
                "layer": ent.Layer, "linetype": ent.Linetype, "lineweight": int(ent.Lineweight),
                "visible": bool(ent.Visible)}
        info.update(self._color_of(ent))
        try:
            mn, mx = ent.GetBoundingBox()
            info["bbox_min"] = [mn[0], mn[1]]
            info["bbox_max"] = [mx[0], mx[1]]
        except Exception:
            pass

        def get(name):
            try:
                return getattr(ent, name)
            except Exception:
                return None
        if obj in ("AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline"):
            co = list(get("Coordinates") or [])
            step = 2 if obj == "AcDbPolyline" else 3
            info["coordinates"] = [list(co[i:i + step]) for i in range(0, len(co), step)]
            info["vertex_count"] = len(info["coordinates"])
            info["closed"] = bool(get("Closed"))
            info["length"] = get("Length")
            if obj == "AcDbPolyline":
                info["elevation"] = get("Elevation")
        elif obj == "AcDbLine":
            info["start_point"] = list(get("StartPoint") or [])
            info["end_point"] = list(get("EndPoint") or [])
            info["length"] = get("Length")
            info["angle"] = math.degrees(get("Angle") or 0)
        elif obj in ("AcDbCircle", "AcDbArc"):
            info["center"] = list(get("Center") or [])[:2]  # get_entities와 같은 [x, y]
            info["radius"] = get("Radius")
            if obj == "AcDbArc":
                info["start_angle"] = math.degrees(get("StartAngle") or 0)
                info["end_angle"] = math.degrees(get("EndAngle") or 0)
                info["arc_length"] = get("ArcLength")
        elif obj == "AcDbEllipse":
            info["center"] = list(get("Center") or [])[:2]
            info["major_axis"] = list(get("MajorAxis") or [])
            info["radius_ratio"] = get("RadiusRatio")
        elif obj in ("AcDbText", "AcDbMText", "AcDbAttributeDefinition"):
            info["text"] = get("TextString")
            info["insertion_point"] = list(get("InsertionPoint") or [])[:2]
            info["height"] = get("Height")
            info["rotation"] = math.degrees(get("Rotation") or 0)
            info["style"] = get("StyleName")
            if obj == "AcDbMText":
                info["width"] = get("Width")
        elif obj == "AcDbBlockReference":
            info["block_name"] = get("Name")
            try:
                info["effective_name"] = ent.EffectiveName
            except Exception:
                pass
            info["insertion_point"] = list(get("InsertionPoint") or [])[:2]
            info["scale"] = [get("XScaleFactor"), get("YScaleFactor"), get("ZScaleFactor")]
            info["rotation"] = math.degrees(get("Rotation") or 0)
            info["has_attributes"] = bool(get("HasAttributes"))
            info["attribute_count"] = len(ent.GetAttributes()) if info["has_attributes"] else 0
        elif obj == "AcDbHatch":
            info["pattern"] = get("PatternName")
            info["area"] = get("Area")
        return info

    # ------------------------------------------------------------ 작도 (COM, OSNAP 영향 없음)

    def create_line(self, start, end, **style) -> dict:
        s, e = V.point(start, "start"), V.point(end, "end")
        if s == e:
            raise ValueError("시작점과 끝점이 같습니다")
        return self._create("선", lambda ms: ms.AddLine(self._vpt(*s), self._vpt(*e)), style)

    def create_polyline(self, points, closed=False, **style) -> dict:
        pts = V.json_points(points, "points", 2)
        flat = [c for p in pts for c in p[:2]]

        def extra(ent):
            if closed:
                ent.Closed = True
        out = self._create("폴리선", lambda ms: ms.AddLightWeightPolyline(self._varr(flat)), style, extra)
        out["vertex_count"] = len(pts)
        return out

    def create_rectangle(self, x1, y1, x2, y2, **style) -> dict:
        x1, y1, x2, y2 = (V.num(v, n) for v, n in ((x1, "x1"), (y1, "y1"), (x2, "x2"), (y2, "y2")))
        if x1 == x2 or y1 == y2:
            raise ValueError("사각형의 가로·세로가 0입니다")
        return self.create_polyline([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], closed=True, **style)

    def create_circle(self, center, radius, **style) -> dict:
        c, r = V.point(center, "center"), V.positive(radius, "radius")
        return self._create("원", lambda ms: ms.AddCircle(self._vpt(*c), r), style)

    def create_arc(self, center, radius, start_angle, end_angle, **style) -> dict:
        c, r = V.point(center, "center"), V.positive(radius, "radius")
        a1, a2 = math.radians(V.num(start_angle, "start_angle")), math.radians(V.num(end_angle, "end_angle"))
        return self._create("호", lambda ms: ms.AddArc(self._vpt(*c), r, a1, a2), style)

    def create_ellipse(self, center, major_axis, minor_axis, rotation=0.0, **style) -> dict:
        c = V.point(center, "center")
        a, b = V.positive(major_axis, "major_axis"), V.positive(minor_axis, "minor_axis")
        if b > a:
            raise ValueError("minor_axis(%s)가 major_axis(%s)보다 큽니다" % (b, a))
        rot = math.radians(V.num(rotation, "rotation"))
        vec = self._vpt(a * math.cos(rot), a * math.sin(rot))
        return self._create("타원", lambda ms: ms.AddEllipse(self._vpt(*c), vec, b / a), style)

    def _text_style_name(self, doc, name: str) -> str:
        styles = doc.TextStyles
        names = []
        for i in range(styles.Count):
            n = styles.Item(i).Name
            names.append(n)
            if n.casefold() == name.casefold():
                return n
        raise ValueError("문자 스타일 '%s'가 없습니다. 있는 스타일: %s" % (name, names))

    def get_text_styles(self) -> list:
        """문자 스타일 목록. 새 도면의 Standard(txt.shx, 큰 글꼴 없음)는 한글이 화면에 ?로 보인다
        (도구 시험 캡처로 확인) — 한글은 큰 글꼴(bigfont)이 있거나 트루타입 글꼴인 스타일을 쓴다."""
        d = self.doc
        styles = d.TextStyles
        cur = str(d.GetVariable("TEXTSTYLE"))
        out = []
        for i in range(styles.Count):
            s = styles.Item(i)
            row = {"name": s.Name, "font_file": s.FontFile, "bigfont_file": s.BigFontFile,
                   "height": s.Height, "width": s.Width, "current": s.Name.casefold() == cur.casefold()}
            try:
                face = s.GetFont()[0]
                if face:
                    row["typeface"] = face
            except Exception:
                pass
            row["korean_capable"] = bool(row.get("typeface") or s.BigFontFile)
            out.append(row)
        return out

    def set_text_style(self, name: str, typeface: str = "", font_file: str = "", bigfont_file: str = "") -> dict:
        """문자 스타일을 만들거나 글꼴을 바꾼다. typeface(트루타입, 예 "맑은 고딕") 또는
        font_file(.shx)+bigfont_file(한글 .shx) 중 하나로 지정한다."""
        if not name or not name.strip():
            raise ValueError("스타일 이름이 비어 있습니다")
        if typeface and (font_file or bigfont_file):
            raise ValueError("typeface와 font_file/bigfont_file은 같이 줄 수 없습니다")
        d = self._require_idle()
        styles = d.TextStyles
        st = None
        for i in range(styles.Count):
            s = styles.Item(i)
            if s.Name.casefold() == name.casefold():
                st = s
                break
        created = st is None
        with self._undo_group(d):
            if created:
                st = styles.Add(name)
            if typeface:
                st.SetFont(typeface, False, False, 129, 0)  # 129 = HANGEUL_CHARSET
            if font_file:
                st.FontFile = font_file
            if bigfont_file:
                st.BigFontFile = bigfont_file
        out = {"name": st.Name, "created": created, "font_file": st.FontFile, "bigfont_file": st.BigFontFile,
               "drawing": d.Name}
        try:
            out["typeface"] = st.GetFont()[0]
        except Exception:
            pass
        return out

    def create_text(self, text, x, y, height=2.5, rotation=0.0, text_style="", **style) -> dict:
        if not isinstance(text, str) or text == "":
            raise ValueError("text가 비어 있습니다")
        p = V.point([x, y], "x,y")
        h = V.positive(height, "height")
        rot = math.radians(V.num(rotation, "rotation"))

        def extra(ent):
            if text_style:
                ent.StyleName = self._text_style_name(self.doc, text_style)
            if rot:
                ent.Rotation = rot
        out = self._create("문자", lambda ms: ms.AddText(text, self._vpt(*p), h), style, extra)
        out["content"] = text
        return out

    def create_mtext(self, text, x, y, height=2.5, width=0.0, text_style="", **style) -> dict:
        if not isinstance(text, str) or text == "":
            raise ValueError("text가 비어 있습니다")
        p = V.point([x, y], "x,y")
        h = V.positive(height, "height")
        w = V.num(width, "width")
        if w < 0:
            raise ValueError("width는 0 이상이어야 합니다(0=줄바꿈 없음)")

        def extra(ent):
            if text_style:
                ent.StyleName = self._text_style_name(self.doc, text_style)
            ent.Height = h
        out = self._create("여러 줄 문자", lambda ms: ms.AddMText(self._vpt(*p), w, text), style, extra)
        out["content"] = text
        return out

    def create_hatch(self, points=None, pattern="SOLID", scale=1.0, boundary_handles=None, **style) -> dict:
        sc = V.positive(scale, "scale")
        if boundary_handles:
            return self._hatch_existing(V.parse_handles(boundary_handles), pattern, sc, style)
        if points is None or points == "":
            raise ValueError("points(경계 꼭짓점) 또는 boundary_handles(이미 그린 닫힌 경계) 중 하나를 주세요")
        pts = V.json_points(points, "points", 3)
        flat = [c for p in pts for c in p[:2]]
        d = self._require_idle()
        with self._undo_group(d):
            ms = d.ModelSpace
            boundary = ms.AddLightWeightPolyline(self._varr(flat))
            boundary.Closed = True
            hatch = None
            try:
                hatch = ms.AddHatch(0, pattern, True)  # 0 = acHatchPatternTypePreDefined
                loop = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [unwrap(boundary)])
                hatch.AppendOuterLoop(loop)
                if pattern.upper() != "SOLID":
                    hatch.PatternScale = sc
                self._apply_style(d, hatch, **style)
                if style.get("layer"):
                    boundary.Layer = hatch.Layer
                hatch.Evaluate()
            except Exception as e:
                for obj in (hatch, boundary):
                    try:
                        if obj is not None:
                            obj.Delete()
                    except Exception:
                        pass
                raise RuntimeError("해치 생성 실패(만든 경계·해치 삭제함): %s" % e) from e
            return {"handle": hatch.Handle, "type": "HATCH", "boundary_handle": boundary.Handle,
                    "drawing": d.Name}

    def _hatch_existing(self, handles, pattern, sc, style) -> dict:
        """이미 그린 닫힌 경계(폴리선·원·타원·스플라인)로 해치. 첫 핸들이 바깥 경계, 나머지는 구멍."""
        d = self._require_idle()
        objs = [self._resolve(d, h) for h in handles]
        with self._undo_group(d):
            hatch = None
            try:
                hatch = d.ModelSpace.AddHatch(0, pattern, True)
                for i, o in enumerate(objs):
                    loop = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [unwrap(o)])
                    (hatch.AppendInnerLoop if i else hatch.AppendOuterLoop)(loop)
                if pattern.upper() != "SOLID":
                    hatch.PatternScale = sc
                self._apply_style(d, hatch, **style)
                hatch.Evaluate()
            except Exception as e:
                try:
                    if hatch is not None:
                        hatch.Delete()
                except Exception:
                    pass
                raise RuntimeError("해치 생성 실패(경계는 닫힌 폴리선·원·타원·스플라인이어야 함, 만든 해치 삭제함): %s"
                                   % e) from e
            return {"handle": hatch.Handle, "type": "HATCH", "boundary_handles": handles, "drawing": d.Name}

    _DIM_KINDS = {"aligned": None, "horizontal": 0.0, "vertical": 90.0, "rotated": None}

    def create_dimension(self, start, end, text_pos=None, text_height=0.0, kind="aligned", angle=0.0,
                         scale=0.0, **style) -> dict:
        s, e = V.point(start, "start"), V.point(end, "end")
        kind = (kind or "aligned").strip().lower()
        if kind not in self._DIM_KINDS:
            raise ValueError("kind는 aligned·horizontal·vertical·rotated 중 하나입니다: %r" % kind)
        rot = self._DIM_KINDS[kind] if kind in ("horizontal", "vertical") else V.num(angle, "angle")
        if text_pos is None:
            if kind == "aligned":
                length = math.hypot(e[0] - s[0], e[1] - s[1]) or 1.0
                nx, ny = -(e[1] - s[1]) / length, (e[0] - s[0]) / length
            else:
                # 치수선 방향의 왼쪽(수평이면 위, 수직이면 왼쪽)으로 띄운다
                a = math.radians(rot)
                length = abs((e[0] - s[0]) * math.cos(a) + (e[1] - s[1]) * math.sin(a)) or 1.0
                nx, ny = -math.sin(a), math.cos(a)
            off = max(length * 0.1, 1.0)
            text_pos = ((s[0] + e[0]) / 2 + nx * off, (s[1] + e[1]) / 2 + ny * off, 0.0)
        t = V.point(list(text_pos)[:3], "text_pos")
        th = V.num(text_height, "text_height")
        sf = V.num(scale, "scale")
        if sf < 0:
            raise ValueError("scale은 0 이상이어야 합니다(0=치수 스타일 그대로)")

        def make(ms):
            if kind == "aligned":
                return ms.AddDimAligned(self._vpt(*s), self._vpt(*e), self._vpt(*t))
            return ms.AddDimRotated(self._vpt(*s), self._vpt(*e), self._vpt(*t), math.radians(rot))

        def extra(ent):
            if sf > 0:
                ent.ScaleFactor = sf
            if th > 0:
                ent.TextHeight = th
        out = self._create("치수", make, style, extra)
        out["kind"] = kind
        return out

    def create_leader(self, points, text, text_height=2.5, arrow_size=0.0, text_style="", **style) -> dict:
        """지시선 + 문자(MLEADER). points 첫 점이 화살표 끝, 마지막 점에 문자가 붙는다."""
        if not isinstance(text, str) or text == "":
            raise ValueError("text가 비어 있습니다")
        pts = V.json_points(points, "points", 2)
        h = V.positive(text_height, "text_height")
        ar = V.num(arrow_size, "arrow_size")
        if ar < 0:
            raise ValueError("arrow_size는 0 이상이어야 합니다(0=문자 높이와 같게)")
        flat = [c for p in pts for c in (p[0], p[1], 0.0)]

        def make(ms):
            r = ms.AddMLeader(self._varr(flat), 0)
            return r[0] if isinstance(r, tuple) else r

        def extra(ent):
            ent.ContentType = 2  # acMTextContent
            if text_style:
                ent.TextStyleName = self._text_style_name(self.doc, text_style)
            ent.TextString = text
            ent.TextHeight = h
            ent.ArrowheadSize = ar or h
            ent.LandingGap = h * 0.3
            ent.DoglegLength = h
        out = self._create("지시선", make, style, extra)
        out["content"] = text
        return out

    # ------------------------------------------------------------ 블록

    def get_blocks(self) -> list:
        blocks = self.doc.Blocks
        out = []
        for i in range(blocks.Count):
            b = blocks.Item(i)
            name = b.Name
            if name.startswith("*") or bool(b.IsLayout) or bool(b.IsXRef):
                continue
            o = b.Origin
            out.append({"name": name, "count": b.Count, "origin": [o[0], o[1]]})
        return out

    def create_block(self, name: str, base_x=0.0, base_y=0.0) -> dict:
        if not name or not name.strip():
            raise ValueError("블록 이름이 비어 있습니다")
        d = self._require_idle()
        blocks = d.Blocks
        for i in range(blocks.Count):
            if blocks.Item(i).Name.casefold() == name.casefold():
                return {"name": blocks.Item(i).Name, "created": False, "drawing": d.Name}
        with self._undo_group(d):
            blocks.Add(self._vpt(V.num(base_x, "base_x"), V.num(base_y, "base_y")), name)
        return {"name": name, "created": True, "drawing": d.Name}

    def insert_block(self, name, x, y, x_scale=1.0, y_scale=1.0, z_scale=1.0, rotation=0.0, **style) -> dict:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("블록 이름이 비어 있습니다")
        p = V.point([x, y], "x,y")
        sc = [V.num(v, k) for k, v in (("x_scale", x_scale), ("y_scale", y_scale), ("z_scale", z_scale))]
        if 0 in sc:
            raise ValueError("블록 축척은 0이 될 수 없습니다: %r" % sc)
        rot = math.radians(V.num(rotation, "rotation"))
        out = self._create("블록 참조", lambda ms: ms.InsertBlock(self._vpt(*p), name, sc[0], sc[1], sc[2], rot),
                           style)
        out["block_name"] = name
        return out

    def get_block_attributes(self, handle: str) -> list:
        ref = self._resolve(self.doc, handle)
        if ref.ObjectName != "AcDbBlockReference":
            raise ValueError("블록 참조가 아닙니다: %s (%s)" % (handle, ref.ObjectName))
        if not ref.HasAttributes:
            return []
        return [{"tag": a.TagString, "value": a.TextString, "handle": a.Handle} for a in ref.GetAttributes()]

    def set_block_attribute(self, handle: str, tag: str, value: str) -> dict:
        d = self._require_idle()
        ref = self._resolve(d, handle)
        if ref.ObjectName != "AcDbBlockReference" or not ref.HasAttributes:
            raise ValueError("속성이 있는 블록 참조가 아닙니다: %s" % handle)
        tags = []
        for a in ref.GetAttributes():
            tags.append(a.TagString)
            if a.TagString.casefold() == tag.casefold():
                with self._undo_group(d):
                    a.TextString = value
                    a.Update()
                return {"handle": handle, "tag": a.TagString, "value": a.TextString, "drawing": d.Name}
        raise ValueError("속성 태그 '%s'가 없습니다. 있는 태그: %s" % (tag, tags))

    # ------------------------------------------------------------ 편집 (단건, COM)

    def _edit(self, handle, fn) -> dict:
        d = self._require_idle()
        ent = self._resolve(d, handle)
        with self._undo_group(d):
            res = fn(ent)
        out = {"handle": handle, "drawing": d.Name}
        if isinstance(res, dict):
            out.update(res)
        return out

    def modify_entity(self, handle, layer="", color=-1, linetype="", visible=None, rotation=None,
                      text="", height=None, true_color="", lineweight=-1) -> dict:
        d = self._require_idle()
        ent = self._resolve(d, handle)
        obj = ent.ObjectName
        texty = ("AcDbText", "AcDbMText", "AcDbAttributeDefinition")
        # 검사를 모두 먼저 한다 — 일부만 바꾸고 오류로 끝나지 않게.
        rgb = V.rgb(true_color) if true_color else None
        aci = V.aci(color) if (not rgb and color is not None and color >= 0) else None
        rot = None
        if rotation is not None:
            if obj not in texty + ("AcDbBlockReference",):
                raise ValueError("rotation은 문자·블록 참조에만 쓸 수 있습니다(%s). 일반 회전은 rotate_entity" % obj)
            rot = math.radians(V.num(rotation, "rotation"))
        if text and obj not in texty:
            raise ValueError("text는 문자 개체에만 쓸 수 있습니다(%s)" % obj)
        h = None
        if height is not None:
            if obj not in texty:
                raise ValueError("height는 문자 개체에만 쓸 수 있습니다(%s)" % obj)
            h = V.positive(height, "height")
        lw = None
        if lineweight is not None and lineweight != -1:
            lw = int(lineweight)
            if lw not in _LINEWEIGHTS + [_BYLAYER_LW, _BYBLOCK_LW, _DEFAULT_LW]:
                raise ValueError("lineweight는 %s 중 하나(1/100mm) 또는 -1·-2·-3이어야 합니다: %r"
                                 % (_LINEWEIGHTS, lineweight))
        lt = self._ensure_linetype(d, linetype) if linetype else None
        changed = []
        with self._undo_group(d):
            if layer:
                ent.Layer = self._ensure_layer(d, layer).Name
                changed.append("layer")
            if rgb:
                self._set_color(ent, true_color=true_color)
                changed.append("true_color")
            elif aci is not None:
                ent.Color = aci
                changed.append("color")
            if lt:
                ent.Linetype = lt
                changed.append("linetype")
            if lw is not None:
                ent.Lineweight = lw
                changed.append("lineweight")
            if visible is not None:
                ent.Visible = bool(visible)
                changed.append("visible")
            if rot is not None:
                ent.Rotation = rot
                changed.append("rotation")
            if text:
                ent.TextString = text
                changed.append("text")
            if h is not None:
                ent.Height = h
                changed.append("height")
            ent.Update()
        return {"handle": handle, "modified": changed, "drawing": d.Name}

    def delete_entity(self, handle) -> dict:
        out = self._edit(handle, lambda ent: ent.Delete())
        out["deleted"] = True
        return out

    def move_entity(self, handle, dx=0.0, dy=0.0, dz=0.0) -> dict:
        v = [V.num(dx, "dx"), V.num(dy, "dy"), V.num(dz, "dz")]
        out = self._edit(handle, lambda ent: ent.Move(self._vpt(0, 0, 0), self._vpt(*v)))
        out["moved"] = v
        return out

    def copy_entity(self, handle, dx=0.0, dy=0.0, dz=0.0) -> dict:
        v = [V.num(dx, "dx"), V.num(dy, "dy"), V.num(dz, "dz")]

        def fn(ent):
            c = ent.Copy()
            if any(v):
                c.Move(self._vpt(0, 0, 0), self._vpt(*v))
            return {"new_handle": c.Handle, "type": _OBJ_TO_DXF.get(c.ObjectName, c.ObjectName)}
        out = self._edit(handle, fn)
        out["original"] = out.pop("handle")
        out["handle"] = out["new_handle"]  # handle = 사본(다른 작도 도구와 같은 뜻)
        return out

    def rotate_entity(self, handle, base_x, base_y, angle) -> dict:
        b = V.point([base_x, base_y], "base")
        a = math.radians(V.num(angle, "angle"))
        out = self._edit(handle, lambda ent: ent.Rotate(self._vpt(*b), a))
        out["rotated"] = V.num(angle, "angle")
        return out

    def scale_entity(self, handle, base_x, base_y, factor) -> dict:
        b = V.point([base_x, base_y], "base")
        f = V.positive(factor, "factor")
        out = self._edit(handle, lambda ent: ent.ScaleEntity(self._vpt(*b), f))
        out["scaled"] = f
        return out

    def mirror_entity(self, handle, x1, y1, x2, y2) -> dict:
        p1, p2 = V.point([x1, y1], "p1"), V.point([x2, y2], "p2")
        if p1 == p2:
            raise ValueError("대칭축의 두 점이 같습니다")

        def fn(ent):
            m = ent.Mirror(self._vpt(*p1), self._vpt(*p2))
            return {"new_handle": m.Handle}
        return self._edit(handle, fn)

    def offset_entity(self, handle, distance) -> dict:
        dist = V.num(distance, "distance")
        if dist == 0:
            raise ValueError("distance가 0입니다")

        def fn(ent):
            res = ent.Offset(dist)
            items = res if isinstance(res, (list, tuple)) else ([res] if res is not None else [])
            return {"new_handles": [o.Handle for o in items]}
        return self._edit(handle, fn)

    def array_linear(self, handle, count, dx, dy, dz=0.0) -> dict:
        n = int(count)
        if not 2 <= n <= 10000:
            raise ValueError("count는 2~10000(원본 포함)이어야 합니다")
        v = [V.num(dx, "dx"), V.num(dy, "dy"), V.num(dz, "dz")]
        if not any(v):
            raise ValueError("변위가 0이라 사본이 제자리에 겹칩니다")

        def fn(ent):
            made = []
            try:
                for i in range(1, n):
                    c = ent.Copy()
                    made.append(c)
                    c.Move(self._vpt(0, 0, 0), self._vpt(v[0] * i, v[1] * i, v[2] * i))
            except Exception:
                self._delete_quietly(made)
                raise
            return {"new_handles": [c.Handle for c in made]}
        return self._edit(handle, fn)

    @staticmethod
    def _delete_quietly(objs):
        """도중에 실패한 배열의 사본을 지운다. 지우기 실패는 원래 오류를 가리지 않게 넘긴다."""
        for o in objs:
            try:
                o.Delete()
            except Exception:
                logger.warning("배열 사본 정리 실패")

    def array_polar(self, handle, count, center_x, center_y, total_angle=360.0) -> dict:
        n = int(count)
        if not 2 <= n <= 10000:
            raise ValueError("count는 2~10000(원본 포함)이어야 합니다")
        c0 = V.point([center_x, center_y], "center")
        total = V.num(total_angle, "total_angle")
        if total == 0:
            raise ValueError("total_angle이 0이라 사본이 제자리에 겹칩니다")
        step = math.radians(total / n if abs(total) >= 360 else total / (n - 1))

        def fn(ent):
            made = []
            try:
                for i in range(1, n):
                    c = ent.Copy()
                    made.append(c)
                    c.Rotate(self._vpt(*c0), step * i)
            except Exception:
                self._delete_quietly(made)
                raise
            return {"new_handles": [c.Handle for c in made]}
        return self._edit(handle, fn)

    # ------------------------------------------------------------ 일괄 편집 (LISP 1회 왕복)

    def _vla_rows(self, handles: List[str], op: str, disp=(0.0, 0.0, 0.0)) -> list:
        """핸들마다 같은 vla 연산을 LISP 한 번에 → [(OK|ERR|MISS, i, 값)]. 지워진 개체는 (entget)으로 거른다."""
        disp = tuple(V.num(v, n) for v, n in zip(disp, ("dx", "dy", "dz")))
        if not handles:
            return [], self.doc.Name  # 부르는 쪽(_batch)이 (행, 도면 이름)을 받는다
        lits = " ".join('"%s"' % V.lisp_str(h) for h in handles)
        # bcq:op1   개체 하나(_en)에 op를 건다. op는 _ob(vla 개체)·_p0·_p1을 쓰고, 사본을 만들면 _nw에 둔다.
        # bcq:undo-copy  op가 중간에 실패했을 때 만들어 둔 사본을 치우고 그 결과를 문구로.
        # 줄: DONE<탭>i<탭>값 | FAIL<탭>i<탭>오류 | GONE<탭>i (없는·지워진 핸들)
        body = (
            "(defun bcq:op1 () (setq _ob (vlax-ename->vla-object _en)) " + op + ")"
            "(defun bcq:undo-copy ()"
            " (cond ((null _nw) \"\")"
            "       ((vl-catch-all-error-p (vl-catch-all-apply (function vla-Delete) (list _nw))) \"; 사본 삭제 실패\")"
            "       (T \"; 사본 삭제함\")))"
            "(setq _p0 (vlax-3d-point 0.0 0.0 0.0) _p1 (vlax-3d-point %.9f %.9f %.9f) _i -1)" % disp +
            "(foreach _h (list " + lits + ")"
            " (setq _i (1+ _i) _nw nil _en (handent _h))"
            " (cond"
            "  ((not (and _en (entget _en))) (write-line (strcat \"GONE\" _d (itoa _i)) _fp))"
            "  ((vl-catch-all-error-p (setq _r (vl-catch-all-apply (function bcq:op1) nil)))"
            "   (write-line (strcat \"FAIL\" _d (itoa _i) _d (vl-catch-all-error-message _r) (bcq:undo-copy)) _fp))"
            "  (T (write-line (strcat \"DONE\" _d (itoa _i) _d (if (= (type _r) (quote STR)) _r \"\")) _fp))))"
        )
        # LISP 한 번(SendCommand 한 번)은 표시 없이도 UNDO 한 묶음이다(실측). COM 표시를 더 씌우면
        # 읽기만 한 LISP도 빈 묶음을 남겨 다음 undo가 헛돈다.
        d = self._require_idle()
        name = d.Name  # 작업 도중 사용자가 탭을 바꿔도 실제로 작업한 도면을 알린다
        lines = self.lisp(body, timeout_s=300.0, doc=d)
        kinds = {"DONE": "OK", "FAIL": "ERR", "GONE": "MISS"}
        rows = []
        for ln in lines:
            c = ln.split("\t", 2)
            if len(c) >= 2 and c[0] in kinds:
                rows.append((kinds[c[0]], int(c[1]), c[2] if len(c) > 2 else ""))
        if len(rows) != len(handles) or sorted(r[1] for r in rows) != list(range(len(handles))):
            # 몇 개는 처리됐을 수 있다 — 성공으로 돌려주지도, 다시 실행하게 두지도 않는다.
            raise RuntimeError("일괄 처리 결과가 불완전합니다(요청 %d개, 결과 %d줄). 일부가 이미 처리됐을 수 있으니 "
                               "다시 실행하기 전에 도면(%s)을 확인하세요." % (len(handles), len(rows), name))
        return rows, name

    def _batch(self, handles, op, disp=(0, 0, 0)):
        done, errors = [], []
        rows, name = self._vla_rows(handles, op, disp)
        for kind, i, val in rows:
            if kind == "OK":
                done.append((i, val))
            else:
                errors.append({"handle": handles[i], "error": "찾을 수 없음" if kind == "MISS" else val})
        return done, errors, name

    def delete_entities(self, handles) -> dict:
        done, errors, name = self._batch(handles, "(vla-Delete _ob)")
        out = {"deleted": len(done), "errors": errors, "drawing": name}
        if errors:
            out["hint"] = _HANDLE_HINT
        return out

    def move_entities(self, handles, dx=0.0, dy=0.0, dz=0.0) -> dict:
        done, errors, name = self._batch(handles, "(vla-Move _ob _p0 _p1)", (dx, dy, dz))
        out = {"moved": len(done), "displacement": [dx, dy, dz], "errors": errors, "drawing": name}
        if errors:
            out["hint"] = _HANDLE_HINT
        return out

    def copy_entities(self, handles, dx=0.0, dy=0.0, dz=0.0) -> dict:
        mv = " (vla-Move _nw _p0 _p1)" if any((dx, dy, dz)) else ""
        done, errors, name = self._batch(handles, "(setq _nw (vla-Copy _ob))" + mv + " (vla-get-Handle _nw)",
                                         (dx, dy, dz))
        return {"copied": len(done),
                "new_entities": [{"original": handles[i], "new_handle": nh} for i, nh in done],
                "errors": errors, "drawing": name}

    def draw_lines_atomic(self, base_handle: str, segments: list, timeout_s: float = 12.0) -> dict:
        """기준 개체와 같은 레이어에 LINE 여러 개를 한 번에. 색·선종류·선굵기는 ByLayer로 명시한다
        (안 주면 CECOLOR/CELTYPE을 받는다). 좌표·레이어 검증에 실패하면 이번 선만 지운다."""
        h = (base_handle or "").strip()
        if not h:
            raise ValueError("기준 객체 핸들이 비어 있습니다")
        if not isinstance(segments, list) or not 1 <= len(segments) <= 500:
            raise ValueError("segments는 1~500개 선분 배열이어야 합니다")
        clean = []
        for i, seg in enumerate(segments):
            if not isinstance(seg, (list, tuple)) or len(seg) != 4:
                raise ValueError("segments[%d]는 [x1,y1,x2,y2]여야 합니다" % i)
            v = [V.num(x, "segments[%d]" % i) for x in seg]
            if v[0] == v[2] and v[1] == v[3]:
                raise ValueError("segments[%d] 길이가 0입니다" % i)
            clean.append(v)
        segs = " ".join("(list %.9f %.9f %.9f %.9f)" % tuple(v) for v in clean)
        # bcq:seg  선 하나를 만들고 바로 다시 읽어 레이어·두 끝점(0.5mm 안)을 확인한다. 하나라도 어긋나면 _ok를 끄고
        #          뒤 선은 만들지 않는다. 만든 선은 _cr에 모아 두었다가 실패하면 이번에 만든 것만 지운다.
        # 줄: LINE<탭>핸들 … (모두 성공) | UNDONE<탭>이유<탭>지운 개수
        body = (
            "(defun bcq:seg (x1 y1 x2 y2 / before e ed)"
            " (if _ok (progn"
            "  (setq before (entlast))"
            "  (entmake (list (quote (0 . \"LINE\")) _spc (cons 8 _lay) (quote (62 . 256)) (quote (6 . \"ByLayer\"))"
            "                 (quote (370 . -1)) (list 10 x1 y1 0.0) (list 11 x2 y2 0.0)))"
            "  (setq e (entlast))"
            "  (cond ((or (null e) (equal e before)) (setq _ok nil _why \"선이 만들어지지 않음\"))"
            "        (T (setq _cr (cons e _cr) ed (entget e))"
            "           (if (not (and (= (cdr (assoc 8 ed)) _lay)"
            "                         (< (distance (cdr (assoc 10 ed)) (list x1 y1 0.0)) 0.0005)"
            "                         (< (distance (cdr (assoc 11 ed)) (list x2 y2 0.0)) 0.0005)))"
            "            (setq _ok nil _why \"좌표 또는 레이어 불일치\")))))))"
            "(setq _cr nil _ok T _why \"\" _base (handent \"" + V.lisp_str(h) + "\"))"
            "(cond"
            " ((not (and _base (entget _base))) (write-line (strcat \"UNDONE\" _d \"기준 핸들 없음\" _d \"0\") _fp))"
            # 기준 개체와 같은 공간(배치 탭이 켜져 있어도 모형 공간 개체 옆에 그린다)
            " (T (setq _lay (cdr (assoc 8 (entget _base))) _spc (cons 67 (if (assoc 67 (entget _base)) (cdr (assoc 67 (entget _base))) 0)))"
            "  (foreach _pt (list " + segs + ") (apply (function bcq:seg) _pt))"
            "  (if _ok"
            "   (foreach _e (reverse _cr) (write-line (strcat \"LINE\" _d (cdr (assoc 5 (entget _e)))) _fp))"
            "   (progn (setq _n 0)"
            "    (foreach _e _cr (if (entget _e) (progn (entdel _e) (setq _n (1+ _n)))))"
            "    (write-line (strcat \"UNDONE\" _d _why _d (itoa _n)) _fp)))))"
        )
        d = self._require_idle()
        t = max(1.0, min(float(timeout_s), 60.0))  # 바깥 제한시간(server)보다 짧게
        lines = self.lisp(body, timeout_s=t, doc=d)  # LISP 한 번 = UNDO 한 묶음(M24-C)
        if lines and lines[0].startswith("UNDONE\t"):
            p = lines[0].split("\t")
            raise RuntimeError("선분 작도 실패: %s (되돌린 선 %s개)" % (p[1], p[2] if len(p) > 2 else "?"))
        hs = [ln.split("\t", 1)[1] for ln in lines if ln.startswith("LINE\t")]
        if len(hs) != len(clean):
            raise RuntimeError("선분 검증 결과 불완전: 요청 %d, 확인 %d — 도면을 확인하세요" % (len(clean), len(hs)))
        return {"created": len(hs), "handles": hs, "verified": True, "drawing": d.Name}

    # ------------------------------------------------------------ undo / redo

    @staticmethod
    def _fingerprint(d) -> tuple:
        """모형 공간 개체 수와 마지막 개체 핸들. COM 읽기만 쓴다 — LISP(SendCommand)를 끼우면
        UNDO와 REDO 사이 사슬이 끊겨 REDO가 아무것도 안 한다(도구 전수 시험에서 확인)."""
        ms = d.ModelSpace
        n = ms.Count
        return n, (ms.Item(n - 1).Handle if n else "")

    def _undo_redo(self, cmd: str, count: int) -> dict:
        d = self._require_idle()
        uc = int(d.GetVariable("UNDOCTL"))
        if not uc & 1:
            raise RuntimeError("UNDOCTL=%d: UNDO가 꺼져 있어 보내지 않았습니다" % uc)
        if count > 1 and uc & 2:
            raise RuntimeError("UNDOCTL=%d: UNDO가 One 모드라 count>1을 보내지 않았습니다" % uc)
        n0, h0 = self._fingerprint(d)
        v0 = self._view(d)
        d.SendCommand(cmd)
        n1, h1 = self._fingerprint(d)
        v1 = self._view(d)
        out = {"requested": count, "before": {"entities": n0, "last_handle": h0},
               "after": {"entities": n1, "last_handle": h1}, "changed": (n0, h0) != (n1, h1),
               "drawing": d.Name}
        view_changed = v0 != v1
        if view_changed:
            out["view_changed"] = True
        if not out["changed"]:
            if view_changed:
                # LISP를 한 번 쓴 뒤의 줌은 UNDO 기록에 들어간다(도구 시험에서 확인) — 그것만 되돌렸을 수 있다.
                # 자동으로 한 번 더 되돌리지 않는다(무엇을 되돌릴지 모르는 채 보내지 않음).
                if cmd.startswith("_.UNDO"):
                    out["warning"] = ("화면(줌)만 바뀌었습니다 — 직전 줌을 되돌린 것으로 보입니다. 작도·편집을 "
                                      "되돌리려면 undo를 한 번 더 부르세요")
                else:
                    out["warning"] = "화면(줌)만 바뀌었습니다 — 되돌렸던 줌을 다시 적용한 것으로 보입니다"
            else:
                out["warning"] = ("개체 수·마지막 핸들이 그대로입니다 — 되돌릴 것이 없었거나 개체 밖의 변경"
                                  "(속성·레이어·위치 등)만 바뀌었을 수 있습니다")
        return out

    def undo(self, count: int = 1) -> dict:
        if type(count) is not int or not 1 <= count <= 32767:
            raise ValueError("count는 1~32767 정수여야 합니다: %r" % (count,))
        return self._undo_redo("_.UNDO %d " % count, count)

    def redo(self) -> dict:
        return self._undo_redo("_.REDO ", 1)

    # ------------------------------------------------------------ LISP·명령

    def run_lisp(self, code: str, timeout_s: float = 60.0) -> dict:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code가 비어 있습니다")
        V.check_parens(code)
        V.check_banned(code)
        t = max(1.0, min(float(timeout_s), 600.0))
        d = self._require_idle()
        lines = self.lisp(code, timeout_s=t, doc=d)  # LISP 한 번 = UNDO 한 묶음, 읽기만 하면 기록 없음(M24-C)
        return {"lines": lines, "count": len(lines), "drawing": d.Name}

    def send_command(self, command: str) -> dict:
        c = (command or "").strip()
        if not (c.startswith("(") and c.endswith(")")):
            raise ValueError("send_command는 AutoLISP 식만 받습니다(예: '(entmake ...)'). 글자 명령은 완료 확인이 "
                             "안 되고 (command)는 OSNAP에 끌리므로 전용 도구나 run_lisp를 쓰세요.")
        res = self.run_lisp(c, 30.0)
        return {"sent": c, "completed": True, "lines": res["lines"], "drawing": res["drawing"]}

    # ------------------------------------------------------------ 뷰·캡처

    def _view(self, d) -> dict:
        c = d.GetVariable("VIEWCTR")
        return {"view_center": [c[0], c[1]], "view_height": d.GetVariable("VIEWSIZE")}

    def zoom_extents(self) -> dict:
        d = self.doc
        self.app.ZoomExtents()
        out = {"zoom": "extents"}
        out.update(self._view(d))
        return out

    def zoom_window(self, x1, y1, x2, y2) -> dict:
        x1, y1, x2, y2 = (V.num(v, n) for v, n in ((x1, "x1"), (y1, "y1"), (x2, "x2"), (y2, "y2")))
        if x1 == x2 or y1 == y2:
            raise ValueError("줌 창의 가로·세로가 0입니다")
        d = self.doc
        self.app.ZoomWindow(self._vpt(min(x1, x2), min(y1, y2)), self._vpt(max(x1, x2), max(y1, y2)))
        out = {"zoom": "window", "method": "com"}
        out.update(self._view(d))
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        tol = max(abs(x2 - x1), abs(y2 - y1)) * 1e-6 + 1e-6
        out["verified"] = abs(out["view_center"][0] - cx) <= tol and abs(out["view_center"][1] - cy) <= tol
        return out

    def regen(self) -> dict:
        self.doc.Regen(0)  # acActiveViewport
        return {"regen": True}

    def capture_view(self, output_path: str = "", crop: bool = True) -> dict:
        """PrintWindow로 AutoCAD 창을 찍고(포커스 안 뺏음) 도면 영역(MDIClient)만 잘라 PNG로 저장.
        캡처 전에 Regen하지 않는다(Regen이 UNDO 기록을 빈 동작으로 만든다)."""
        d = self.doc
        if output_path:
            if os.path.splitext(output_path)[1].lower() != ".png":
                raise ValueError("output_path는 .png 파일이어야 합니다: %s" % output_path)
            output_path = os.path.abspath(output_path)
        else:
            output_path = os.path.join(tempfile.gettempdir(), "cadmcp_capture_%d_%d.png"
                                       % (os.getpid(), int(time.time() * 1000)))
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        hwnd = self.hwnd
        user32 = ctypes.windll.user32
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        try:
            if user32.IsIconic(wt.HWND(hwnd)):
                raise RuntimeError("AutoCAD 창이 최소화되어 있어 찍을 수 없습니다")
            img = grab_window(hwnd)
            if img is None:
                raise RuntimeError("PrintWindow 캡처가 비었습니다(창이 그려지지 않음)")
            win = wt.RECT()
            user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(win))
            box = None
            if crop:
                r = _child_rect(hwnd, "MDIClient")
                if r:
                    box = (r[0] - win.left, r[1] - win.top, r[2] - win.left, r[3] - win.top)
                    img = img.crop(box)
                    if img.convert("L").getextrema()[1] == 0:  # 창 테두리는 그려졌는데 도면 영역만 검정
                        raise RuntimeError("도면 영역 캡처가 비었습니다(전부 검정) — AutoCAD 화면이 다시 그려진 뒤 다시 찍으세요")
        finally:
            if old:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
        fd, staging = tempfile.mkstemp(dir=os.path.dirname(output_path), prefix=".cadmcp_cap_", suffix=".part")
        os.close(fd)
        try:
            img.save(staging, format="PNG")
            os.replace(staging, output_path)
        finally:
            if os.path.exists(staging):
                os.remove(staging)
        return {"path": output_path, "captured": True, "bytes": os.path.getsize(output_path),
                "width": img.width, "height": img.height, "cropped": bool(box), "drawing": d.Name}

    # ------------------------------------------------------------ 정밀 기하·XREF·배치 조회 (읽기 전용)

    def get_geometry(self, handles: List[str], vertex_start: int = 0, max_vertices: int = 2000) -> dict:
        vertex_start, max_vertices = int(vertex_start), int(max_vertices)
        if vertex_start < 0 or not 1 <= max_vertices <= geom_query.MAX_VERTICES:
            raise ValueError("vertex_start는 0 이상, max_vertices는 1~%d이어야 합니다" % geom_query.MAX_VERTICES)
        if not handles:
            return {"count": 0, "returned": 0, "truncated": False, "entities": []}
        lines = self.lisp(geom_query.geometry_body(handles, vertex_start, max_vertices), timeout_s=120.0)
        rows = [geom_query.parse_geom_line(ln) for ln in lines if ln.strip()]
        page = fit_page(rows, len(rows), 0, "entities")
        page["requested"] = len(handles)
        if page.pop("next_offset", None) is not None:
            page["next_index"] = page["entities"][-1]["index"] + 1
        page["missing"] = len(handles) - len(rows) if not page["truncated"] else None
        page["drawing"] = self.doc.Name
        return page

    def get_xrefs(self, max_refs: int = 50) -> dict:
        max_refs = int(max_refs)
        if max_refs < 0:
            raise ValueError("max_refs는 0 이상이어야 합니다")
        out = geom_query.parse_xrefs(self.lisp(geom_query._GEOM_DEFUN + geom_query.XREF_BODY), max_refs)
        out["drawing"] = self.doc.Name
        return out

    def find_text_overlaps(self, layer: str = "", window=None, min_ratio: float = 0.0, include_hidden: bool = False,
                           limit: int = 200, offset: int = 0) -> dict:
        limit, offset, min_ratio = int(limit), int(offset), float(min_ratio)
        if limit < 1 or offset < 0 or not 0.0 <= min_ratio <= 1.0:
            raise ValueError("limit은 1 이상, offset은 0 이상, min_ratio는 0~1이어야 합니다")
        if window is not None:
            window = [float(v) for v in window]
            if len(window) != 4:
                raise ValueError("window는 [x1, y1, x2, y2]")
            window = [min(window[0], window[2]), min(window[1], window[3]), max(window[0], window[2]),
                      max(window[1], window[3])]
        boxes = geom_query.parse_text_boxes(self.lisp(geom_query.text_boxes_body(layer, include_hidden), timeout_s=120))
        n, pairs = geom_query.find_overlaps(boxes, window, min_ratio)
        out = {"drawing": self.doc.Name, "checked": n}
        out.update(fit_page(pairs[offset:offset + limit], len(pairs), offset, "pairs"))
        return out

    def get_layouts(self, include_viewports: bool = True, max_frozen: int = 50, limit: int = 200,
                    offset: int = 0) -> dict:
        limit, offset, max_frozen = int(limit), int(offset), int(max_frozen)
        if limit < 1 or offset < 0 or max_frozen < 0:
            raise ValueError("limit은 1 이상, offset·max_frozen은 0 이상이어야 합니다")
        d = self.doc
        out = {"drawing": d.Name, "active_layout": d.ActiveLayout.Name, "layouts": geom_query.layout_info(d)}
        if include_viewports:
            vps = geom_query.parse_viewports(self.lisp(geom_query._GEOM_DEFUN + geom_query.VIEWPORT_BODY),
                                             max_frozen)
            order = {r["name"]: r["tab_order"] for r in out["layouts"]}
            vps.sort(key=lambda v: (order.get(v["layout"], 1 << 30), v["layout"]))
            out.update(fit_page(vps[offset:offset + limit], len(vps), offset, "viewports"))
        return out
