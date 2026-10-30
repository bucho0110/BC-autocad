# -*- coding: utf-8 -*-
# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""
CAD Multi Plotter (다중 플롯 유틸리티) - BC.0.3.0 (MCP 패키지 버전과 같게)
=========================================================
오토캐드(AutoCAD) 및 호환 CAD에서 모형(Model) 공간의 다중 도곽(블록·사각 폴리라인·수동 영역)을
자동 인식·정렬하여 일괄 PDF 변환 또는 프린터로 다중 출력하는 독립 GUI 도구입니다.
"""

import ctypes
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BC.CAD_Multi_Plotter.0.3.0")

import os
import sys
import json
import time
import math
import base64
import logging
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

import win32com.client
import pythoncom

# ─── 경로 설정 (MCP 패키지 안의 스킬: 어느 PC에 복사해도 돌도록 위치는 skills.common.paths에서) ───
sys.dont_write_bytecode = True
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from skills.common import paths as _paths  # noqa: E402
from skills.common.icon_b64 import ICON_B64  # noqa: E402
import lisp_runner  # noqa: E402  (src: 파일 eval 실행기 — (load) 없음, 멈추면 ESC 복구)
from validators import lisp_str as _ls  # noqa: E402  (LISP 문자열 이스케이프: 인치 " · 네트워크 프린터 \\)

# 로컬 작업 임시 폴더 (%LOCALAPPDATA%/bc-autocad/work/multi_plot — 동기화 폴더 오염 방지)
LOCAL_WORK_DIR = os.path.join(_paths.WORK, "multi_plot")
os.makedirs(LOCAL_WORK_DIR, exist_ok=True)

# ─── 로깅 설정 ───
LOG_FILE = os.path.join(_paths.LOGS, "multi_plot.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

CONFIG_FILE = os.path.join(_paths.SETTINGS, "MPL.json")

# ─── BC_TOOL 표준 내재화 아이콘: skills/common/icon_b64.py ───


def get_resource(b64_string: str, ext: str) -> str:
    fd, path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(base64.b64decode(b64_string))
    return path


# ─── 표준 규격 용지 정의 (기본값: A4) ───
PAPER_PRESETS = [
    ("A4 (210 x 297 mm)", 210.0, 297.0, ["ISO_full_bleed_A4_(210.00_x_297.00_MM)", "ISO_A4_(210.00_x_297.00_MM)", "A4"]),
    ("A3 (297 x 420 mm)", 297.0, 420.0, ["ISO_full_bleed_A3_(297.00_x_420.00_MM)", "ISO_A3_(297.00_x_420.00_MM)", "A3"]),
    ("B4 (250 x 353 mm)", 250.0, 353.0, ["ISO_B4_(250.00_x_353.00_MM)", "B4", "JIS B4"]),
    ("B3 (353 x 500 mm)", 353.0, 500.0, ["ISO_B3_(353.00_x_500.00_MM)", "B3", "JIS B3"]),
    ("A2 (420 x 594 mm)", 420.0, 594.0, ["ISO_full_bleed_A2_(420.00_x_594.00_MM)", "ISO_A2_(420.00_x_594.00_MM)", "A2"]),
    ("A1 (594 x 841 mm)", 594.0, 841.0, ["ISO_full_bleed_A1_(594.00_x_841.00_MM)", "ISO_A1_(594.00_x_841.00_MM)", "A1"]),
    ("A0 (841 x 1189 mm)", 841.0, 1189.0, ["ISO_full_bleed_A0_(841.00_x_1189.00_MM)", "ISO_A0_(841.00_x_1189.00_MM)", "A0"]),
]

# ─── 인쇄 순서 4종 정의 (사용자 첨부 이미지 기준) ───
SORT_ORDERS = [
    ("Z_TOP_DOWN", "⤡ [Z] 위 -> 아래 정렬 우선  |  좌 -> 우 방향으로 출력"),
    ("N_BOTTOM_UP", "⇅ [N↑] 좌 -> 우 정렬 우선  |  아래 -> 위 방향으로 출력"),
    ("S_BOTTOM_UP", "⤢ [역Z] 아래 -> 위 정렬 우선  |  좌 -> 우 방향으로 출력"),
    ("N_TOP_DOWN", "⇅ [N↓] 좌 -> 우 정렬 우선  |  위 -> 아래 방향으로 출력"),
]


def scan_autocad_plot_resources():
    """PC 내 설치된 AutoCAD Plotters(.pc3) 및 Plot Styles(.ctb) 목록을 자동 스캔합니다."""
    pc3_list = []
    ctb_list = []
    appdata = os.environ.get("APPDATA", "")
    autodesk_dir = os.path.join(appdata, "Autodesk")

    if os.path.isdir(autodesk_dir):
        for root, _dirs, files in os.walk(autodesk_dir):
            for fname in files:
                lower = fname.lower()
                if lower.endswith(".pc3") and fname not in pc3_list:
                    pc3_list.append(fname)
                elif lower.endswith(".ctb") and fname not in ctb_list:
                    ctb_list.append(fname)

    # 기본 우선순위 정렬
    preferred_pc3 = [
        "DWG To PDF.pc3",
        "AutoCAD PDF (General Documentation).pc3",
        "AutoCAD PDF (High Quality Print).pc3",
        "Default Windows System Printer.pc3",
    ]
    sorted_pc3 = [p for p in preferred_pc3 if p in pc3_list] + sorted(
        [p for p in pc3_list if p not in preferred_pc3]
    )
    if not sorted_pc3:
        sorted_pc3 = preferred_pc3

    preferred_ctb = ["monochrome.ctb", "acad.ctb", "Grayscale.ctb", "없음 (None)"]
    sorted_ctb = [c for c in preferred_ctb if c in ctb_list or c == "없음 (None)"] + sorted(
        [c for c in ctb_list if c not in preferred_ctb]
    )
    return sorted_pc3, sorted_ctb


def sort_frames(frames: list, order_code: str, cluster_ratio: float = 0.25) -> list:
    """
    도곽 리스트를 지정된 4가지 인쇄순서(Z, N↑, 역Z, N↓)로 정렬합니다.
    미세한 좌표 오차로 순서가 뒤집히지 않도록 행(Row)/열(Col) 클러스터링 허용오차를 적용합니다.
    """
    if not frames:
        return []

    avg_w = sum(max(1.0, f["max_x"] - f["min_x"]) for f in frames) / len(frames)
    avg_h = sum(max(1.0, f["max_y"] - f["min_y"]) for f in frames) / len(frames)
    tol_x = avg_w * cluster_ratio
    tol_y = avg_h * cluster_ratio

    items = [dict(f) for f in frames]

    if order_code in ("Z_TOP_DOWN", "S_BOTTOM_UP"):
        # 행(Row) 우선 정렬: Y 기준 클러스터링 후 각 행 안에서 X 오름차순(좌 -> 우)
        reverse_y = order_code == "Z_TOP_DOWN"  # 위->아래면 Y 내림차순
        items.sort(key=lambda r: r["min_y"], reverse=reverse_y)

        rows = []
        for item in items:
            placed = False
            for row in rows:
                ref_y = row[0]["min_y"]
                if abs(item["min_y"] - ref_y) <= tol_y:
                    row.append(item)
                    placed = True
                    break
            if not placed:
                rows.append([item])

        result = []
        for row in rows:
            row.sort(key=lambda r: r["min_x"])  # 좌 -> 우
            result.extend(row)
        return result

    else:
        # 열(Column) 우선 정렬: X 오름차순(좌 -> 우) 클러스터링 후 각 열 안에서 Y 정렬
        reverse_y = order_code == "N_TOP_DOWN"  # 위->아래면 Y 내림차순, 아래->위면 Y 오름차순
        items.sort(key=lambda r: r["min_x"])

        cols = []
        for item in items:
            placed = False
            for col in cols:
                ref_x = col[0]["min_x"]
                if abs(item["min_x"] - ref_x) <= tol_x:
                    col.append(item)
                    placed = True
                    break
            if not placed:
                cols.append([item])

        result = []
        for col in cols:
            col.sort(key=lambda r: r["min_y"], reverse=reverse_y)
            result.extend(col)
        return result


class AutoCADPlotBridge:
    """
    AutoCAD(우선) 및 호환 CAD와 COM + AutoLISP 하이브리드로 통신하여
    도곽 탐색, 샘플 객체 선택, 다중 플롯을 안정적으로 수행하는 브리지 클래스.
    """

    def __init__(self, autocad_only: bool = False):
        self.app = None
        self.doc = None
        self.engine_name = None
        # MCP에서 부를 때는 AutoCAD에만 붙는다 — AutoCAD가 꺼져 있을 때 켜져 있는 다른 CAD에 플롯을 보내지 않게
        self.autocad_only = autocad_only

    def connect(self, prefer_autocad: bool = True):
        """실행 중인 AutoCAD(또는 호환 CAD)에 연결합니다."""
        pythoncom.CoInitialize()
        prog_ids = [
            ("AutoCAD", "AutoCAD.Application"),
            ("AutoCAD 2023", "AutoCAD.Application.24.2"),
            ("IntelliCAD", "Icad.Application"),
            ("BricsCAD", "BricscadApp.App"),
            ("GstarCAD", "GstarCAD.Application"),
            ("ZWCAD", "ZWCAD.Application"),
        ]
        if self.autocad_only:
            prog_ids = [p for p in prog_ids if p[1].startswith("AutoCAD.")]
        for name, pid in prog_ids:
            try:
                app = win32com.client.GetActiveObject(pid)
                doc = app.ActiveDocument
                self.app = app
                self.doc = doc
                self.engine_name = name
                return True, f"{name} 연결됨 - [{doc.Name}]"
            except Exception:
                continue

        return False, "실행 중인 AutoCAD 도면을 찾을 수 없습니다. 먼저 AutoCAD를 켜고 도면을 열어주세요."

    def _save_plot_vars(self):
        out = {}
        for v in ("FILEDIA", "BACKGROUNDPLOT"):
            try:
                out[v] = self.doc.GetVariable(v)
            except Exception:
                pass
        return out

    def _restore_plot_vars(self, saved):
        for v, val in saved.items():
            try:
                if self.doc.GetVariable(v) != val:
                    self.doc.SetVariable(v, val)
            except Exception as e:
                logging.warning(f"{v} 복구 실패: {e}")

    def run_lisp_and_wait(self, lisp_code: str, result_path: str, timeout: float = 60.0) -> bool:
        """
        LISP를 파일 eval로 실행(SendCommand 동기)하고 LISP가 쓴 결과 파일이 있는지 확인합니다.
        Variant 배열 마샬링 오류 없이 네이티브 속도로 동작합니다.
        """
        if os.path.exists(result_path):
            try:
                os.remove(result_path)
            except OSError:
                pass

        # MCP와 같은 파일 eval 실행기로 보낸다((load) 없음 → 신뢰 경로 보안창과 무관, 입력 대기가
        # 제한시간을 넘기면 AutoCAD 입력 포커스 창에 ESC를 보내 푼다). 결과 파일은 LISP 코드가 직접 쓴다.
        try:
            hwnd = int(self.app.HWND)
        except Exception:
            hwnd = lisp_runner.find_acad_hwnd()
        try:
            lisp_runner.run(self.doc, hwnd, lisp_code, timeout_s=timeout)
        except Exception as e:
            logging.error(f"LISP 실행 실패: {e}")
            return False
        return os.path.exists(result_path) and os.path.getsize(result_path) > 0

    def pick_sample_frame_in_cad(self):
        """
        사용자가 캐드 화면에서 샘플 도곽(블록 또는 닫힌 폴리라인) 1개를 클릭하면
        해당 도곽의 종류(INSERT/LWPOLYLINE), 블록명, 레이어명, 크기를 반환합니다.
        """
        ok, msg = self.connect(prefer_autocad=True)
        if not ok:
            return None, msg

        try:
            self.app.Visible = True
            self.doc.Activate()
        except Exception:
            pass

        res_file = os.path.join(LOCAL_WORK_DIR, "sample_pick.txt").replace("\\", "/")
        lisp_code = f""";; Sample Frame Picker
