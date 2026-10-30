"""스킬 창이 AutoCAD와 이야기하는 통로. MCP 본체(src)의 재시도 감싸개와 LISP 실행기를 그대로 쓴다.

- 창 프로세스는 MCP와 다른 프로세스다. COM 연결도 따로 맺는다.
- 쓰기·LISP 전에는 사람이 명령 중인지 확인한다(MCP와 같은 원칙).
- 객체 고르기(getpoint·entsel)는 LISP로 하고, 사람이 고를 때까지 기다린다(제한시간 넘으면 ESC).
"""

import pythoncom
import win32com.client
import win32com.client.dynamic

from . import paths  # noqa: F401 — src를 sys.path에 올린다
from cad_controller import ComProxy  # noqa: E402
import lisp_runner  # noqa: E402

PICK_TIMEOUT = 600.0
# 연결이 죽은 경우(AutoCAD를 다시 켰을 때 등)의 HRESULT — src/cad_controller와 같은 목록
_DEAD = (-2147417848, -2147418105, -2147418094, -2147023174, -2147023170, -2147221021, -2147220995)


class CadNotReady(RuntimeError):
    pass


class Acad:
    def __init__(self):
        self.app = None
        self.hwnd = 0

    def connect(self):
        if self.app is not None:
            return self.app
        pythoncom.CoInitialize()
        try:
            raw = win32com.client.GetActiveObject("AutoCAD.Application")
        except Exception as e:
            raise CadNotReady("실행 중인 AutoCAD를 찾지 못했습니다. AutoCAD를 먼저 켜 주세요. (%s)" % e)
        self.app = ComProxy(win32com.client.dynamic.Dispatch(raw._oleobj_))
        self.hwnd = int(self.app.HWND)
        return self.app

    @property
    def doc(self):
        """활성 도면. AutoCAD를 다시 켜서 옛 연결이 죽었으면 한 번 다시 붙는다."""
        for attempt in (0, 1):
            try:
                return self.connect().ActiveDocument
            except CadNotReady:
                raise
            except Exception as e:
                if attempt == 0 and getattr(e, "hresult", None) in _DEAD:
                    self.app, self.hwnd = None, 0
                    continue
                raise CadNotReady("활성 도면이 없습니다. (%s)" % e)

    def undo_group(self):
        """여러 번 나눠 실행해도 UNDO 한 번에 되돌리게 묶는다(DTIN 배치 —)."""
        acad = self

        class _G:
            def __enter__(self):
                self.d = acad.require_idle()
                self.d.StartUndoMark()
                return self.d

            def __exit__(self, *exc):
                try:
                    self.d.EndUndoMark()
                except Exception:
                    pass
                return False
        return _G()

    def require_idle(self):
        doc = self.doc
        if int(doc.GetVariable("CMDACTIVE")):
            raise CadNotReady("AutoCAD가 명령 중입니다. 명령을 끝낸 뒤 다시 누르세요.")
        return doc

    def lisp(self, body: str, timeout_s: float = 60.0):
        """body를 실행하고 결과 줄을 돌려준다. body는 (write-line ... _fp)로 결과를 쓴다."""
        doc = self.require_idle()
        return lisp_runner.run(doc, self.hwnd, ensure_lib() + body, timeout_s)

    def lisp_undo(self, body: str, timeout_s: float = 60.0):
        """쓰기 작업: UNDO 한 번에 되돌릴 묶음으로 실행한다(오류 때 롤백은 LISP 실행기가 한다)."""
        doc = self.require_idle()
        doc.StartUndoMark()
        try:
            rows = []
            from .lisplib import split_forms
            for part in split_forms(body):
                rows += lisp_runner.run(doc, self.hwnd, ensure_lib() + part, timeout_s)
            return rows
        finally:
            try:
                doc.EndUndoMark()
            except Exception:
                pass

    def activate(self):
        """객체를 고르게 하기 전에 AutoCAD 창을 앞으로."""
        try:
            import ctypes
            import ctypes.wintypes
            ctypes.windll.user32.SetForegroundWindow(ctypes.wintypes.HWND(self.hwnd or self.connect().HWND))
        except Exception:
            pass


def ensure_lib() -> str:
    """스킬 LISP 라이브러리가 이 도면에 아직 없으면 정의하는 식(파일 eval, (load) 없음)."""
    from . import lisplib
    return lisplib.ensure_expr()
