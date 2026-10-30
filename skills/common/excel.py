# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""켜져 있는 엑셀과 주고받기(COM). 엑셀을 새로 켜지 않는다 — 사람이 보고 있는 엑셀에 쓴다."""

import re

import pythoncom
import win32com.client


class ExcelNotReady(RuntimeError):
    pass


def app():
    pythoncom.CoInitialize()
    try:
        return win32com.client.GetActiveObject("Excel.Application")
    except Exception:
        raise ExcelNotReady("켜져 있는 엑셀을 찾지 못했습니다. 엑셀을 켜고 통합문서를 열어 두세요.")


def sheets():
    """열린 모든 통합문서의 시트 목록 [(통합문서, 시트)]"""
    xl = app()
    out = []
    for i in range(1, xl.Workbooks.Count + 1):
        wb = xl.Workbooks(i)
        for j in range(1, wb.Worksheets.Count + 1):
            out.append((wb.Name, wb.Worksheets(j).Name))
    return out


def activate(book: str, sheet: str):
    xl = app()
    ws = xl.Workbooks(book).Worksheets(sheet)
    ws.Activate()
    return ws


BUSY_HINT = "엑셀이 응답하지 않습니다. 셀을 편집 중이면 엔터나 ESC로 끝내고, 시트 보호가 걸려 있으면 풀고 다시 하세요."


def _busy(e):
    """셀 편집 중·시트 보호 같은 COM 오류를 안내 문구로."""
    return ExcelNotReady("%s (%s)" % (BUSY_HINT, e))


def active_cell():
    """(시트, 행, 열) — 지금 선택된 셀(범위면 왼쪽 위)."""
    xl = app()
    try:
        if xl.ActiveSheet is None:
            raise ExcelNotReady("엑셀에 열린 시트가 없습니다.")
        sel = xl.Selection
        try:
            c = sel.Cells(1, 1)
        except Exception:
            c = xl.ActiveCell
        return xl.ActiveSheet, int(c.Row), int(c.Column)
    except ExcelNotReady:
        raise
    except Exception as e:
        raise _busy(e)


def selection_values():
    """선택 범위 값(2차원 목록). 빈 행은 뺀다."""
    xl = app()
    try:
        v = xl.Selection.Value
    except Exception:
        raise ExcelNotReady("엑셀에서 범위를 먼저 선택하세요(셀 편집 중이면 먼저 끝내세요).")
    if not isinstance(v, tuple):
        v = ((v,),)
    rows = [list(r) for r in v]
    return [r for r in rows if any(x not in (None, "") for x in r)]


def write_rows(ws, row: int, col: int, rows, autofit=True):
    """rows(2차원)를 (row, col)부터 한 번에 쓴다. 행 길이가 달라도 된다."""
    if not rows:
        return
    width = max(len(r) for r in rows)
    data = [list(r) + [""] * (width - len(r)) for r in rows]
    try:
        rng = ws.Range(ws.Cells(row, col), ws.Cells(row + len(data) - 1, col + width - 1))
        rng.Value = data
        _number_formats(ws, row, col, data)
    except Exception as e:
        raise _busy(e)
    if autofit:
        try:
            rng.EntireColumn.AutoFit()
        except Exception:
            pass


_NUM = re.compile(r"^-?\d+(\.(\d+))?$")


def _number_formats(ws, row, col, data):
    """'100.0000'처럼 소수 자리를 맞춰 보낸 숫자 글자는 엑셀이 숫자로 바꾸며 끝 0을 지운다(100).
    보낸 자리 수 그대로 보이도록 칸 표시 형식을 0.0000처럼 맞춘다. 열마다 같은 형식이 이어지는 칸을 한 번에 칠한다."""
    for j in range(len(data[0])):
        start, cur = 0, None
        for i in range(len(data) + 1):
            f = None
            if i < len(data):
                m = _NUM.match(str(data[i][j])) if isinstance(data[i][j], str) else None
                if m:
                    f = "0." + "0" * len(m.group(2)) if m.group(2) else "0"
            if i == len(data) or f != cur:
                if cur:
                    ws.Range(ws.Cells(row + start, col + j), ws.Cells(row + i - 1, col + j)).NumberFormat = cur
                start, cur = i, f


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None
