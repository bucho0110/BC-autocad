;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_windows.lsp — 창 명령과 도움말 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)

(defun c:FPEL () (bc:open-window "FPEL") (princ))  ; 종단도 다중 EL 표기
(defun c:DTIN () (bc:open-window "DTIN") (princ))  ; 삼각망 작성
(defun c:TTP () (bc:open-window "TTP") (princ))  ; Z값 점·문자 생성
(defun c:CCON () (bc:open-window "CCON") (princ))  ; 등고선 생성
(defun c:CMOB () (bc:open-window "CMOB") (princ))  ; 지형 외곽 경계 그리기
(defun c:GRP () (bc:open-window "GRP") (princ))  ; 지형에서 종단 추출
(defun c:CFM () (bc:open-window "CFM") (princ))  ; 지형에서 횡단 추출
(defun c:QCAR () (bc:open-window "QCAR") (princ))  ; 용지도 면적 산출
(defun c:DRP () (bc:open-window "DRP") (princ))  ; 엑셀 값으로 종단 그리기
(defun c:DCS () (bc:open-window "DCS") (princ))  ; 종단·횡단 그리기
(defun c:DLS () (bc:open-window "DLS") (princ))  ; 종단 선형 계산
(defun c:GSE () (bc:open-window "GSE") (princ))  ; 종단 계획고 찾기
(defun c:CFB () (bc:open-window "CFB") (princ))  ; 횡단면도 야장으로
(defun c:EWT () (bc:open-window "EWT") (princ))  ; 토적표 내용 엑셀로
(defun c:CL () (bc:open-window "CL") (princ))  ; 객체 길이 쓰기
(defun c:QCL () (bc:open-window "QCL") (princ))  ; 간편 객체 길이 쓰기
(defun c:TLAE () (bc:open-window "TLAE") (princ))  ; 객체 길이·면적 합산 조회
(defun c:HAR () (bc:open-window "HAR") (princ))  ; 종류별 해치 면적 조회
(defun c:SEAT () (bc:open-window "SEAT") (princ))  ; 선택 객체 면적 표 그리기
(defun c:DMT () (bc:open-window "DMT") (princ))  ; 구적도 그리기
(defun c:CTE () (bc:open-window "CTE") (princ))  ; 캐드 표 엑셀로
(defun c:ETC () (bc:open-window "ETC") (princ))  ; 엑셀 표 캐드로
(defun c:DDE () (bc:open-window "DDE") (princ))  ; 중복 객체 삭제
(defun c:DOE () (bc:open-window "DOE") (princ))  ; 겹친 객체 삭제
(defun c:JJJ () (bc:open-window "JJJ") (princ))  ; 선 결합
(defun c:CPL () (bc:open-window "CPL") (princ))  ; 폴리선 상호 변환
(defun c:FTF () (bc:open-window "FTF") (princ))  ; 없는 글꼴 일괄 수정
(defun c:CEX () (bc:open-window "CEX") (princ))  ; 객체 좌표 출력
(defun c:RCE () (bc:open-window "RCE") (princ))  ; 순번 붙여 좌표 출력
(defun c:CIM () (bc:open-window "CIM") (princ))  ; 좌표 목록으로 작도
(defun c:TTE () (bc:open-window "TTE") (princ))  ; 문자를 엑셀로
(defun c:DSTA () (bc:open-window "DSTA") (princ))  ; 선형 측점 표기
(defun c:DIBC () (bc:open-window "DIBC") (princ))  ; 측점별 이격 거리 산정
(defun c:HWLI () (bc:open-window "HWLI") (princ))  ; 측점 값 보간(기본→실시설계)
(defun c:DRRE () (bc:open-window "DRRE") (princ))  ; 호안 전개도 작도
(defun c:DCEM () (bc:open-window "DCEM") (princ))  ; 횡단 EL 눈금 표시
(defun c:DDGP () (bc:open-window "DDGP") (princ))  ; 횡단 계획선 일괄 작도
(defun c:RCSE () (bc:open-window "RCSE") (princ))  ; 평면 대횡단 작성
(defun c:CSAR () (bc:open-window "CSAR") (princ))  ; 횡단면 도곽 배치
(defun c:HWLM () (bc:open-window "HWLM") (princ))  ; 횡단 계획홍수위 일괄 표기
(defun c:CTS () (bc:open-window "CTS") (princ))  ; 문자 그림자 생성
(defun c:RET () (bc:open-window "RET") (princ))  ; 철근 재료표 작성
(defun c:RCHK () (bc:open-window "RCHK") (princ))  ; 구조도/상세도 철근 비교 검사
(defun c:ADD () (bc:open-window "ADD") (princ))  ; 숫자 증감
(defun c:INN () (bc:open-window "INN") (princ))  ; 임의 숫자 증가
(defun c:MUIN () (bc:open-window "MUIN") (princ))  ; 여러 도면 원래 좌표로 불러오기
(defun c:CALC () (bc:open-window "CALC") (princ))  ; CAD 계산기
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
  (princ "\n  BCTTP   Z값 점·문자 생성 (대화상자)")
  (princ "\n  ── 지형")
  (princ "\n  BCCCON  등고선 생성 (대화상자)")
  (princ "\n  BCWCZ   등고선 높이 문자 쓰기")
  (princ "\n  BCDCON  등고선 높이별 레이어 분리")
  (princ "\n  BCCMOB  지형 외곽 경계 그리기 (대화상자)")
  (princ "\n  BCDSEL  EL 조건 점 표시")
  (princ "\n  BCGRP   지형에서 종단 추출 (대화상자)")
  (princ "\n  BCCFM   지형에서 횡단 추출 (대화상자)")
  (princ "\n  BCQCAR  용지도 면적 산출 (대화상자)")
  (princ "\n  ── 종단·횡단")
  (princ "\n  BCDRP   엑셀 값으로 종단 그리기 (대화상자)")
  (princ "\n  BCDCS   종단·횡단 그리기 (대화상자)")
  (princ "\n  BCDLS   종단 선형 계산 (대화상자)")
  (princ "\n  BCGSE   종단 계획고 찾기 (대화상자)")
  (princ "\n  BCCFB   횡단면도 야장으로 (대화상자)")
  (princ "\n  BCEWT   토적표 내용 엑셀로 (대화상자)")
  (princ "\n  ── 수량·표")
  (princ "\n  BCCL    객체 길이 쓰기 (대화상자)")
  (princ "\n  BCQCL   간편 객체 길이 쓰기 (대화상자)")
  (princ "\n  BCTLAE  객체 길이·면적 합산 조회 (대화상자)")
  (princ "\n  BCHAR   종류별 해치 면적 조회 (대화상자)")
  (princ "\n  BCSEAT  선택 객체 면적 표 그리기 (대화상자)")
  (princ "\n  BCDMT   구적도 그리기 (대화상자)")
  (princ "\n  BCCTE   캐드 표 엑셀로 (대화상자)")
  (princ "\n  BCETC   엑셀 표 캐드로 (대화상자)")
  (princ "\n  ── 정리")
  (princ "\n  BCDDE   중복 객체 삭제 (대화상자)")
  (princ "\n  BCDOE   겹친 객체 삭제 (대화상자)")
  (princ "\n  BCJJJ   선 결합 (대화상자)")
  (princ "\n  BCCPL   폴리선 상호 변환 (대화상자)")
  (princ "\n  BCFTF   없는 글꼴 일괄 수정 (대화상자)")
  (princ "\n  ── 좌표")
  (princ "\n  BCXY    좌표 문자 표기")
  (princ "\n  BCZBC   경계 좌표표 작성")
  (princ "\n  BCWCD   도곽 경계 좌표 표기")
  (princ "\n  BCCEX   객체 좌표 출력 (대화상자)")
  (princ "\n  BCRCE   순번 붙여 좌표 출력 (대화상자)")
  (princ "\n  BCCIM   좌표 목록으로 작도 (대화상자)")
  (princ "\n  BCTTE   문자를 엑셀로 (대화상자)")
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
  (princ "\n  BCART   문자 정렬")
  (princ "\n  BCCTS   문자 그림자 생성 (대화상자)")
  (princ "\n  BCRET   철근 재료표 작성 (대화상자)")
  (princ "\n  BCRCHK  구조도/상세도 철근 비교 검사 (대화상자)")
  (princ "\n  BCADD   숫자 증감 (대화상자)")
  (princ "\n  BCINN   임의 숫자 증가 (대화상자)")
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
  (princ "\n  BCCALC  CAD 계산기 (대화상자)")
  (princ "\n  BCMPL   다중 플롯 (대화상자)")
  (princ "\n  ※ 명령은 BC를 붙여 입력합니다(FE → BCFE). 단축 이름은 BCHELP 대화상자에서 활성화합니다.")
  (if bc:*short* (progn (princ "\n  ※ 활성화된 단축 이름:") (foreach _k bc:*short* (princ (strcat " " _k))) (princ "  (모두 해제: BCOFF)")))
  (princ))
