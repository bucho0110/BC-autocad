# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""AutoCAD용 MCP 서버(한글판). AutoCAD 2023에서 시험.

만든 사람: BUCHO. 라이선스는 패키지의 LICENSE(BUCHO 무료 공개 라이선스).
속 구현은 AutoCAD 실측(README 9장) 기준이다.
"""

import asyncio
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional, Union, List

sys.dont_write_bytecode = True  # 워크스페이스(드라이브 동기화) 폴더에 __pycache__를 만들지 않는다

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.exceptions import ToolError

if __package__:
    from .cad_controller import AcadControl, CadBusy, _CONNECTION_LOST
    from . import validators as V
    from .lisp_runner import LispCancelled, LispError, post_escape, is_dialog, focus_window
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cad_controller import AcadControl, CadBusy, _CONNECTION_LOST
    import validators as V
    from lisp_runner import LispCancelled, LispError, post_escape, is_dialog, focus_window

if sys.platform == "win32" and os.environ.get("PYTHONIOENCODING") is None:
    for s in (sys.stdin, sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _log_handlers():
    """stderr + 회전 로그 파일(%LOCALAPPDATA%/cad-mcp-kr/cad_mcp.log). stdout은 MCP 통신용이라 쓰지 않는다."""
    handlers = [logging.StreamHandler(sys.stderr)]
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "cad-mcp-kr", "cad_mcp.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handlers.append(RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    return handlers


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    handlers=_log_handlers())
logger = logging.getLogger("cad_mcp")

INSTRUCTIONS = """AutoCAD 제어 MCP(한글판). AutoCAD의 '활성 도면'에 작업한다(AutoCAD를 자동 실행하지 않음).

- 좌표는 도면 단위, 각도는 도(degree), 색은 ACI(0~256) 또는 true_color "R,G,B".
- 작도·편집 도구는 한 호출을 UNDO 한 묶음으로 남긴다. 반환의 drawing은 실제로 작업한 도면 이름이다.
- 사용자가 AutoCAD에서 명령 중이면 MCP는 건드리지 않고 거절한다. 그때는 사용자에게 알리고 기다린다.
- 조회는 get_entities·ssget_query(fields="handles"로 가볍게)·find_text·entget_by_handles. 응답이 크면
  truncated=true와 next_offset(next_index)이 오니 이어 받는다. 영역 조회는 화면 밖도 잡는다.
  정확한 좌표(폴리선 꼭짓점·bulge·호·스플라인·문자 정렬점, 모두 WCS)는 get_geometry로 여러 개를 한 번에.
  외부 참조는 get_xrefs, 배치 탭·뷰포트(축척·모형 범위·뷰포트 동결 레이어)는 get_layouts.
  문자끼리 겹친 곳 검수는 find_text_overlaps(표로만 알림, 도면은 안 바꿈).
- run_lisp: 결과는 (write-line "..." _fp)로 쓴다. _fp·_d(탭)는 예약. (command ...)·입력 대기 함수(getpoint 등)·(load ...)는
  쓰지 말 것. 길이 제한 없음(파일로 넘김), 한글 가능.
- "결과를 확인할 수 없다"·"취소했다"는 오류가 오면 같은 작업을 다시 보내지 말고 먼저 도면을 확인한다.
- 화면 확인은 capture_view(도면 영역만 PNG로 저장, 포커스를 뺏지 않음).
- "백그라운드로", "화면 건드리지 말고 파일로" 같은 요청이나 큰 그림·새 도면 만들기는 build_drawing_background
  (화면 없는 AutoCAD로 새 DWG를 만든다. 사용자의 AutoCAD 화면은 건드리지 않는다).
- 스킬 명령 91개(EL·지형·종단·횡단·좌표·선형·측점·제방·사면·하천 횡단·수량·표·정리·수정·레이어·도면 불러오기·계산기·다중 플롯, 예: FE·CCON·GRP·DRP·QCAR·RET·XY·DSTA·HWLM·LOL·CALC): skill_list로 목록,
  사람에게는 skill_open(창)이 기본, 값이 정해진 일은 skill_run. AutoCAD에서는 BCFE처럼 BC를 붙인 이름(BCHELP에서 체크한 명령만 FE 같은 짧은 이름도).
  · skill_run 전에 skill_list(command=명령)로 settings 키 이름을 확인한다(명령마다 이름·의미가 다르다).
  · skill_run은 엑셀 없이 JSON으로 한다(rows로 넣고 table·rows로 받는다). 설명의 '엑셀'은 창에서 쓸 때 이야기다.
  · 좌표 스킬(XY·CEX·CIM·ZBC·WCD)은 settings.좌표가 기본 '토목'(X=북, Y=동)이라 CAD의 [x, y]와 순서가 반대다.
    CAD의 [x, y] 순서로 주고받으려면 settings {"좌표": "수학"}.
  · '높이'(문자 크기)는 명령마다 기준이 다르다(축척 1000 기준값 또는 도면 단위 — skill_list(command)의 label에 적혀 있다).
    처음엔 기본값을 쓰고 capture_view로 확인한다.
  · 경사는 '1:1.5'·'2%' 같은 글자로 주는 것이 안전하다(숫자 1.5는 스킬에 따라 1:1.5 또는 기울기 1.5로 읽힌다).
