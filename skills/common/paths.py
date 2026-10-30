"""스킬 공통 경로. 어느 PC에 복사해도 돌도록 위치는 모두 이 파일 자신에서 계산한다.

- ROOT: MCP 패키지 최상위(src·skills·install이 있는 폴더)
- DATA: PC별 쓰기 폴더(%LOCALAPPDATA%/bc-autocad). 설정·로그·임시 파일·생성된 AutoCAD 명령 파일을 둔다.
  패키지 폴더(드라이브 동기화 폴더일 수 있다)에는 아무것도 쓰지 않는다.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
SKILLS = os.path.join(ROOT, "skills")
LISP_DIR = os.path.join(SKILLS, "lisp")

DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "bc-autocad")
SETTINGS = os.path.join(DATA, "settings")
LOGS = os.path.join(DATA, "logs")
WORK = os.path.join(DATA, "work")

for _d in (DATA, SETTINGS, LOGS, WORK):
    os.makedirs(_d, exist_ok=True)

if SRC not in sys.path:
    sys.path.insert(0, SRC)


def lisp_path(p: str) -> str:
    """LISP 문자열에 넣을 경로(슬래시)."""
    return p.replace("\\", "/")


def pythonw() -> str:
    """창을 띄울 때 쓸 pythonw.exe. 지금 도는 파이썬 옆의 것을 쓴다(가상환경 그대로)."""
    exe = sys.executable
    d = os.path.dirname(exe)
    cand = os.path.join(d, "pythonw.exe")
    return cand if os.path.exists(cand) else exe
