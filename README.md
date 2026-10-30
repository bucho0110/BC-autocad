# BC-autocad — AutoCAD MCP 서버 (한글판) · BC.0.2.0

**AutoCAD**를 AI 에이전트(Claude Code·안티그래비티·Codex)에서 자연어로 제어할 수 있도록 지원하는 MCP 서버입니다.
AI 연동 없이 AutoCAD에서 직접 실행할 수 있는 **토목 전용 명령 40개**(EL·좌표·측점·사면·하천 횡단·다중 플롯)도 함께 제공합니다.

- 개발자: **BUCHO** · MCP 도구 67개 · 토목 명령 40개 · 모든 설명과 메시지는 한국어로 제공합니다.
- 버전 **BC.0.2.0**: 현재 사용자 테스트 단계의 버전이며, 검증을 마친 후 정식 버전(BC.1.0.0)으로 갱신할 예정입니다. 버전 정보는 AutoCAD `BCHELP` 대화상자 제목 표시줄에서도 확인할 수 있습니다.
- 문의·요청: 저장소 https://github.com/bucho0110/BC-autocad 의 **Issues**에 등록해 주십시오.
- 라이선스: `LICENSE`(BUCHO 무료 공개 라이선스) — 업무 용도를 포함해 누구나 무료로 사용, 수정 및 배포할 수 있습니다. 유료 판매 및 유료 서비스 제공은 금지되며, 변형하거나 배포할 때는 원작자 출처(BUCHO)와 라이선스 전문을 반드시 포함해야 합니다.