(vl-load-com)
(defun mplot_pick_sample ( / esel ent edata etype bname lay obj minpt maxpt p1 p2 fp)
  (princ "\\n=======================================================")
  (princ "\\n[다중플롯] 기준 도곽(블록 또는 사각 폴리라인)을 클릭하세요: ")
  (setq esel (entsel))
  (setq fp (open "{res_file}" "w" "utf8"))
  (if esel
    (progn
      (setq ent (car esel))
      (setq edata (entget ent))
      (setq etype (cdr (assoc 0 edata)))
      (setq lay (cdr (assoc 8 edata)))
      (setq obj (vlax-ename->vla-object ent))
      (setq bname "")
      (if (= etype "INSERT")
        (if (vlax-property-available-p obj 'EffectiveName)
          (setq bname (vla-get-EffectiveName obj))
          (setq bname (cdr (assoc 2 edata)))
        )
      )
      (vla-GetBoundingBox obj 'minpt 'maxpt)
      (setq p1 (vlax-safearray->list minpt))
      (setq p2 (vlax-safearray->list maxpt))
      (write-line (strcat "OK\\t" etype "\\t" bname "\\t" lay "\\t"
                          (rtos (car p1) 2 4) "\\t" (rtos (cadr p1) 2 4) "\\t"
                          (rtos (car p2) 2 4) "\\t" (rtos (cadr p2) 2 4)) fp)
    )
    (write-line "CANCEL" fp)
  )
  (close fp)
  (princ)
)
(mplot_pick_sample)
"""
        if not self.run_lisp_and_wait(lisp_code, res_file, timeout=120.0):
            return None, "캐드에서 객체 선택 시간이 초과되었거나 취소되었습니다."

        with open(res_file, "r", encoding="utf-8-sig", errors="replace") as f:
            line = f.read().strip()

        if not line.startswith("OK\t"):
            return None, "도곽 선택이 취소되었습니다."

        parts = line.split("\t")
        info = {
            "etype": parts[1],
            "block_name": parts[2],
            "layer": parts[3],
            "min_x": float(parts[4]),
            "min_y": float(parts[5]),
            "max_x": float(parts[6]),
            "max_y": float(parts[7]),
        }
        info["width"] = abs(info["max_x"] - info["min_x"])
        info["height"] = abs(info["max_y"] - info["min_y"])
        return info, "샘플 도곽을 인식했습니다."

    def pick_manual_window_in_cad(self):
        """LISP getpoint·getcorner로 수동 인쇄 영역 두 점을 입력받습니다."""
        ok, msg = self.connect(prefer_autocad=True)
        if not ok:
            return None, msg

        try:
            self.app.Visible = True
            self.doc.Activate()
        except Exception:
            pass

        res_file = os.path.join(LOCAL_WORK_DIR, "window_pick.txt").replace("\\", "/")
        lisp_code = f""";; Manual Window Picker
(defun mplot_pick_win ( / p1 p2 fp)
  (princ "\\n[다중플롯] 출력 영역 첫 번째 구석점 클릭: ")
  (setq p1 (getpoint))
  (setq fp (open "{res_file}" "w" "utf8"))
  (if p1
    (progn
      (princ "\\n[다중플롯] 반대편 구석점 클릭: ")
      (setq p2 (getcorner p1))
      (if p2
        (write-line (strcat "OK\\t"
                            (rtos (min (car p1) (car p2)) 2 4) "\\t"
                            (rtos (min (cadr p1) (cadr p2)) 2 4) "\\t"
                            (rtos (max (car p1) (car p2)) 2 4) "\\t"
                            (rtos (max (cadr p1) (cadr p2)) 2 4)) fp)
        (write-line "CANCEL" fp)
      )
    )
    (write-line "CANCEL" fp)
  )
  (close fp)
  (princ)
)
(mplot_pick_win)
"""
        if not self.run_lisp_and_wait(lisp_code, res_file, timeout=120.0):
            return None, "영역 지정이 취소되었습니다."

        with open(res_file, "r", encoding="utf-8-sig", errors="replace") as f:
            line = f.read().strip()

        if not line.startswith("OK\t"):
            return None, "영역 지정이 취소되었습니다."

        parts = line.split("\t")
        frame = {
            "dwg_name": self.doc.Name,
            "dwg_path": self.doc.FullName,
            "kind": "수동영역",
            "label": "Window",
            "min_x": float(parts[1]),
            "min_y": float(parts[2]),
            "max_x": float(parts[3]),
            "max_y": float(parts[4]),
        }
        return frame, "수동 영역이 추가되었습니다."

    def scan_frames_in_active_doc(
        self,
        mode: str = "AUTO",
        target_etype: str = "",
        target_block: str = "",
        target_layer: str = "",
        expected_w: float = 0.0,
        expected_h: float = 0.0,
        interactive_select: bool = False,
    ):
        """
        현재 열린 도면에서 조건에 맞는 도곽들을 일괄 스캔하여 좌표 목록을 반환합니다.
        - mode == "EXTENTS": 모형 전체 범위(Extents) 1장 반환
        - mode == "AUTO": 도면 내 모든 도곽 후보(블록 또는 닫힌 직사각형 폴리라인 중 표준 용지 비율에 근접한 객체) 자동 탐색
        - mode == "SPECIFIED": 지정된 블록명 또는 레이어+크기 조건에 맞는 도곽 탐색 (전체 또는 사용자 드래그 선택)
        """
        ok, msg = self.connect(prefer_autocad=True)
        if not ok:
            return [], msg

        res_file = os.path.join(LOCAL_WORK_DIR, "frames_dump.txt").replace("\\", "/")

        if mode == "EXTENTS":
            lisp_code = f""";; Extents Getter
(vl-load-com)
(defun mplot_get_extents ( / pmin pmax fp)
  (setq pmin (getvar "EXTMIN"))
  (setq pmax (getvar "EXTMAX"))
  (setq fp (open "{res_file}" "w" "utf8"))
  (write-line (strcat "EXTENTS\\t전체영역\\t0\\t"
                      (rtos (car pmin) 2 4) "\\t" (rtos (cadr pmin) 2 4) "\\t"
                      (rtos (car pmax) 2 4) "\\t" (rtos (cadr pmax) 2 4)) fp)
  (close fp)
  (princ)
)
(mplot_get_extents)
"""
            if not self.run_lisp_and_wait(lisp_code, res_file, timeout=30.0):
                return [], "전체 영역(Extents) 조회 실패"
        else:
            ss_method = '(ssget \'((410 . "Model")))' if interactive_select else '(ssget "X" \'((410 . "Model")))'
            if interactive_select:
                try:
                    self.app.Visible = True
                    self.doc.Activate()
                except Exception:
                    pass

            lisp_code = f""";; Frame Scanner
(vl-load-com)
(defun mplot_scan_frames ( / ss i ent edata etype lay bname vts obj minpt maxpt p1 p2 w h fp)
  (setq fp (open "{res_file}" "w" "utf8"))
  (if {"T" if interactive_select else "nil"}
    (princ "\\n[다중플롯] 출력할 도곽들이 포함된 영역을 드래그하여 선택하세요 (엔터=선택완료): ")
  )
  (setq ss {ss_method})
  (if ss
    (progn
      (setq i 0)
      (while (< i (sslength ss))
        (setq ent (ssname ss i))
        (setq edata (entget ent))
        (setq etype (cdr (assoc 0 edata)))
        (setq lay (cdr (assoc 8 edata)))
        (if (or (= etype "INSERT") (= etype "LWPOLYLINE") (= etype "POLYLINE"))
          (progn
            (setq obj (vlax-ename->vla-object ent))
            (setq bname "")
            (if (= etype "INSERT")
              (if (vlax-property-available-p obj 'EffectiveName)
                (setq bname (vla-get-EffectiveName obj))
                (setq bname (cdr (assoc 2 edata)))
              )
            )
            (if (not (vl-catch-all-error-p (vl-catch-all-apply 'vla-GetBoundingBox (list obj 'minpt 'maxpt))))
              (progn
                (setq p1 (vlax-safearray->list minpt))
                (setq p2 (vlax-safearray->list maxpt))
                (setq w (abs (- (car p2) (car p1))))
                (setq h (abs (- (cadr p2) (cadr p1))))
                (if (and (> w 1.0) (> h 1.0))
                  (write-line (strcat etype "\\t" bname "\\t" lay "\\t"
                                      (rtos (car p1) 2 4) "\\t" (rtos (cadr p1) 2 4) "\\t"
                                      (rtos (car p2) 2 4) "\\t" (rtos (cadr p2) 2 4)) fp)
                )
              )
            )
          )
        )
        (setq i (1+ i))
      )
    )
  )
  (write-line "#EOF" fp)
  (close fp)
  (princ)
)
(mplot_scan_frames)
"""
            if not self.run_lisp_and_wait(lisp_code, res_file, timeout=120.0):
                return [], "도곽 탐색 시간이 초과되었습니다."

        raw_candidates = []
        with open(res_file, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line == "#EOF":
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                etype, bname, lay = parts[0], parts[1], parts[2]
                min_x, min_y, max_x, max_y = float(parts[3]), float(parts[4]), float(parts[5]), float(parts[6])
                w = abs(max_x - min_x)
                h = abs(max_y - min_y)
                raw_candidates.append({
                    "dwg_name": self.doc.Name,
                    "dwg_path": self.doc.FullName,
                    "kind": etype,
                    "block_name": bname,
                    "layer": lay,
                    "label": bname if bname else lay,
                    "min_x": min_x,
                    "min_y": min_y,
                    "max_x": max_x,
                    "max_y": max_y,
                    "width": w,
                    "height": h,
                })

        if mode == "EXTENTS":
            return raw_candidates, f"전체 객체영역 1건 인식됨"

        filtered = self._filter_candidates(
            raw_candidates, mode, target_etype, target_block, target_layer, expected_w, expected_h
        )
        return filtered, f"도곽 {len(filtered)}개 인식 완료"

    def _filter_candidates(
        self,
        candidates: list,
        mode: str,
        target_etype: str,
        target_block: str,
        target_layer: str,
        expected_w: float,
        expected_h: float,
    ) -> list:
        """수집된 엔티티 중 실제 도곽만 정밀 필터링하고 중복 도곽을 제거합니다."""
        if not candidates:
            return []

        matched = []
        if mode == "SPECIFIED" and (target_block or target_layer or expected_w > 0):
            for c in candidates:
                if target_etype == "INSERT" and target_block:
                    if c["kind"] == "INSERT" and c["block_name"].upper() == target_block.upper():
                        matched.append(c)
                else:
                    # 레이어 및 크기 유사도(±15%) 비교
                    lay_ok = (not target_layer) or (c["layer"].upper() == target_layer.upper())
                    if expected_w > 0 and expected_h > 0:
                        w_ok = abs(c["width"] - expected_w) <= expected_w * 0.15 and abs(c["height"] - expected_h) <= expected_h * 0.15
                        w_rot_ok = abs(c["width"] - expected_h) <= expected_h * 0.15 and abs(c["height"] - expected_w) <= expected_w * 0.15
                        size_ok = w_ok or w_rot_ok
                    else:
                        size_ok = True
                    if lay_ok and size_ok:
                        matched.append(c)
        else:
            # AUTO 모드:
            # 1순위: 이름에 BOX, FRAME, 도각, 도곽, A3, A4, FORM, DWG, BORDER 등이 포함된 INSERT 블록 또는 동일 크기가 여러 개 반복되는 블록
            block_groups = {}
            for c in candidates:
                if c["kind"] == "INSERT":
                    key = c["block_name"].upper()
                    block_groups.setdefault(key, []).append(c)

            frame_keywords = ("BOX", "FRAME", "도각", "도곽", "A1", "A3", "A4", "BORDER", "SHEET", "TITLE", "FORM")
            keyword_blocks = []
            for bname, items in block_groups.items():
                if any(k in bname for k in frame_keywords):
                    # 너무 작은 기호 블록(예: hwl, swl 등) 제외: 종횡비가 용지 비율(1.2~1.65) 근처인 것
                    valid_items = [
                        it for it in items
                        if 1.15 <= (max(it["width"], it["height"]) / max(0.001, min(it["width"], it["height"]))) <= 1.75
                        and max(it["width"], it["height"]) >= 150.0
                    ]
                    keyword_blocks.extend(valid_items)

            if keyword_blocks:
                matched = keyword_blocks
            else:
                # 2순위: 도면 내에서 용지 비율(√2 ≈ 1.414, 허용 1.25~1.60)을 가진 큰 사각형(INSERT 또는 LWPOLYLINE) 클러스터 탐색
                paper_like = []
                for c in candidates:
                    long_s = max(c["width"], c["height"])
                    short_s = max(0.001, min(c["width"], c["height"]))
                    ratio = long_s / short_s
                    if 1.25 <= ratio <= 1.60 and long_s >= 180.0:
                        paper_like.append(c)

                if paper_like:
                    # 가장 빈도가 높은 크기(±10%) 그룹을 도곽으로 채택 (내곽/외곽 겹침 시 외곽 우선)
                    size_clusters = []
                    for p in paper_like:
                        ls = max(p["width"], p["height"])
                        placed = False
                        for cl in size_clusters:
                            ref_ls = max(cl[0]["width"], cl[0]["height"])
                            if abs(ls - ref_ls) <= ref_ls * 0.10:
                                cl.append(p)
                                placed = True
                                break
                        if not placed:
                            size_clusters.append([p])
                    # 가장 개수가 많고, 개수가 같으면 크기가 큰(외곽) 클러스터 선택
                    size_clusters.sort(key=lambda cl: (len(cl), max(cl[0]["width"], cl[0]["height"])), reverse=True)
                    matched = size_clusters[0]

        # 동일 위치 중복 도곽 제거 (좌하단·우상단이 거의 같은 경우 1개만 유지)
        unique_frames = []
        for m in matched:
            is_dup = False
            for u in unique_frames:
                if (
                    abs(m["min_x"] - u["min_x"]) < m["width"] * 0.05
                    and abs(m["min_y"] - u["min_y"]) < m["height"] * 0.05
                    and abs(m["max_x"] - u["max_x"]) < m["width"] * 0.05
                    and abs(m["max_y"] - u["max_y"]) < m["height"] * 0.05
                ):
                    is_dup = True
                    break
            if not is_dup:
                unique_frames.append(m)

        return unique_frames

    def get_pc3_media_list(self, plotter_name: str):
        """현재 선택된 .pc3 플로터에 등록된 모든 용지(사용자 정의 PMP 용지 포함) 목록을 조회합니다."""
        ok, msg = self.connect(prefer_autocad=True)
        if not ok:
            return [], msg

        res_file = os.path.join(LOCAL_WORK_DIR, "pc3_media_list.txt").replace("\\", "/")
        lisp_code = f""";; PC3 Media List Reader
(vl-load-com)
(defun mplot_get_medias ( / doc lay mlist m loc_m fp)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)))
  (setq lay (vla-get-ActiveLayout doc))
  (vla-RefreshPlotDeviceInfo lay)
  (vl-catch-all-apply 'vla-put-ConfigName (list lay "{_ls(plotter_name)}"))
  (vla-RefreshPlotDeviceInfo lay)
  (setq mlist (vlax-safearray->list (vlax-variant-value (vla-GetCanonicalMediaNames lay))))
  (setq fp (open "{res_file}" "w" "utf8"))
  (foreach m mlist
    (setq loc_m (vla-GetLocaleMediaName lay m))
    (write-line (strcat loc_m "||" m) fp)
  )
  (write-line "#EOF" fp)
  (close fp)
  (princ)
)
(mplot_get_medias)
"""
        if not self.run_lisp_and_wait(lisp_code, res_file, timeout=30.0):
            return [], "플로터 용지 목록을 불러오지 못했습니다."

        medias = []
        with open(res_file, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line == "#EOF":
                    continue
                if "||" in line:
                    loc_name, can_name = line.split("||", 1)
                    medias.append(f"[PC3] {loc_name} || {can_name}")
        return medias, f"{len(medias)}개의 용지 규격을 불러왔습니다."

    @staticmethod
    def _resize_pdf_to_custom_mm(pdf_path: str, target_w_mm: float, target_h_mm: float, is_landscape: bool):
        """
        출력된 벡터 PDF 첫 페이지를 사용자가 입력한 가로(mm) × 세로(mm) 용지에 비율을 지켜 가운데로 옮겨 담는다
        (벡터 그대로, pypdf). 원래 페이지가 회전(/Rotate)돼 있으면 먼저 내용에 반영해 똑바로 놓는다.
        반환: 성공이면 None, 실패면 이유(원본 PDF는 그대로 남는다 — 부른 쪽이 사용자에게 알린다).
        """
        if not os.path.exists(pdf_path):
            return "PDF 파일이 없습니다"
        temp_pdf = pdf_path + ".tmp.pdf"
        try:
            from pypdf import PageObject, PdfReader, PdfWriter, Transformation
            long_mm = max(10.0, target_w_mm, target_h_mm)
            short_mm = max(10.0, min(target_w_mm, target_h_mm))
            final_w_mm = long_mm if is_landscape else short_mm
            final_h_mm = short_mm if is_landscape else long_mm

            # 1 inch = 25.4 mm = 72 pt
            w_pt = final_w_mm * 72.0 / 25.4
            h_pt = final_h_mm * 72.0 / 25.4

            reader = PdfReader(pdf_path)
            if not reader.pages:
                return "PDF에 페이지가 없습니다"
            src = reader.pages[0]
            src.transfer_rotation_to_content()
            box = src.cropbox
            sx, sy = float(box.left), float(box.bottom)
            sw, sh = float(box.width), float(box.height)
            if sw <= 0 or sh <= 0:
                return "페이지 크기가 0입니다"
            k = min(w_pt / sw, h_pt / sh)
            tx = (w_pt - sw * k) / 2.0 - sx * k
            ty = (h_pt - sh * k) / 2.0 - sy * k

            page = PageObject.create_blank_page(width=w_pt, height=h_pt)
            page.merge_transformed_page(src, Transformation().scale(k, k).translate(tx, ty))
            writer = PdfWriter()
            writer.add_page(page)

            with open(temp_pdf, "wb") as f:
                writer.write(f)
            os.replace(temp_pdf, pdf_path)
            return None
        except Exception as e:
            logging.error(f"사용자 용지 PDF 규격 변환 오류: {e}")
            if os.path.exists(temp_pdf):
                try:
                    os.remove(temp_pdf)
                except OSError:
                    pass
            return "%s: %s" % (type(e).__name__, e)

    def execute_batch_plot(
        self,
        frames: list,
        plotter_name: str,
        paper_preset_label: str,
        ctb_name: str,
        orientation_mode: str,
        reverse_upside_down: bool,
        fit_to_paper: bool,
        custom_scale_denom: float,
        center_plot: bool,
        output_dir: str,
        is_pdf_output: bool,
        use_custom_paper: bool = False,
        custom_paper_w: float = 210.0,
        custom_paper_h: float = 297.0,
        progress_callback=None,
    ):
        """
        정렬된 도곽 목록을 AutoCAD ActiveX(vla-PlotToFile / vla-PlotToDevice) LISP 엔진으로 순차 출력합니다.
        """
        ok, msg = self.connect(prefer_autocad=True)
        if not ok:
            return False, [], msg

        # 선택된 용지 프리셋 또는 PC3 직접 지정 용지에서 후보 미디어 이름 추출
        paper_keywords = ["ISO_full_bleed_A4_(210.00_x_297.00_MM)", "ISO_A4_(210.00_x_297.00_MM)", "A4"]
        if "||" in paper_preset_label:
            exact_can = paper_preset_label.split("||", 1)[1].strip()
            paper_keywords = [exact_can, exact_can, exact_can]
        elif use_custom_paper:
            # 사용자 지정 용지인 경우 캐드 내 유사 비율 Full Bleed 용지로 먼저 벡터 출력 후 정확한 mm로 리사이징
            paper_keywords = ["ISO_full_bleed_A3_(297.00_x_420.00_MM)", "ISO_full_bleed_A4_(210.00_x_297.00_MM)", "A3"]
        else:
            for label, _pw, _ph, kw_list in PAPER_PRESETS:
                if label == paper_preset_label:
                    paper_keywords = kw_list
                    break

        os.makedirs(output_dir, exist_ok=True)
        generated_pdfs = []
        resize_failed = []
        total = len(frames)

        for idx, frame in enumerate(frames, start=1):
            if progress_callback:
                progress_callback(idx, total, f"[{idx}/{total}] 출력 중: {frame['dwg_name']} (#{idx:03d})")

            target_dwg_path = frame.get("dwg_path", "")
            if target_dwg_path and os.path.exists(target_dwg_path):
                try:
                    if os.path.normcase(self.doc.FullName) != os.path.normcase(target_dwg_path):
                        found_open = False
                        for d_i in range(self.app.Documents.Count):
                            d_obj = self.app.Documents.Item(d_i)
                            if os.path.normcase(d_obj.FullName) == os.path.normcase(target_dwg_path):
                                d_obj.Activate()
                                self.doc = d_obj
                                found_open = True
                                break
                        if not found_open:
                            self.doc = self.app.Documents.Open(target_dwg_path)
                        time.sleep(0.3)
                except Exception as e:
                    logging.warning(f"문서 전환 예외: {e}")

            # 도곽 방향에 따른 회전값 결정
            # AutoCAD AcPlotRotation: 0=0deg, 1=90deg, 2=180deg, 3=270deg
            w = frame["max_x"] - frame["min_x"]
            h = frame["max_y"] - frame["min_y"]
            if orientation_mode == "AUTO":
                is_landscape = w >= h
            elif orientation_mode == "LANDSCAPE":
                is_landscape = True
            else:
                is_landscape = False

            if is_landscape:
                rot = 3 if reverse_upside_down else 1
            else:
                rot = 2 if reverse_upside_down else 0

            base_dwg = os.path.splitext(frame["dwg_name"])[0]
            pdf_filename = f"{base_dwg}_{idx:03d}.pdf"
            pdf_fullpath = os.path.join(output_dir, pdf_filename)
            if is_pdf_output and os.path.exists(pdf_fullpath):
                try:
                    os.remove(pdf_fullpath)
                except OSError:
                    pass

            done_flag = os.path.join(LOCAL_WORK_DIR, f"plot_done_{idx}.txt").replace("\\", "/")
            pdf_escaped = pdf_fullpath.replace("\\", "/")
            ctb_str = "" if ctb_name.startswith("없음") else ctb_name
            kw1 = paper_keywords[0]
            kw2 = paper_keywords[1] if len(paper_keywords) > 1 else kw1
            kw3 = paper_keywords[2] if len(paper_keywords) > 2 else kw1

            lisp_plot = f""";; Single Sheet Plot Runner
(vl-load-com)
(defun mplot_run_one ( / doc lay plot media_list matched_media m loc_m pmin pmax bg_old fd_old res fp)
  (setq bg_old (getvar "BACKGROUNDPLOT"))
  (setq fd_old (getvar "FILEDIA"))
  (setvar "BACKGROUNDPLOT" 0)
  (setvar "FILEDIA" 0)
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)))
  (setq lay (vla-get-ActiveLayout doc))
  (vla-RefreshPlotDeviceInfo lay)
  (vl-catch-all-apply 'vla-put-ConfigName (list lay "{_ls(plotter_name)}"))
  (vla-RefreshPlotDeviceInfo lay)

  ;; 용지 이름 자동 매칭 (CanonicalMediaName 및 LocaleMediaName 대조)
  (setq media_list (vlax-safearray->list (vlax-variant-value (vla-GetCanonicalMediaNames lay))))
  (setq matched_media nil)
  (foreach m media_list
    (if (and (null matched_media)
             (or (vl-string-search (strcase "{_ls(kw1)}") (strcase m))
                 (vl-string-search (strcase "{_ls(kw2)}") (strcase m))))
      (setq matched_media m)
    )
  )
  (if (null matched_media)
    (foreach m media_list
      (setq loc_m (vla-GetLocaleMediaName lay m))
      (if (and (null matched_media)
               (or (vl-string-search (strcase "{_ls(kw3)}") (strcase m))
                   (vl-string-search (strcase "{_ls(kw3)}") (strcase loc_m))))
        (setq matched_media m)
      )
    )
  )
  (if matched_media
    (vl-catch-all-apply 'vla-put-CanonicalMediaName (list lay matched_media))
  )

  ;; CTB 플롯 스타일 설정
  (if (/= "{_ls(ctb_str)}" "")
    (progn
      (vl-catch-all-apply 'vla-put-PlotWithPlotStyles (list lay :vlax-true))
      (vl-catch-all-apply 'vla-put-StyleSheet (list lay "{_ls(ctb_str)}"))
    )
    (vl-catch-all-apply 'vla-put-PlotWithPlotStyles (list lay :vlax-false))
  )

  ;; 출력 윈도우 영역 지정
  (setq pmin (vlax-make-safearray vlax-vbDouble '(0 . 1)))
  (setq pmax (vlax-make-safearray vlax-vbDouble '(0 . 1)))
  (vlax-safearray-fill pmin (list {frame['min_x']:.4f} {frame['min_y']:.4f}))
  (vlax-safearray-fill pmax (list {frame['max_x']:.4f} {frame['max_y']:.4f}))
  (vla-SetWindowToPlot lay pmin pmax)
  (vla-put-PlotType lay acWindow)

  ;; 중심 플롯 및 방향, 축척 설정
  (vla-put-CenterPlot lay {":vlax-true" if center_plot else ":vlax-false"})
  (vla-put-PlotRotation lay {rot})
  (if {"T" if fit_to_paper else "nil"}
    (progn
      (vla-put-UseStandardScale lay :vlax-true)
      (vla-put-StandardScale lay acScaleToFit)
    )
    (progn
      (vla-put-UseStandardScale lay :vlax-false)
      (vla-SetCustomScale lay 1.0 {max(0.001, custom_scale_denom):.4f})
    )
  )

  (setq plot (vla-get-Plot doc))
  (if {"T" if is_pdf_output else "nil"}
    (setq res (vl-catch-all-apply 'vla-PlotToFile (list plot "{pdf_escaped}")))
    (setq res (vl-catch-all-apply 'vla-PlotToDevice (list plot)))
  )

  (setvar "BACKGROUNDPLOT" bg_old)
  (setvar "FILEDIA" fd_old)

  (setq fp (open "{done_flag}" "w" "utf8"))
  (if (vl-catch-all-error-p res)
    (write-line (strcat "ERR\\t" (vl-catch-all-error-message res)) fp)
    (write-line "OK" fp)
  )
  (close fp)
  (princ)
)
(mplot_run_one)
"""
            saved_vars = self._save_plot_vars()
            try:
                ok_one = self.run_lisp_and_wait(lisp_plot, done_flag, timeout=90.0)
            finally:
                self._restore_plot_vars(saved_vars)
            if not ok_one:
                logging.error(f"시트 #{idx} 출력 타임아웃")
                return False, generated_pdfs, f"시트 #{idx} 출력 중 응답 시간이 초과되었습니다."

            with open(done_flag, "r", encoding="utf-8-sig", errors="replace") as f:
                status_line = f.read().strip()

            if status_line.startswith("ERR\t"):
                logging.error(f"시트 #{idx} 출력 오류: {status_line}")
                return False, generated_pdfs, f"시트 #{idx} 출력 오류: {status_line[4:]}"

            if is_pdf_output and os.path.exists(pdf_fullpath):
                if use_custom_paper:
                    why = self._resize_pdf_to_custom_mm(pdf_fullpath, custom_paper_w, custom_paper_h, is_landscape)
                    if why:
                        resize_failed.append(f"#{idx} {why}")
                generated_pdfs.append(pdf_fullpath)

        msg = f"총 {total}장 다중 출력이 완료되었습니다."
        if resize_failed:
            # 사용자 용지로 못 바꾼 장은 원래 용지 그대로 남았다 — 성공으로 덮지 않고 알린다
            msg += f" 다만 사용자 용지 변환에 실패한 {len(resize_failed)}장은 원래 용지 그대로입니다: " + "; ".join(resize_failed[:5])
        return True, generated_pdfs, msg


class CADMultiPlotterApp(tk.Tk):
    """
    모형 공간 다중 도곽 인식·정렬 및 다중 파일 일괄 인쇄를 지원하는
    오토캐드 다중 플롯 GUI 메인 애플리케이션.
    """

    def __init__(self):
        super().__init__()
        self.title("MPL  다중 플롯")  # 버전은 BCHELP 창에만
        self.geometry("1100x770")
        self.minsize(1000, 710)
        self.configure(bg="#1E1F22")

        # ─── BC_TOOL 네이티브 아이콘 적용 ───
        try:
            self.icon_path = get_resource(ICON_B64, ".ico")
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()
            sm_cx = ctypes.windll.user32.GetSystemMetrics(49)
            sm_cy = ctypes.windll.user32.GetSystemMetrics(50)
            lg_cx = ctypes.windll.user32.GetSystemMetrics(11)
            lg_cy = ctypes.windll.user32.GetSystemMetrics(12)
            hSmall = ctypes.windll.user32.LoadImageW(0, self.icon_path, 1, sm_cx, sm_cy, 0x00000010)
            hLarge = ctypes.windll.user32.LoadImageW(0, self.icon_path, 1, lg_cx, lg_cy, 0x00000010)
            if hSmall:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hSmall)
            if hLarge:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hLarge)
        except Exception as e:
            logging.warning(f"아이콘 로드 예외: {e}")

        self.bridge = AutoCADPlotBridge()
        self.pc3_list, self.ctb_list = scan_autocad_plot_resources()
        self.frames_data = []  # 탐색 및 정렬된 도곽 리스트
        self.extra_dwg_files = []  # 외부 추가 DWG 파일 목록
        self.sample_info = {"etype": "", "block_name": "", "layer": "", "width": 0.0, "height": 0.0}

        # ─── 상태 변수 (기본값: A4, PDF출력, 위->아래 Z순서) ───
        self.var_output_type = tk.StringVar(value="PDF")  # "PDF" or "PRINTER"
        self.var_plotter = tk.StringVar(value=self.pc3_list[0] if self.pc3_list else "DWG To PDF.pc3")
        self.var_paper = tk.StringVar(value="A4 (210 x 297 mm)")
        self.var_use_custom_paper = tk.BooleanVar(value=False)
        self.var_custom_paper_w = tk.StringVar(value="210")
        self.var_custom_paper_h = tk.StringVar(value="297")
        self.var_orientation = tk.StringVar(value="AUTO")  # AUTO, LANDSCAPE, PORTRAIT
        self.var_upside_down = tk.BooleanVar(value=False)
        self.var_area_mode = tk.StringVar(value="AUTO")  # AUTO, SPECIFIED, WINDOW, EXTENTS
        self.var_sort_order = tk.StringVar(value="Z_TOP_DOWN")
        self.var_fit_paper = tk.BooleanVar(value=True)
        self.var_custom_scale = tk.StringVar(value="1000")
        self.var_center_plot = tk.BooleanVar(value=True)
        self.var_ctb = tk.StringVar(value="monochrome.ctb" if "monochrome.ctb" in self.ctb_list else self.ctb_list[0])
        self.var_output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "CAD_Plot_Output"))
        self.var_merge_pdf = tk.BooleanVar(value=True)
        self.var_keep_single_pdf = tk.BooleanVar(value=True)
        self.var_status = tk.StringVar(value="준비 완료 — [도곽 자동인식] 또는 [도곽 지정]을 눌러 도면을 불러오세요.")

        self._load_saved_config()
        self._setup_styles()
        self._build_ui()
        self.after(300, self._check_initial_cad_connection)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#2B2D30", foreground="#E8EAED", fieldbackground="#2B2D30", rowheight=26, font=("맑은 고딕", 9))
        style.configure("Treeview.Heading", background="#383A3E", foreground="#F2C94C", font=("맑은 고딕", 9, "bold"))
        style.map("Treeview", background=[("selected", "#3E5879")], foreground=[("selected", "#FFFFFF")])
        style.configure("TCombobox", fieldbackground="#2B2D30", background="#383A3E", foreground="#FFFFFF")

    def _build_ui(self):
        # 전체 좌우 분할: 좌측 설정 패널(380px) + 우측 도곽/파일 리스트 패널
        main_frame = tk.Frame(self, bg="#1E1F22")
        main_frame.pack(fill="both", expand=True, padx=10, pady=8)

        left_panel = tk.Frame(main_frame, bg="#25262A", width=380, highlightbackground="#44474E", highlightthickness=1)
        left_panel.pack(side="left", fill="y", padx=(0, 10))
        left_panel.pack_propagate(False)

        right_panel = tk.Frame(main_frame, bg="#25262A", highlightbackground="#44474E", highlightthickness=1)
        right_panel.pack(side="left", fill="both", expand=True)

        self._build_left_settings(left_panel)
        self._build_right_list(right_panel)

        # 하단 상태바 & 진행바
        bottom_bar = tk.Frame(self, bg="#18191C", height=34)
        bottom_bar.pack(fill="x", side="bottom", padx=10, pady=(0, 6))
        self.progress = ttk.Progressbar(bottom_bar, orient="horizontal", length=220, mode="determinate")
        self.progress.pack(side="right", padx=8, pady=6)
        tk.Label(bottom_bar, textvariable=self.var_status, bg="#18191C", fg="#A8C7FA", font=("맑은 고딕", 9), anchor="w").pack(side="left", padx=8, fill="x", expand=True)

    def _section_header(self, parent, title_text: str):
        hdr = tk.Frame(parent, bg="#313338", height=26)
        hdr.pack(fill="x", pady=(7, 3))
        tk.Label(hdr, text=f"  {title_text}", bg="#313338", fg="#F2C94C", font=("맑은 고딕", 9, "bold"), anchor="w").pack(fill="x", pady=3)

    def _build_left_settings(self, parent):
        # 1. 프린터 / 플로터 섹션
        self._section_header(parent, "1. 프린터 / 플로터")
        f_out = tk.Frame(parent, bg="#25262A")
        f_out.pack(fill="x", padx=12, pady=2)
        tk.Radiobutton(
            f_out, text="파일출력 (PDF)", variable=self.var_output_type, value="PDF",
            command=self._on_output_type_change, bg="#25262A", fg="#F2C94C", selectcolor="#1E1F22",
            activebackground="#25262A", font=("맑은 고딕", 9, "bold")
        ).pack(side="left", padx=(0, 14))
        tk.Radiobutton(
            f_out, text="일반 프린터 출력", variable=self.var_output_type, value="PRINTER",
            command=self._on_output_type_change, bg="#25262A", fg="#E8EAED", selectcolor="#1E1F22",
            activebackground="#25262A", font=("맑은 고딕", 9)
        ).pack(side="left")

        f_pc3 = tk.Frame(parent, bg="#25262A")
        f_pc3.pack(fill="x", padx=12, pady=2)
        tk.Label(f_pc3, text="플로터(.pc3):", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9), width=10, anchor="w").pack(side="left")
        self.cmb_plotter = ttk.Combobox(f_pc3, textvariable=self.var_plotter, values=self.pc3_list, state="readonly")
        self.cmb_plotter.pack(side="left", fill="x", expand=True)

        # 2. 용지 및 방향 섹션 (기본값: A4 + 사용자 용지 직접 지정)
        self._section_header(parent, "2. 용지 규격 및 방향 (기본: A4)")
        f_orient = tk.Frame(parent, bg="#25262A")
        f_orient.pack(fill="x", padx=12, pady=2)
        for label, val in [("자동(비율맞춤)", "AUTO"), ("가로", "LANDSCAPE"), ("세로", "PORTRAIT")]:
            tk.Radiobutton(
                f_orient, text=label, variable=self.var_orientation, value=val,
                command=self._refresh_table_view, bg="#25262A", fg="#E8EAED", selectcolor="#1E1F22",
                activebackground="#25262A", font=("맑은 고딕", 9)
            ).pack(side="left", padx=(0, 6))
        tk.Checkbutton(
            f_orient, text="대칭", variable=self.var_upside_down,
            bg="#25262A", fg="#CCCCCC", selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 8)
        ).pack(side="right")

        f_paper = tk.Frame(parent, bg="#25262A")
        f_paper.pack(fill="x", padx=12, pady=2)
        tk.Label(f_paper, text="규격 용지:", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9), width=9, anchor="w").pack(side="left")
        paper_names = [p[0] for p in PAPER_PRESETS]
        self.cmb_paper = ttk.Combobox(f_paper, textvariable=self.var_paper, values=paper_names, state="readonly")
        self.cmb_paper.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.cmb_paper.bind("<<ComboboxSelected>>", self._on_preset_paper_selected)
        tk.Button(
            f_paper, text="PC3용지", command=self.cmd_load_pc3_media_list,
            bg="#383A3E", fg="#A8C7FA", relief="flat", font=("맑은 고딕", 8), padx=5
        ).pack(side="right")

        # 빠른 용지 선택 버튼 (A4, A3, B4, A2, A1)
        f_qpaper = tk.Frame(parent, bg="#25262A")
        f_qpaper.pack(fill="x", padx=12, pady=2)
        for short_name, full_label in [
            ("A4 (기본)", "A4 (210 x 297 mm)"),
            ("A3", "A3 (297 x 420 mm)"),
            ("B4", "B4 (250 x 353 mm)"),
            ("A2", "A2 (420 x 594 mm)"),
            ("A1", "A1 (594 x 841 mm)"),
        ]:
            tk.Button(
                f_qpaper, text=short_name, bg="#383A3E", fg="#FFFFFF", relief="flat",
                font=("맑은 고딕", 8), padx=6, pady=2,
                command=lambda fl=full_label: self._select_quick_paper(fl)
            ).pack(side="left", padx=2, expand=True, fill="x")

        # 사용자 용지 직접 입력 (가로 x 세로 mm)
        f_cpaper = tk.Frame(parent, bg="#25262A")
        f_cpaper.pack(fill="x", padx=12, pady=3)
        tk.Checkbutton(
            f_cpaper, text="사용자 용지:", variable=self.var_use_custom_paper,
            command=self._refresh_table_view, bg="#25262A", fg="#F2C94C",
            selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 9, "bold")
        ).pack(side="left")
        ent_cw = tk.Entry(f_cpaper, textvariable=self.var_custom_paper_w, width=7, bg="#1E1F22", fg="#FF8A65", insertbackground="#FFFFFF", justify="center", font=("맑은 고딕", 9, "bold"))
        ent_cw.pack(side="left", padx=(4, 2))
        tk.Label(f_cpaper, text="x", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9, "bold")).pack(side="left", padx=2)
        ent_ch = tk.Entry(f_cpaper, textvariable=self.var_custom_paper_h, width=7, bg="#1E1F22", fg="#FF8A65", insertbackground="#FFFFFF", justify="center", font=("맑은 고딕", 9, "bold"))
        ent_ch.pack(side="left", padx=(2, 4))
        tk.Label(f_cpaper, text="(mm)", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9)).pack(side="left")
        ent_cw.bind("<KeyRelease>", lambda _e: (self.var_use_custom_paper.set(True), self._refresh_table_view()))
        ent_ch.bind("<KeyRelease>", lambda _e: (self.var_use_custom_paper.set(True), self._refresh_table_view()))

        # 3. 출력 영역 및 인쇄순서 (첨부 스크린샷 완벽 반영)
        self._section_header(parent, "3. 출력 영역 및 인쇄순서")
        f_order = tk.Frame(parent, bg="#25262A")
        f_order.pack(fill="x", padx=12, pady=2)
        tk.Label(f_order, text="인쇄순서:", bg="#25262A", fg="#F2C94C", font=("맑은 고딕", 9, "bold"), width=8, anchor="w").pack(side="left")
        order_labels = [o[1] for o in SORT_ORDERS]
        self.cmb_order = ttk.Combobox(f_order, values=order_labels, state="readonly")
        self.cmb_order.current(0)
        self.cmb_order.pack(side="left", fill="x", expand=True)
        self.cmb_order.bind("<<ComboboxSelected>>", self._on_sort_order_changed)

        # 출력 영역 4개 버튼 (도곽맞춤 / 도곽지정 / 영역지정 / 모든 객체영역)
        f_area_btns = tk.Frame(parent, bg="#25262A")
        f_area_btns.pack(fill="x", padx=12, pady=3)
        btn_style = {"bg": "#33363D", "fg": "#E8EAED", "activebackground": "#4A6984", "activeforeground": "#FFFFFF", "relief": "groove", "font": ("맑은 고딕", 9, "bold"), "pady": 4}

        tk.Button(f_area_btns, text="▣ 도곽맞춤 (도면 전체 도곽 자동인식)", command=self.cmd_auto_detect_frames, **btn_style).pack(fill="x", pady=2)

        f_sub_spec = tk.Frame(f_area_btns, bg="#25262A")
        f_sub_spec.pack(fill="x", pady=2)
        tk.Button(f_sub_spec, text="⊞ 도곽지정 (1. 샘플찍기)", command=self.cmd_pick_sample_frame, **btn_style).pack(side="left", fill="x", expand=True, padx=(0, 2))
        tk.Button(f_sub_spec, text="2. 전체탐색", command=lambda: self.cmd_scan_by_sample(False), **btn_style).pack(side="left", padx=2)
        tk.Button(f_sub_spec, text="3. 드래그선택", command=lambda: self.cmd_scan_by_sample(True), **btn_style).pack(side="left", padx=(2, 0))

        f_sub_win = tk.Frame(f_area_btns, bg="#25262A")
        f_sub_win.pack(fill="x", pady=2)
        tk.Button(f_sub_win, text="◩ 영역지정 (창 클릭 추가)", command=self.cmd_add_manual_window, **btn_style).pack(side="left", fill="x", expand=True, padx=(0, 3))
        tk.Button(f_sub_win, text="⛶ 모든 객체영역 (Extents)", command=self.cmd_add_extents, **btn_style).pack(side="left", fill="x", expand=True, padx=(3, 0))

        # 축척 설정 (용지 맞춤 / 수동 축척)
        f_scale = tk.Frame(parent, bg="#25262A")
        f_scale.pack(fill="x", padx=12, pady=3)
        tk.Checkbutton(
            f_scale, text="용지 맞춤 (Fit)", variable=self.var_fit_paper, command=self._refresh_table_view,
            bg="#25262A", fg="#F2C94C", selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 9, "bold")
        ).pack(side="left")
        tk.Label(f_scale, text="   수동 축척 1 :", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9)).pack(side="left")
        self.ent_scale = tk.Entry(f_scale, textvariable=self.var_custom_scale, width=7, bg="#1E1F22", fg="#FFFFFF", insertbackground="#FFFFFF")
        self.ent_scale.pack(side="left", padx=4)
        tk.Checkbutton(
            f_scale, text="중심 플롯", variable=self.var_center_plot,
            bg="#25262A", fg="#CCCCCC", selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 9)
        ).pack(side="right")

        # 4. 플롯 스타일 (CTB) 및 PDF 저장 옵션
        self._section_header(parent, "4. 플롯 스타일 (CTB) 및 저장 설정")
        f_ctb = tk.Frame(parent, bg="#25262A")
        f_ctb.pack(fill="x", padx=12, pady=2)
        tk.Label(f_ctb, text="플롯 스타일:", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9), width=10, anchor="w").pack(side="left")
        self.cmb_ctb = ttk.Combobox(f_ctb, textvariable=self.var_ctb, values=self.ctb_list, state="readonly")
        self.cmb_ctb.pack(side="left", fill="x", expand=True)

        f_dir = tk.Frame(parent, bg="#25262A")
        f_dir.pack(fill="x", padx=12, pady=2)
        tk.Label(f_dir, text="저장 폴더:", bg="#25262A", fg="#CCCCCC", font=("맑은 고딕", 9), width=10, anchor="w").pack(side="left")
        tk.Entry(f_dir, textvariable=self.var_output_dir, bg="#1E1F22", fg="#E8EAED", insertbackground="#FFFFFF", font=("맑은 고딕", 8)).pack(side="left", fill="x", expand=True, padx=(0, 4))
        tk.Button(f_dir, text="폴더..", command=self._choose_output_dir, bg="#383A3E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=6).pack(side="right")

        f_pdf_opt = tk.Frame(parent, bg="#25262A")
        f_pdf_opt.pack(fill="x", padx=12, pady=2)
        tk.Checkbutton(
            f_pdf_opt, text="단일 PDF로 병합 생성", variable=self.var_merge_pdf,
            bg="#25262A", fg="#81C995", selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 9, "bold")
        ).pack(side="left")
        tk.Checkbutton(
            f_pdf_opt, text="낱장 PDF도 유지", variable=self.var_keep_single_pdf,
            bg="#25262A", fg="#CCCCCC", selectcolor="#1E1F22", activebackground="#25262A", font=("맑은 고딕", 8)
        ).pack(side="right")

        # 5. 하단 실행 버튼 (인쇄 정보 저장 / 인쇄하기)
        f_run = tk.Frame(parent, bg="#25262A")
        f_run.pack(fill="x", side="bottom", padx=12, pady=8)
        tk.Button(
            f_run, text="💾 설정 저장", command=self._save_config,
            bg="#383A3E", fg="#E8EAED", relief="flat", font=("맑은 고딕", 9, "bold"), width=12, pady=8
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            f_run, text="🖨️ 인쇄하기 (다중 플롯 실행)", command=self.cmd_execute_plot,
            bg="#1E6F50", fg="#FFFFFF", activebackground="#278E66", activeforeground="#FFFFFF",
            relief="flat", font=("맑은 고딕", 10, "bold"), pady=8
        ).pack(side="left", fill="x", expand=True)

    def _build_right_list(self, parent):
        # 상단 툴바: 현재 연결된 캐드 표시 + 다중 DWG 파일 추가 버튼 + 전체선택/초기화
        top_bar = tk.Frame(parent, bg="#313338", height=40)
        top_bar.pack(fill="x", padx=8, pady=(8, 4))

        self.lbl_cad_conn = tk.Label(top_bar, text="● CAD 연결 확인 중...", bg="#313338", fg="#F2C94C", font=("맑은 고딕", 9, "bold"))
        self.lbl_cad_conn.pack(side="left", padx=8, pady=6)

        tk.Button(top_bar, text="🔄 CAD 재연결", command=self._check_initial_cad_connection, bg="#44474E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8, pady=3).pack(side="left", padx=4)
        tk.Button(top_bar, text="📂 외부 DWG 파일 일괄 추가...", command=self.cmd_add_external_dwgs, bg="#3E5879", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 9, "bold"), padx=10, pady=3).pack(side="left", padx=8)
        tk.Button(top_bar, text="📁 출력 폴더 열기", command=self._open_output_dir, bg="#44474E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8, pady=3).pack(side="right", padx=6)

        # 중간 요약 및 리스트 제어 바
        ctrl_bar = tk.Frame(parent, bg="#25262A")
        ctrl_bar.pack(fill="x", padx=8, pady=2)
        self.lbl_count = tk.Label(ctrl_bar, text="전체출력: 0 / 0 매", bg="#25262A", fg="#81C995", font=("맑은 고딕", 10, "bold"))
        self.lbl_count.pack(side="left", padx=4)

        self.lbl_sample_desc = tk.Label(ctrl_bar, text="(기준 도곽: 자동 탐색 모드)", bg="#25262A", fg="#AAAAAA", font=("맑은 고딕", 9))
        self.lbl_sample_desc.pack(side="left", padx=10)

        tk.Button(ctrl_bar, text="🗑 목록 비우기", command=self.cmd_clear_list, bg="#5C2B29", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="❌ 선택 삭제", command=self.cmd_remove_selected, bg="#383A3E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="▼ 아래로", command=lambda: self.cmd_move_item(1), bg="#383A3E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="▲ 위로", command=lambda: self.cmd_move_item(-1), bg="#383A3E", fg="#FFFFFF", relief="flat", font=("맑은 고딕", 8), padx=8).pack(side="right", padx=2)

        # 도곽 목록 테이블 (Treeview)
        tree_frame = tk.Frame(parent, bg="#25262A")
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        cols = ("seq", "dwg", "kind", "label", "size", "orient", "scale", "coords")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("seq", text="순번")
        self.tree.heading("dwg", text="도면 파일명")
        self.tree.heading("kind", text="인식구분")
        self.tree.heading("label", text="블록명 / 레이어")
        self.tree.heading("size", text="도곽크기 (W×H)")
        self.tree.heading("orient", text="출력방향")
        self.tree.heading("scale", text="적용축척")
        self.tree.heading("coords", text="영역 좌표 (MinX, MinY ~ MaxX, MaxY)")

        self.tree.column("seq", width=52, anchor="center")
        self.tree.column("dwg", width=150, anchor="w")
        self.tree.column("kind", width=80, anchor="center")
        self.tree.column("label", width=110, anchor="w")
        self.tree.column("size", width=115, anchor="center")
        self.tree.column("orient", width=75, anchor="center")
        self.tree.column("scale", width=95, anchor="center")
        self.tree.column("coords", width=220, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _check_initial_cad_connection(self):
        ok, msg = self.bridge.connect(prefer_autocad=True)
        if ok:
            self.lbl_cad_conn.configure(text=f"● {msg}", fg="#81C995")
        else:
            self.lbl_cad_conn.configure(text=f"○ {msg}", fg="#F28B82")

    def _on_output_type_change(self):
        if self.var_output_type.get() == "PDF":
            if "PDF" not in self.var_plotter.get().upper():
                self.var_plotter.set("DWG To PDF.pc3")
        else:
            if "Default Windows System Printer.pc3" in self.pc3_list:
                self.var_plotter.set("Default Windows System Printer.pc3")

    def _select_quick_paper(self, full_label: str):
        self.var_paper.set(full_label)
        self.var_use_custom_paper.set(False)
        for label, pw, ph, _kw in PAPER_PRESETS:
            if label == full_label:
                self.var_custom_paper_w.set(f"{pw:g}")
                self.var_custom_paper_h.set(f"{ph:g}")
                break
        self._refresh_table_view()

    def _on_preset_paper_selected(self, _event=None):
        self.var_use_custom_paper.set(False)
        cur = self.var_paper.get()
        for label, pw, ph, _kw in PAPER_PRESETS:
            if label == cur:
                self.var_custom_paper_w.set(f"{pw:g}")
                self.var_custom_paper_h.set(f"{ph:g}")
                break
        self._refresh_table_view()

    def cmd_load_pc3_media_list(self):
        """현재 선택된 .pc3 플로터의 모든 내장/사용자정의 용지를 캐드에서 읽어와 드롭다운에 추가합니다."""
        self.var_status.set(f"[{self.var_plotter.get()}] 플로터의 전체 용지 목록을 조회 중입니다...")
        self.update_idletasks()
        medias, msg = self.bridge.get_pc3_media_list(self.var_plotter.get())
        if medias:
            preset_names = [p[0] for p in PAPER_PRESETS]
            self.cmb_paper["values"] = preset_names + medias
            self.var_status.set(f"{msg} — [규격 용지] 드롭다운을 열어 선택하세요.")
            messagebox.showinfo("PC3 용지 불러오기 완료", f"{msg}\n\n[규격 용지] 드롭다운 목록 하단에서 캐드 등록 용지를 선택하실 수 있습니다.")
        else:
            messagebox.showwarning("PC3 용지 조회", msg)
            self.var_status.set(msg)

    def _on_sort_order_changed(self, _event=None):
        idx = self.cmb_order.current()
        if 0 <= idx < len(SORT_ORDERS):
            self.var_sort_order.set(SORT_ORDERS[idx][0])
        if self.frames_data:
            self.frames_data = sort_frames(self.frames_data, self.var_sort_order.get())
            self._refresh_table_view()

    def _get_selected_paper_dims(self):
        if self.var_use_custom_paper.get():
            try:
                cw = float(self.var_custom_paper_w.get().strip())
                ch = float(self.var_custom_paper_h.get().strip())
                if cw > 0 and ch > 0:
                    return cw, ch
            except ValueError:
                pass
        cur = self.var_paper.get()
        for label, pw, ph, _kw in PAPER_PRESETS:
            if label == cur:
                return pw, ph
        return 210.0, 297.0

    def _refresh_table_view(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        pw, ph = self._get_selected_paper_dims()
        paper_long = max(pw, ph)
        paper_short = min(pw, ph)
        orient_mode = self.var_orientation.get()
        fit_mode = self.var_fit_paper.get()
        custom_sc = self.var_custom_scale.get().strip()

        for idx, f in enumerate(self.frames_data, start=1):
            w = max(0.001, abs(f["max_x"] - f["min_x"]))
            h = max(0.001, abs(f["max_y"] - f["min_y"]))
            if orient_mode == "AUTO":
                is_land = w >= h
            elif orient_mode == "LANDSCAPE":
                is_land = True
            else:
                is_land = False

            orient_str = "가로" if is_land else "세로"
            if fit_mode:
                eff_pw = paper_long if is_land else paper_short
                eff_ph = paper_short if is_land else paper_long
                ratio = max(w / eff_pw, h / eff_ph)
                scale_str = f"Fit (1:{ratio:.2f})"
            else:
                scale_str = f"1:{custom_sc}"

            coord_str = f"({f['min_x']:.1f}, {f['min_y']:.1f}) ~ ({f['max_x']:.1f}, {f['max_y']:.1f})"
            self.tree.insert(
                "", "end",
                values=(
                    f"{idx:03d}",
                    f["dwg_name"],
                    f["kind"],
                    f.get("label", ""),
                    f"{w:.1f} × {h:.1f}",
                    orient_str,
                    scale_str,
                    coord_str,
                )
            )

        cnt = len(self.frames_data)
        self.lbl_count.configure(text=f"전체출력: {cnt} / {cnt} 매")

    def _on_tree_double_click(self, _event):
        """목록의 도곽을 더블클릭하면 오토캐드 화면에서 해당 도곽 위치로 즉시 줌(Zoom Window)합니다."""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self.frames_data):
            f = self.frames_data[idx]
            ok, _ = self.bridge.connect(prefer_autocad=True)
            if ok and self.bridge.doc.Name.lower() == f["dwg_name"].lower():
                cmd = f'_ZOOM _W {f["min_x"]},{f["min_y"]} {f["max_x"]},{f["max_y"]}\n'
                try:
                    self.bridge.doc.SendCommand(cmd)
                except Exception:
                    pass

    def cmd_auto_detect_frames(self):
        self._check_initial_cad_connection()
        self.var_status.set("현재 열린 도면에서 도곽을 자동 탐색하고 있습니다...")
        self.update_idletasks()
        frames, msg = self.bridge.scan_frames_in_active_doc(mode="AUTO")
        if frames:
            self.frames_data = sort_frames(frames, self.var_sort_order.get())
            self._refresh_table_view()
            self.lbl_sample_desc.configure(text=f"(자동인식: {frames[0].get('label', '도곽')})")
            self.var_status.set(f"도곽맞춤 완료: 총 {len(self.frames_data)}개의 도곽이 정렬되었습니다.")
        else:
            messagebox.showwarning("도곽 자동인식", f"자동으로 인식된 도곽이 없습니다.\n({msg})\n\n[⊞ 도곽지정 (1. 샘플찍기)] 버튼으로 도곽 선이나 블록을 직접 한 번 찍어주세요.")
            self.var_status.set("자동 인식된 도곽 없음 — [도곽지정 (1. 샘플찍기)]를 이용해 주세요.")

    def cmd_pick_sample_frame(self):
        self.var_status.set("오토캐드 창에서 기준 도곽(블록 또는 사각 폴리라인) 1개를 클릭하세요...")
        self.iconify()  # 캐드 클릭이 편하도록 잠시 창 최소화
        self.update_idletasks()
        info, msg = self.bridge.pick_sample_frame_in_cad()
        self.deiconify()
        self.lift()
        if not info:
            self.var_status.set(msg)
            return

        self.sample_info = info
        desc = f"타입:{info['etype']} | 블록:{info['block_name'] or '-'} | 레이어:{info['layer']} | 크기:{info['width']:.1f}×{info['height']:.1f}"
        self.lbl_sample_desc.configure(text=f"({desc})")
        # 샘플 선택 직후 해당 조건으로 도면 전체 도곽 자동 탐색 실행
        self.cmd_scan_by_sample(interactive_select=False)

    def cmd_scan_by_sample(self, interactive_select: bool = False):
        if not self.sample_info.get("etype"):
            messagebox.showinfo("안내", "먼저 [1. 샘플찍기] 버튼으로 기준 도곽을 1개 선택해 주세요.")
            return

        if interactive_select:
            self.var_status.set("오토캐드 창에서 출력할 도곽들을 드래그하여 선택 후 엔터를 치세요...")
            self.iconify()
            self.update_idletasks()

        frames, msg = self.bridge.scan_frames_in_active_doc(
            mode="SPECIFIED",
            target_etype=self.sample_info["etype"],
            target_block=self.sample_info["block_name"],
            target_layer=self.sample_info["layer"],
            expected_w=self.sample_info["width"],
            expected_h=self.sample_info["height"],
            interactive_select=interactive_select,
        )
        if interactive_select:
            self.deiconify()
            self.lift()

        if frames:
            self.frames_data = sort_frames(frames, self.var_sort_order.get())
            self._refresh_table_view()
            self.var_status.set(f"기준 도곽으로 총 {len(self.frames_data)}매가 검색·정렬되었습니다.")
        else:
            self.var_status.set(f"조건에 맞는 도곽을 찾지 못했습니다. ({msg})")

    def cmd_add_manual_window(self):
        self.var_status.set("오토캐드 화면에서 인쇄할 영역의 두 구석점을 클릭하세요...")
        self.iconify()
        self.update_idletasks()
        frame, msg = self.bridge.pick_manual_window_in_cad()
        self.deiconify()
        self.lift()
        if frame:
            self.frames_data.append(frame)
            self.frames_data = sort_frames(self.frames_data, self.var_sort_order.get())
            self._refresh_table_view()
            self.var_status.set(f"수동 출력 영역이 추가되었습니다. (총 {len(self.frames_data)}매)")
        else:
            self.var_status.set(msg)

    def cmd_add_extents(self):
        frames, msg = self.bridge.scan_frames_in_active_doc(mode="EXTENTS")
        if frames:
            self.frames_data = frames
            self._refresh_table_view()
            self.var_status.set("모든 객체영역(Extents) 1매가 설정되었습니다.")
        else:
            self.var_status.set(msg)

    def cmd_add_external_dwgs(self):
        """여러 외부 DWG 파일을 선택하여 순차적으로 열고 도곽을 스캔해 목록에 추가합니다."""
        paths = filedialog.askopenfilenames(
            title="다중 플롯할 DWG 도면 파일 선택 (복수 선택 가능)",
            filetypes=[("AutoCAD 도면 (*.dwg)", "*.dwg"), ("모든 파일 (*.*)", "*.*")],
        )
        if not paths:
            return

        ok, msg = self.bridge.connect(prefer_autocad=True)
        if not ok:
            messagebox.showerror("연결 실패", msg)
            return

        added_count = 0
        for p in paths:
            norm_p = os.path.abspath(p)
            self.var_status.set(f"도면 열기 및 도곽 스캔 중: {os.path.basename(norm_p)}...")
            self.update_idletasks()
            try:
                doc = self.bridge.app.Documents.Open(norm_p)
                time.sleep(0.5)
                self.bridge.doc = doc
                mode = "SPECIFIED" if self.sample_info.get("etype") else "AUTO"
                frames, _ = self.bridge.scan_frames_in_active_doc(
                    mode=mode,
                    target_etype=self.sample_info.get("etype", ""),
                    target_block=self.sample_info.get("block_name", ""),
                    target_layer=self.sample_info.get("layer", ""),
                    expected_w=self.sample_info.get("width", 0.0),
                    expected_h=self.sample_info.get("height", 0.0),
                )
                if frames:
                    frames = sort_frames(frames, self.var_sort_order.get())
                    self.frames_data.extend(frames)
                    added_count += len(frames)
            except Exception as e:
                logging.error(f"외부 DWG 열기 오류 ({norm_p}): {e}")

        self._refresh_table_view()
        self.var_status.set(f"외부 DWG {len(paths)}개 파일에서 총 {added_count}매의 도곽을 추가했습니다.")

    def cmd_move_item(self, direction: int):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        new_idx = idx + direction
        if 0 <= new_idx < len(self.frames_data):
            self.frames_data[idx], self.frames_data[new_idx] = self.frames_data[new_idx], self.frames_data[idx]
            self._refresh_table_view()
            child_id = self.tree.get_children()[new_idx]
            self.tree.selection_set(child_id)

    def cmd_remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        indices = sorted([self.tree.index(s) for s in sel], reverse=True)
        for i in indices:
            if 0 <= i < len(self.frames_data):
                self.frames_data.pop(i)
        self._refresh_table_view()

    def cmd_clear_list(self):
        self.frames_data.clear()
        self._refresh_table_view()
        self.var_status.set("목록을 비웠습니다.")

    def _choose_output_dir(self):
        d = filedialog.askdirectory(title="PDF 출력 파일을 저장할 폴더 선택", initialdir=self.var_output_dir.get())
        if d:
            self.var_output_dir.set(d)

    def _open_output_dir(self):
        out_d = self.var_output_dir.get()
        os.makedirs(out_d, exist_ok=True)
        os.startfile(out_d)

    def _save_config(self):
        cfg = {
            "output_type": self.var_output_type.get(),
            "plotter": self.var_plotter.get(),
            "paper": self.var_paper.get(),
            "use_custom_paper": self.var_use_custom_paper.get(),
            "custom_paper_w": self.var_custom_paper_w.get(),
            "custom_paper_h": self.var_custom_paper_h.get(),
            "orientation": self.var_orientation.get(),
            "upside_down": self.var_upside_down.get(),
            "sort_order": self.var_sort_order.get(),
            "fit_paper": self.var_fit_paper.get(),
            "custom_scale": self.var_custom_scale.get(),
            "center_plot": self.var_center_plot.get(),
            "ctb": self.var_ctb.get(),
            "output_dir": self.var_output_dir.get(),
            "merge_pdf": self.var_merge_pdf.get(),
            "keep_single_pdf": self.var_keep_single_pdf.get(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.var_status.set("현재 인쇄 설정이 config.json에 저장되었습니다.")
        except Exception as e:
            logging.error(f"설정 저장 실패: {e}")

    def _load_saved_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.var_output_type.set(cfg.get("output_type", "PDF"))
            self.var_plotter.set(cfg.get("plotter", self.var_plotter.get()))
            self.var_paper.set(cfg.get("paper", "A4 (210 x 297 mm)"))
            self.var_use_custom_paper.set(cfg.get("use_custom_paper", False))
            self.var_custom_paper_w.set(cfg.get("custom_paper_w", "210"))
            self.var_custom_paper_h.set(cfg.get("custom_paper_h", "297"))
            self.var_orientation.set(cfg.get("orientation", "AUTO"))
            self.var_upside_down.set(cfg.get("upside_down", False))
            self.var_sort_order.set(cfg.get("sort_order", "Z_TOP_DOWN"))
            self.var_fit_paper.set(cfg.get("fit_paper", True))
            self.var_custom_scale.set(cfg.get("custom_scale", "1000"))
            self.var_center_plot.set(cfg.get("center_plot", True))
            self.var_ctb.set(cfg.get("ctb", self.var_ctb.get()))
            self.var_output_dir.set(cfg.get("output_dir", self.var_output_dir.get()))
            self.var_merge_pdf.set(cfg.get("merge_pdf", True))
            self.var_keep_single_pdf.set(cfg.get("keep_single_pdf", True))
        except Exception as e:
            logging.warning(f"설정 로드 실패: {e}")

    def cmd_execute_plot(self):
        if not self.frames_data:
            messagebox.showwarning("출력 대상 없음", "출력할 도곽이 목록에 없습니다.\n먼저 [▣ 도곽맞춤] 또는 [⊞ 도곽지정]으로 도곽을 불러오세요.")
            return

        is_pdf = self.var_output_type.get() == "PDF" or "PDF" in self.var_plotter.get().upper()
        out_dir = self.var_output_dir.get().strip()
        if is_pdf and not out_dir:
            messagebox.showwarning("저장 폴더 확인", "PDF 파일을 저장할 폴더 경로를 지정해 주세요.")
            return

        try:
            custom_sc = float(self.var_custom_scale.get().strip())
        except ValueError:
            custom_sc = 1000.0

        use_cp = self.var_use_custom_paper.get()
        cp_w, cp_h = 210.0, 297.0
        if use_cp:
            try:
                cp_w = float(self.var_custom_paper_w.get().strip())
                cp_h = float(self.var_custom_paper_h.get().strip())
                if cp_w <= 0 or cp_h <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("사용자 용지 확인", "사용자 용지 가로(W)·세로(H) 크기를 양수(mm)로 입력해 주세요.")
                return

        self._save_config()
        self.progress["maximum"] = len(self.frames_data)
        self.progress["value"] = 0

        def update_prog(cur_idx, total_cnt, status_txt):
            self.progress["value"] = cur_idx
            self.var_status.set(status_txt)
            self.update_idletasks()

        # 도면 파일별로 그룹화하여 순차 처리
        ok, pdf_files, msg = self.bridge.execute_batch_plot(
            frames=self.frames_data,
            plotter_name=self.var_plotter.get(),
            paper_preset_label=self.var_paper.get(),
            ctb_name=self.var_ctb.get(),
            orientation_mode=self.var_orientation.get(),
            reverse_upside_down=self.var_upside_down.get(),
            fit_to_paper=self.var_fit_paper.get(),
            custom_scale_denom=custom_sc,
            center_plot=self.var_center_plot.get(),
            output_dir=out_dir,
            is_pdf_output=is_pdf,
            use_custom_paper=use_cp,
            custom_paper_w=cp_w,
            custom_paper_h=cp_h,
            progress_callback=update_prog,
        )

        if not ok:
            messagebox.showerror("다중 플롯 실패", msg)
            self.var_status.set(f"오류: {msg}")
            return

        merged_path = ""
        if is_pdf and self.var_merge_pdf.get() and len(pdf_files) > 1:
            merged_path = self._merge_pdf_files(pdf_files, out_dir)
            if merged_path and not self.var_keep_single_pdf.get():
                for pf in pdf_files:
                    try:
                        os.remove(pf)
                    except OSError:
                        pass

        done_msg = f"총 {len(self.frames_data)}매 다중 플롯이 완료되었습니다!"
        if "다만" in msg:
            # 출력 엔진이 붙인 경고(사용자 용지로 못 바꾼 장 등)를 덮지 않고 그대로 보인다
            done_msg += "\n\n※ " + msg[msg.index("다만"):]
        if is_pdf:
            done_msg += f"\n\n저장 폴더: {out_dir}"
            if merged_path:
                done_msg += f"\n통합 PDF: {os.path.basename(merged_path)}"
            elif self.var_merge_pdf.get() and len(pdf_files) > 1:
                done_msg += "\n※ 통합 PDF 만들기에 실패했습니다(낱장 PDF는 그대로 있습니다). 로그를 확인하세요."
        self.var_status.set(done_msg.replace("\n", " "))
        logging.info(done_msg.replace("\n", " | "))

        if messagebox.askyesno("출력 완료", f"{done_msg}\n\n저장된 출력 폴더를 바로 여시겠습니까?"):
            self._open_output_dir()

    def _merge_pdf_files(self, pdf_files: list, out_dir: str) -> str:
        """개별 출력된 PDF들을 순서대로 하나의 통합 PDF로 합친다(pypdf)."""
        try:
            from pypdf import PdfWriter
            base_name = os.path.splitext(self.frames_data[0]["dwg_name"])[0]
            ts = datetime.now().strftime("%H%M%S")
            merged_pdf = os.path.join(out_dir, f"{base_name}_통합출력_{len(pdf_files)}매_{ts}.pdf")
            writer = PdfWriter()
            for pf in pdf_files:
                if os.path.exists(pf):
                    writer.append(pf)
            with open(merged_pdf, "wb") as f:
                writer.write(f)
            writer.close()
            return merged_pdf
        except Exception as e:
            logging.error(f"PDF 병합 실패: {e}")
            return ""


def main():
    app = CADMultiPlotterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
