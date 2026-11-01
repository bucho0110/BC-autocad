;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_windows.lsp — 창 명령과 도움말 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)

(defun c:FPEL () (bc:open-window "FPEL") (princ))  ; 종단도 다중 EL 표기
(defun c:DTIN () (bc:open-window "DTIN") (princ))  ; 삼각망 작성
(defun c:TTP () (bc:open-window "TTP") (princ))  ; Z값 점·문자 생성
(defun c:CCON () (bc:open-window "CCON") (princ))  ; 표고점으로 등고선 그리기
(defun c:CMOB () (bc:open-window "CMOB") (princ))  ; 지형 외곽 경계 그리기
(defun c:GRP () (bc:open-window "GRP") (princ))  ; 지형에서 종단 추출
(defun c:CFM () (bc:open-window "CFM") (princ))  ; 지형에서 횡단 추출
(defun c:QCAR () (bc:open-window "QCAR") (princ))  ; 지적별 편입 면적 계산
(defun c:DRP () (bc:open-window "DRP") (princ))  ; 엑셀 표로 종단면도 작도
(defun c:DCS () (bc:open-window "DCS") (princ))  ; 종단·횡단 그리기
(defun c:DLS () (bc:open-window "DLS") (princ))  ; 종곡선 계산·계획선 작도
(defun c:GSE () (bc:open-window "GSE") (princ))  ; 종단 계획고 조회·추출
(defun c:CFB () (bc:open-window "CFB") (princ))  ; 횡단 지반선을 야장 엑셀로
(defun c:EWT () (bc:open-window "EWT") (princ))  ; 토적표 블록 값 엑셀로 모으기
(defun c:CL () (bc:open-window "CL") (princ))  ; 선 길이 표기
(defun c:QCL () (bc:open-window "QCL") (princ))  ; 선 길이 바로 표기
(defun c:TLAE () (bc:open-window "TLAE") (princ))  ; 객체 길이·면적 합산 조회
(defun c:HAR () (bc:open-window "HAR") (princ))  ; 해치 유형별 면적표 작성
(defun c:SEAT () (bc:open-window "SEAT") (princ))  ; 닫힌 객체 면적표 작성
(defun c:DMT () (bc:open-window "DMT") (princ))  ; 삼각형 분할 구적도 작성
(defun c:CTE () (bc:open-window "CTE") (princ))  ; 도면 표를 엑셀로 옮기기
(defun c:ETC () (bc:open-window "ETC") (princ))  ; 엑셀 범위를 도면 표로
(defun c:DDE () (bc:open-window "DDE") (princ))  ; 동일 중복 객체 정리
(defun c:DOE () (bc:open-window "DOE") (princ))  ; 중첩선 정리·일직선 병합
(defun c:JJJ () (bc:open-window "JJJ") (princ))  ; 맞닿은 선 폴리선으로 잇기
(defun c:CPL () (bc:open-window "CPL") (princ))  ; 폴리선 유형 변환(2D·3D)
(defun c:FTF () (bc:open-window "FTF") (princ))  ; 누락 글꼴 대체
(defun c:CEX () (bc:open-window "CEX") (princ))  ; 객체 좌표 출력
(defun c:RCE () (bc:open-window "RCE") (princ))  ; 순번 붙여 좌표 출력
(defun c:CIM () (bc:open-window "CIM") (princ))  ; 좌표 목록으로 작도
(defun c:TTE () (bc:open-window "TTE") (princ))  ; 문자 값 엑셀에 넣기
(defun c:DSTA () (bc:open-window "DSTA") (princ))  ; 선형 측점 표기
(defun c:DIBC () (bc:open-window "DIBC") (princ))  ; 측점별 이격 거리 산정
(defun c:HWLI () (bc:open-window "HWLI") (princ))  ; 측점 값 보간(기본→실시설계)
(defun c:DRRE () (bc:open-window "DRRE") (princ))  ; 호안 전개도 작도
(defun c:DCEM () (bc:open-window "DCEM") (princ))  ; 횡단 EL 눈금 표시
(defun c:DDGP () (bc:open-window "DDGP") (princ))  ; 횡단 계획선 일괄 작도
(defun c:RCSE () (bc:open-window "RCSE") (princ))  ; 평면 대횡단 작성
(defun c:CSAR () (bc:open-window "CSAR") (princ))  ; 횡단면 도곽 배치
(defun c:HWLM () (bc:open-window "HWLM") (princ))  ; 횡단 계획홍수위 일괄 표기
(defun c:CTS () (bc:open-window "CTS") (princ))  ; 문자 뒤 그림자 만들기
(defun c:RET () (bc:open-window "RET") (princ))  ; 철근 상세 읽어 재료표 그리기
(defun c:RCHK () (bc:open-window "RCHK") (princ))  ; 구조도·상세도 철근 대조
(defun c:ADD () (bc:open-window "ADD") (princ))  ; 문자 속 숫자 사칙연산
(defun c:INN () (bc:open-window "INN") (princ))  ; ? 자리 일련번호 매기기
(defun c:MUIN () (bc:open-window "MUIN") (princ))  ; 여러 도면 원래 좌표로 불러오기
(defun c:CALC () (bc:open-window "CALC") (princ))  ; 도면 값 계산기
(defun c:MPL () (bc:open-window "MPL") (princ))  ; 도곽별 일괄 출력
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
  (princ "\n  BCTTP   Z값 점·문자 생성 (대화상자)")
  (princ "\n  ── 지형")
  (princ "\n  BCCCON  표고점으로 등고선 그리기 (대화상자)")
  (princ "\n  BCWCZ   등고선 표고 표기")
  (princ "\n  BCDCON  등고선 표고별 레이어·색상 구분")
  (princ "\n  BCCMOB  지형 외곽 경계 그리기 (대화상자)")
  (princ "\n  BCDSEL  EL 조건 점 표시")
  (princ "\n  BCGRP   지형에서 종단 추출 (대화상자)")
  (princ "\n  BCCFM   지형에서 횡단 추출 (대화상자)")
  (princ "\n  BCQCAR  지적별 편입 면적 계산 (대화상자)")
  (princ "\n  ── 종단·횡단")
  (princ "\n  BCDRP   엑셀 표로 종단면도 작도 (대화상자)")
  (princ "\n  BCDCS   종단·횡단 그리기 (대화상자)")
  (princ "\n  BCDLS   종곡선 계산·계획선 작도 (대화상자)")
  (princ "\n  BCGSE   종단 계획고 조회·추출 (대화상자)")
  (princ "\n  BCCFB   횡단 지반선을 야장 엑셀로 (대화상자)")
  (princ "\n  BCEWT   토적표 블록 값 엑셀로 모으기 (대화상자)")
  (princ "\n  ── 수량·표")
  (princ "\n  BCCL    선 길이 표기 (대화상자)")
  (princ "\n  BCQCL   선 길이 바로 표기 (대화상자)")
  (princ "\n  BCTLAE  객체 길이·면적 합산 조회 (대화상자)")
  (princ "\n  BCHAR   해치 유형별 면적표 작성 (대화상자)")
  (princ "\n  BCSEAT  닫힌 객체 면적표 작성 (대화상자)")
  (princ "\n  BCDMT   삼각형 분할 구적도 작성 (대화상자)")
  (princ "\n  BCCTE   도면 표를 엑셀로 옮기기 (대화상자)")
  (princ "\n  BCETC   엑셀 범위를 도면 표로 (대화상자)")
  (princ "\n  ── 정리")
  (princ "\n  BCDDE   동일 중복 객체 정리 (대화상자)")
  (princ "\n  BCDOE   중첩선 정리·일직선 병합 (대화상자)")
  (princ "\n  BCJJJ   맞닿은 선 폴리선으로 잇기 (대화상자)")
  (princ "\n  BCCPL   폴리선 유형 변환(2D·3D) (대화상자)")
  (princ "\n  BCFTF   누락 글꼴 대체 (대화상자)")
  (princ "\n  ── 좌표")
  (princ "\n  BCXY    좌표 문자 표기")
  (princ "\n  BCZBC   경계 좌표표 작성")
  (princ "\n  BCWCD   도곽 경계 좌표 표기")
  (princ "\n  BCCEX   객체 좌표 출력 (대화상자)")
  (princ "\n  BCRCE   순번 붙여 좌표 출력 (대화상자)")
  (princ "\n  BCCIM   좌표 목록으로 작도 (대화상자)")
  (princ "\n  BCTTE   문자 값 엑셀에 넣기 (대화상자)")
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
  (princ "\n  BCART   문자 정렬점·줄 맞추기")
  (princ "\n  BCCTS   문자 뒤 그림자 만들기 (대화상자)")
  (princ "\n  BCRET   철근 상세 읽어 재료표 그리기 (대화상자)")
  (princ "\n  BCRCHK  구조도·상세도 철근 대조 (대화상자)")
  (princ "\n  BCADD   문자 속 숫자 사칙연산 (대화상자)")
  (princ "\n  BCINN   ? 자리 일련번호 매기기 (대화상자)")
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
  (princ "\n  BCCALC  도면 값 계산기 (대화상자)")
  (princ "\n  BCMPL   도곽별 일괄 출력 (대화상자)")
  (princ "\n  ※ 명령은 BC를 붙여 입력합니다(FE → BCFE). 단축 이름은 BCHELP 대화상자에서 활성화합니다.")
  (if bc:*short* (progn (princ "\n  ※ 활성화된 단축 이름:") (foreach _k bc:*short* (princ (strcat " " _k))) (princ "  (모두 해제: BCOFF)")))
  (princ))