**목차** — [1. 설치 전 확인](#1-설치-전-확인-사용자ai-공통) · [2. 설치](#2-설치) · [3. AI 에이전트 연동](#3-ai-에이전트-연동) · [4. 토목 명령 40개](#4-토목-명령-40개) · [5. 문제 해결](#5-문제-해결) · [6. 주요 동작 규칙](#6-주요-동작-규칙-ai고급-사용자) · [7. MCP 도구 67개](#7-mcp-도구-67개) · [8. 파일 구성과 테스트](#8-파일-구성과-테스트-개발자-참고) · [9. 실측 및 검증 기록](#9-실측-및-검증-기록-개발자-참고)

---

## 1. 설치 전 확인 (사용자·AI 공통)

| 항목 | 내용 |
|---|---|
| **Python** | **Python 3.10 이상을 사전에 직접 설치해야 합니다.** 본 패키지는 Python을 배포하지 않습니다. 공식 웹사이트(https://www.python.org/downloads/)에서 내려받아 설치하며, **설치 첫 화면 하단의 "Add python.exe to PATH" 옵션을 반드시 선택**하십시오. (검증 버전: 3.14) |
| **AutoCAD** | AutoCAD 2021 이상을 지원 대상으로 하며, 동작 검증은 AutoCAD 2023에서 했습니다(다른 버전은 아직 검증하지 않았습니다). 2020 이하는 LISP의 UTF-8 지원이 없어 사용할 수 없습니다. **설치와 사용 시 모두 AutoCAD를 먼저 실행하고 도면을 하나 열어 두어야 합니다.** 본 서버는 AutoCAD를 직접 실행하지 않습니다. |
| **AI 에이전트** | 자연어로 AutoCAD를 제어하려면 Claude Code, 안티그래비티, Codex 중 하나가 필요합니다(3장 참조). 토목 명령(`BCFE`·`BCDSTA`·`BCMPL` 등)만 사용할 경우에는 필요하지 않습니다. |
| **의존 패키지** | `requirements.txt`의 패키지(`mcp`, `pywin32`, `Pillow`, `pypdf`)는 설치 스크립트 실행 시 자동으로 설치됩니다. (`pypdf`는 다중 플롯의 PDF 병합 및 용지 변환에 사용되며, 설치되지 않으면 해당 기능만 비활성화됩니다.) |

> **AI 에이전트가 설치를 대행하는 경우**: 시스템에 Python이 설치되어 있지 않다면 임의로 설치(winget 등)하지 말고, 위의 다운로드 경로와 "Add python.exe to PATH" 선택 안내를 사용자에게 전달한 후 작업을 중단합니다.

**Python 설치 확인**: 명령 프롬프트(`cmd`)에서 `python --version`을 실행해 `Python 3.1x.x`와 같이 출력되는지 확인합니다.
버전이 출력되지 않으면 Python 설치 관리자를 다시 실행해 **Modify**를 선택하고, **Add Python to environment variables**를 선택한 뒤 완료합니다.

## 2. 설치

### 2-1. 간편 설치 (권장)

1. 패키지 폴더를 원하는 경로에 둡니다. GitHub에서 내려받을 경우 저장소 화면의 **Code → Download ZIP**으로 내려받아 압축을 해제합니다.
   코드에 고정 경로가 없고 PC별 파일(설정·로그·임시 파일)은 `%LOCALAPPDATA%\bc-autocad\`(일반적으로 `C:\Users\<사용자 이름>\AppData\Local\bc-autocad\`)에 별도로 저장되므로,
   폴더 전체를 복사하거나 이동하여 사용해도 됩니다.
2. **AutoCAD를 실행하고 도면을 하나 열어 둡니다.**
3. 폴더의 **`install.cmd`를 더블클릭**하여 실행합니다. Python이 설치되어 있지 않거나 3.10 미만인 경우, 또는 실행 중인 AutoCAD가 2020 이하 버전인 경우 안내 메시지를 출력하고 중단합니다.
4. 콘솔 창에 진행 내역이 출력되고 `끝.`이 표시되면 설치가 완료된 것입니다. 아무 키나 눌러 창을 닫습니다.
5. **AutoCAD를 완전히 종료한 후 다시 실행합니다.** 토목 명령은 AutoCAD 실행 시 등록됩니다.
6. AutoCAD 명령줄에 `BCHELP`를 입력하여 명령 목록 대화상자가 표시되면 정상입니다.
7. AI 에이전트를 사용하는 경우, 에이전트를 **다시 실행**한 뒤 3장의 방법으로 연동을 확인합니다.

`install.cmd`가 수행하는 작업(`python install\install.py --all`과 동일):
- `%LOCALAPPDATA%\bc-autocad\venv`에 전용 가상환경을 만들고 의존 패키지를 설치합니다.
- AutoCAD 플러그인 번들 폴더를 생성하여, AutoCAD 실행 및 도면 열기 시 `BCFE`·`BCXY`·`BCMPL` 등의 명령이 자동으로 로드되도록 구성합니다.
- AutoCAD의 신뢰할 수 있는 위치(TRUSTEDPATHS)에 패키지 경로를 추가하여, 최초 로드 시 보안 경고 대화상자가 나타나지 않도록 합니다.
  AutoCAD가 실행되어 있지 않거나 열린 도면이 없으면 이 단계는 건너뛰고 안내 메시지를 출력합니다. 이 경우 AutoCAD를 실행한 뒤 `install.cmd`를 다시 실행합니다.
- 이 PC에 설치된 AI 에이전트(Claude Code·안티그래비티·Codex)를 감지하여 모두 등록합니다(3장).
- 변경 대상 설정 파일은 수정 전에 `%LOCALAPPDATA%\bc-autocad\backup\<날짜_시각>\`에 백업합니다.

### 2-2. 명령줄 설치와 옵션 (고급)

명령줄에서 설치하려면 다음을 실행합니다.
```
python install\install.py --all
```
별도로 구성한 Python 가상환경을 사용하려면 해당 Python 경로를 지정합니다.
```
<가상환경>\Scripts\python.exe install\install.py --python <가상환경>\Scripts\python.exe --acad --claude --antigravity --codex
```

| 옵션 | 기능 |
|---|---|
| (옵션 없음) | AutoCAD 플러그인 폴더 `%APPDATA%\Autodesk\ApplicationPlugins\BC_AutoCAD.bundle`을 생성합니다. 이후 AutoCAD 실행 및 도면 열기 시 `BCFE`·`BCXY`·`BCMPL` 등의 명령이 자동 등록됩니다(단축 이름은 4장). 수동 로드용 동일 파일을 `%LOCALAPPDATA%\bc-autocad\bc_autocad.lsp`에도 배치합니다(`APPLOAD`용). |
| `--acad` | AutoCAD 신뢰 경로(TRUSTEDPATHS)에 패키지 로드 경로를 추가합니다. 이전 버전에서 '시작하기 세트'에 등록한 항목이 남아 있으면 제거합니다. |
| `--claude` | Claude Code의 사용자 전역 범위(user scope)에 `bc-autocad`를 등록합니다. `--all` 사용 시 `claude`가 감지된 경우에만 수행합니다. |
| `--antigravity` | 안티그래비티 CLI 설정과, 존재하는 경우 데스크톱 앱 설정에도 `bc-autocad`를 등록합니다(3장 표). `--all` 사용 시 사용자 폴더에 `.gemini`가 있는 경우에만 수행합니다. |
| `--codex` | OpenAI Codex 설정(`~/.codex/config.toml`)에 `bc-autocad`를 등록합니다. 다른 설정은 변경하지 않습니다. `--all` 사용 시 `codex`가 감지된 경우에만 수행합니다. |
| `--venv` | 가상환경을 새로 생성합니다(`--all` 사용 시 `--python`을 지정하지 않으면 자동 수행). |

### 2-3. 삭제

- **토목 명령**: 플러그인 폴더 `%APPDATA%\Autodesk\ApplicationPlugins\BC_AutoCAD.bundle`을 삭제한 후 AutoCAD를 다시 실행합니다.
- **AI 에이전트 등록**: 3장의 에이전트별 등록 해제 방법을 따릅니다.
- **설정·로그·가상환경**: `%LOCALAPPDATA%\bc-autocad` 폴더를 삭제합니다.

> `%APPDATA%`·`%LOCALAPPDATA%` 경로는 **Win + R**(실행 창)이나 탐색기 주소창에 그대로 붙여 넣고 Enter를 누르면 바로 열립니다(숨김 폴더 포함).

## 3. AI 에이전트 연동

본 서버는 **사용자 PC 내부에서만 동작하는 로컬 MCP 서버**입니다. AI 프로그램이 해당 PC에서 서버를 직접 실행해야 하므로,
**PC에 설치된 AI 도구(터미널 CLI, VS Code 확장, 일부 데스크톱 앱)에서만** 사용할 수 있습니다.
웹 브라우저 기반 AI(claude.ai, chatgpt.com, Gemini 웹)는 인터넷 주소로 연결하는 원격 MCP 서버만 연동할 수 있으므로 지원 대상이 아닙니다.
터널링으로 로컬 서버를 외부에 노출하는 방식은 AutoCAD 제어 권한이 외부에 노출되는 보안 위험이 있어 권장하지 않습니다.

`install.cmd`는 이 PC에 **설치된 AI 에이전트를 자동으로 감지하여 모두 등록**합니다. 에이전트를 나중에 설치했다면 `install.cmd`를 다시 실행하거나,
`python install\install.py --claude`와 같이 해당 옵션만 지정합니다(별도 가상환경을 사용하는 경우 `--python <경로>`를 함께 지정).

| AI 에이전트 | 지원 환경 | 등록 위치 | 지원하지 않는 환경 |
|---|---|---|---|
| **Claude Code** (Anthropic) | 터미널(CLI), VS Code 확장 | `claude mcp add bc-autocad -s user …` — 사용자 전역 범위로 등록되어 작업 폴더와 관계없이 인식되며, VS Code 확장에서도 같은 등록을 사용합니다. | claude.ai 웹 |
| **안티그래비티** (Google) | 터미널(CLI `agy`), 데스크톱 앱 Antigravity IDE | CLI: `~/.gemini/config/mcp_config.json`<br>데스크톱 앱: `~/.gemini/antigravity-ide/mcp_config.json`(이전 앱은 `~/.gemini/antigravity/mcp_config.json`)<br>프로그램별로 설정 파일이 다르므로 존재하는 파일 모두에 등록합니다. | Gemini 웹 |
| **Codex** (OpenAI, ChatGPT 계정) | 터미널(CLI), VS Code 확장 | `~/.codex/config.toml`의 `[mcp_servers.bc-autocad]` — CLI와 VS Code 확장이 같은 파일을 사용합니다. 다른 설정은 변경하지 않습니다. | ChatGPT 앱(웹·데스크톱) |

`~`는 사용자 홈 폴더(`C:\Users\<사용자 이름>`)를 뜻합니다. Claude **데스크톱 앱**도 로컬 MCP를 지원하지만, 현재 설치 스크립트는 자동으로 등록하지 않습니다.

### 3-1. Claude Code
1. Claude Code를 설치합니다(Anthropic 안내 참조). 터미널에서 `claude`가 실행되면 됩니다.
2. `install.cmd`를 실행합니다. 출력에 `Claude Code 등록:`이 표시되면 등록된 것입니다.
3. Claude Code를 **다시 실행합니다**. 이미 실행 중이던 세션에는 반영되지 않습니다.
4. 확인: 터미널에서 `claude mcp list`를 실행해 `bc-autocad … Connected`를 확인하거나, Claude Code 세션에서 `/mcp` 목록에 `bc-autocad`가 있는지 확인합니다.
   VS Code 확장은 VS Code를 다시 실행하면 동일하게 적용됩니다.
- 등록 해제: `claude mcp remove bc-autocad -s user`

### 3-2. 안티그래비티
1. 안티그래비티(CLI `agy` 또는 데스크톱 앱)를 설치하고 한 번 실행하여 로그인합니다. 사용자 폴더에 `.gemini` 폴더가 생성됩니다.
2. `install.cmd`를 실행합니다. 출력에 `안티그래비티 등록: …mcp_config.json`이 설정 파일 수만큼 표시됩니다.
3. 실행 중인 안티그래비티를 모두 종료한 뒤 다시 실행합니다.
4. 확인: CLI는 터미널에서 `agy mcp list`를 실행해 `bc-autocad  stdio  enabled`를 확인합니다.
   데스크톱 앱은 채팅창에 "bc-autocad로 ping 해 줘"라고 입력하여 `pong` 응답을 확인합니다.
- 등록 해제: CLI는 `agy mcp remove bc-autocad`를 실행합니다. 데스크톱 앱은 위 표의 `mcp_config.json`을 텍스트 편집기로 열어 `"bc-autocad": { … }` 설정 블록을 삭제합니다.

### 3-3. Codex (ChatGPT 계정)
1. Codex(CLI 또는 VS Code 확장)를 설치하고 ChatGPT 계정으로 로그인합니다(OpenAI 안내 참조).
2. `install.cmd`를 실행합니다. `codex` 실행 파일이나 `~/.codex` 폴더가 있으면 등록합니다(`CODEX_HOME`을 사용하는 경우 해당 폴더).
3. Codex를 다시 실행하고 `/mcp`에서 `bc-autocad`를 확인합니다.
- 처리 시간이 긴 도구(다중 플롯)를 위해 `tool_timeout_sec = 1800`(Codex 기본값 60초)을, 최초 실행 여유를 위해 `startup_timeout_sec = 30`을 설정합니다.
- 등록 해제: `~/.codex/config.toml`에서 `[mcp_servers.bc-autocad]`부터 다음 `[`로 시작하는 줄 전까지 삭제합니다.
- **Codex 연동은 아직 실제 환경에서 검증하지 못했습니다.** 개발 환경에 Codex가 없어 설정 파일만 Codex 공식 형식에 맞추어 생성합니다.

### 3-4. 공통 사항
- **연동 확인**: 에이전트에 "bc-autocad로 ping 해 줘"라고 요청합니다. 정상이면 `{"status":"pong","drawing":"열린 도면 이름"}`이 반환됩니다. 실패하면 "health_check 해 줘"로 상태를 점검합니다.
- **요청 예시**: "열린 도면 목록 보여 줘", "현재 도면의 레이어 목록 알려 줘", "토목 명령 목록 보여 줘(skill_list)".
- **AutoCAD 선행 실행**: 서버는 실행 중인 AutoCAD의 **활성 도면**에서 작업합니다.
- **단일 에이전트 사용**: 여러 에이전트에 등록해도 되지만, 동일한 AutoCAD에 동시에 작업을 요청하면 대기하거나 거부될 수 있으므로 한 번에 하나의 에이전트만 사용하십시오.
- **사용자 작업 보호**: 사용자가 AutoCAD에서 명령을 실행 중이면 MCP는 간섭을 막기 위해 요청을 거부합니다. AI에 작업을 지시하기 전에 AutoCAD 명령줄이 대기 상태(`명령:`)인지 확인하십시오(필요 시 Esc 키를 2~3회 입력).
- 패키지 폴더를 다른 경로로 옮기면 등록된 경로가 달라지므로 `install.cmd`를 다시 실행합니다.

## 4. 토목 명령 40개

AutoCAD 명령줄에서 직접 실행하는 토목·좌표·출력 명령입니다. 목록은 AutoCAD에서 `BCHELP`, AI(MCP)에서는 `skill_list`로 확인합니다.

### 4-1. 명령 이름: 기본값은 `BC` 접두어

- 설치 직후에는 다른 유틸리티나 AutoCAD 명령과의 충돌을 막기 위해 모든 명령에 `BC` 접두어가 붙습니다(`BCFE`, `BCDSTA`, `BCMPL`).
  따라서 **패키지 설치만으로는 기존 단축키 환경이 변경되지 않습니다.**
- 아래 표는 편의상 `BC`를 뺀 **단축 이름**으로 표기했습니다. 입력할 때는 `BC`를 붙이거나 단축 이름을 활성화합니다.
- **단축 이름(`FE` 등) 활성화**: AutoCAD 명령줄에 `BCHELP`를 입력해 대화상자를 연 뒤, 해당 명령 앞의 체크 칸(☐/☑)을 클릭하거나 [모두 활성화]를 클릭합니다.
  활성화한 명령은 `FE`와 `BCFE` 모두로 실행할 수 있습니다.
  - 설정은 이 PC의 `%LOCALAPPDATA%\bc-autocad\settings\shortnames.txt`에 저장되며, 새 버전으로 업데이트해도 유지됩니다. 자동으로 활성화되거나 해제되지 않습니다.
  - 활성화하려는 이름을 이 PC에서 이미 사용 중이면(단축키 파일 `acad.pgp`, 같은 이름의 프로그램 명령, 먼저 로드된 LISP) 해당 목록을 표시하고 진행 여부를 확인합니다.
    AutoCAD는 LISP 명령을 같은 이름의 단축키보다 먼저 실행하므로, 활성화하면 기존 단축키 대신 본 패키지의 명령이 실행됩니다.
  - 활성화·해제는 현재 도면에 즉시 적용됩니다. 이미 열려 있는 다른 도면에는 다시 열 때 적용됩니다.
  - 단축 이름으로 실행하면 명령줄에 `[BC] BCFE`와 같이 실행된 명령을 표시합니다.
- **모두 해제(원상 복구)**: AutoCAD 명령줄에 `BCOFF`를 입력합니다. 모든 단축 이름을 해제하고, 기존에 사용하던 같은 이름의 단축키와 LISP를 복원합니다.
- `BC` 이름을 다른 프로그램이 이미 사용 중이면 해당 이름은 생성하지 않습니다.
- AI가 MCP(`skill_run`)로 실행할 때는 명령 이름을 거치지 않고 내부 기능을 직접 호출하므로, 단축 이름의 활성화 여부와 관계없이 항상 본 패키지의 기능으로 동작합니다.

### 4-2. 명령 목록

| 분류 | 명령 | 방식 |
|---|---|---|
| EL | `FE` 상대 EL, `FW` 측구 EL(형식 1~7), `FEL` 원하는 EL 위치, `CEE` EL 표기 형식 복사·증감, `GEL` 두 점 사이 EL·폴리선 정점 Z 보간, `SLEL` 경사로 평면 EL, `IEL` 삼각망 EL | 도면 선택 |
| EL | `FPEL` 종단 다중 EL(Excel), `DTIN` 삼각망 작성 | 대화상자 |
| 좌표 | `XY` 좌표 표기, `ZBC` 경계 좌표표, `WCD` 도곽 경계 좌표 | 도면 선택 |
| 좌표 | `CEX` 좌표 내보내기(Excel·텍스트), `RCE` 순번 좌표 Excel 출력, `CIM` Excel·텍스트 좌표로 작도 | 대화상자 |
| 선형·측점 | `DCP` 두 선(좌안·우안) 사이 중심선, `DCEN` 원·호 중심선·두 선 사이 중심선, `STT` 측점 인출선(한 점·두 점+연장·명칭, 구간 = 평면도 지구명 형식 두 줄 `명칭 L=1,208m` / `(No.18+076 ~ No.19+270)`), `GST` 측점 조회, `CST` 두 측점 문자 사이 연장, `NUST` 측점 문자↔숫자 변환, `MIP` 원곡선 IP(IA·R·TL·CL) | 도면 선택 |
| 선형·측점 | `DSTA` 선형 측점 표기(간격·교차선·Excel 목록), `DIBC` 측점별 이격 거리(하폭) Excel 출력, `HWLI` 기본설계 값→실시설계 측점 보간 | 대화상자 |
| 제방·사면 | `DSLO` 계획 사면 표시(쌓기·깎기, 주·보조), `NSLO` 자연 사면 표시, `DFB` 앞성토 사면(부채꼴), `SLL` 경사선, `SLT` 경사 표시(1:n·%), `CSS` 횡단 사면(지반선까지·소단), `CUT` 층따기 | 도면 선택 |
| 하천 횡단 | `DCEM` EL 폴대, `HWLM` Excel 측점별 H.W.L·S.W.L·여유고 일괄 표기, `DDGP` Excel 측점별 제방 계획선(하상·계획고·하폭·둑마루·앞/뒷비탈·호안 경사·고수부지·제방 횡경사) 일괄 작도, `CSAR` 도곽 내 횡단 배치, `RCSE` 평면 대횡단(지반 EL을 평면 측점선에 표기) | 대화상자 |
| 사면 | `DRRE` 호안 전개도(Excel 양식 → 전개도·수량표, 곡선부 연장 보정) | 대화상자 |
| 수정 | `XYB` X·Y 축척 개별 변환 | 도면 선택 |
| 유틸리티 | `MPL`(=`MPLOT`) 다중 플롯 | 대화상자 |

### 4-3. 사용 방법

- **도면 선택 방식**
  - 명령을 입력하면 즉시 도면에서 점·문자 등을 선택하는 단계로 진입하며, Enter 또는 Esc를 누를 때까지 반복합니다.
  - 명령 실행 중 `S`를 입력하면 설정 대화상자가 열립니다. 설정을 저장한 후 **명령을 다시 실행**하면 변경 사항이 적용됩니다.
  - 기준 EL: 도면의 문자를 선택하면 그 안의 마지막 숫자를 인식합니다(`EL=12.5m` → 12.5, `EL.(-)1.50` → −1.5). `E`를 입력하면 기준값을 직접 입력할 수 있습니다.
  - 축척: `1000`은 m 단위 도면(도면 1 = 1m), `1`은 mm 단위 도면입니다. EL 문자 높이 설정은 축척 1000 기준입니다.
- **대화상자 방식**
  - 명령을 입력하면 설정 대화상자가 먼저 열립니다. 도면에서 객체를 선택하는 동안에는 대화상자가 잠시 최소화되었다가 다시 표시됩니다.
  - Excel 연동 명령은 **열려 있는 Excel**의 선택 셀·범위를 읽거나 데이터를 출력합니다. Excel로 출력하는 수치는 지정한 소수 자릿수 그대로 표시됩니다(좌표 기본값: 소수 넷째 자리, 사사오입).
- **측점 표기**: Station 형식은 `1+250.5`(km+m), Number 형식은 간격 20일 때 `No.62+10.5`(번호+나머지)입니다. 측점 명령의 접두어 기본값은 `No.`이며 설정에서 변경할 수 있습니다.
  선형을 선택하면 진행 방향을 확인합니다(작도된 방향과 반대이면 `N`).
- **사면**: 평면 사면 표시는 쌓기의 경우 안쪽 선(둑마루·법견), 깎기의 경우 바깥쪽 선이 상단이므로 사면 표기선(짧은 선)이 해당 측에 작도됩니다.
  횡단 명령(`CSS`·`CUT`·`SLL`·`SLT`)은 H·V 축척을 각각 입력받으며(1000 = 도면 1이 1m), 경사 1:n은 수직 1 : 수평 n입니다. 현재는 기본 형상이며 사용 의견에 따라 보완합니다.
- **하천 횡단**(`DCEM`·`HWLM`·`DDGP`·`RCSE`): 대화상자에서 **견본 단면 등록**(지반선 → 중심선 → 측점 문자 → 지반고 문자 순으로 선택)을 한 번 수행하면,
  같은 레이어·같은 길이의 중심선을 가진 단면을 모두 인식합니다. 단면 위치는 중심선 X, 지반 높이는 지반선 보간, 측점은 누가거리 소수 넷째 자리로 Excel과 대조합니다.
- **설정 파일**: `%LOCALAPPDATA%\bc-autocad\settings\<명령>.txt`(한 줄에 `키=값`). AutoCAD 명령·대화상자·MCP가 같은 파일을 사용합니다.
- **문자 스타일**: 문자는 도면의 현재 문자 스타일과 레이어로 작성합니다(설정에서 레이어 지정 가능). 새 도면에서 한글이 `?`로 표시되면 5장을 참조하십시오.
- 각 명령은 핵심 옵션부터 구현했습니다. 필요한 옵션은 Issues로 요청해 주십시오.

### 4-4. AI(MCP)에서 사용

- 화면 표시가 필요한 작업은 `skill_open(명령)`(대화상자 열기)을 기본으로 사용합니다. 값이 정해진 작업은 `skill_run(명령, args)`로 대화상자 없이 실행합니다.
  예: `skill_run("FE", '{"base_point":[0,0],"base_el":100,"points":[[5,2.5]]}')`
- 인자는 `skill_list`의 `run_args`, 설정 키는 `skill_list(command="DSTA")`처럼 명령을 지정해 받는 `settings`로 확인합니다.
  `settings`로 해당 호출에만 설정 값을 덮어쓸 수 있습니다. 한 번의 호출이 UNDO 한 단계입니다.
- 하천 횡단(`DCEM`·`HWLM`·`DDGP`)은 `sample_handles`(지반선·중심선·측점 문자·지반고 문자 핸들)로 견본을 등록하며,
  `dry_run: true`로 작도 전에 단면 인식 결과(측점, 단면별 세로·가로 축척, 중복 측점)를 먼저 확인할 수 있습니다.
- 반환값이 nil뿐인 경우(DCP·CST·NUST·MIP·IEL) 예상 원인을 포함한 오류 메시지를 반환합니다.

## 5. 문제 해결

| 증상 | 확인 및 조치 |
|---|---|
| `install.cmd` 실행 시 "Python이 설치되어 있지 않습니다" | 1장의 Python 설치와 "Add python.exe to PATH" 선택 여부를 확인합니다. `cmd`에서 `python --version`이 출력되어야 합니다. |
| AutoCAD에서 `BCFE` 등이 "알 수 없는 명령" | ① `install.cmd`가 `끝.`까지 완료되었는지 ② 플러그인 폴더 `%APPDATA%\Autodesk\ApplicationPlugins\BC_AutoCAD.bundle`이 생성되었는지 ③ 설치 후 AutoCAD를 완전히 종료하고 다시 실행했는지 ④ AutoCAD 명령줄에서 `APPAUTOLOAD` 값이 0이 아닌지 확인합니다. 즉시 사용해야 하는 경우 `APPLOAD`로 `%LOCALAPPDATA%\bc-autocad\bc_autocad.lsp`를 직접 로드합니다. |
| `FE`는 "알 수 없는 명령"으로 표시되고 `BCFE`만 실행되는 경우 | 정상입니다. 단축 이름은 `BCHELP` 대화상자에서 활성화해야 합니다(4-1). |
| 단축 이름을 활성화한 뒤 다른 프로그램의 같은 이름 명령이 실행되지 않음 | `BCOFF`로 모두 해제하거나 `BCHELP` 대화상자에서 해당 명령만 해제합니다. 기존 명령이 즉시 복원됩니다. |
| 최초 로드 시 보안 경고 대화상자 표시 | AutoCAD를 실행하고 도면을 연 상태에서 `install.cmd`를 다시 실행합니다(신뢰 경로 등록). |
| 명령줄 안내 문자가 깨지거나 로드 중 멈춤 | AutoCAD 명령줄에 `LISPSYS`를 입력해 값이 `1`인지 확인합니다. `0`(이전 LISP 엔진)이면 UTF-8 한글 `.lsp`를 정상적으로 읽지 못하므로 `1`로 변경한 뒤 AutoCAD를 다시 실행합니다. AI(MCP) 작업은 이 설정과 무관합니다. |
| 명령 실행 중 `S`를 입력해도 설정 대화상자가 열리지 않음 | 로드 파일의 Python 경로가 변경된 경우입니다. `install.cmd`를 다시 실행합니다. |
| 도면의 한글이 `?`로 표시됨 | 데이터는 정상이며 문자 스타일 문제입니다. 새 도면의 `Standard`(txt.shx)에는 한글 글꼴이 지정되어 있지 않습니다. AutoCAD `STYLE` 명령으로 해당 스타일에 한글 글꼴(맑은 고딕 등)을 지정합니다. AI 연동 시에는 6장 2항을 참조하십시오. |
| 에이전트 목록(`/mcp`)에 `bc-autocad`가 없음 | 에이전트를 다시 실행했는지, 등록되었는지(3장 확인 방법) 확인합니다. 에이전트를 나중에 설치했다면 `install.cmd`를 다시 실행합니다. |
| "실행 중인 AutoCAD를 찾지 못했습니다" | AutoCAD를 실행한 후 다시 요청합니다. AutoCAD와 AI 에이전트(터미널)의 **실행 권한이 다르면(한쪽만 관리자 권한)** 프로세스 간 통신이 차단되므로 두 프로그램 모두 일반 권한으로 실행하십시오. |
| "AutoCAD가 명령 실행 중입니다" | AutoCAD 명령줄에서 진행 중인 명령을 끝내거나 Esc를 누른 뒤 다시 요청합니다. |
| "앞선 작업이 …초째 끝나지 않았습니다" | AI에 `health_check`를 요청해 `dialog_open`을 확인합니다. 대화상자가 열려 있으면 화면에서 직접 닫고, 그렇지 않으면 `cancel_command`를 실행합니다. |
| `redo`가 `changed=false` | 6장 3번 — `undo`와 `redo` 사이에 다른 도구를 호출하지 않습니다. |
| `undo`가 `changed=false`, `view_changed=true` | 6장 3번 — 화면 확대·축소가 되돌려진 것입니다. `undo`를 한 번 더 실행합니다. |

## 6. 주요 동작 규칙 (AI·고급 사용자)

1. **사용자 작업 중에는 실행하지 않습니다.** AutoCAD가 명령 실행 중(CMDACTIVE≠0)이거나 대기 상태가 아니면 도구 호출을 거부합니다. 사용자에게 명령 종료(Esc)를 요청한 뒤 다시 호출합니다.
2. **한글이 `?`로 표시되는 경우**: 문자 스타일 문제이며 값은 정상입니다. `get_text_styles`에서 `korean_capable=true`인 스타일을 `style`로 지정하거나, `set_text_style(name, typeface="맑은 고딕")` 또는 `font_file`+`bigfont_file`로 스타일을 생성합니다. 견본 도면이 있으면 해당 스타일을 따릅니다.
3. **실행 취소(Undo)·재실행(Redo)**
   - 작도·편집 도구 호출 1회가 UNDO 한 단계입니다. 조회 도구와 읽기 전용 `run_lisp`는 UNDO 기록을 남기지 않습니다.
   - `redo`는 직전 작업이 `undo`인 경우에만 유효합니다. **두 호출 사이에 LISP를 사용하는 도구(조회 포함)를 호출하면 REDO가 동작하지 않습니다**(AutoCAD 동작). 결과의 `changed`로 적용 여부를 확인합니다.
   - **LISP 실행 후의 화면 확대·축소는 UNDO 기록에 포함됩니다.** 이 경우 첫 번째 `undo`는 화면만 되돌리고 `view_changed=true`와 경고를 반환합니다. 작도 내용을 되돌리려면 한 번 더 호출합니다(서버가 자동으로 추가 실행하지 않습니다).
4. **run_lisp 규칙**: 결과는 `(write-line "..." _fp)`로 출력합니다. `_fp`·`_d`(탭)는 예약어입니다. 사용 금지: `(command ...)`(객체 스냅 영향 — `entmake`/`entmod`/`vla-*` 사용), `getpoint` 등 입력 대기 함수, `(load ...)`(보안 경고). 길이 제한이 없으며(파일로 전달) 한글을 사용할 수 있습니다. ssget 레이어 이름의 `#` `.` `-` 등은 역따옴표로 이스케이프하고, 영역 선택은 `"_X"`로 선택한 뒤 좌표로 걸러냅니다(`"_C"`는 화면 밖 객체를 누락).
5. **제한 시간**: LISP가 `timeout_s` 안에 끝나지 않으면 서버가 AutoCAD 입력 포커스 창에 Esc를 보내 취소하고 "취소" 오류를 반환합니다. **대화상자가 열려 있으면 Esc를 보내지 않습니다.** "결과를 확인할 수 없다"·"취소했다" 오류 이후에는 같은 작업을 재전송하지 말고 도면 상태부터 확인합니다.
6. **선행 작업 지연(5초)**: 이전 작업이 AutoCAD 안에서 5초 이상 끝나지 않으면 새 요청은 대기열에 넣지 않고 즉시 실패 처리합니다(모든 도구가 함께 멈추는 것을 방지). `health_check`로 대화상자 여부 등 상태를 확인하고, MCP가 남긴 입력 대기 상태이면 `cancel_command`를 호출합니다.
7. **영역 조회**(`get_entities`의 bbox, `ssget_query`의 area)는 객체의 외곽 범위가 영역과 겹치면 포함합니다. 화면 밖·꺼진 레이어의 객체도 포함하며, 기울어진 객체는 넓게 선택될 수 있습니다.
8. **화면 캡처**(`capture_view`)는 AutoCAD 창을 앞으로 가져오지 않고 도면 영역만 PNG로 저장합니다. AutoCAD가 최소화되어 있으면 실패합니다. 캡처 전에 Regen하지 않습니다(Regen이 UNDO를 무효화함).

## 7. MCP 도구 67개

| 분류 | 도구 |
|---|---|
| 연결·진단 | `ping`, `get_cad_info`(별칭 `get_icad_info`), `health_check` |
| 도면 | `list_documents`, `activate_document`, `open_drawing(path, read_only)`, `save_drawing(path="")`, `close_drawing(save=True)`, `new_drawing`, `get_drawing_info` |
| 레이어·문자 스타일 | `get_layers`, `set_layer`, `set_active_layer`, `get_text_styles`, `set_text_style` |
| 조회 | `get_entities`, `get_entity`, `count_entities`, `ssget_query`, `entget_by_handles`, `find_text` |
| 정밀 조회(읽기 전용) | `get_geometry`(여러 핸들의 꼭짓점·bulge·호·스플라인·문자 정렬점, 모두 WCS), `get_xrefs`(외부 참조·삽입 위치), `get_layouts`(배치 탭·뷰포트 축척·모형 범위·뷰포트 동결 레이어), `find_text_overlaps`(문자 간 겹침을 표로만 보고하며 도면은 변경하지 않음. 같은 위치의 같은 문자 중복도 검출) |
| 작도 | `create_line`, `create_polyline`, `create_rectangle`, `create_circle`, `create_arc`, `create_ellipse`, `create_text`, `create_mtext`, `create_hatch`, `create_dimension`, `draw_lines_atomic` |
| 블록 | `get_blocks`, `create_block`, `insert_block`, `get_block_attributes`, `set_block_attribute` |
| 편집 | `modify_entity`, `delete_entity`, `move_entity`, `copy_entity`, `rotate_entity`, `scale_entity`, `mirror_entity`, `offset_entity`, `array_linear`, `array_polar` |
| 일괄 편집 | `delete_entities`, `move_entities`, `copy_entities` |
| 실행 취소 | `undo(count)`, `redo` |
| LISP·명령 | `run_lisp(code, timeout_s)`, `send_command(LISP 식)`, `cancel_command` |
| 화면·캡처 | `capture_view(output_path)`, `zoom_extents`, `zoom_window`, `regen` |
| 토목 명령 | `skill_list`, `skill_open`, `skill_run`(4-4) |

- 공통 작도 인자: `layer`(없으면 생성하며 현재 레이어는 변경하지 않음), `color`(ACI 0~256), `true_color`("R,G,B"), `linetype`(없으면 표준 .lin에서 로드), `lineweight`(1/100mm).
  반환값에는 `handle`과 실제 작업한 도면 이름 `drawing`이 포함됩니다.
- `run_lisp`에서 `(load)` 등 파일을 로드하는 함수는 차단합니다(AutoCAD 보안 경고로 멈출 수 있음). 코드 본문을 직접 전달합니다.
- 좌표는 소수 8자리입니다. 오류는 MCP 오류(isError)로 반환합니다. `get_icad_info`는 `get_cad_info`의 이전 이름입니다.

## 8. 파일 구성과 테스트 (개발자 참고)

| 파일 | 내용 |
|---|---|
| `src/server.py` | MCP 도구 정의(한국어 설명), 오류를 MCP 오류로 변환 |
| `src/cad_controller.py` | COM 계층: 전용 STA 스레드 1개, 호출별 재시도(ComProxy), UNDO 묶음, 작도·편집·조회·캡처 |
| `src/lisp_runner.py` | LISP 실행기: 한 줄 UTF-8 파일 → 짧은 인라인 식으로 읽어 `eval`, 결과 파일 END 확인, 제한 시간 Esc |
| `src/validators.py` | CAD 전달 전 사전 검증: 괄호, 와일드카드 이스케이프, 객체 유형명, 핸들, 숫자·색·점, 금지 함수 |
| `skills/registry.py` | 토목 명령 목록·설명·설정 항목(단일 원본) |
| `skills/lisp/*.lsp` | 도면 선택 명령과 공통 함수(`bc_core`). `install/build_lisp.py`가 생성하는 파일: 대화상자 명령 등록·BCHELP(`bc_windows`), 기존 동일 이름 명령 보존(`bc_00_guard`), BC 이름·단축 이름·`BCOFF`(`bc_zz_alias`) |
| `skills/windows/*.py`, `skills/multi_plot/` | 대화상자 명령(명령별 1개 파일, MPL은 `multi_plot`) |
| `skills/common/` | 경로·설정 파일·AutoCAD 연결·Excel·좌표·대화상자 공통 모듈 |
| `skills/mcp_tools.py` | MCP `skill_list`·`skill_open`·`skill_run` |
| `skills/launch.py` | 대화상자 실행기(`pythonw launch.py <명령>`) |
| `install/install.py` | 설치·등록(2장). 패키지 폴더 내부에는 기록하지 않습니다 |
| `install/build_lisp.py` | 개발용: 명령 목록(registry) 변경 후 `skills/lisp/`의 `bc_windows`·`bc_00_guard`·`bc_zz_alias`를 다시 생성 |
| `tests/test_tools_live.py` | 실제 AutoCAD에서 전체 도구 테스트(새 도면에서만 수행, 마지막에 임시 폴더에 저장 파일 1개를 남김) |
| `tests/test_skills_live.py`, `test_skills2_live.py`~`test_skills4_live.py` | MCP 서버를 실행해 토목 명령(1단계 EL·좌표·MPL, 2단계 선형·측점, 3단계 제방·사면, 4단계 하천 횡단)을 새 테스트 도면에서 실행·확인 |
| `tests/test_units.py` | AutoCAD 없이 수행하는 계산 테스트(측점·삼각망·DDGP·DRRE·CSAR·좌표 소수) |
| `tests/test_regression_live.py` | 수정한 결함의 재발 확인 1(부호·서식·경사 입력·핸들 검증·XYB 잠긴 레이어 등) |
| `tests/test_fixes_live.py` | 수정한 결함의 재발 확인 2(LISP 끝 주석·빈 핸들 목록·비도형 핸들·문자 검색 특수문자·영역 0,0,0,0·배치 탭 작도 등) |
| `tests/test_alias_live.py` | BC 이름·단축 이름 활성화와 해제·`BCOFF` 확인 |
| `tests/test_geom_live.py` | 정밀 조회(`get_geometry`·`get_xrefs`·`get_layouts`)와 문자 겹침 검사 |
| `tests/test_rce_live.py` | `RCE` 대화상자 실행 흐름(점 선택만 지정 좌표로 대체하고, 화면에 표시되지 않는 새 Excel에 출력) |
| `tests/test_skill_defaults.py` | 설정 기본값이 Python(registry)과 LISP에서 일치하는지 대조 |

테스트는 `<python> -X utf8 tests\<파일>`로 실행하며, 마지막에 `FAIL: []`이 출력되면 통과입니다. `_live` 테스트는 AutoCAD가 실행 중이고 활성 도면이 새 도면(`Drawing*`)일 때만 수행됩니다.

- 로그: MCP `%LOCALAPPDATA%\cad-mcp-kr\cad_mcp.log`(5MB 순환), 대화상자 명령 `%LOCALAPPDATA%\bc-autocad\logs\`.
- MCP 서버는 비동기 서버 안에서 COM 호출을 하나의 스레드로 모아 처리합니다(호출 단위 재시도·제한 시간·Esc 감시 포함).

## 9. 실측 및 검증 기록 (개발자 참고)

AutoCAD 2023 환경에서 실측하고 검증한 사항입니다.

- 외부 프로세스의 SendCommand는 **동기 방식**입니다(LISP가 끝나야 반환). 닫히지 않은 LISP나 입력 대기 상태에서는 **반환되지 않습니다.**
- 인라인 SendCommand는 약 7.5KB에서 멈춥니다 → 파일 eval 방식으로 처리합니다(210KB 0.43초, 한글 정상). `(load)`를 사용하지 않으므로 SECURELOAD·신뢰 경로와 무관합니다.
- 멈춤 복구: 주 창에 보낸 Esc는 효과가 없고, **입력 포커스 창**에 보낸 WM_CHAR Esc로 해제됩니다.
- VL.Application.16 eval(다른 MCP 구현에서 쓰는 방식)은 **사용하지 않습니다**: 쓰기 작업 시 응답 없음 현상이 발생하고, 210KB 입력에서 AutoCAD가 강제 종료되었습니다.
- `(command "_.LINE" ...)`은 객체 스냅의 영향을 받습니다((0.3,10.2)→(0,10)). COM 작도는 영향을 받지 않습니다.
- `ssget "_C"`는 화면 밖 객체를 누락합니다. 레이어 필터에는 역따옴표 이스케이프가 필요합니다.
- `(open f "w" "utf8")`은 BOM 없는 UTF-8로 기록합니다. 기본값은 CP949입니다.
- 새 도면 생성·저장 직후에는 COM 호출이 잠시 거부됩니다 → 호출마다 재시도합니다(최대 약 20초).
- COM StartUndoMark/EndUndoMark는 그 사이의 LISP 작업까지 한 묶음으로 처리합니다. LISP 1회 실행은 표시 없이도 한 묶음입니다.
- (2026-10-29) UTF-8 `.lsp`는 신뢰 경로에 있으면 `(load)`로 한글이 정상 로드됩니다(BOM 유무 무관, LISPSYS=1). 따라서 AutoCAD 명령은 원본 `.lsp`를 플러그인 폴더의 로드 파일로 불러오고, MCP·대화상자는 같은 원본을 한 줄 사본으로 eval합니다.
- (2026-10-29) `rtos`는 DIMZIN 설정에 따라 소수 끝의 0을 생략합니다(`1.00`→`1`). 토목 명령은 DIMZIN을 일시적으로 0으로 두는 `bc:rtos`를 사용합니다.
- (2026-10-29) 비균일 축척 블록의 `vla-Explode` 반환 배열은 원소를 읽을 때 "잘못된 색인" 오류가 발생합니다. XYB는 분해 후 새 객체를 `entnext`로 수집합니다.
- (2026-10-29) 시작하기 세트(현재 프로필 `Dialogs\Appload\Startup` 레지스트리)에 로드 파일을 등록했으나 AutoCAD 재실행 시 로드되지 않았습니다(직접 로드는 정상). 이에 AutoCAD 공식 자동 로드 방식인 플러그인 폴더(`ApplicationPlugins`, `PackageContents.xml`, `APPAUTOLOAD`)로 변경했습니다.
- (2026-10-29) 설계 프로그램으로 작성한 하천 횡단면도는 단면마다 세로·가로 축척이 다를 수 있습니다(실제 하천 도면: 세로 1/200~1/1000, 가로 1/200~1/4000). 하천 횡단 명령은 단면 왼쪽 EL 눈금과 하단 거리 눈금 숫자로 해당 단면의 축척을 판독합니다.
- (2026-10-29) `DCP`: 각 선의 분할점마다 맞은편 선에 수선의 발을 내려 그 사이의 등거리점을 연결합니다(양방향). 맞은편 선의 끝을 벗어나는 대응점은 제외하여 두 선이 실제로 마주 보는 구간만 작도합니다(한쪽이 짧거나 U자 만곡·합류부 나팔형인 경우 포함). 표본 간격은 두 선 폭의 1/100 이하(최대 2만 개)입니다. 실제 제방선(2.4km, 간격 141m)에서 10초, 전 구간 양쪽 거리 차 2.2mm 이내(기존 방식은 5분 이상). 작도하지 않는 경우: 닫힌 선, 두 선의 교차·겹침·T자 접촉(끝점 하나를 공유하는 V자 형상은 작도 대상에 포함), 고도가 변하는 3D 선, 한 선이 다른 선을 감싸 중심이 양쪽에 생기는 경우.
- (2026-10-29) `DIBC`: 측점의 수직선이 대상 선과 해당 측점 부근이 아닌 먼 위치에서 만나면(해당 구간에 대상 선이 없는 경우) 거리로 계산하지 않고 빈칸으로 둡니다. 합계(폭)는 모든 선이 있을 때만 기록합니다. 판정 기준은 '교점에서 선형에 내린 점이 선형을 따라 해당 측점에서 교점 거리 이내'이므로 선형 꺾임점 부근의 안쪽 선도 빈칸이 되지 않습니다. 수직선 길이는 도면 범위의 2배입니다(mm 도면 대응).
- (2026-10-30) `DCP` 설정 `끝연장`(기본값 해제): 활성화하면 중심선 양 끝을 끝 방향으로 연장하여 두 선의 끝점 중 더 나간 쪽과 나란하게 합니다.
- (2026-10-30) `STT` 방식 `구간`: 하천 평면도 지구명 견본과 같은 두 줄 문자(인출선·Dot 없음)를 구간 양 끝 안쪽에 선형 방향으로 작성합니다. 구간이 문자보다 짧으면 가운데 한 곳에 작성합니다. 연장은 두 측점의 차이(천 단위 쉼표, 소수 `구간소수`), 구분자는 `구간구분`(기본값 ` ~ `)입니다.
- (2026-10-30) 명령 이름: 기본값은 `BC` 접두어 이름만 사용합니다(`BCFE`). 단축 이름(`FE`)은 `BCHELP` 대화상자에서 활성화한 명령만 사용하며, `BCOFF`로 모두 해제합니다(4-1). AutoCAD는 LISP 명령을 같은 이름의 단축키보다 먼저 실행하고(실측), BC 이름만 두고 자동 완성에 의존하면 앞부분이 일치하는 다른 명령이 우선할 수 있어(`CIRC` → CIRCLE, 실측) 이 방식으로 결정했습니다. 버전은 `BCHELP` 대화상자 제목에만 표시합니다.
- (2026-10-30) Excel에 숫자를 출력할 때 지정한 소수 자릿수가 그대로 표시되도록 셀 표시 형식을 지정합니다(Excel은 `100.0000`을 숫자로 변환하면서 끝의 0을 생략함). 좌표 소수는 사사오입합니다(`7.125`→`7.13`). `CEX`·`RCE`의 좌표 소수 기본값은 4자리이며, `RCE`는 행마다 열 너비를 맞춥니다.
- (2026-10-30) 안티그래비티는 CLI와 데스크톱 앱의 MCP 설정 파일이 서로 달라, 설치 스크립트가 존재하는 파일 모두에 등록합니다(3장).
- (2026-10-30) 플러그인 자동 로드 대상을 AutoCAD 2021(R24.0) 이상으로 정했습니다. UTF-8 `.lsp`(LISPSYS=1)와 `(open … "utf8")`이 2021부터 지원되므로 2020 이하는 대상에서 제외합니다(2021·2022는 미검증).
