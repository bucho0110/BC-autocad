;;; bc_windows.lsp — 창 명령과 도움말 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)

(defun c:FPEL () (bc:open-window "FPEL") (princ))  ; 종단 여러 EL 찾아 표기
(defun c:DTIN () (bc:open-window "DTIN") (princ))  ; 삼각망 그리기
(defun c:CEX () (bc:open-window "CEX") (princ))  ; 좌표 내보내기
(defun c:RCE () (bc:open-window "RCE") (princ))  ; 순번 좌표 내보내기
(defun c:CIM () (bc:open-window "CIM") (princ))  ; 좌표 가져오기
(defun c:DSTA () (bc:open-window "DSTA") (princ))  ; 선형에 측점 쓰기
(defun c:DIBC () (bc:open-window "DIBC") (princ))  ; 선형 이격 거리 조회
(defun c:HWLI () (bc:open-window "HWLI") (princ))  ; 기본설계 값으로 실시설계 보간
(defun c:DRRE () (bc:open-window "DRRE") (princ))  ; 호안 전개도 그리기
(defun c:DCEM () (bc:open-window "DCEM") (princ))  ; 하천 횡단 레벨 표시
(defun c:DDGP () (bc:open-window "DDGP") (princ))  ; 하천 지반선에 일괄 계획선
(defun c:RCSE () (bc:open-window "RCSE") (princ))  ; 하천 평면 대횡단
(defun c:CSAR () (bc:open-window "CSAR") (princ))  ; 도곽에 횡단 배치
(defun c:HWLM () (bc:open-window "HWLM") (princ))  ; 하천 횡단 홍수위 표시 일괄
(defun c:MPL () (bc:open-window "MPL") (princ))  ; 다중 플롯
(defun c:MPLOT () (bc:fn-MPL))

;; BCHELP: 명령 목록 창을 띄우고, 명령줄 기록(F2)에도 목록을 남긴다
(defun c:BCHELP ()
  (bc:open-window "BCHELP")
  (princ "\n[BC] 명령 목록 (F2로 전체 보기)")
  (princ "\n  ── EL")
  (princ "\n  BCFE    상대 EL 구하기")
  (princ "\n  BCFW    측구 EL 구하기")
  (princ "\n  BCFEL   EL 표시 (원하는 EL 위치 찾기)")
  (princ "\n  BCCEE   단면 EL 값 문자 복사 증감")
  (princ "\n  BCGEL   두 점 사이 EL 구하기")
  (princ "\n  BCSLEL  경사 입력해 평면 EL 구하기")
  (princ "\n  BCIEL   삼각망 EL 구하기")
  (princ "\n  BCFPEL  종단 여러 EL 찾아 표기 (대화상자)")
  (princ "\n  BCDTIN  삼각망 그리기 (대화상자)")
  (princ "\n  ── 좌표")
  (princ "\n  BCXY    XY 좌표 쓰기")
  (princ "\n  BCZBC   경계 좌표 추출")
  (princ "\n  BCWCD   도곽 경계 좌표 쓰기")
  (princ "\n  BCCEX   좌표 내보내기 (대화상자)")
  (princ "\n  BCRCE   순번 좌표 내보내기 (대화상자)")
  (princ "\n  BCCIM   좌표 가져오기 (대화상자)")
  (princ "\n  ── 선형")
  (princ "\n  BCDCP   두 선 사이 중심선")
  (princ "\n  BCDCEN  중심선 표시")
  (princ "\n  BCDSTA  선형에 측점 쓰기 (대화상자)")
  (princ "\n  BCSTT   측점 인출선 표기")
  (princ "\n  BCGST   선형 측점 조회")
  (princ "\n  BCDIBC  선형 이격 거리 조회 (대화상자)")
  (princ "\n  BCCST   측점 문자 거리 계산")
  (princ "\n  BCNUST  측점 문자 ↔ 숫자 변경")
  (princ "\n  BCMIP   원곡선 선형 IP 그리기")
  (princ "\n  BCHWLI  기본설계 값으로 실시설계 보간 (대화상자)")
  (princ "\n  ── 사면")
  (princ "\n  BCDSLO  계획 사면 그리기")
  (princ "\n  BCNSLO  자연 사면 그리기")
  (princ "\n  BCDFB   앞성토 사면 그리기")
  (princ "\n  BCSLL   경사선 그리기")
  (princ "\n  BCSLT   경사 표시")
  (princ "\n  BCCSS   횡단 사면 그리기")
  (princ "\n  BCCUT   횡단면도 층따기")
  (princ "\n  BCDRRE  호안 전개도 그리기 (대화상자)")
  (princ "\n  ── 하천 횡단")
  (princ "\n  BCDCEM  하천 횡단 레벨 표시 (대화상자)")
  (princ "\n  BCDDGP  하천 지반선에 일괄 계획선 (대화상자)")
  (princ "\n  BCRCSE  하천 평면 대횡단 (대화상자)")
  (princ "\n  BCCSAR  도곽에 횡단 배치 (대화상자)")
  (princ "\n  BCHWLM  하천 횡단 홍수위 표시 일괄 (대화상자)")
  (princ "\n  ── 수정")
  (princ "\n  BCXYB   X·Y 축척 다르게 변환")
  (princ "\n  ── 유틸리티")
  (princ "\n  BCMPL   다중 플롯 (대화상자)")
  (princ "\n  ※ 명령은 BC를 붙여 입력합니다(FE → BCFE). 단축 이름은 BCHELP 대화상자에서 활성화합니다.")
  (if bc:*short* (progn (princ "\n  ※ 활성화된 단축 이름:") (foreach _k bc:*short* (princ (strcat " " _k))) (princ "  (모두 해제: BCOFF)")))
  (princ))
