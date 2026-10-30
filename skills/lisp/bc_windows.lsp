;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_windows.lsp — 창 명령과 도움말 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)

(defun c:FPEL () (bc:open-window "FPEL") (princ))  ; 종단도 다중 EL 표기
(defun c:DTIN () (bc:open-window "DTIN") (princ))  ; 삼각망 작성
(defun c:CEX () (bc:open-window "CEX") (princ))  ; 객체 좌표 출력
(defun c:RCE () (bc:open-window "RCE") (princ))  ; 순번 붙여 좌표 출력
(defun c:CIM () (bc:open-window "CIM") (princ))  ; 좌표 목록으로 작도
(defun c:DSTA () (bc:open-window "DSTA") (princ))  ; 선형 측점 표기
(defun c:DIBC () (bc:open-window "DIBC") (princ))  ; 측점별 이격 거리 산정
(defun c:HWLI () (bc:open-window "HWLI") (princ))  ; 측점 값 보간(기본→실시설계)
(defun c:DRRE () (bc:open-window "DRRE") (princ))  ; 호안 전개도 작도
(defun c:DCEM () (bc:open-window "DCEM") (princ))  ; 횡단 EL 눈금 표시
(defun c:DDGP () (bc:open-window "DDGP") (princ))  ; 횡단 계획선 일괄 작도
(defun c:RCSE () (bc:open-window "RCSE") (princ))  ; 평면 대횡단 작성
(defun c:CSAR () (bc:open-window "CSAR") (princ))  ; 횡단면 도곽 배치
(defun c:HWLM () (bc:open-window "HWLM") (princ))  ; 횡단 계획홍수위 일괄 표기
(defun c:MUIN () (bc:open-window "MUIN") (princ))  ; 여러 도면 원래 좌표로 불러오기
(defun c:MPL () (bc:open-window "MPL") (princ))  ; 다중 플롯
(defun c:MPLOT () (bc:fn-MPL))

;; BCHELP: 명령 목록 창을 띄우고, 명령줄 기록(F2)에도 목록을 남긴다
(defun c:BCHELP ()
  (bc:open-window "BCHELP")
  (princ "\n[BC] 명령 목록 (F2로 전체 보기)")
  (princ "\n  ── EL")
  (princ "\n  BCFE    기준 EL 대비 위치 EL 표기")
  (princ "\n  BCFW    측구 EL 표기")
  (princ "\n  BCFEL   지정 EL 위치 찾아 표시")
  (princ "\n  BCCEE   EL 문자 복사·증감")
  (princ "\n  BCGEL   두 점 사이 EL 보간")
  (princ "\n  BCSLEL  경사로 평면 EL 표기")
  (princ "\n  BCIEL   삼각망 위치 EL 산정")
  (princ "\n  BCFPEL  종단도 다중 EL 표기 (대화상자)")
  (princ "\n  BCDTIN  삼각망 작성 (대화상자)")
  (princ "\n  ── 좌표")
  (princ "\n  BCXY    좌표 문자 표기")
  (princ "\n  BCZBC   경계 좌표표 작성")
  (princ "\n  BCWCD   도곽 경계 좌표 표기")
  (princ "\n  BCCEX   객체 좌표 출력 (대화상자)")
  (princ "\n  BCRCE   순번 붙여 좌표 출력 (대화상자)")
  (princ "\n  BCCIM   좌표 목록으로 작도 (대화상자)")
  (princ "\n  ── 선형")
  (princ "\n  BCDCP   두 선의 중심선 작도")
  (princ "\n  BCDCEN  원·호·두 선 중심선 표시")
  (princ "\n  BCDSTA  선형 측점 표기 (대화상자)")
  (princ "\n  BCSTT   측점 인출 표기")
  (princ "\n  BCGST   지정점 측점 확인")
  (princ "\n  BCDIBC  측점별 이격 거리 산정 (대화상자)")
  (princ "\n  BCCST   두 측점 사이 거리")
  (princ "\n  BCNUST  측점 표기 ↔ 거리 변환")
  (princ "\n  BCMIP   원곡선 IP 작도")
  (princ "\n  BCHWLI  측점 값 보간(기본→실시설계) (대화상자)")
  (princ "\n  ── 사면")
  (princ "\n  BCDSLO  계획 사면 기호 작도")
  (princ "\n  BCNSLO  자연 사면 기호 작도")
  (princ "\n  BCDFB   앞성토 사면 작도")
  (princ "\n  BCSLL   경사선 작도")
  (princ "\n  BCSLT   경사 기호 표기")
  (princ "\n  BCCSS   횡단 사면 작도")
  (princ "\n  BCCUT   층따기 작도")
  (princ "\n  BCDRRE  호안 전개도 작도 (대화상자)")
  (princ "\n  ── 하천 횡단")
  (princ "\n  BCDCEM  횡단 EL 눈금 표시 (대화상자)")
  (princ "\n  BCDDGP  횡단 계획선 일괄 작도 (대화상자)")
  (princ "\n  BCRCSE  평면 대횡단 작성 (대화상자)")
  (princ "\n  BCCSAR  횡단면 도곽 배치 (대화상자)")
  (princ "\n  BCHWLM  횡단 계획홍수위 일괄 표기 (대화상자)")
  (princ "\n  ── 수정")
  (princ "\n  BCXYB   X·Y 축척 개별 변환")
  (princ "\n  BCCR    문자를 사각형 가운데로 정렬")
  (princ "\n  ── 레이어")
  (princ "\n  BCLOL   고른 레이어만 켜기")
  (princ "\n  BCLOF   고른 레이어 끄기")
  (princ "\n  BCLON   레이어 전체 켜기")
  (princ "\n  BCOLO   꺼진 레이어만 표시")
  (princ "\n  BCLFR   고른 레이어 동결")
  (princ "\n  BCFRE   고른 레이어 외 전체 동결")
  (princ "\n  BCLTH   레이어 전체 동결 해제")
  (princ "\n  BCLLO   고른 레이어 잠금")
  (princ "\n  BCLUL   고른 레이어 잠금 해제")
  (princ "\n  BCULA   레이어 전체 잠금 해제")
  (princ "\n  BCLOE   고른 레이어 외 전체 잠금")
  (princ "\n  BCSCL   객체 레이어를 현재 레이어로")
  (princ "\n  BCCCL   객체를 현재 레이어로 이동")
  (princ "\n  ── 유틸리티")
  (princ "\n  BCMUIN  여러 도면 원래 좌표로 불러오기 (대화상자)")
  (princ "\n  BCMPL   다중 플롯 (대화상자)")
  (princ "\n  ※ 명령은 BC를 붙여 입력합니다(FE → BCFE). 단축 이름은 BCHELP 대화상자에서 활성화합니다.")
  (if bc:*short* (progn (princ "\n  ※ 활성화된 단축 이름:") (foreach _k bc:*short* (princ (strcat " " _k))) (princ "  (모두 해제: BCOFF)")))
  (princ))
