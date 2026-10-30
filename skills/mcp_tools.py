# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""MCP에서 스킬 명령을 부르는 통로.

- skill_list: 명령 목록
- skill_open: 창(또는 설정 창)을 띄운다 — 사람이 쓰는 기본 방식
- skill_run: 창 없이 값만으로 실행한다. 설정은 저장된 설정 파일 위에 settings 인자를 덮어 쓴다.

skill_run의 LISP 실행은 server의 COM 스레드에서 ctl.lisp로 한다(유휴 확인·ESC 복구·UNDO 한 묶음).
"""

import importlib
import json
import os
import subprocess
import time

from skills import registry
from skills.common import coords as C
from skills.common import lisplib
from skills.common import paths
from skills.common import settings as S
from skills.common import terrain

RUN_SPECS = {
    "FE": "base_point [x,y], base_el, points [[x,y],...] (또는 handle: 선·폴리선 정점 전부)",
    "FW": "base_point, base_el, points 또는 handle",
    "FEL": "base_point, base_el, targets [EL,...]",
    "CEE": "handles [모양 객체], base_point(모양의 EL 위치), points",
    "GEL": "p1, el1, p2, el2, points",
    "SLEL": "base_point, base_el, slope ('1:100'·'2%'·0.01, 하향은 음수), points, curve_handle(선택)",
    "IEL": "points (삼각망 3D면이 도면에 있어야 함)",
    "XY": "points, leader_points(선택, 기본 점에서 오른쪽 위)",
    "ZBC": "handle(폴리선), table_point",
    "WCD": "handle(사각 폴리선)",
    "XYB": "handles, base_point, sx, sy",
    "CALC": "expression('(2*3)+sin(30)'·'폭 5.0 × 2' 같은 식) 또는 settings.대상('문자'|'치수'|'객체 길이'|'면적(객체)'|'체적'|'수식' + handles, '거리'|'수평 거리'|'수직 거리' + points 이어진 점)·settings.방식('+'|'-'|'×'|'÷'|'평균') → expression·result·text. write_point [x,y]면 결과 문자 쓰기, replace_handle이면 그 문자 내용 바꾸기. 길이·면적·체적은 settings.축척(1000=m 도면)으로 m 단위",
    "MUIN": "files [경로…](.dwg·.dxf), explode(기본 true — false면 파일 이름 블록) → 파일별 넣은 객체 수. 원래 좌표 그대로",
    "CR": "handles(문자들), p1·p2(사각형 두 모서리) 또는 target_handle(그 객체 가운데) → 옮긴 문자 수",
    "LOL": "layers [레이어 이름…] 또는 handles [객체 핸들…] — 이 레이어만 켜고 나머지 끔 → 바뀐 레이어 수",
    "LOF": "layers 또는 handles — 그 레이어 끔",
    "LON": "(인자 없음) 모든 레이어 켬",
    "OLO": "(인자 없음) 꺼져 있던 레이어만 켜고 켜져 있던 것은 끔(꺼진 게 없으면 0)",
    "LFR": "layers 또는 handles — 그 레이어 동결(현재 레이어는 제외)",
    "FRE": "layers 또는 handles — 그 레이어 외 모두 동결",
    "LTH": "(인자 없음) 모든 레이어 동결 해제",
    "LLO": "layers 또는 handles — 그 레이어 잠금",
    "LUL": "layers 또는 handles — 그 레이어 잠금 해제",
    "ULA": "(인자 없음) 모든 레이어 잠금 해제",
    "LOE": "layers 또는 handles — 그 레이어 외 모두 잠금",
    "SCL": "layer(이름) 또는 handle(그 객체의 레이어) → 현재 레이어 이름",
    "CCL": "handles — 현재 레이어로 옮김(잠긴 레이어 객체는 그대로) → 옮긴 객체 수",
    "CEX": "handles(선택, 없으면 도면 전체 대상 종류), csv_path(선택) → rows(기본 토목 좌표 [북, 동] — settings 좌표=수학이면 [x, y]). 2000행 넘으면 truncated — 전부는 csv_path로",
    "CIM": "rows [[...]] — 열 순서는 settings.열(기본 '번호,X,Y' 3열, 토목 좌표 X=북). [[x, y]]만 줄 때는 settings {\"열\": \"X,Y\", \"좌표\": \"수학\"}",
    "TTE": "groups [[핸들…], …](묶음마다 한 열) 또는 handles(한 묶음), 없으면 도면 전체 문자 → rows(엑셀에 넣을 표, settings.방향 '아래로'면 묶음=열). settings.처리로 내보낸 문자 레이어·색 변경·삭제",
    "RCE": "창 전용 — 사람이 점을 하나씩 찍는 명령이라 skill_run으로는 못 한다. skill_open(\"RCE\")",
    "FPEL": "start_point, start_el, rows [[측점, EL, 표기1, 표기2]]",
    "DTIN": "handles(선택, 없으면 도면 전체 대상 종류)",
    "CCON": "handles(선택, 없으면 도면 전체 대상 종류 — settings.방식 '3D면(삼각망) 선택'이면 3DFACE) → 점·삼각형·높이·등고선 수, z_range. 간격·레이어·외측최소화(1~5)·특정높이는 settings",
    "WCZ": "pairs [[낮은 쪽 점, 높은 쪽 점], …] — 선분이 지나는 등고선마다 높이 문자 → 쓴 문자 수",
    "DCON": "handles(등고선, 선택 — 없으면 도면 전체 선·폴리선·스플라인) → 옮긴 객체 수. settings 간격·머리말·시작색(R,G,B)·명도단계",
    "GRP": "handle(선형 LINE·LWPOLYLINE·ARC), terrain_handles(선택, 없으면 도면 전체 3DFACE·선·폴리선), insert_point [x,y](선택: 기준선 왼쪽 끝에 종단·표 작도) → rows [측점, 누가거리, 지반고](지형 밖은 빈칸), vertices, length. settings 간격·시작거리·H/V축척·표기·정점 줄이기",
    "CFM": "handle(중심선), settings.방식 '그려진 횡단선 선택'(+ section_handles) | '측점 간격마다' | '엑셀 측점 목록'(+ stations [측점…]), terrain_handles(선택), base_point [x,y](선택: 첫 횡단 중심에 작도) → sections [{station, dist, ground [[거리(왼쪽 −), EL]], center_el}]",
    "ART": "handles(문자), point [x,y](수평·수직 정렬 기준점, 간격 조정만이면 생략), settings 방식·정렬점·간격함께·간격방식·간격·이격 → 정렬한 문자 수",
    "CTS": "handles(문자), settings.방식 '문자 외곽선'(트루타입 TEXT만, 정밀도·두께%)|'문자 복사'(X·Y 문자 높이 배수), 그림자색·원본색·레이어 → made, skipped [{handle, reason}] (그림자는 원본 뒤로)",
    "RET": "handles(철근 상세의 원·번호 블록·문자·밑줄 선 전부), insert_point [x,y](선택: 표 왼쪽 위 — 없으면 계산만), mark_bad(기본 true: 인식 못 한 원에 '철근-인식안됨' 광선) → details 수, tables [{grade, rows [번호, 직경, 길이(m), 본수, 총길이, 단위중량, 총중량, 비고]}], unrecognized, duplicates. settings 할증·비고·강도별·길이단위(자동: 소수점 있으면 m)·정렬",
    "INN": "settings.내용('도면 (?/6)'처럼 ? 자리), 시작값·증분·자리수·소수·천단위·16진수 + ① 복사: source_handle, base_point, points [[x,y]…] ② 고치기: handles(고른 순서대로) → values",
    "QCAR": "boundary_handle(용지 경계 닫힌 폴리선), alignment_handle(선택: 번호 순서용 선형), handles(선택: 지적·지번·행정구역 객체, 없으면 도면 전체 LWPOLYLINE·문자 — settings 지적선레이어·지번문자레이어로 가름), draw(기본 true: 면적 산출선·번호) → rows [행정구역, 번호, 지번, 지목, 면적, 편입면적, 전체편입, 비고]·summary(합계·경계·차이=합계−경계)",
    "CMOB": "handles(선택, 없으면 도면 전체 대상 종류), settings.여유도(2~10) → 경계 고리 수·정점 수",
    "DSEL": "handles(선택, 없으면 도면 전체 대상 종류), settings 조건·EL, center [x,y](선택: 연결선 시작점) → 찾은 점 수",
    "TTP": "handles(선택, 없으면 도면 전체 대상 종류), settings.기능('문자→Z점'|'점·블록→Z문자'|'선 정점→Z점·문자'|'문자 주변 점·블록 Z 올리기') → 만든 점·문자 수, Z 올린 수",
    "MPL": "mode AUTO|EXTENTS, output_dir, paper('A3 (297 x 420 mm)' 등), plotter, ctb, order, merge, custom_paper [가로mm, 세로mm](선택)",
    "DCP": "handles [선1, 선2] — 두 선이 서로 마주 보는 구간에만 중심선(기본). settings {\"끝연장\": true}면 양 끝을 끝 접선 방향으로 늘여 두 선의 끝점 중 더 나간 쪽과 나란하게. 거절: 닫힌 선·교차·겹침·T자 맞닿음(끝점 하나 공유는 됨)·고도가 변하는 3D 선·한 선이 다른 선을 감쌈. settings.허용오차는 도면 단위(m 도면 0.001 = 1mm, mm 도면이면 1)",
    "DCEN": "handles (원·호들) 또는 two_lines [선1, 선2]",
    "GST": "handle(선형), reverse(선택), points",
    "STT": "handle, reverse(선택), points(또는 stations [누가거리 숫자 m 또는 측점 글자 '1+250'·'No.12+5'(settings.측점구분)]), sides 'L'|'R'|'A'. 두 점+연장 표기는 points 2개 + name + settings {\"방식\": \"두점\"}. 평면도 지구명 견본 형식(구간 양 끝 안쪽에 '명칭 L=1,208m' / '(No.18+076 ~ No.19+270)' 두 줄, 인출선 없음)은 settings {\"방식\": \"구간\"}(구간구분·구간소수·구간거리·줄간격·문자스타일)",
    "CST": "stations [측점, 측점] → 연장(m). '1+250'(km+m)은 settings 측점구분 Station(기본), 'No.12+5'(체인 번호)는 Number와 측점간격",
    "NUST": "handles(문자들)",
    "MIP": "handle(호가 든 LWPOLYLINE)",
    "DSTA": "handle, reverse(선택), stations(선택: 누가거리·측점 목록, 없으면 간격마다)",
    "DIBC": "handle(기준), others [핸들…], reverse(선택) → table [측점, 누가거리, 선1, 선2…, 합계]. 거리 부호: 진행 방향 왼쪽 +, 오른쪽 −. 빈칸 = 그 측점의 수직선이 그 선을 측점 옆에서 만나지 않음(0이나 '선 없음'으로 단정하지 말 것). 합계는 모든 선이 있을 때만",
    "HWLI": "base_handle, detail_handle, rows [[측점, 값…]], base_reverse·detail_reverse(선택) → 표",
    "DSLO": "handles [시작선(안쪽), 끝선(바깥쪽)], start_point·end_point(선택, 둘 다 줘야 시작선 위 그 구간만)",
    "NSLO": "handle(상단선), side_point(사면이 내려가는 쪽 점), bottom_handle(선택)",
    "DFB": "apex(사면 시작 한 점), handle(끝선 호)",
    "SLL": "start_point, slope('1:1.5'·'2%'·0.5, 위 +/아래 −), end_x",
    "SLT": "p1, p2 → (높이/거리 비, 문자, 핸들)",
    "CSS": "ground_handle(지반선), point(법견·법선), side 'L'|'R' → (쌓기/깎기, 지반 만남, 핸들…)",
    "CUT": "ground_handle, p1, p2(지반선 위 X 구간) → 층 수",
    "DCEM": "sample_handles [지반선, 중심선, 측점 문자, 지반고 문자](견본 등록, 선택 — 없으면 지난 견본), dry_run(true면 그리지 않고 단면 인식 표만)",
    "HWLM": "rows [[측점, HWL, SWL, 여유고]], sample_handles(선택, DCEM과 같음), dry_run(선택)",
    "RCSE": "handle(평면 선형), reverse(선택), spec(선택)",
    "DRRE": "mode 'template'(handle, reverse → 양식 행) 또는 'draw'(rows [[누가거리, 구분, R, 경사, 길이(높이), 밑다짐폭, 중심~호안머리]], origin [x,y]) → 구간·면적",
    "CSAR": "pick {centers [[x, y아래]], win [dx0,dy0,dx1,dy1], frame_handle, frame [insx,insy,minx,miny,maxx,maxy], area [ax0,ay0,ax1,ay1](도곽 삽입점 기준), extra [핸들], base [x,y]}",
    "DDGP": "rows(첫 행은 반드시 한글 머리글 — 열을 이름으로 찾는다: 측점·하상고·좌/우 계획고·하폭·제방폭·제내지경사·제외지경사·호안경사·HWL·SWL·여유고), sample_handles(선택, DCEM과 같음), dry_run(선택)",
}


def settings_schema(cmd: str) -> list:
    """skill_run의 settings에 넣을 수 있는 키 [{key, label, type, default, choices}]. 바로 찍는 명령은 registry,
    창 명령은 skills/windows/<명령>.py의 FIELDS. 없으면 [] (MPL은 창 설정을 쓰지 않는다)."""
    import importlib
    fields = registry.COMMANDS.get(cmd, {}).get("fields")
    if not fields:
        try:
            fields = importlib.import_module("skills.windows.%s" % cmd.lower()).FIELDS
        except (ImportError, AttributeError):
            fields = []
    return [{"key": k, "label": lab, "type": t, "default": d, "choices": c} for k, lab, t, d, c in fields]


def table():
    """skill_list: 명령마다 설명·run_args(skill_run 인자)·settings(설정 키·기본값)·설정 파일."""
    out = registry.table()
    for r in out:
        r["run_args"] = RUN_SPECS.get(r["command"], "")
        r["settings"] = settings_schema(r["command"])
        r["settings_file"] = S.path(r["command"])
    return out


def open_window(cmd: str) -> dict:
    cmd = cmd.upper()
    if cmd not in registry.COMMANDS:
        raise LookupError("모르는 명령: %s. skill_list로 목록을 보세요." % cmd)
    info = registry.COMMANDS[cmd]
    if info["kind"] == "lisp" and not info.get("fields"):
        return {"opened": False, "hint": "%s는 설정 창이 없습니다. AutoCAD에서 %s를 직접 치세요." % (cmd, cmd)}
    launch = os.path.join(paths.SKILLS, "launch.py")
    subprocess.Popen([paths.pythonw(), launch, cmd], cwd=paths.ROOT,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    what = "설정 창" if info["kind"] == "lisp" else "창"
    return {"opened": True, "command": cmd, "window": what,
            "hint": "사람이 창에서 실행합니다. 바로 찍는 명령이면 저장 후 AutoCAD에서 %s를 치면 됩니다." % cmd}


# ---------------------------------------------------------------- LISP 값 표기

def lq(s) -> str:
    """LISP 문자열 리터럴(역슬래시·따옴표 이스케이프 — 사용자 문자를 바꾸지 않는다,)."""
    from validators import lisp_str
    return '"' + lisp_str(s) + '"'


def lnum(v) -> str:
    return "%.10f" % float(v)


def lpt(p) -> str:
    p = list(p) + [0.0] * (3 - len(p))
    return "(list %s %s %s)" % (lnum(p[0]), lnum(p[1]), lnum(p[2]))


def lval(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return lnum(v)
    return lq(v)


def lcfg(cmd: str, overrides: dict) -> str:
    """저장된 설정 + overrides → LISP 연관 목록 식. 키는 registry 설정 항목만."""
    cfg = merged_cfg(cmd, registry.defaults(cmd), overrides)
    return "(list %s)" % " ".join("(cons %s %s)" % (lq(k), lval(v)) for k, v in cfg.items())


def cast_like(v, like, key=""):
    """설정 값을 기본값 형식으로(정수로 준 높이 3 → 3.0 — LISP 정수 나눗셈 방지,)."""
    try:
        if isinstance(like, bool):
            return v if isinstance(v, bool) else str(v).strip() in ("1", "T", "true", "True")
        if isinstance(like, int):
            return int(float(v))
        if isinstance(like, float):
            return float(v)
    except (TypeError, ValueError):
        raise ValueError("설정 %s 값이 숫자가 아닙니다: %r" % (key, v))
    return str(v)


def merged_cfg(cmd: str, defaults: dict, overrides) -> dict:
    """저장된 설정 위에 overrides를 덮는다. 없는 키는 거절, 값은 기본값 형식으로."""
    cfg = S.load(cmd, defaults)
    for k, v in (overrides or {}).items():
        if k not in cfg:
            raise ValueError("%s에 없는 설정 키: %s (가능: %s)" % (cmd, k, ", ".join(cfg)))
        cfg[k] = cast_like(v, defaults.get(k, cfg[k]), k)
    return cfg


def slope_ratio(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("+-")
    if s.endswith("%"):
        r = float(s[:-1]) / 100.0
    elif ":" in s:
        a, b = s.split(":", 1)
        r = float(a) / float(b)
    elif "/" in s:
        a, b = s.split("/", 1)
        r = float(a) / float(b)
    else:
        r = float(s)
    return -r if neg else r


def _need(a, *keys):
    for k in keys:
        if k not in a or a[k] in (None, ""):
            raise ValueError("인자 %s가 필요합니다." % k)


def _pts_or_handle(a):
    if a.get("handle"):
        return '(bc:verts (handent %s))' % lq(a["handle"])
    _need(a, "points")
    return "(list %s)" % " ".join(lpt(p) for p in a["points"])


def body_for(cmd: str, a: dict) -> str:
    """skill_run 명령별 LISP 본문. 결과는 R<탭>... 줄로 낸다."""
    st = a.get("settings") or {}
    emit = '(write-line (strcat "R\\t" (vl-princ-to-string _r)) _fp)'
    if cmd in ("FE", "FW"):
        _need(a, "base_point", "base_el")
        core = "bc:fe-core" if cmd == "FE" else "bc:fw-core"
        return ("(setq _c %s) (foreach _p %s (setq _r (%s %s %s _p _c)) %s)"
                % (lcfg(cmd, st), _pts_or_handle(a), core, lpt(a["base_point"]), lnum(a["base_el"]), emit))
    if cmd == "FEL":
        _need(a, "base_point", "base_el", "targets")
        return ("(setq _c %s) (foreach _t (list %s) (setq _r (bc:fel-core %s %s _t _c)) %s)"
                % (lcfg(cmd, st), " ".join(lnum(t) for t in a["targets"]), lpt(a["base_point"]), lnum(a["base_el"]), emit))
    if cmd == "CEE":
        _need(a, "handles", "base_point", "points")
        return ("(setq _c %s _e (mapcar 'handent (list %s))) (foreach _p (list %s) (setq _r (bc:cee-core _e %s _p _c)) %s)"
                % (lcfg(cmd, st), " ".join(lq(h) for h in a["handles"]), " ".join(lpt(p) for p in a["points"]),
                   lpt(a["base_point"]), emit))
    if cmd == "GEL":
        _need(a, "p1", "el1", "p2", "el2", "points")
        return ("(setq _c %s) (foreach _p (list %s) (setq _r (bc:gel-core %s %s %s %s _p _c)) %s)"
                % (lcfg(cmd, st), " ".join(lpt(p) for p in a["points"]), lpt(a["p1"]), lnum(a["el1"]),
                   lpt(a["p2"]), lnum(a["el2"]), emit))
    if cmd == "SLEL":
        _need(a, "base_point", "base_el", "slope", "points")
        en = "(handent %s)" % lq(a["curve_handle"]) if a.get("curve_handle") else "nil"
        return ("(setq _c %s) (foreach _p (list %s) (setq _r (bc:slel-core %s %s %s _p %s _c)) %s)"
                % (lcfg(cmd, st), " ".join(lpt(p) for p in a["points"]), lpt(a["base_point"]), lnum(a["base_el"]),
                   lnum(slope_ratio(a["slope"])), en, emit))
    if cmd == "IEL":
        _need(a, "points")
        return ("(setq _c %s) (foreach _p (list %s) (setq _r (bc:iel-core _p _c)) %s)"
                % (lcfg(cmd, st), " ".join(lpt(p) for p in a["points"]), emit))
    if cmd == "XY":
        _need(a, "points")
        lead = a.get("leader_points") or []
        parts = []
        for i, p in enumerate(a["points"]):
            q = lead[i] if i < len(lead) else None
            parts.append("(setq _r (bc:xy-core %s %s _c nil)) %s" % (lpt(p), lpt(q) if q else
                         "(list (+ %s (* 3 (bc:xy-h _c))) (+ %s (* 3 (bc:xy-h _c))) 0.0)" % (lnum(p[0]), lnum(p[1])), emit))
        return "(setq _c %s) %s" % (lcfg(cmd, st), " ".join(parts))
    if cmd == "ZBC":
        _need(a, "handle", "table_point")
        return "(setq _r (bc:zbc-core (handent %s) %s %s)) %s" % (lq(a["handle"]), lpt(a["table_point"]), lcfg(cmd, st), emit)
    if cmd == "WCD":
        _need(a, "handle")
        return "(setq _r (bc:wcd-core (handent %s) %s)) %s" % (lq(a["handle"]), lcfg(cmd, st), emit)
    if cmd == "XYB":
        _need(a, "handles", "base_point", "sx", "sy")
        return ("(setq _l (mapcar 'handent (list %s)))"
                " (if (setq _w (bc:xyb-check _l %s %s)) (write-line (strcat \"ERR\" _d _w) _fp)"
                " (progn (setq _r (bc:xyb-core _l %s %s %s)) %s))"
                % (" ".join(lq(h) for h in a["handles"]), lnum(a["sx"]), lnum(a["sy"]),
                   lpt(a["base_point"]), lnum(a["sx"]), lnum(a["sy"]), emit))
    if cmd in LAYER_PICK:
        lays, hs = a.get("layers") or [], a.get("handles") or []
        if not lays and not hs:
            raise ValueError("%s: layers(레이어 이름 목록) 또는 handles(객체 핸들 목록)가 필요합니다" % cmd)
        return ("(setq _n (append (list %s) (bc:lay-of (mapcar 'handent (list %s)))))"
                " (if (setq _w (bc:lay-missing _n)) (write-line (strcat \"ERR\" _d _w) _fp)"
                " (progn (setq _r (bc:%s-core _n)) %s))"
                % (" ".join(lq(x) for x in lays), " ".join(lq(h) for h in hs), cmd.lower(), emit))
    if cmd in LAYER_ALL:
        return "(setq _r (bc:%s-core)) %s" % (cmd.lower(), emit)
    if cmd == "SCL":
        if a.get("layer"):
            name = lq(a["layer"])
        else:
            _need(a, "handle")
            name = "(cdr (assoc 8 (entget (handent %s))))" % lq(a["handle"])
        return ("(setq _n %s) (if (setq _w (bc:lay-missing (list _n))) (write-line (strcat \"ERR\" _d _w) _fp)"
                " (progn (setq _r (bc:scl-core _n)) %s))" % (name, emit))
    if cmd == "CCL":
        _need(a, "handles")
        return "(setq _r (bc:ccl-core (mapcar 'handent (list %s)))) %s" % (" ".join(lq(h) for h in a["handles"]), emit)
    if cmd == "CR":
        _need(a, "handles")
        if a.get("target_handle"):
            tgt = "(bc:obj-center (handent %s))" % lq(a["target_handle"])
        else:
            _need(a, "p1", "p2")
            tgt = "(bc:mid2 %s %s)" % (lpt(a["p1"]), lpt(a["p2"]))
        return ("(setq _l (vl-remove-if-not (function (lambda (e) (member (cdr (assoc 0 (entget e))) (list \"TEXT\" \"MTEXT\"))))"
                " (mapcar 'handent (list %s))))"
                " (if _l (progn (setq _r (bc:cr-core _l %s)) %s) (write-line (strcat \"ERR\" _d \"handles에 문자(TEXT·MTEXT)가 없습니다\") _fp))"
                % (" ".join(lq(h) for h in a["handles"]), tgt, emit))
    rev = "T" if a.get("reverse") else "nil"
    if cmd == "DCP":
        _need(a, "handles")
        return "(setq _r (bc:dcp-core (handent %s) (handent %s) %s)) %s" % (lq(a["handles"][0]), lq(a["handles"][1]), lcfg(cmd, st), emit)
    if cmd == "DCEN":
        if a.get("two_lines"):
            return "(setq _r (bc:dcen-two (handent %s) (handent %s) %s)) %s" % (lq(a["two_lines"][0]), lq(a["two_lines"][1]), lcfg(cmd, st), emit)
        _need(a, "handles")
        return "(setq _c %s) (foreach _h (list %s) (setq _r (bc:dcen-circle (handent _h) _c)) %s)" % (
            lcfg(cmd, st), " ".join(lq(h) for h in a["handles"]), emit)
    if cmd == "GST":
        _need(a, "handle", "points")
        return "(setq _c %s _e (handent %s)) (foreach _p (list %s) (setq _r (bc:gst-core _e %s _p _c)) %s)" % (
            lcfg(cmd, st), lq(a["handle"]), " ".join(lpt(p) for p in a["points"]), rev, emit)
    if cmd == "STT":
        _need(a, "handle")
        sides = {"R": "(list -1)", "A": "(list 1 -1)"}.get(str(a.get("sides", "L")).upper(), "(list 1)")
        if a.get("stations"):
            # 누가거리 숫자 또는 측점 글자('1+250'·'No.12+5' — settings.측점구분에 맞춰 읽는다)
            vals, words = [], []
            for d in a["stations"]:
                try:
                    vals.append(lnum(d))
                except (TypeError, ValueError):
                    vals.append("(bc:sta-parse %s _c)" % lq(d))
                    words.append(lq(d))
            dds = "(mapcar (quote (lambda (d) (* (- d (bc:sta-start _c)) (bc:upm-sta _c)))) (list %s))" % " ".join(vals)
        else:
            _need(a, "points")
            dds = "(mapcar (quote (lambda (p) (bc:curve-d _e p %s))) (list %s))" % (rev, " ".join(lpt(p) for p in a["points"]))
            words = []
        name = lq(a["name"]) if a.get("name") else '(bc:cfg _c "표기명칭")'
        # 읽지 못한 측점 글자가 있으면 그리지 않고 알린다
        bad = ('(setq _why nil) (foreach _h (list %s) (if (and (not _why) (not (bc:sta-parse _h _c))) (setq _why _h)))'
               % " ".join(words)) if words else "(setq _why nil)"
        return ("(setq _c %s _e (handent %s)) %s (if _why (write-line (strcat \"ERR\" _d \"측점을 읽지 못했습니다: \" _why"
                " \" (settings.측점구분 확인)\") _fp) (progn (setq _r (bc:stt-core _e %s %s _c %s %s)) %s))" % (
                    lcfg(cmd, st), lq(a["handle"]), bad, rev, dds, sides, name, emit))
    if cmd == "CST":
        _need(a, "stations")
        return ("(setq _c %s _a (bc:sta-parse %s _c) _b (bc:sta-parse %s _c)) (setq _r (if (and _a _b) (abs (- _b _a)))) %s"
                % (lcfg(cmd, st), lq(a["stations"][0]), lq(a["stations"][1]), emit))
    if cmd == "NUST":
        _need(a, "handles")
        return "(setq _c %s) (foreach _h (list %s) (setq _r (bc:nust-one (handent _h) _c)) %s)" % (
            lcfg(cmd, st), " ".join(lq(h) for h in a["handles"]), emit)
    if cmd == "MIP":
        _need(a, "handle")
        return "(setq _r (bc:mip-core (handent %s) %s)) %s" % (lq(a["handle"]), lcfg(cmd, st), emit)
    if cmd == "DSLO":
        _need(a, "handles")
        h1, h2 = lq(a["handles"][0]), lq(a["handles"][1])
        rng = ("(bc:curve-d (handent %s) %s nil) (bc:curve-d (handent %s) %s nil)" % (h1, lpt(a["start_point"]), h1, lpt(a["end_point"]))
               if a.get("start_point") and a.get("end_point") else "0.0 (bc:curve-len (handent %s))" % h1)
        return "(setq _r (bc:dslo-core (handent %s) (handent %s) %s %s)) %s" % (h1, h2, rng, lcfg(cmd, st), emit)
    if cmd == "NSLO":
        _need(a, "handle", "side_point")
        b = "(handent %s)" % lq(a["bottom_handle"]) if a.get("bottom_handle") else "nil"
        return ("(setq _r (bc:nslo-core (handent %s) %s %s 0.0 (bc:curve-len (handent %s)) %s)) %s"
                % (lq(a["handle"]), lpt(a["side_point"]), b, lq(a["handle"]), lcfg(cmd, st), emit))
    if cmd == "DFB":
        _need(a, "apex", "handle")
        return "(setq _r (bc:dfb-core %s (handent %s) %s)) %s" % (lpt(a["apex"]), lq(a["handle"]), lcfg(cmd, st), emit)
    if cmd == "SLL":
        _need(a, "start_point", "slope", "end_x")
        return "(setq _r (bc:sll-core %s %s %s %s)) %s" % (lpt(a["start_point"]), lnum(slope_ratio(a["slope"])),
                                                         lnum(a["end_x"]), lcfg(cmd, st), emit)
    if cmd == "SLT":
        _need(a, "p1", "p2")
        return "(setq _r (bc:slt-core %s %s %s)) %s" % (lpt(a["p1"]), lpt(a["p2"]), lcfg(cmd, st), emit)
    if cmd == "CSS":
        _need(a, "ground_handle", "point", "side")
        side = "1" if str(a["side"]).upper() in ("R", "1", "RIGHT", "우") else "-1"
        return "(setq _r (bc:css-core (handent %s) %s %s %s)) %s" % (lq(a["ground_handle"]), lpt(a["point"]), side,
                                                                  lcfg(cmd, st), emit)
    if cmd == "CUT":
        _need(a, "ground_handle", "p1", "p2")
        return "(setq _r (bc:cut-core (handent %s) %s %s %s)) %s" % (lq(a["ground_handle"]), lpt(a["p1"]), lpt(a["p2"]),
                                                                  lcfg(cmd, st), emit)
    if cmd == "ART":
        _need(a, "handles")
        pt = lpt(a["point"]) if a.get("point") else "nil"
        return ("(setq _r (bc:art-core (mapcar 'handent (list %s)) %s %s)) %s"
                % (" ".join(lq(h) for h in a["handles"]), pt, lcfg(cmd, st), emit))
    if cmd == "WCZ":
        _need(a, "pairs")
        return ("(setq _c %s _r 0) (foreach _q (list %s) (setq _r (+ _r (bc:wcz-core (car _q) (cadr _q) _c)))) %s"
                % (lcfg(cmd, st), " ".join("(list %s %s)" % (lpt(p), lpt(q)) for p, q in a["pairs"]), emit))
    if cmd == "DSEL":
        ens = ("(mapcar 'handent (list %s))" % " ".join(lq(h) for h in a["handles"]) if a.get("handles") else
               "(bc:ss-list (ssget \"_X\" (append (bc:dsel-filter _c) (list (cons 410 \"Model\")))))")
        return ("(setq _c %s) (setq _r (bc:dsel-core %s %s _c)) %s"
                % (lcfg(cmd, st), ens, lpt(a["center"]) if a.get("center") else "nil", emit))
    if cmd == "DCON":
        ens = ("(mapcar 'handent (list %s))" % " ".join(lq(h) for h in a["handles"]) if a.get("handles") else
               "(bc:ss-list (ssget \"_X\" (list (cons 0 \"LWPOLYLINE,POLYLINE,SPLINE,LINE\") (cons 410 \"Model\"))))")
        return "(setq _r (bc:dcon-core %s %s)) %s" % (ens, lcfg(cmd, st), emit)
    raise LookupError("%s는 skill_run에서 값만으로 실행하는 방식을 아직 지원하지 않습니다(창: skill_open)." % cmd)


def _dump_body(handles, types, usealign=False) -> str:
    al = "T" if usealign else "nil"
    if handles:
        return ("(foreach _h (list %s) (if (handent _h) (bc:dump-ent (handent _h) %s _fp)))"
                % (" ".join(lq(h) for h in handles), al))
    return '(bc:dump-ss (ssget "_X" (list (cons 0 %s) (cons 410 "Model"))) %s _fp)' % (lq(types), al)


HANDLE_KEYS = ("handle", "handles", "others", "two_lines", "curve_handle", "base_handle", "detail_handle",
               "ground_handle", "bottom_handle", "target_handle", "replace_handle", "terrain_handles", "section_handles",
               "boundary_handle", "alignment_handle", "source_handle")
LAYER_PICK = ("LOL", "LOF", "LFR", "FRE", "LLO", "LUL", "LOE")  # 레이어 이름 또는 객체 핸들로 고르는 레이어 명령
LAYER_ALL = ("LON", "OLO", "LTH", "ULA")  # 인자 없이 전체 레이어에 하는 명령
_CURVES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "SPLINE"}
# 명령 → {인자 이름: 받는 개체 종류} — 엉뚱한 개체(문자 등)를 넘기면 허공에 그리기 전에 거절한다
KIND_RULES = {"CSS": {"ground_handle": {"LWPOLYLINE", "POLYLINE", "LINE"}},
              "GRP": {"handle": {"LINE", "LWPOLYLINE", "ARC"}}, "CFM": {"handle": {"LINE", "LWPOLYLINE", "ARC"},
                                                                  "section_handles": {"LINE", "LWPOLYLINE"}},
              "CUT": {"ground_handle": {"LWPOLYLINE", "POLYLINE"}},
              "NSLO": {"handle": _CURVES, "bottom_handle": _CURVES},
              "ZBC": {"handle": {"LWPOLYLINE", "POLYLINE"}}, "WCD": {"handle": {"LWPOLYLINE", "POLYLINE"}},
              "MIP": {"handle": {"LWPOLYLINE"}}, "NUST": {"handles": {"TEXT", "MTEXT"}},
              "DCP": {"handles": _CURVES}, "GST": {"handle": _CURVES}, "STT": {"handle": _CURVES},
              "DSTA": {"handle": _CURVES}, "DIBC": {"handle": _CURVES, "others": _CURVES},
              "HWLI": {"base_handle": _CURVES, "detail_handle": _CURVES}, "RCSE": {"handle": _CURVES},
              # FE·FW handle은 정점을 읽는다(bc:verts) — 호·스플라인은 정점이 없어 빈 결과가 된다
              "FE": {"handle": {"LINE", "LWPOLYLINE", "POLYLINE"}}, "FW": {"handle": {"LINE", "LWPOLYLINE", "POLYLINE"}},
              "DCEN": {"handles": {"CIRCLE", "ARC"}, "two_lines": {"LINE", "LWPOLYLINE", "POLYLINE"}}, "DSLO": {"handles": _CURVES},
              "DFB": {"handle": _CURVES}, "SLEL": {"curve_handle": _CURVES}, "DRRE": {"handle": {"LWPOLYLINE"}}}
# 견본 단면 핸들 4개의 자리별 종류(DCEM·HWLM·DDGP sample_handles: 지반선, 중심선, 측점 문자, 지반고 문자)
SAMPLE_KINDS = ({"LWPOLYLINE", "POLYLINE", "LINE"}, {"LINE", "LWPOLYLINE"}, {"TEXT", "MTEXT"}, {"TEXT", "MTEXT"})


# 결과가 모두 nil이면 실패인 명령과 흔한 원인
NIL_MEANS_FAIL = {
    "DCP": ("닫힌 선이거나 길이 0, 두 선이 서로 만나거나 겹침(끝점만 맞닿는 것은 괜찮음), 고도가 변하는 3D 선, "
            "한 선이 다른 선을 감쌈(중심이 양쪽에 생김), 또는 서로 마주 보는 구간이 없음"),
    "CST": "측점 문자를 읽지 못함(settings.측점구분: 'No.12+5'처럼 체인 번호면 Number, '1+250'이면 Station)",
    "NUST": "측점·숫자로 읽을 수 없는 문자이거나 잠긴 레이어",
    "MIP": "호(볼록)가 든 LWPOLYLINE이 아니거나 모든 호가 반원",
    "IEL": "점 아래에 3DFACE(삼각망)가 없음",
}


def _draw(ctl, doc, lib, body, t1):
    """그리기 LISP — 길면 식 경계에서 나눠 차례로, UNDO 한 번에 되돌리게 묶는다."""
    from skills.common.lisplib import split_forms
    with ctl._undo_group(doc):
        for part in split_forms(body):
            ctl.lisp(lib + part, doc=doc, timeout_s=t1)


def _check_handles(ctl, lib, doc, cmd, a, timeout_s):
    """인자에 든 핸들이 도면에 있는지(없으면 원점에 엉뚱하게 그리는 대신 거절,)."""
    hs, key_of = [], {}
    for k in HANDLE_KEYS:
        v = a.get(k)
        if v in (None, ""):
            continue
        if k in ("handles", "others", "two_lines", "terrain_handles", "section_handles"):
            if isinstance(v, str):
                raise ValueError("%s는 핸들 목록(JSON 배열)이어야 합니다: %r" % (k, v))
            vs = [str(x) for x in v]
        else:
            vs = [str(v)]
        hs += vs
        for h in vs:
            key_of.setdefault(h.upper(), k)
    sample_kind = {}
    sh = a.get("sample_handles")
    if sh:
        if not (isinstance(sh, list) and len(sh) == 4):
            raise ValueError("sample_handles는 [지반선, 중심선, 측점 문자, 지반고 문자] 핸들 4개여야 합니다")
        for h, kinds in zip(sh, SAMPLE_KINDS):
            hs.append(str(h))
            key_of.setdefault(str(h).upper(), "sample_handles")
            sample_kind[str(h).upper()] = kinds
    if not hs:
        return
    body = ('(foreach _h (list %s) (write-line (strcat "H" _d _h _d (if (handent _h)'
            ' (cdr (assoc 0 (entget (handent _h)))) "NONE")) _fp))' % " ".join(lq(h) for h in hs))
    rules = KIND_RULES.get(cmd, {})
    for r in ctl.lisp(lib + body, doc=doc, timeout_s=timeout_s):
        c = r.split("\t")
        if c[0] != "H":
            continue
        if c[2] == "NONE":
            raise LookupError("핸들 %s가 도면(%s)에 없습니다(활성 도면이 바뀌었는지 확인)." % (c[1], doc.Name))
        k = key_of.get(c[1].upper())
        kinds = sample_kind.get(c[1].upper()) if k == "sample_handles" else rules.get(k)
        if kinds and c[2] not in kinds:
            raise ValueError("%s의 %s는 %s여야 합니다(받은 것: %s %s)." % (cmd, k, "/".join(sorted(kinds)), c[1], c[2]))


def run(ctl, cmd: str, a: dict, budget: float = 120.0) -> dict:
    """COM 스레드에서 부른다. ctl은 src.cad_controller.AcadControl.
    budget은 서버 바깥 제한시간. LISP 한 번의 제한시간은 그보다 15초 짧게 잡아 ESC 복구가 먼저 돌게 한다."""
    cmd = cmd.upper()
    if cmd not in registry.COMMANDS:
        raise LookupError("모르는 명령: %s" % cmd)
    a = a or {}
    if cmd == "MPL":
        ctl._require_idle()  # 사람이 AutoCAD에서 명령 중이면 다른 도구처럼 거절한다
        return run_mpl(a)
    t1 = max(5.0, min(80.0, float(budget) - 15.0))
    doc = ctl._require_idle()
    lib = lisplib.ensure_expr()
    _check_handles(ctl, lib, doc, cmd, a, t1)

    if cmd == "MUIN":
        from skills.windows import muin
        return muin.run_mcp(ctl, doc, lib, a, t1)
    if cmd == "CEX":
        from skills.windows import cex
        cfg = merged_cfg("CEX", cex.DEFAULTS, a.get("settings"))
        rows = ctl.lisp(lib + _dump_body(a.get("handles"), cex.type_filter(cfg), cfg["정렬점"]), doc=doc, timeout_s=t1)
        out, marks = cex.build_rows(C.parse_dump(rows), cfg)
        res = {"drawing": doc.Name, "rows": out[:2000], "row_count": len(out), "truncated": len(out) > 2000}
        if cfg["순번"] and cfg["도면순번"] and marks:
            _draw(ctl, doc, lib, cex.marks_lisp(marks, cfg), t1)
            res["marked"] = len(marks)
        if a.get("csv_path"):
            cex.write_text(a["csv_path"], out, ",")
            res["csv_path"] = a["csv_path"]
        return res
    if cmd == "CIM":
        from skills.windows import cim
        cfg = merged_cfg("CIM", cim.DEFAULTS, a.get("settings"))
        _need(a, "rows")
        pts = cim.parse_rows(a["rows"], cfg)
        if not pts:
            raise ValueError("rows에서 좌표를 읽지 못했습니다(settings.열 확인).")
        _draw(ctl, doc, lib, cim.build_lisp(pts, cfg), t1)
        return {"drawing": doc.Name, "points": len(pts)}
    if cmd == "FPEL":
        from skills.windows import fpel
        cfg = merged_cfg("FPEL", fpel.DEFAULTS, a.get("settings"))
        _need(a, "start_point", "start_el", "rows")
        items = fpel.items_from_rows(a["rows"], cfg)
        _draw(ctl, doc, lib, fpel.build_lisp(items, cfg, a["start_point"], float(a["start_el"])), t1)
        return {"drawing": doc.Name, "marked": len(items)}
    if cmd == "CCON":
        from skills.windows import ccon
        cfg = merged_cfg("CCON", ccon.DEFAULTS, a.get("settings"))
        if a.get("handles"):
            sel = '(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))' % " ".join(
                lq(h) for h in a["handles"])
        else:
            ty = "3DFACE" if cfg["방식"] != "점에서 삼각망" else terrain.types_for(cfg)
            sel = '(setq _ss (ssget "_X" (list (cons 0 %s) (cons 410 "Model"))))' % lq(ty)
        rows = ctl.lisp(lib + sel + ccon.dump_lisp(cfg), doc=doc, timeout_s=t1)
        parts, info = ccon.build(*ccon.surface(rows, cfg), cfg)
        with ctl._undo_group(doc):
            for c in ccon.chunks(parts):
                ctl.lisp(lib + c, doc=doc, timeout_s=t1)
        return dict(info, drawing=doc.Name)
    if cmd in ("GRP", "CFM"):
        from skills.common import profile as G
        mod = importlib.import_module("skills.windows.%s" % cmd.lower())
        cfg = merged_cfg(cmd, mod.DEFAULTS, a.get("settings"))
        _need(a, "handle")
        body = '(setq _al (handent %s) _skip (list _al)) %s' % (lq(a["handle"]), G.ALIGN_LISP)
        if a.get("section_handles"):
            body += ('(setq _sl (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _sl)))'
                     ' (setq _skip (append _skip (bc:ss-list _sl))) %s'
                     % (" ".join(lq(h) for h in a["section_handles"]), mod.LINES_LISP))
        if a.get("terrain_handles"):
            body += ('(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                     % " ".join(lq(h) for h in a["terrain_handles"]))
        else:
            body += '(setq _ss (ssget "_X" (list (cons 0 %s) (cons 410 "Model"))))' % lq(G.TERRAIN_TYPES)
        rows = ctl.lisp(lib + body + G.TERRAIN_LISP, doc=doc, timeout_s=t1)
        if cmd == "GRP":
            _el, prof, table, ms, _st = mod.compute(rows, rows, cfg)
            res = {"drawing": doc.Name, "rows": [["측점", "누가거리", "지반고"]] + table, "vertices": len(prof),
                   "length": round(G.total_len(_el), 4)}
            if a.get("insert_point"):
                _draw(ctl, doc, lib, mod.build_lisp(prof, table, ms, a["insert_point"], cfg), t1)
                res["drawn"] = True
            return res
        elems = G.parse_align(rows)
        if cfg["역방향"]:
            elems = G.reverse_elems(elems)
        drawn = [((float(c[1]), float(c[2])), (float(c[3]), float(c[4])))
                 for c in (r.split("\t") for r in rows) if c[0] == "X"]
        secs = mod.compute(elems, G.parse_edges(rows, cfg["Z0제외"]),
                           mod.section_lines(elems, cfg, drawn, a.get("stations")), cfg, G.parse_faces(rows, cfg["Z0제외"]))
        res = {"drawing": doc.Name, "sections": secs}
        if a.get("base_point") and secs:
            _draw(ctl, doc, lib, mod.build_lisp(secs, a["base_point"], cfg), t1)
            res["drawn"] = len(secs)
        return res
    if cmd == "CTS":
        from skills.windows import cts
        cfg = merged_cfg("CTS", cts.DEFAULTS, a.get("settings"))
        _need(a, "handles")

        def write(code):
            with ctl._undo_group(doc):
                return ctl.lisp(lib + code, doc=doc, timeout_s=t1)
        if cfg["방식"] == cts.MODES[1]:
            src = a["handles"]
        else:
            src = ctl.lisp(lib + '(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                           % " ".join(lq(h) for h in a["handles"]) + cts.INFO_LISP, doc=doc, timeout_s=t1)
        return dict(cts.run_core(None, write, src, cfg), drawing=doc.Name)
    if cmd == "RET":
        from skills.windows import ret
        cfg = merged_cfg("RET", ret.DEFAULTS, a.get("settings"))
        _need(a, "handles")
        rows = ctl.lisp(lib + '(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                        % " ".join(lq(h) for h in a["handles"]) + ret.DUMP_LISP, doc=doc, timeout_s=t1)
        details, bad = ret.recognize(*ret.parse_dump(rows), cfg)
        tables = ret.compute(details, cfg) if details else []
        code = ret.bad_lisp(bad) if a.get("mark_bad", True) else ""
        if a.get("insert_point") and tables:
            code += ret.tables_lisp(tables, a["insert_point"], cfg)
        if code:
            _draw(ctl, doc, lib, code, t1)
        return {"drawing": doc.Name, "details": len(details), "duplicates": ret.duplicates(details),
                "unrecognized": bad, "tables": [{"grade": t["grade"], "rows": t["rows"], "weight": t["weight"],
                                                 "weight_add": t["weight_add"]} for t in tables],
                "drawn": bool(a.get("insert_point") and tables)}
    if cmd == "INN":
        from skills.windows import inn
        cfg = merged_cfg("INN", inn.DEFAULTS, a.get("settings"))
        if a.get("handles"):  # 기존 문자 고치기: 고른 순서대로 다음 값
            vals = inn.values(cfg, len(a["handles"]))
            body = "".join('(vla-put-TextString (vlax-ename->vla-object (handent %s)) %s) (entupd (handent %s))'
                           % (lq(h), lq(v), lq(h)) for h, v in zip(a["handles"], vals))
        else:
            _need(a, "source_handle", "base_point", "points")
            vals = inn.values(cfg, len(a["points"]))
            body = inn.copy_lisp("(handent %s)" % lq(a["source_handle"]), vals, lpt(a["base_point"]),
                                 [lpt(p) for p in a["points"]])
        _draw(ctl, doc, lib, body, t1)
        return {"drawing": doc.Name, "values": vals}
    if cmd == "QCAR":
        from skills.common import profile as G
        from skills.windows import qcar
        cfg = merged_cfg("QCAR", qcar.DEFAULTS, a.get("settings"))
        _need(a, "boundary_handle")
        body = ('(setq _bd (handent %s) _skip (list _bd)) (write-line (strcat "BD" _d (cdr (assoc 5 (entget _bd)))) _fp)'
                % lq(a["boundary_handle"]))
        if a.get("alignment_handle"):
            body += '(setq _al (handent %s) _skip (cons _al _skip)) %s' % (lq(a["alignment_handle"]), G.ALIGN_LISP)
        if a.get("handles"):
            body += ('(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                     % " ".join(lq(h) for h in a["handles"]))
        else:
            body += '(setq _ss (ssget "_X" (list (cons 0 "LWPOLYLINE,TEXT,MTEXT") (cons 410 "Model"))))'
        rows = ctl.lisp(lib + body + '(write-line "ENDAL" _fp)' + qcar.DUMP_LISP, doc=doc, timeout_s=t1)
        res = qcar.run_core(lambda code: ctl.lisp(lib + code, doc=doc, timeout_s=t1),
                            lambda code: _draw(ctl, doc, lib, code, t1), rows, cfg, a.get("draw", True))
        return dict(res, drawing=doc.Name)
    if cmd == "CMOB":
        from skills.windows import cmob
        cfg = merged_cfg("CMOB", cmob.DEFAULTS, a.get("settings"))
        rows = ctl.lisp(lib + _dump_body(a.get("handles"), terrain.types_for(cfg)), doc=doc, timeout_s=t1)
        code, info = cmob.build(C.parse_dump(rows), cfg)
        _draw(ctl, doc, lib, code, t1)
        return dict(info, drawing=doc.Name)
    if cmd == "CALC":
        from skills.windows import calc
        return calc.run_mcp(ctl, doc, lib, a, t1, merged_cfg, lq, lambda code: _draw(ctl, doc, lib, code, t1))
    if cmd == "TTE":
        from skills.windows import tte
        cfg = merged_cfg("TTE", tte.DEFAULTS, a.get("settings"))
        gs = a.get("groups") or ([a["handles"]] if a.get("handles") else [None])
        groups = []
        for g in gs:
            if g:
                sel = ('(setq _ss (ssadd)) (foreach _h (list %s) (if (handent _h) (ssadd (handent _h) _ss)))'
                       % " ".join(lq(h) for h in g))
            else:
                sel = '(setq _ss (ssget "_X" (list (cons 0 %s) (cons 410 "Model"))))' % lq(tte.types_for(cfg))
            groups.append(tte.sort_items(tte.parse(ctl.lisp(lib + sel + tte.dump_lisp(cfg), doc=doc, timeout_s=t1)),
                                         cfg["정렬"]))
        code = tte.after_lisp([it["handle"] for g in groups for it in g], cfg)
        if code:
            _draw(ctl, doc, lib, code, t1)
        rows = tte.grid(groups, cfg)
        return {"drawing": doc.Name, "rows": rows[:2000], "row_count": len(rows), "truncated": len(rows) > 2000,
                "texts": sum(len(g) for g in groups)}
    if cmd == "TTP":
        from skills.windows import ttp
        cfg = merged_cfg("TTP", ttp.DEFAULTS, a.get("settings"))
        rows = ctl.lisp(lib + _dump_body(a.get("handles"), ttp.types_for(cfg), cfg["문자기준"] == "정렬점"),
                        doc=doc, timeout_s=t1)
        code, made = ttp.build(C.parse_dump(rows), cfg)
        if code:
            _draw(ctl, doc, lib, code, t1)
        return dict(made, drawing=doc.Name)
    if cmd == "DTIN":
        from skills.windows import dtin
        cfg = merged_cfg("DTIN", dtin.DEFAULTS, a.get("settings"))
        types = ",".join(t for k, t in (("대상점", "POINT"), ("대상블록", "INSERT"), ("대상선", "LINE,LWPOLYLINE,POLYLINE"),
                                         ("대상문자", "TEXT,MTEXT")) if cfg[k])
        rows = ctl.lisp(lib + _dump_body(a.get("handles"), types), doc=doc, timeout_s=t1)
        P, tris = dtin.triangulate(dtin.points_from_dump(C.parse_dump(rows), cfg))
        tris = dtin.filter_long(P, tris, cfg["최대변"])
        with ctl._undo_group(doc):
            for i in range(0, len(tris), 1500):
                ctl.lisp(lib + dtin.faces_lisp(P, tris, cfg["레이어"], cfg["색"], i, 1500), doc=doc, timeout_s=t1)
        return {"drawing": doc.Name, "points": len(P), "faces": len(tris), "layer": cfg["레이어"]}
    if cmd == "DRRE":
        from skills.windows import drre
        cfg = merged_cfg(cmd, drre.DEFAULTS, a.get("settings"))
        if a.get("mode", "draw") == "template":
            _need(a, "handle")
            rows = ctl.lisp(lib + drre.SEG_BODY.replace('(bc:pick-align "호안 선형(LWPOLYLINE) 선택")',
                                                        '(list (handent %s) %s)' % (lq(a["handle"]), "T" if a.get("reverse") else "nil")),
                            doc=doc, timeout_s=t1)
            A_ = [x.split(chr(9)) for x in rows if x.startswith("A" + chr(9))]
            segs = [((float(c[1]), float(c[2])), (float(c[3]), float(c[4])), float(c[5]))
                    for c in (x.split(chr(9)) for x in rows) if c[0] == "G"]
            return {"drawing": doc.Name, "rows": drre.template_rows(float(A_[0][2]), A_[0][1] == "1", segs, cfg)}
        _need(a, "rows", "origin")
        res = drre.compute(a["rows"], cfg)
        body = drre.draw_lisp(res, cfg, a["origin"])
        if body:
            _draw(ctl, doc, lib, body, t1)
        return {"drawing": doc.Name, "segments": res["segs"], "total": res["total"]}
    if cmd == "RCSE":
        from skills.common import xsec as XS
        from skills.windows import rcse
        cfg = merged_cfg(cmd, rcse.DEFAULTS, a.get("settings"))
        _need(a, "handle")
        spec = a.get("spec") or XS.load_spec()
        if not spec:
            raise ValueError("견본 단면(spec)이 없습니다.")
        secs = XS.find(spec, C.parse_dump(ctl.lisp(lib + XS.dump_body(spec), doc=doc, timeout_s=t1)),
                       cfg["측점구분"], float(cfg["측점간격"]))
        L = float(ctl.lisp(lib + '(write-line (bc:rtos (bc:curve-len (handent %s)) 2 10) _fp)' % lq(a["handle"]), doc=doc, timeout_s=t1)[0])
        items = rcse.plan_items(secs, L, cfg)
        rows = ctl.lisp(lib + rcse.sample_body(a["handle"], bool(a.get("reverse")), [d for _s, d in items]), doc=doc, timeout_s=t1)
        sm = {round(float(c[1]), 6): (float(c[2]), float(c[3]), float(c[4])) for c in (r.split("\t") for r in rows) if c[0] == "S"}
        body, n = rcse.build_lisp(items, sm, cfg)
        if body:
            _draw(ctl, doc, lib, body, t1)
        return {"drawing": doc.Name, "sections_found": len(secs), "marked": n}
    if cmd == "CSAR":
        from skills.windows import csar
        cfg = merged_cfg(cmd, csar.DEFAULTS, a.get("settings"))
        _need(a, "pick")

        def group(bodies):
            with ctl._undo_group(doc):
                for b in bodies:
                    ctl.lisp(lib + b, doc=doc, timeout_s=t1)
        nf, ns = csar.run_plan(lambda b: ctl.lisp(lib + b, doc=doc, timeout_s=t1), group, a["pick"], cfg)
        return {"drawing": doc.Name, "frames": nf, "sections": ns}
    if cmd in ("DCEM", "HWLM", "DDGP"):
        from skills.common import xsec as XS
        from skills.windows import dcem, hwlm, ddgp
        mod = {"DCEM": dcem, "HWLM": hwlm, "DDGP": ddgp}[cmd]
        cfg = merged_cfg(cmd, mod.DEFAULTS, a.get("settings"))
        spec = a.get("spec")
        if a.get("sample_handles"):
            # 견본 단면을 핸들 4개로 등록(지반선·중심선·측점 문자·지반고 문자) — 창에서 찍은 것과 같은 견본으로 저장
            # 개수·자리별 종류는 _check_handles에서 이미 확인했다
            spec = XS.spec_from_rows(ctl.lisp(lib + XS.sample_body_from_handles(a["sample_handles"]), doc=doc,
                                              timeout_s=t1))
            if not spec or not spec["center_len"] > 0:
                raise ValueError("견본 핸들로 견본을 만들지 못했습니다(핸들 순서 확인 — 둘째는 세로 중심선이어야 함)")
        spec = spec or XS.load_spec()
        if not spec:
            raise ValueError("견본 단면(spec)이 없습니다. sample_handles [지반선, 중심선, 측점 문자, 지반고 문자]를 주거나 "
                             "창에서 '견본 단면 등록'을 하세요.")
        rows = ctl.lisp(lib + XS.dump_body(spec), doc=doc, timeout_s=t1)
        secs = XS.find(spec, C.parse_dump(rows), cfg.get("측점구분", "Station"), float(cfg.get("측점간격", 20.0)))
        ok = [s for s in secs if XS.usable(s)]
        if a.get("sample_handles") and not a.get("dry_run") and secs:
            # 새 견본은 실제로 그릴 때, 단면을 하나 이상 찾았을 때만 저장한다(미리보기가 창에서 등록한 견본을 덮지 않게)
            XS.save_spec(spec)
        if a.get("dry_run"):
            # 그리지 않고 인식 결과만 — 측점·단면별 축척·같은 측점 중복을 먼저 확인한다
            rep = XS.section_report(secs)
            return {"drawing": doc.Name, "dry_run": True, "spec": spec, "sections_found": len(secs),
                    "sections_usable": len(ok), "duplicates": [r["station"] for r in rep if r["duplicate"]][:50],
                    "sections": rep[:300], "truncated": len(rep) > 300}
        if cmd == "DCEM":
            body, n, miss = dcem.build_lisp(ok, cfg), len(ok), []
        elif cmd == "HWLM":
            _need(a, "rows")
            body, n, miss = hwlm.build_lisp(secs, hwlm.rows_to_data(a["rows"], cfg), cfg)
        else:
            _need(a, "rows")
            body, n, miss, bad = ddgp.build_lisp(secs, ddgp.parse_table(a["rows"], cfg), cfg)
            miss = miss + ["%s(%s)" % b for b in bad]
        if body:
            _draw(ctl, doc, lib, body, t1)
        return {"drawing": doc.Name, "sections_found": len(secs), "sections_usable": len(ok), "marked": n,
                "not_in_excel": miss[:50],
                "sections": [{"station": s["station"], "dist": s["dist"], "el_g": s["el_g"], "usable": XS.usable(s)}
                             for s in secs][:200]}
    if cmd in ("DSTA", "DIBC"):
        from skills.windows import dsta, dibc
        mod = dsta if cmd == "DSTA" else dibc
        cfg = merged_cfg(cmd, mod.DEFAULTS, a.get("settings"))
        _need(a, "handle")
        rev = bool(a.get("reverse"))
        L = float(ctl.lisp(lib + '(write-line (bc:rtos (bc:curve-len (handent %s)) 2 10) _fp)' % lq(a["handle"]), doc=doc, timeout_s=t1)[0])
        if cmd == "DSTA":
            if a.get("stations"):
                k, d0 = dsta.upm(cfg), dsta.start_dist(cfg)
                ds = [C.station_to_dist(v, cfg["측점구분"], float(cfg["간격"])) for v in a["stations"]]
                items = [((d - d0) * k, d, "cross") for d in ds if d is not None and -1e-6 <= (d - d0) * k <= L + 1e-6]
                dec = int(cfg["교차소수"])
            else:
                items, dec = dsta.plan(L, cfg), None
            sm = dsta.parse_samples(ctl.lisp(lib + dsta.sample_body(a["handle"], rev, [i[0] for i in items]), doc=doc, timeout_s=t1))
            samples = [(dd, d, kind) + sm[round(dd, 6)] for dd, d, kind in items]
            _draw(ctl, doc, lib, dsta.draw_lisp(samples, cfg, dec), t1)
            return {"drawing": doc.Name, "marked": len(samples),
                    "stations": [dsta.label(d, dict(cfg, 머리말=""), dec) for _dd, d, _k, _x, _y, _a in samples][:500]}
        _need(a, "others")
        cfg2 = dict(cfg, km만=False, 플러스0생략=False)
        items = dsta.plan(L, cfg2)
        rows = ctl.lisp(lib + dibc.hit_body(a["handle"], rev, [i[0] for i in items], a["others"]), doc=doc, timeout_s=t1)
        return {"drawing": doc.Name, "table": dibc.table(rows, items, len(a["others"]), cfg)}
    if cmd == "HWLI":
        from skills.windows import dsta, hwli
        cfg = merged_cfg(cmd, hwli.DEFAULTS, a.get("settings"))
        _need(a, "base_handle", "detail_handle", "rows")
        tbl = hwli.base_table(a["rows"], cfg)
        k = dsta.upm(cfg)
        b0 = C.station_to_dist(cfg["기본시작"], cfg["기본측점구분"], float(cfg["기본간격"])) or 0.0
        rb = "T" if a.get("base_reverse") else "nil"
        rs = "T" if a.get("detail_reverse") else "nil"
        Ls = float(ctl.lisp(lib + '(write-line (bc:rtos (bc:curve-len (handent %s)) 2 10) _fp)' % lq(a["detail_handle"]), doc=doc, timeout_s=t1)[0])
        items = dsta.plan(Ls, dict(cfg, km만=False, 플러스0생략=False))
        q = ('(setq _bl (handent %s) _sl (handent %s)) (foreach _dd (list %s) (setq _p (bc:curve-pt _sl _dd %s))'
             ' (write-line (strcat "M\t" (bc:rtos _dd 2 10) "\t" (bc:rtos (bc:curve-d _bl _p %s) 2 10)) _fp))'
             % (lq(a["base_handle"]), lq(a["detail_handle"]), " ".join(lnum(i[0]) for i in items), rs, rb))
        res = ctl.lisp(lib + q, doc=doc, timeout_s=t1)
        m = {round(float(r.split("\t")[1]), 6): float(r.split("\t")[2]) for r in res if r.startswith("M\t")}
        pairs = [(d, b0 + m[round(dd, 6)] / k) for dd, d, _kind in items if round(dd, 6) in m]
        return {"drawing": doc.Name, "table": hwli.interpolate(tbl, pairs, cfg)}

    body = body_for(cmd, a)
    with ctl._undo_group(doc):
        rows = ctl.lisp(lib + body, doc=doc, timeout_s=t1)
    err = [r.split("\t", 1)[1] for r in rows if r.startswith("ERR\t")]
    if err:
        raise ValueError("%s: %s" % (cmd, err[0]))
    res = [r.split("\t", 1)[1] for r in rows if r.startswith("R\t")]
    if cmd in ("FE", "FW") and a.get("handle") and not res:
        raise ValueError("%s: 핸들 %s에서 정점을 읽지 못했습니다(LINE·LWPOLYLINE·POLYLINE만)." % (cmd, a["handle"]))
    if cmd in NIL_MEANS_FAIL and res and all(x == "nil" for x in res):
        # 원인은 AutoCAD 명령줄에만 찍힌다 — AI가 볼 수 있게 흔한 원인을 붙여 오류로 알린다
        raise ValueError("%s가 아무것도 하지 못했습니다(결과 nil). 흔한 원인: %s" % (cmd, NIL_MEANS_FAIL[cmd]))
    return {"drawing": doc.Name, "command": cmd, "results": res}


def run_mpl(a: dict) -> dict:
    """다중 플롯 엔진을 창 없이. 같은 프로세스에서 AutoCAD에 따로 붙는다."""
    from skills.multi_plot import multi_plot as M
    b = M.AutoCADPlotBridge(autocad_only=True)
    frames, msg = b.scan_frames_in_active_doc(mode=a.get("mode", "AUTO"))
    if not frames:
        raise LookupError("도곽을 찾지 못했습니다: %s" % msg)
    frames = M.sort_frames(frames, a.get("order", "Z_TOP_DOWN"))
    out = a.get("output_dir") or os.path.join(os.path.expanduser("~"), "Desktop", "CAD_Plot_Output")
    cp = a.get("custom_paper")
    if cp is not None and not (isinstance(cp, (list, tuple)) and len(cp) == 2):
        raise ValueError("custom_paper는 [가로mm, 세로mm]이어야 합니다")
    ok, pdfs, msg2 = b.execute_batch_plot(
        frames, a.get("plotter", "DWG To PDF.pc3"), a.get("paper", "A3 (297 x 420 mm)"), a.get("ctb", "monochrome.ctb"),
        a.get("orientation", "AUTO"), bool(a.get("upside_down", False)), bool(a.get("fit", True)),
        float(a.get("scale_denom", 1000.0)), bool(a.get("center", True)), out, True,
        use_custom_paper=bool(cp), custom_paper_w=float(cp[0]) if cp else 210.0, custom_paper_h=float(cp[1]) if cp else 297.0)
    res = {"ok": ok, "message": msg2, "frames": len(frames), "pdfs": pdfs}
    if ok and a.get("merge") and len(pdfs) > 1:
        try:
            from pypdf import PdfWriter
        except ImportError:
            res["merge_skipped"] = "pypdf가 없어 병합하지 않았습니다(pip install pypdf)."
            return res
        # 시각을 붙인다 — 같은 이름의 지난 통합본이 PDF 보기 창에 열려 있어도 덮어쓰다 실패하지 않게(창 쪽과 같은 규칙)
        merged = os.path.join(out, "%s_통합출력_%d매_%s.pdf" % (
            os.path.splitext(os.path.basename(pdfs[0]))[0].rsplit("_", 1)[0], len(pdfs), time.strftime("%H%M%S")))
        try:
            writer = PdfWriter()
            for p in pdfs:
                writer.append(p)
            with open(merged, "wb") as f:
                writer.write(f)
            writer.close()
            res["merged"] = merged
        except Exception as e:  # noqa: BLE001 — 낱장 PDF는 이미 나왔으니 목록은 그대로 돌려준다
            res["merge_error"] = "%s: %s" % (type(e).__name__, e)
    elif ok and a.get("merge"):
        res["merge_skipped"] = "PDF가 1장이라 합치지 않았습니다."
    return res


def parse_args(args_json: str) -> dict:
    if not args_json:
        return {}
    try:
        v = json.loads(args_json)
    except json.JSONDecodeError as e:
        raise ValueError("args는 JSON 객체 문자열이어야 합니다: %s" % e)
    if not isinstance(v, dict):
        raise ValueError("args는 JSON 객체여야 합니다.")
    return v