- 영역 (0,0,0,0): get_entities의 숫자 영역 0,0,0,0은 '영역 없음(전체)', ssget_query의 글자 area "0,0,0,0"은 원점 한 점.
- LISP로 그린 뒤 줌·캡처를 하면 그 줌도 UNDO에 남는다 — undo 결과의 view_changed를 보고 한 번 더 부를지 정한다.
- 핸들은 도면마다 따로다. 도면을 여럿 열어 두었으면 activate_document로 대상 도면을 먼저 정한다.
"""

mcp = FastMCP(name="AutoCAD MCP (BC)", instructions=INSTRUCTIONS)
ctl = AcadControl()


def _ok(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))


async def _run(fn, *args, timeout: float = 90.0, **kwargs) -> str:
    """COM 스레드에서 실행하고 압축 JSON으로. 오류는 ToolError(isError=True)로 올린다.
    timeout은 안쪽 LISP 제한시간(기본 45초)보다 길어야 ESC 복구가 먼저 돈다."""
    try:
        try:
            return _ok(await ctl.executor.call(fn, *args, timeout=timeout, **kwargs))
        except Exception as e:  # noqa: BLE001
            # AutoCAD를 껐다 켜면 첫 호출은 죽은 연결로 실패한다(연결 정보는 그때 지워진다). 죽은 연결로 보낸 호출은
            # AutoCAD에 닿지 않았으므로 한 번만 다시 보낸다.
            if getattr(e, "hresult", None) not in _CONNECTION_LOST:
                raise
            logger.info("AutoCAD 연결이 끊겨 다시 붙어 한 번 더 보냅니다: %s", fn.__name__)
            return _ok(await ctl.executor.call(fn, *args, timeout=timeout, **kwargs))
    except ToolError:
        raise
    except (CadBusy, LispCancelled, LispError, ValueError, LookupError, FileNotFoundError) as e:
        raise ToolError(str(e))
    except Exception as e:  # noqa: BLE001 — 모델이 원인을 볼 수 있게 종류와 문구를 그대로
        logger.exception("도구 실행 오류")
        raise ToolError("%s: %s" % (type(e).__name__, e))


def _style(layer="", color=-1, true_color="", linetype="", lineweight=-1) -> dict:
    return {"layer": layer, "color": color, "true_color": true_color, "linetype": linetype,
            "lineweight": lineweight}


# ---------------------------------------------------------------- 연결·정보

@mcp.tool(structured_output=False)
async def ping(ctx: Context) -> str:
    """AutoCAD 연결 확인. 'pong'과 활성 도면 이름."""
    return await _run(ctl.ping, timeout=15)


@mcp.tool(structured_output=False)
async def get_cad_info(ctx: Context) -> str:
    """AutoCAD 프로그램과 활성 도면 정보(이름·경로·버전)."""
    return await _run(ctl.get_cad_info, timeout=15)


@mcp.tool(structured_output=False)
async def get_icad_info(ctx: Context) -> str:
    """get_cad_info와 같다(옛 이름)."""
    return await _run(ctl.get_cad_info, timeout=15)


@mcp.tool(structured_output=False)
async def health_check(ctx: Context) -> str:
    """상태 진단: 연결, 응답 시간(ms), 활성 도면, 명령 중 여부(cmdactive), 유휴(quiescent), 대화창 여부,
    COM 작업 스레드가 앞 작업에 묶여 있는지(com_busy). 다른 도구가 막힐 때 먼저 부른다."""
    busy = ctl.executor.busy_info()
    if busy and busy["seconds"] > ctl.executor.BUSY_FAST_FAIL:
        fw = focus_window(ctl.main_hwnd())
        if busy["seconds"] < busy["limit"] and not is_dialog(fw):
            hint = "앞 작업이 실행 중입니다(제한 %.0f초 안). 끝난 뒤 다시 부르세요 — 끊지 마세요." % busy["limit"]
        else:
            hint = "앞 작업이 제한시간을 넘겼거나 대화창이 떠 있습니다. 화면을 확인하거나 cancel_command."
        return _ok({"com_busy": busy, "dialog_open": is_dialog(fw),
                    "focus_root": {"class": fw["root_class"], "title": fw["root_title"]}, "hint": hint})
    try:
        res = json.loads(await _run(ctl.health_check, timeout=20))
    except ToolError as e:
        # 앞 작업에 막혀 진단도 못 돌았다 — COM 없이 볼 수 있는 것만이라도 돌려준다.
        fw = focus_window(ctl.main_hwnd())
        return _ok({"responsive": False, "error": str(e), "com_busy": ctl.executor.busy_info(),
                    "dialog_open": is_dialog(fw), "focus_root": {"class": fw["root_class"], "title": fw["root_title"]}})
    res["com_busy"] = busy
    return _ok(res)


# ---------------------------------------------------------------- 도면

@mcp.tool(structured_output=False)
async def list_documents(ctx: Context) -> str:
    """열려 있는 도면 목록 [{index, name, full_name, active}]."""
    return await _run(ctl.list_documents)


@mcp.tool(structured_output=False)
async def activate_document(ctx: Context, name: str) -> str:
    """도면 이름(일부 포함) 또는 경로로 활성 도면을 바꾼다. 예: '평면도'"""
    return await _run(ctl.activate_document, name)


@mcp.tool(structured_output=False)
async def open_drawing(ctx: Context, path: str, read_only: bool = False) -> str:
    """도면 파일(.dwg/.dxf)을 연다. 이미 열려 있으면 그 도면을 활성으로 바꾼다."""
    return await _run(ctl.open_drawing, path, read_only, timeout=120)


@mcp.tool(structured_output=False)
async def save_drawing(ctx: Context, path: str = "") -> str:
    """활성 도면 저장. path를 주면 그 이름으로 저장(.dwg/.dxf), 비우면 제자리 저장
    (저장된 적 없는 새 도면은 path 필수)."""
    return await _run(ctl.save_drawing, path, timeout=120)


@mcp.tool(structured_output=False)
async def close_drawing(ctx: Context, save: bool = True) -> str:
    """활성 도면을 닫는다. save=True면 저장 후 닫고, False면 변경을 버리고 닫는다(묻는 창 없음)."""
    return await _run(ctl.close_drawing, save, timeout=120)


@mcp.tool(structured_output=False)
async def new_drawing(ctx: Context) -> str:
    """새 도면을 만들고 활성으로 한다."""
    return await _run(ctl.new_drawing, timeout=60)


@mcp.tool(structured_output=False)
async def get_drawing_info(ctx: Context) -> str:
    """활성 도면 정보(이름·경로·저장 여부·읽기 전용·범위·한계·모형 개체 수·현재 레이어·단위)."""
    return await _run(ctl.get_drawing_info)


# ---------------------------------------------------------------- 레이어

@mcp.tool(structured_output=False)
async def get_layers(ctx: Context) -> str:
    """모든 레이어 [{name, on, frozen, locked, color, true_color?, linetype, lineweight, current}]."""
    return await _run(ctl.get_layers)


@mcp.tool(structured_output=False)
async def set_layer(ctx: Context, name: str, color: int = -1, on: Optional[bool] = None,
                    locked: Optional[bool] = None, linetype: str = "", true_color: str = "",
                    lineweight: int = -1) -> str:
    """레이어를 만들거나 속성을 바꾼다(없으면 생성, 현재 레이어는 안 바꿈). 준 값만 반영한다.
    color: ACI 1~255. true_color: "R,G,B"(color보다 우선). linetype: 없으면 표준 .lin에서 불러옴.
    lineweight: 1/100mm(예 25=0.25mm), -3=기본."""
    return await _run(ctl.set_layer, name, color, on, locked, linetype, true_color, lineweight)


@mcp.tool(structured_output=False)
async def set_active_layer(ctx: Context, name: str) -> str:
    """현재 레이어를 바꾼다(레이어가 있어야 함)."""
    return await _run(ctl.set_active_layer, name)


# ---------------------------------------------------------------- 조회

@mcp.tool(structured_output=False)
async def get_entities(ctx: Context, layer: str = "", entity_type: str = "", limit: int = 100, offset: int = 0,
                       bbox_x1: float = 0, bbox_y1: float = 0, bbox_x2: float = 0, bbox_y2: float = 0) -> str:
    """모형 공간 개체 조회(LISP ssget, 큰 도면도 빠름).
    entity_type: DXF명(LINE/TEXT/MTEXT/LWPOLYLINE/INSERT…) 또는 ActiveX명, 쉼표로 여러 개.
    layer: 정확히 일치(와일드카드 문자 자동 이스케이프). bbox_*: 영역(좌하·우상), 모두 0이면 안 씀 —
    개체 외곽이 영역과 겹치면 포함(화면 밖·꺼진 레이어도 잡음, 비스듬한 개체는 넉넉히 잡힐 수 있음).
    반환 {count, returned, truncated, entities:[{index, handle, type, layer, color, visible, bbox_min, bbox_max,
    insertion_point, true_color?, text?}], next_offset(잘렸을 때)}. 좌표는 소수 8자리."""
    bbox = V.bbox_args(bbox_x1, bbox_y1, bbox_x2, bbox_y2)
    return await _run(ctl.get_entities, layer, entity_type, limit, offset, bbox, timeout=150)


@mcp.tool(structured_output=False)
async def get_entity(ctx: Context, handle: str) -> str:
    """핸들 한 개의 상세(COM): 종류별 좌표(폴리선 꼭짓점 전부)·반지름·문자·블록 이름·색(true_color)·선종류·선굵기·외곽."""
    return await _run(ctl.get_entity, handle)


@mcp.tool(structured_output=False)
async def count_entities(ctx: Context, layer: str = "", entity_type: str = "") -> str:
    """개체 수 {total(모형 전체), matched(조건 일치)}."""
    return await _run(ctl.count_entities, layer, entity_type)


@mcp.tool(structured_output=False)
async def ssget_query(ctx: Context, entity_type: str = "", layer: str = "", text_like: str = "", color: int = -1,
                      area: str = "", limit: int = 2000, offset: int = 0, fields: str = "full") -> str:
    """범용 조회. text_like: 문자 와일드카드(예 "*교량*", "No.*"). color: ACI. area: "x1,y1,x2,y2"(화면 밖 포함).
    fields="handles"면 {index, handle, type, layer}만 — 핸들만 필요한 '골라서 고치기'에 빠르고 작다.
    반환 모양은 get_entities와 같다. 반환 handle을 entget_by_handles·modify_entity·delete_entities 등에 넘긴다."""
    area_v = None
    if area:
        parts = [V.num(x, "area") for x in area.split(",")]
        if len(parts) != 4:
            raise ToolError('area는 "x1,y1,x2,y2" 형식이어야 합니다')
        # 글자로 직접 준 영역은 "0,0,0,0"도 원점 한 점 영역이다(get_entities의 숫자 기본값 0 = 영역 없음과 다르다)
        x1, y1, x2, y2 = parts
        area_v = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    return await _run(ctl.ssget_query, entity_type, layer, text_like, color, area_v, limit, offset, fields,
                      timeout=150)


@mcp.tool(structured_output=False)
async def entget_by_handles(ctx: Context, handles: Union[str, List[str]]) -> str:
    """핸들 여러 개 한 번에 상세 조회(get_entities와 같은 필드, index = handles 안의 위치).
    handles: JSON 배열 ["5A2","5A3"]. 없는 핸들은 빠지고 missing에 수. 잘리면 next_index — handles[next_index:]로 다시."""
    try:
        h = V.parse_handles(handles)
    except ValueError as e:
        raise ToolError(str(e))
    return await _run(ctl.entget_by_handles, h, timeout=150)


@mcp.tool(structured_output=False)
async def find_text(ctx: Context, keyword: str, zoom: bool = False, margin: float = 200.0,
                    limit: int = 2000, offset: int = 0) -> str:
    """TEXT·MTEXT에서 keyword가 글자 그대로 들어간 것 찾기(대소문자 무시, @·,·[ 같은 글자도 그대로). 와일드카드는 ssget_query(text_like). zoom=True면 이 페이지 첫 결과로 줌.
    반환 {found, returned, truncated, results:[{x, y, handle, layer, text}], next_offset}."""
    if zoom and not margin > 0:
        raise ToolError("zoom=True면 margin은 0보다 커야 합니다")
    res = json.loads(await _run(ctl.find_text, keyword, limit, offset, timeout=150))
    if zoom and res.get("results"):
        f = res["results"][0]
        res["zoom"] = json.loads(await _run(ctl.zoom_window, f["x"] - margin, f["y"] - margin,
                                            f["x"] + margin, f["y"] + margin))
    return _ok(res)


@mcp.tool(structured_output=False)
async def get_geometry(ctx: Context, handles: Union[str, List[str]], vertex_start: int = 0,
                       max_vertices: int = 2000) -> str:
    """핸들 여러 개의 정밀 기하를 한 번에(읽기 전용). 좌표는 모두 WCS [x, y, z](뒤집힌 개체의 OCS도 바꿔 줌), 각도는 도.
    LINE start/end_point · LWPOLYLINE/POLYLINE vertices [[x,y,z,bulge]](bulge=호 사잇각/4의 tan, +는 반시계)·closed ·
    ARC center·radius·start/end_angle(반시계 기준)·arc_start/end_point · CIRCLE · ELLIPSE · SPLINE degree·control_points·
    knots·weights·fit_points · TEXT/MTEXT insertion/alignment_point·height·rotation·style·text · INSERT block_name·
    insertion_point·x/y/z_scale·rotation · HATCH area · DIMENSION measurement. 곡선은 length.
    normal은 법선이 +Z가 아닐 때만. 긴 선은 vertex_count·vertices_truncated·next_vertex_start —
    그 핸들 하나만 vertex_start=next_vertex_start로 다시 부른다. max_vertices 1~3000(개체당).
    없는 핸들은 빠지고 missing에 수. 응답이 크면 next_index — handles[next_index:]로 다시."""
    try:
        h = V.parse_handles(handles)
    except ValueError as e:
        raise ToolError(str(e))
    return await _run(ctl.get_geometry, h, vertex_start, max_vertices, timeout=150)


@mcp.tool(structured_output=False)
async def get_xrefs(ctx: Context, max_refs: int = 50) -> str:
    """활성 도면의 외부 참조(XREF) 목록(읽기 전용): name·path·resolved(찾아서 불러옴)·overlay·nested·ref_count와
    참조 개체 refs[{handle, layout, layer, insertion_point, scale, rotation}](XREF당 max_refs개까지)."""
    return await _run(ctl.get_xrefs, max_refs, timeout=150)


@mcp.tool(structured_output=False)
async def get_layouts(ctx: Context, include_viewports: bool = True, max_frozen: int = 50, limit: int = 200,
                      offset: int = 0) -> str:
    """배치(레이아웃) 탭과 뷰포트 조회(읽기 전용). layouts[{name, tab_order, model, plotter, media, plot_style,
    paper_size, paper_units}] + viewports[{handle, layout, center(종이), width, height, scale(종이/모형),
    scale_1_to, model_center·model_window[x1,y1,x2,y2](평면·비틀림 0일 때), locked, on, clip_handle?,
    frozen_layers(뷰포트 동결, max_frozen개까지)·frozen_layer_count}]. 한 번도 열지 않은 배치의 뷰포트는 안 잡힐 수 있다."""
    return await _run(ctl.get_layouts, include_viewports, max_frozen, limit, offset, timeout=150)


@mcp.tool(structured_output=False)
async def find_text_overlaps(ctx: Context, layer: str = "", x1: float = None, y1: float = None, x2: float = None,
                             y2: float = None, min_ratio: float = 0.0, include_hidden: bool = False,
                             limit: int = 200, offset: int = 0) -> str:
    """문자 겹침 검수(읽기 전용 — 도면은 바꾸지 않는다). 모형·배치마다 TEXT·MTEXT 글자 상자(회전 반영)가 서로 겹치는 짝.
    layer: 레이어 필터(와일드카드, 비우면 전부. 이름의 # @ . * ? ~ [ ] 는 앞에 ` — 예 "`#03 계획명칭*"). x1~y2: 이 영역에 걸친 문자만(넷 다 주거나 다 비움).
    min_ratio: 겹친 넓이 / 작은 상자 넓이가 이 값 이상만(0~1). include_hidden: 꺼진·동결 레이어도 볼지.
    블록 안 문자·속성은 보지 않는다. 반환 {checked, count, pairs:[{a, b:{handle, layer, type, text},
    layout, overlap_ratio, overlap_area, at[x,y](겹친 곳 가운데), same_text}](겹침 큰 순), next_offset}."""
    win = [x1, y1, x2, y2]
    if any(v is None for v in win) and not all(v is None for v in win):
        raise ToolError("영역은 x1·y1·x2·y2 넷 다 주거나 다 비웁니다")
    return await _run(ctl.find_text_overlaps, layer, None if win[0] is None else win, min_ratio, include_hidden,
                      limit, offset, timeout=200)


# ---------------------------------------------------------------- 작도

@mcp.tool(structured_output=False)
async def create_line(ctx: Context, start_x: float, start_y: float, end_x: float, end_y: float,
                      layer: str = "", color: int = -1, true_color: str = "", linetype: str = "",
                      lineweight: int = -1) -> str:
    """선 그리기(COM, 객체 스냅 영향 없음). 공통: layer(없으면 생성, 현재 레이어 안 바꿈), color(ACI, -1=현재값),
    true_color("R,G,B"), linetype(없으면 불러옴), lineweight(1/100mm, -1=그대로)."""
    return await _run(ctl.create_line, [start_x, start_y], [end_x, end_y],
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_polyline(ctx: Context, points: Union[str, List[List[float]]], closed: bool = False,
                          layer: str = "", color: int = -1, true_color: str = "", linetype: str = "",
                          lineweight: int = -1) -> str:
    """경량 폴리선(LWPOLYLINE). points: [[x1,y1],[x2,y2],...] (JSON 문자열 또는 배열)."""
    return await _run(ctl.create_polyline, points, closed, **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_rectangle(ctx: Context, x1: float, y1: float, x2: float, y2: float,
                           layer: str = "", color: int = -1, true_color: str = "", linetype: str = "",
                           lineweight: int = -1) -> str:
    """사각형(닫힌 LWPOLYLINE, 꼭짓점 4개). 두 대각 점."""
    return await _run(ctl.create_rectangle, x1, y1, x2, y2, **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_circle(ctx: Context, center_x: float, center_y: float, radius: float,
                        layer: str = "", color: int = -1, true_color: str = "", linetype: str = "",
                        lineweight: int = -1) -> str:
    """원."""
    return await _run(ctl.create_circle, [center_x, center_y], radius,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_arc(ctx: Context, center_x: float, center_y: float, radius: float, start_angle: float,
                     end_angle: float, layer: str = "", color: int = -1, true_color: str = "", linetype: str = "",
                     lineweight: int = -1) -> str:
    """호. 각도는 도, 시작각에서 반시계로 끝각까지."""
    return await _run(ctl.create_arc, [center_x, center_y], radius, start_angle, end_angle,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_ellipse(ctx: Context, center_x: float, center_y: float, major_axis: float, minor_axis: float,
                         rotation: float = 0.0, layer: str = "", color: int = -1, true_color: str = "",
                         linetype: str = "", lineweight: int = -1) -> str:
    """타원. major_axis·minor_axis는 반지름 길이, rotation은 장축 방향(도)."""
    return await _run(ctl.create_ellipse, [center_x, center_y], major_axis, minor_axis, rotation,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_text(ctx: Context, text: str, x: float, y: float, height: float = 2.5, rotation: float = 0.0,
                      layer: str = "", color: int = -1, true_color: str = "", style: str = "",
                      linetype: str = "", lineweight: int = -1) -> str:
    """한 줄 문자(TEXT). 삽입점 x,y, 높이, 회전(도). 한글·±°² 값은 그대로 들어간다.
    style: 문자 스타일 이름(비우면 현재 스타일). 한글이 화면에 ?로 보이면 get_text_styles에서
    korean_capable=true인 스타일을 골라 준다(새 도면 Standard=txt.shx는 한글 글꼴이 없다)."""
    return await _run(ctl.create_text, text, x, y, height, rotation, style,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_mtext(ctx: Context, text: str, x: float, y: float, height: float = 2.5, width: float = 0.0,
                       layer: str = "", color: int = -1, true_color: str = "", style: str = "",
                       linetype: str = "", lineweight: int = -1) -> str:
    """여러 줄 문자(MTEXT). width=0이면 줄바꿈 없음. 줄 나눔은 \\P. style은 create_text와 같다."""
    return await _run(ctl.create_mtext, text, x, y, height, width, style,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def get_text_styles(ctx: Context) -> str:
    """문자 스타일 목록 [{name, font_file, bigfont_file, typeface?, height, width, current, korean_capable}].
    korean_capable: 큰 글꼴(bigfont)이나 트루타입 글꼴이 있어 한글이 화면에 보이는 스타일."""
    return await _run(ctl.get_text_styles)


@mcp.tool(structured_output=False)
async def set_text_style(ctx: Context, name: str, typeface: str = "", font_file: str = "",
                         bigfont_file: str = "") -> str:
    """문자 스타일을 만들거나 글꼴을 바꾼다. typeface(트루타입, 예 "맑은 고딕") 또는
    font_file(.shx)+bigfont_file(한글 큰 글꼴 .shx) 중 하나. 견본 도면의 스타일을 따를 때는 get_text_styles로 먼저 확인."""
    return await _run(ctl.set_text_style, name, typeface, font_file, bigfont_file)


@mcp.tool(structured_output=False)
async def create_hatch(ctx: Context, points: Union[str, List[List[float]]], pattern: str = "SOLID",
                       scale: float = 1.0, layer: str = "", color: int = -1, true_color: str = "",
                       linetype: str = "", lineweight: int = -1) -> str:
    """해치. points: 경계 꼭짓점 3개 이상(닫힌 경계 폴리선도 함께 만들어 boundary_handle로 준다)."""
    return await _run(ctl.create_hatch, points, pattern, scale,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def create_dimension(ctx: Context, start_x: float, start_y: float, end_x: float, end_y: float,
                           text_x: Optional[float] = None, text_y: Optional[float] = None,
                           text_height: float = 0.0, layer: str = "", color: int = -1, true_color: str = "",
                           linetype: str = "", lineweight: int = -1) -> str:
    """정렬 치수. text_x/y를 안 주면 선분 옆에 자동 배치. text_height 0이면 치수 스타일 그대로."""
    tp = [text_x, text_y] if text_x is not None and text_y is not None else None
    return await _run(ctl.create_dimension, [start_x, start_y], [end_x, end_y], tp, text_height,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def draw_lines_atomic(ctx: Context, base_handle: str, segments: Union[str, List[List[float]]],
                            timeout_s: float = 12.0) -> str:
    """기준 개체와 같은 레이어에 LINE 여러 개를 한 번에(색·선종류·선굵기 ByLayer). segments: [[x1,y1,x2,y2],...].
    좌표(0.5mm)·레이어를 검증하고 하나라도 틀리면 이번 선만 모두 지운다."""
    segs = json.loads(segments) if isinstance(segments, str) else segments
    t = max(1.0, min(float(timeout_s), 60.0))
    return await _run(ctl.draw_lines_atomic, base_handle, segs, t, timeout=t + 30)


# ---------------------------------------------------------------- 블록

@mcp.tool(structured_output=False)
async def get_blocks(ctx: Context) -> str:
    """블록 정의 목록(익명·배치·외부참조 제외) [{name, count, origin}]."""
    return await _run(ctl.get_blocks)


@mcp.tool(structured_output=False)
async def create_block(ctx: Context, name: str, base_x: float = 0.0, base_y: float = 0.0) -> str:
    """빈 블록 정의를 만든다(같은 이름이 있으면 그대로 둠)."""
    return await _run(ctl.create_block, name, base_x, base_y)


@mcp.tool(structured_output=False)
async def insert_block(ctx: Context, name: str, x: float, y: float, x_scale: float = 1.0, y_scale: float = 1.0,
                       z_scale: float = 1.0, rotation: float = 0.0, layer: str = "", color: int = -1,
                       true_color: str = "", linetype: str = "", lineweight: int = -1) -> str:
    """블록 참조 삽입. rotation은 도. name에 .dwg 경로를 주면 그 파일을 블록으로 불러 넣는다."""
    return await _run(ctl.insert_block, name, x, y, x_scale, y_scale, z_scale, rotation,
                      **_style(layer, color, true_color, linetype, lineweight))


@mcp.tool(structured_output=False)
async def get_block_attributes(ctx: Context, handle: str) -> str:
    """블록 참조의 속성 [{tag, value, handle}]."""
    return await _run(ctl.get_block_attributes, handle)


@mcp.tool(structured_output=False)
async def set_block_attribute(ctx: Context, handle: str, tag: str, value: str) -> str:
    """블록 참조의 속성값 변경(태그는 대소문자 무시). 없는 태그면 있는 태그 목록과 함께 오류."""
    return await _run(ctl.set_block_attribute, handle, tag, value)


# ---------------------------------------------------------------- 편집

@mcp.tool(structured_output=False)
async def modify_entity(ctx: Context, handle: str, layer: str = "", color: int = -1, linetype: str = "",
                        visible: Optional[bool] = None, rotation: Optional[float] = None, text: str = "",
                        height: Optional[float] = None, true_color: str = "", lineweight: int = -1) -> str:
    """개체 속성 변경(준 값만). rotation(도)·text·height는 문자·블록 참조용."""
    return await _run(ctl.modify_entity, handle, layer, color, linetype, visible, rotation, text, height,
                      true_color, lineweight)


@mcp.tool(structured_output=False)
async def delete_entity(ctx: Context, handle: str) -> str:
    """개체 하나 삭제."""
    return await _run(ctl.delete_entity, handle)


@mcp.tool(structured_output=False)
async def move_entity(ctx: Context, handle: str, dx: float = 0, dy: float = 0, dz: float = 0) -> str:
    """개체 이동(변위 dx, dy, dz)."""
    return await _run(ctl.move_entity, handle, dx, dy, dz)


@mcp.tool(structured_output=False)
async def copy_entity(ctx: Context, handle: str, dx: float = 0, dy: float = 0, dz: float = 0) -> str:
    """개체 복사 후 변위만큼 이동. 반환 handle = 사본."""
    return await _run(ctl.copy_entity, handle, dx, dy, dz)


@mcp.tool(structured_output=False)
async def rotate_entity(ctx: Context, handle: str, base_x: float, base_y: float, angle: float) -> str:
    """기준점을 중심으로 회전(도, 반시계 +)."""
    return await _run(ctl.rotate_entity, handle, base_x, base_y, angle)


@mcp.tool(structured_output=False)
async def scale_entity(ctx: Context, handle: str, base_x: float, base_y: float, factor: float) -> str:
    """기준점 기준 축척 변경."""
    return await _run(ctl.scale_entity, handle, base_x, base_y, factor)


@mcp.tool(structured_output=False)
async def mirror_entity(ctx: Context, handle: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """두 점을 지나는 축으로 대칭 사본을 만든다(원본 유지). 반환 new_handle."""
    return await _run(ctl.mirror_entity, handle, x1, y1, x2, y2)


@mcp.tool(structured_output=False)
async def offset_entity(ctx: Context, handle: str, distance: float) -> str:
    """간격 띄우기(부호로 방향). 반환 new_handles."""
    return await _run(ctl.offset_entity, handle, distance)


@mcp.tool(structured_output=False)
async def array_linear(ctx: Context, handle: str, count: int, dx: float, dy: float, dz: float = 0.0) -> str:
    """직선 배열: 원본 포함 count개, 한 칸 변위 dx, dy."""
    return await _run(ctl.array_linear, handle, count, dx, dy, dz, timeout=300)


@mcp.tool(structured_output=False)
async def array_polar(ctx: Context, handle: str, count: int, center_x: float, center_y: float,
                      total_angle: float = 360.0) -> str:
    """원형 배열: 원본 포함 count개를 중심점 기준 total_angle(도) 안에 고르게."""
    return await _run(ctl.array_polar, handle, count, center_x, center_y, total_angle, timeout=300)


@mcp.tool(structured_output=False)
async def delete_entities(ctx: Context, handles: Union[str, List[str]]) -> str:
    """여러 개체 일괄 삭제(LISP 1회 왕복, UNDO 한 묶음). handles: JSON 배열. 개체별 실패는 errors에."""
    try:
        h = V.parse_handles(handles)
    except ValueError as e:
        raise ToolError(str(e))
    return await _run(ctl.delete_entities, h, timeout=330)


@mcp.tool(structured_output=False)
async def move_entities(ctx: Context, handles: Union[str, List[str]], dx: float = 0, dy: float = 0,
                        dz: float = 0) -> str:
    """여러 개체 일괄 이동(LISP 1회 왕복, UNDO 한 묶음)."""
    try:
        h = V.parse_handles(handles)
    except ValueError as e:
        raise ToolError(str(e))
    return await _run(ctl.move_entities, h, dx, dy, dz, timeout=330)


@mcp.tool(structured_output=False)
async def copy_entities(ctx: Context, handles: Union[str, List[str]], dx: float = 0, dy: float = 0,
                        dz: float = 0) -> str:
    """여러 개체 일괄 복사(LISP 1회 왕복, UNDO 한 묶음). new_entities:[{original, new_handle}]."""
    try:
        h = V.parse_handles(handles)
    except ValueError as e:
        raise ToolError(str(e))
    return await _run(ctl.copy_entities, h, dx, dy, dz, timeout=330)


# ---------------------------------------------------------------- undo / redo

@mcp.tool(structured_output=False)
async def undo(ctx: Context, count: int = 1) -> str:
    """최근 count개(1~32767) 작업을 되돌린다. MCP 작도·편집 도구는 호출 하나가 한 묶음이다.
    반환 before/after(개체 수·마지막 핸들)와 changed. UNDO가 꺼졌거나 One 모드면 보내지 않는다.
    주의: LISP를 쓰는 도구(조회 포함) 뒤의 줌은 UNDO 기록에 들어간다 — 그러면 첫 undo는 줌만 되돌리고
    view_changed=true·경고가 온다. 작도를 되돌리려면 한 번 더 부른다(자동으로 더 되돌리지 않음)."""
    return await _run(ctl.undo, count)


@mcp.tool(structured_output=False)
async def redo(ctx: Context) -> str:
    """바로 앞의 undo를 다시 한다(AutoCAD는 따로 부른 undo 뒤에도 복원됨). changed로 확인."""
    return await _run(ctl.redo)


# ---------------------------------------------------------------- LISP·명령

@mcp.tool(structured_output=False)
async def run_lisp(ctx: Context, code: str, timeout_s: float = 60.0) -> str:
    """AutoLISP를 실행하고 결과 줄을 받는다(UNDO 한 묶음).

    - 결과는 이미 열린 파일 핸들 _fp에 (write-line "..." _fp). _fp·_d(탭 문자)는 예약 — open/close/재정의 금지.
    - 길이 제한 없음(파일로 넘겨 eval), 한글·기호 그대로. 좌표는 (rtos x 2 8) 권장.
    - ssget 레이어 필터의 #·.·- 등은 역따옴표 이스케이프: (cons 8 "0.`#축제"). 영역 선택 "_C"/"_W"는 화면 밖을
      놓치므로 "_X"로 고른 뒤 좌표로 거를 것.
    - 금지: (command ...)(객체 스냅에 끌림 — entmake/entmod/vla-* 사용), getpoint 등 입력 대기, (load ...).
    - 런타임 오류는 "LISP 실행 오류"로 바로 오고(결과를 몇 줄 쓴 뒤라도), 이번 호출이 새로 만든 개체는 지워진다.
    - _ss·_e·_en·_i·_n 등 흔한 내부 이름은 호출 안에서만 산다(끝나면 사라짐). 호출 사이에 값을 남기려면 다른 이름을 쓴다.
    - timeout_s(최대 600)를 넘기면 ESC로 취소하고 "취소" 오류를 낸다 — 다시 보내기 전에 도면을 확인.
    반환 {lines, count, drawing}."""
    return await _run(ctl.run_lisp, code, timeout_s, timeout=min(float(timeout_s), 600.0) + 30)


@mcp.tool(structured_output=False)
async def send_command(ctx: Context, command: str) -> str:
    """AutoLISP 식 하나를 실행(run_lisp와 같은 실행기, 제한 30초). 글자 명령("_.ZOOM E" 등)은 받지 않는다 —
    완료 확인이 안 되고 (command)는 객체 스냅에 끌리므로 전용 도구(zoom_extents 등)나 run_lisp를 쓸 것.
    예: '(entmake (list (cons 0 "LINE") (cons 8 "0") (list 10 0.0 0.0 0.0) (list 11 100.0 100.0 0.0)))'"""
    return await _run(ctl.send_command, command, timeout=60)


@mcp.tool(structured_output=False)
async def cancel_command(ctx: Context) -> str:
    """AutoCAD 명령줄을 ESC 두 번으로 취소(입력 포커스 창에 보냄, 포커스를 뺏지 않음). 대화창이 떠 있으면
    보내지 않는다. MCP 작업이 남긴 입력 대기를 풀 때만 쓴다 — 사용자가 쓰던 명령도 취소되니 주의."""
    info = post_escape(ctl.main_hwnd())  # 아직 COM으로 붙기 전이어도 창 목록에서 찾는다
    await asyncio.sleep(0.5)
    out = {"esc_sent": info["sent"], "focus_root_class": info["root_class"], "focus_root_title": info["root_title"]}
    if is_dialog(info):
        out["warning"] = "대화창이 떠 있어 ESC를 보내지 않았습니다 — AutoCAD 화면에서 직접 확인하세요."
    out["com_busy"] = ctl.executor.busy_info()
    return _ok(out)


# ---------------------------------------------------------------- 뷰·캡처

@mcp.tool(structured_output=False)
async def capture_view(ctx: Context, output_path: str = "") -> str:
    """AutoCAD 도면 영역을 PNG로 저장(PrintWindow — 다른 창에 가려져도 되고 포커스를 뺏지 않음).
    output_path(.png)를 비우면 임시 폴더. 반환 {path, captured, bytes, width, height}. 저장한 PNG를 열어 확인한다."""
    return await _run(ctl.capture_view, output_path)


@mcp.tool(structured_output=False)
async def zoom_extents(ctx: Context) -> str:
    """전체 범위로 줌. 반환 view_center, view_height."""
    return await _run(ctl.zoom_extents)


@mcp.tool(structured_output=False)
async def zoom_window(ctx: Context, x1: float, y1: float, x2: float, y2: float) -> str:
    """지정 영역으로 줌(COM). 반환 {zoom, verified, view_center, view_height} — view_height는 화면 비율 때문에
    요청보다 클 수 있다. 곧바로 capture_view 해도 된다. 줌은 UNDO 기록에 들어갈 수 있다(undo 설명 참고)."""
    return await _run(ctl.zoom_window, x1, y1, x2, y2)


@mcp.tool(structured_output=False)
async def regen(ctx: Context) -> str:
    """도면 재생성(Regen). 주의: Regen 직후 undo는 보이는 변화 없이 Regen만 되돌릴 수 있다."""
    return await _run(ctl.regen)


# ---------------------------------------------------------------- 백그라운드 작도

@mcp.tool(structured_output=False)
async def build_drawing_background(ctx: Context, code: str, output_path: str, base_drawing: str = "",
                                   overwrite: bool = False, use_skills: bool = True, timeout_s: float = 300.0,
                                   preview: bool = True) -> str:
    """백그라운드 작도: 화면 없는 AutoCAD(accoreconsole)로 LISP를 실행해 새 DWG 파일을 만든다.
    켜져 있는 AutoCAD 화면·도면은 건드리지 않는다(AutoCAD가 꺼져 있어도 되고, 사용자가 작업 중이어도 된다).
    사용자가 "백그라운드로", "화면 건드리지 말고 파일로 만들어 줘"라고 하거나, 큰 그림·새 도면을 만들 때 쓴다.
    code: LISP 본문. 결과는 (write-line "..." _fp)로 쓰면 lines로 돌아온다. entmake/vla-* 외에 (command ...)도 쓸 수 있다
    (객체 스냅 꺼짐). use_skills면 토목 명령 함수(bc:*)를 먼저 불러 둔다.
    output_path: 저장할 .dwg 전체 경로(2018 형식). 이미 있으면 overwrite=true일 때만 덮어쓴다.
    base_drawing: 이 도면을 열어 시작(원본은 바꾸지 않고 결과는 output_path에만 저장).
    preview(기본 true): 저장 뒤 모형 공간 전체를 PNG(흰 배경, 1600×1280)로 출력해 preview 경로로 준다 —
    화면 없이 결과를 눈으로 확인할 때 그 PNG를 연다. 출력에 실패하면 preview=null과 preview_note(도면은 저장됨).
    반환 {output, entities, seconds, bytes, lines, console, preview}. 화면 AutoCAD에서 보려면 open_drawing(output_path, read_only=true)."""
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)
    import background
    try:
        return _ok(await asyncio.to_thread(background.build, code, output_path, base_drawing, overwrite, use_skills,
                                           timeout_s, preview))
    except (ValueError, FileNotFoundError, FileExistsError, TimeoutError, RuntimeError) as e:
        raise ToolError(str(e))


# ---------------------------------------------------------------- 스킬(토목·좌표·다중 플롯 명령)

def _skills():
    """skills 패키지(패키지 최상위 폴더 기준). 처음 쓸 때만 불러온다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from skills import mcp_tools
    return mcp_tools


@mcp.tool(structured_output=False)
async def skill_list(ctx: Context, command: str = "") -> str:
    """AutoCAD 스킬 명령 91개 목록(EL·지형·종단·횡단·좌표·선형·측점·사면·하천 횡단·수량·표·정리·수정·레이어·도면 불러오기·계산기·다중 플롯).
    command를 비우면 전체 요약: command, title, group, kind(lisp=AutoCAD에서 바로 찍는 명령 / window=창), desc, run_args.
    command를 주면 그 명령 하나를 자세히: settings(skill_run의 settings에 넣을 수 있는 키·기본값·선택지), settings_file.
    skill_run 전에 그 명령을 command로 한 번 불러 설정 키 이름을 확인한다(명령마다 '간격'·'측점간격'처럼 다르다).
    사람이 쓰는 기본 방식은 AutoCAD에서 명령을 직접 치거나 skill_open으로 창을 띄우는 것이다."""
    rows = _skills().table()
    if command:
        hit = [r for r in rows if r["command"] == command.strip().upper()]
        if not hit:
            raise ToolError("모르는 명령: %s" % command)
        return _ok(hit[0])
    return _ok([{k: v for k, v in r.items() if k not in ("settings", "settings_file")} for r in rows])


@mcp.tool(structured_output=False)
async def skill_open(ctx: Context, command: str) -> str:
    """스킬 창을 띄운다(사람이 쓰는 기본 방식). window 명령은 그 창, lisp 명령은 설정 창.
    COM을 쓰지 않고 별도 프로세스로 띄우므로 바로 돌아온다."""
    try:
        return _ok(_skills().open_window(command))
    except (LookupError, OSError) as e:
        raise ToolError(str(e))


@mcp.tool(structured_output=False)
async def skill_run(ctx: Context, command: str, args: str = "{}", timeout: float = 120.0) -> str:
    """스킬 명령을 창 없이 값만으로 실행한다. args는 JSON 객체 문자열.
    공통: settings {설정키: 값} — 저장된 설정 파일 위에 덮어 쓴다(키는 registry 설정 항목, skill_list 참고).
    명령별 인자는 skill_list의 run_args. 예) FE: {"base_point":[0,0],"base_el":100,"points":[[5,2.5]]}
    한 호출이 UNDO 한 묶음. 반환 모양은 명령마다 다르다: 값 명령(FE·DCP 등)은 results(명령별 (값 핸들목록)),
    표·작도 명령은 table·rows·sections·marked 등 다른 키(results가 없을 수 있음). MPL은 PDF 경로 목록."""
    mt = _skills()
    a = mt.parse_args(args)
    outer = max(30.0, float(timeout))
    if command.upper() == "MPL" and float(timeout) == 120.0:
        outer = 1800.0  # 다중 플롯은 시트마다 최대 90초 — 기본값이면 넉넉히
    # 안쪽 LISP 한 번은 outer−15초로 잡혀 ESC 복구가 바깥 제한보다 먼저 돈다
    return await _run(mt.run, ctl, command, a, outer, timeout=outer)


@mcp.tool(structured_output=False)
async def bug_report(ctx: Context, problem: str = "", command: str = "", error_text: str = "", log_lines: int = 40) -> str:
    """오류 보고서 만들기 — 사용자가 "안 돼", "오류 보고서 만들어 줘"라고 하면 부른다. AutoCAD가 꺼져 있어도 된다.
    problem: 사용자가 말한 증상(무엇을 하려 했고 무엇이 일어났는지, 사용자의 말 그대로).
    command: 문제가 난 BC 명령 이름(예 RET, 없으면 비움) — 그 명령의 저장된 설정과 창 로그를 넣는다.
    error_text: 받은 오류 원문(도구 오류 메시지·AutoCAD 명령줄 문구).
    → text(GitHub Issues에 붙일 마크다운), path(같은 내용 파일). 사용자 폴더·이름·도면 파일 이름은 가린다.
    사용자에게 text를 보여 주고, 회사·과업 정보가 없는지 확인받은 뒤 https://github.com/bucho0110/BC-autocad/issues 에
    올리도록(또는 파일을 전달하도록) 안내한다. 도면 내용은 모으지 않는다."""
    import report
    acad, err = None, ""
    try:
        acad = await asyncio.wait_for(ctl.executor.call(report.acad_env, ctl, timeout=15), 20)
    except Exception as e:  # noqa: BLE001 — AutoCAD가 꺼졌거나 막혀 있어도 보고서는 만든다
        err = "%s: %s" % (type(e).__name__, e)
    text, path = report.build(command, problem, error_text, acad, err, max(5, min(200, int(log_lines))))
    return _ok({"text": text, "path": path,
                "next": "사용자에게 text를 보여 주고 개인·회사 정보가 없는지 확인받은 뒤 GitHub Issues에 올리도록 안내하세요."})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
