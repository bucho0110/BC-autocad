# Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
"""오류 보고서(MCP 도구 bug_report) — 문제가 생겼을 때 AI가 환경·명령·설정·오류 원문·로그 끝부분을 모아
GitHub Issues에 붙일 수 있는 글(마크다운)로 만든다. 같은 글을 %LOCALAPPDATA%/bc-autocad/reports/에 파일로도 남긴다.

개인정보·도면 내용은 넣지 않는다: 사용자 폴더 경로·사용자 이름·컴퓨터 이름은 가리고, 도면 파일 이름은 '<도면>.dwg'로 바꾼다.
도면 내용(문자·좌표)은 모으지 않는다. 보고서를 올리기 전에 사람이 한 번 읽어 보도록 안내한다.
"""

import datetime
import os
import platform
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
MCP_LOG = os.path.join(LOCAL, "cad-mcp-kr", "cad_mcp.log")
DATA = os.path.join(LOCAL, "bc-autocad")
PACKAGES = ("mcp", "pywin32", "Pillow", "pypdf", "fonttools")


def mask(text: str) -> str:
    """사용자 폴더·사용자 이름·컴퓨터 이름·도면 파일 이름을 가린다."""
    s = str(text)
    home = os.path.expanduser("~")
    for p in sorted({home, home.replace("\\", "/"), os.environ.get("USERPROFILE", "")}, key=len, reverse=True):
        if p:
            s = re.sub(re.escape(p), "%USERPROFILE%", s, flags=re.I)
    for name in (os.environ.get("USERNAME"), os.environ.get("COMPUTERNAME")):
        if name and len(name) > 2:
            s = re.sub(re.escape(name), "<이름>", s, flags=re.I)
    # 설치 폴더·파이썬 폴더는 그대로 두고(원인 찾기에 필요), 그 밖의 폴더 경로는 가린다(과업·지구 이름이 들어 있을 수 있다)
    keep = {}
    for i, p in enumerate(sorted({ROOT, sys.prefix, sys.base_prefix}, key=len, reverse=True)):
        for j, v in enumerate((p, p.replace("\\", "/"))):
            tag = "\x00%d_%d\x00" % (i, j)
            keep[tag] = v
            s = re.sub(re.escape(v), lambda _m, t=tag: t, s, flags=re.I)
    s = re.sub(r"[A-Za-z]:[\\/](?:[^\\/\r\n\"'`<>|*?]*[\\/])*", "<경로>\\\\", s)
    for tag, v in keep.items():
        s = s.replace(tag, v)
    # 도면 이름
    s = re.sub(r"[^\\/:*?\"<>|\r\n\t,()\[\]{}']+\.(dwg|dxf|dwt)\b", r"<도면>.\1", s, flags=re.I)
    return s


def _version():
    try:
        sys.path.insert(0, ROOT)
        from skills.common.ui import VERSION
        return VERSION
    except Exception as e:  # noqa: BLE001 — 보고서는 무엇이든 만들어야 한다
        return "알 수 없음(%s)" % type(e).__name__


def _packages():
    from importlib import metadata
    out = []
    for p in PACKAGES:
        try:
            out.append("%s %s" % (p, metadata.version(p)))
        except Exception:  # noqa: BLE001
            out.append("%s 없음" % p)
    return ", ".join(out)


def _admin():
    try:
        import ctypes
        return "예" if ctypes.windll.shell32.IsUserAnAdmin() else "아니요"
    except Exception:  # noqa: BLE001
        return "알 수 없음"


def _tail(path, n, errors_only=False):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    if errors_only:
        keep, inside = [], False
        for ln in lines:
            hit = " ERROR " in ln or "[ERROR]" in ln or ln.startswith("Traceback")
            if hit or (inside and ln.startswith((" ", "\t"))):
                keep.append(ln)
                inside = True
            else:
                inside = False
        lines = keep
    return [ln.rstrip("\n") for ln in lines[-n:]]


def acad_env(ctl):
    """COM 스레드에서: AutoCAD 버전·언어·제품. 도면 이름은 넣지 않는다."""
    app = ctl.connect()
    out = {"version": str(app.Version), "documents": int(app.Documents.Count)}
    try:
        d = app.ActiveDocument
        out["locale"] = str(d.GetVariable("LOCALE"))
        out["product"] = str(d.GetVariable("PRODUCT"))
        out["lispsys"] = str(d.GetVariable("LISPSYS"))
        out["cmdactive"] = int(d.GetVariable("CMDACTIVE"))
        tp = str(d.GetVariable("TRUSTEDPATHS") or "").replace("\\", "/").lower()
        out["trusted"] = (ROOT.replace("\\", "/").lower().rstrip("/") + "/skills/lisp") in tp
    except Exception as e:  # noqa: BLE001 — 열린 도면이 없으면(시작 탭) 버전만
        out["note"] = "열린 도면 없음(%s)" % type(e).__name__
    return out


def build(command="", problem="", error_text="", acad=None, acad_error="", log_lines=40):
    """→ (마크다운 글, 저장한 파일 경로)."""
    from skills.common import settings as S  # noqa: E402 — ROOT를 sys.path에 넣은 뒤
    cmd = (command or "").strip().upper()
    now = datetime.datetime.now()
    lines = ["## 오류 보고 (BC-autocad)", "",
             "### 무엇이 안 되나요", problem.strip() or "(사용자 설명을 적어 주세요: 무엇을 하려 했고, 무엇이 일어났는지)", "",
             "### 환경",
             "- BC 버전: %s" % _version(),
             "- Windows: %s (%s)" % (platform.platform(), platform.machine()),
             "- Python: %s (%s)" % (platform.python_version(), mask(sys.executable)),
             "- 패키지: %s" % _packages(),
             "- 설치 폴더: %s" % mask(ROOT),
             "- MCP 서버 관리자 권한: %s (AutoCAD와 다르면 연결되지 않습니다)" % _admin()]
    if acad:
        lines.append("- AutoCAD: 버전 %s, 제품 %s, 언어 %s, LISPSYS %s, 명령 중 %s, 신뢰 경로 등록 %s, 열린 도면 %s개%s" % (
            acad.get("version"), acad.get("product", "-"), acad.get("locale", "-"), acad.get("lispsys", "-"),
            acad.get("cmdactive", "-"), {True: "예", False: "아니요"}.get(acad.get("trusted"), "-"),
            acad.get("documents"), (" — " + acad["note"]) if acad.get("note") else ""))
    else:
        lines.append("- AutoCAD: 연결 안 됨(%s)" % (mask(acad_error) or "꺼져 있음"))
    if cmd:
        lines += ["", "### 명령: %s" % cmd]
        p = S.path(cmd)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                lines += ["저장된 설정(%s):" % mask(p), "```"] + [mask(x.rstrip()) for x in f if x.strip()] + ["```"]
        else:
            lines.append("저장된 설정 없음(기본값으로 실행)")
    if error_text.strip():
        lines += ["", "### 오류 원문", "```", mask(error_text.strip()), "```"]
    errs = _tail(MCP_LOG, log_lines, errors_only=True)
    if errs:
        lines += ["", "### MCP 로그의 최근 오류 (cad_mcp.log)", "```"] + [mask(x) for x in errs] + ["```"]
    if cmd:
        wl = _tail(os.path.join(DATA, "logs", cmd + ".log"), log_lines)
        if wl:
            lines += ["", "### 창 명령 로그 (%s.log 끝부분)" % cmd, "```"] + [mask(x) for x in wl] + ["```"]
    lines += ["", "---", "올리기 전에 위 내용에 회사·과업·개인 정보가 없는지 확인해 주세요. "
              "가능하면 문제가 나는 도면을 작게 줄인 시험 도면(민감한 내용 없이)도 함께 첨부해 주세요.",
              "만든 시각: %s" % now.strftime("%Y-%m-%d %H:%M")]
    text = "\n".join(lines) + "\n"
    out_dir = os.path.join(DATA, "reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "report_%s%s.md" % (now.strftime("%y%m%d_%H%M%S"), ("_" + cmd) if cmd else ""))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return text, path
