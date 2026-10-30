;;; bc_el.lsp — EL 명령 (FE FW FEL CEE GEL SLEL IEL)
;;; 공통 규칙
;;;  - 축척 1000 = m 도면(1m = 도면 1), 축척 1 = mm 도면. 문자 높이 설정은 축척 1000 기준.
;;;  - 기준 EL은 도면 문자를 고르면 그 안의 맨 뒤 숫자, E를 치면 직접 입력.
;;;  - 설정은 S → 설정 창(저장 후 명령 다시 실행). 같은 설정 파일을 MCP도 쓴다.
;;;  - bc:*-core 함수는 사람 입력 없이 값만으로 그린다(MCP가 부른다).

;;; ================================================================ 공통 기본값

(setq bc:el-defaults
  '(("축척" . 1000.0) ("레이어" . "") ("높이" . 0.3) ("DIMSCALE적용" . 0) ("소수" . 3)
    ("머리말" . "") ("꼬리말" . "") ("양수기호" . 0)))

(defun bc:el-cfg (cmd extra) (bc:cfg-load cmd (append bc:el-defaults extra)))

(defun bc:el-of (basept baseel pt scale)
  ;; 기준점 대비 높이 차를 m로 바꿔 더한다.
  (+ baseel (/ (- (cadr pt) (cadr basept)) (bc:upm scale))))

(defun bc:el-str (cfg v)
  (strcat (bc:cfg cfg "머리말") (bc:fmt v (bc:cfg cfg "소수") (= (bc:cfg cfg "양수기호") 1)) (bc:cfg cfg "꼬리말")))

(defun bc:el-head (cmd cfg base)
  (princ (strcat "\n<현재 설정 : 기준 EL = " (if base (bc:rtos base 2 3) "-")
                 ", 축척 = " (bc:rtos (bc:cfg cfg "축척") 2 3) "> [" cmd "]")))

(defun bc:ask-base-el (cmd cfg dflt / r)
  ;; 반환: 숫자 / "S"(설정) / nil
  (setq r (bc:get-number-or-pick "기준점 EL 문자 선택 또는 [EL 값 입력(E)/축척 변경(C)/설정 변경(S)]" "E C S" dflt))
  (cond ((= r "E") (getreal "\n기준 EL 값 입력: "))
        ((= r "C")
         (if (setq r (getreal (strcat "\n축척 입력(1000=m 도면, 1=mm 도면) <" (bc:rtos (bc:cfg cfg "축척") 2 3) ">: ")))
           (progn (bc:cfg-save cmd (bc:cfg-set cfg "축척" r)) "C")
           "C"))
        (T r)))

;;; ================================================================ FE 상대 EL 구하기

(setq bc:fe-extra
  '(("표기위치" . "위") ("점삽입" . 0) ("수평거리" . 0) ("거리소수" . 3) ("지시선" . 0) ("지시선길이" . 3.0)
    ("지시선각도" . 45.0)))

(defun bc:fe-core (basept baseel pt cfg / el h lay s off p2 p3 dx ents tx)
  ;; pt의 EL을 계산해 문자로 표기. 반환 (el 핸들목록)
  (setq el (bc:el-of basept baseel pt (bc:cfg cfg "축척"))
        h (bc:text-h cfg) lay (bc:cfg cfg "레이어")
        s (bc:el-str cfg el)
        dx (/ (abs (- (car pt) (car basept))) (bc:upm (bc:cfg cfg "축척"))))
  (if (= (bc:cfg cfg "점삽입") 1) (setq ents (cons (bc:point pt lay) ents)))
  (if (= (bc:cfg cfg "지시선") 1)
    (progn
      (setq p2 (polar pt (* pi (/ (bc:cfg cfg "지시선각도") 180.0)) (* h (bc:cfg cfg "지시선길이")))
            p3 (polar p2 0.0 (* h 0.8 (max 4 (strlen s)))))
      (setq ents (cons (bc:pline (list pt p2 p3) nil lay) ents))
      (setq ents (cons (bc:text (polar p2 (/ pi 2) (* h 0.4)) s h lay "BL" 0.0) ents))
      (if (= (bc:cfg cfg "수평거리") 1)
        (setq ents (cons (bc:text (polar p2 (* pi 1.5) (* h 0.4))
                                  (strcat "(L=" (bc:rtos dx 2 (bc:cfg cfg "거리소수")) "m)") h lay "TL" 0.0) ents))))
    (progn
      (setq off (* h 0.6) tx s)
      (if (= (bc:cfg cfg "수평거리") 1)
        (setq tx (strcat s " (L=" (bc:rtos dx 2 (bc:cfg cfg "거리소수")) "m)")))
      (setq ents (cons (if (= (bc:cfg cfg "표기위치") "아래")
                         (bc:text (polar pt (* pi 1.5) off) tx h lay "TC" 0.0)
                         (bc:text (polar pt (/ pi 2) off) tx h lay "BC" 0.0))
                       ents))))
  (list el (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents)))

(defun c:FE (/ cfg base bp p r en v)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "FE" bc:fe-extra))
  (bc:el-head "FE" cfg nil)
  (setq r (bc:ask-base-el "FE" cfg nil))
  (while (= r "C") (setq cfg (bc:el-cfg "FE" bc:fe-extra) r (bc:ask-base-el "FE" cfg nil)))
  (cond
    ((= r "S") (bc:open-window "FE") (bc:settings-hint "FE"))
    ((numberp r)
     (setq base r)
     (if (setq bp (getpoint "\n기준점 지정: "))
       (progn
         (setq bp (bc:wcs bp))
         (while (progn (initget "E") (setq p (getpoint "\nEL 표기점 지정 또는 [폴리선 선택(E)]: ")))
           (if (= p "E")
             (if (and (setq en (car (entsel "\n정점에 EL 표기할 선·폴리선 선택: "))) (bc:verts en))
               (foreach v (bc:verts en) (bc:fe-core bp base v cfg)))
             (progn
               (setq r (bc:fe-core bp base (bc:wcs p) cfg))
               (princ (strcat "\nEL = " (bc:rtos (car r) 2 4))))))))))
  (bc:end))

;;; ================================================================ FW 측구 EL (지시선 형식 1~7)

(setq bc:fw-extra
  '(("선레이어" . "") ("형식" . 1) ("지시선길이" . 3.0) ("문자위치" . "위") ("화살표" . 1.0) ("선길이" . 2.0)
    ("문자폭" . 0.0)))

(defun bc:fw-core (basept baseel pt cfg / el h lay llay s w L a b c d ents f side)
  (setq el (bc:el-of basept baseel pt (bc:cfg cfg "축척"))
        h (bc:text-h cfg) lay (bc:cfg cfg "레이어")
        llay (if (/= (bc:cfg cfg "선레이어") "") (bc:cfg cfg "선레이어") lay)
        s (bc:el-str cfg el)
        w (* h 0.85 (max 4 (strlen s)))
        L (* h (bc:cfg cfg "지시선길이"))
        f (bc:cfg cfg "형식"))
  (cond
    ((= f 1) ; 수직 위로 → 오른쪽 밑줄, 글자는 밑줄 위
     (setq a (polar pt (/ pi 2) L) b (polar a 0.0 w))
     (setq ents (list (bc:pline (list pt a b) nil llay) (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0))))
    ((= f 2) ; 수직 아래로
     (setq a (polar pt (* pi 1.5) L) b (polar a 0.0 w))
     (setq ents (list (bc:pline (list pt a b) nil llay) (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0))))
    ((= f 3) ; 오른쪽 위 사선
     (setq a (list (+ (car pt) L) (+ (cadr pt) L) (caddr pt)) b (polar a 0.0 w))
     (setq ents (list (bc:pline (list pt a b) nil llay) (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0))))
    ((= f 4) ; 오른쪽 아래 사선
     (setq a (list (+ (car pt) L) (- (cadr pt) L) (caddr pt)) b (polar a 0.0 w))
     (setq ents (list (bc:pline (list pt a b) nil llay) (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0))))
    ((= f 5) ; 화살표 + 수직 위
     (setq a (polar pt (/ pi 2) L) b (polar a 0.0 w))
     (setq ents (list (bc:pline (list pt a b) nil llay)
                      (bc:arrow pt (* pi 1.5) (* h (bc:cfg cfg "화살표")) llay)
                      (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0))))
    ((= f 6) ; 하천 제방고: 수직선, 문자는 위 또는 좌·우
     (setq c (polar pt (/ pi 2) (* h (bc:cfg cfg "선길이") 2.0)))
     (setq side (if (< (car pt) (car basept)) -1 1))
     (setq ents (list (bc:line pt c llay)
                      (cond ((= (bc:cfg cfg "문자위치") "위") (bc:text (polar c (/ pi 2) (* h 0.3)) s h lay "BC" 0.0))
                            ((= side -1) (bc:text (polar c pi (* h 0.4)) s h lay "TR" 0.0))
                            (T (bc:text (polar c 0.0 (* h 0.4)) s h lay "TL" 0.0))))))
    (T ; 7 십자 표시
     (setq d (* h (bc:cfg cfg "선길이") 0.5))
     (setq ents (list (bc:line (polar pt pi d) (polar pt 0.0 d) llay)
                      (bc:line (polar pt (* pi 1.5) d) (polar pt (/ pi 2) d) llay)
                      (bc:text (polar pt (/ pi 2) (+ d (* h 0.3))) s h lay "BC" 0.0)))))
  ;; 문자 폭(0 = 스타일 값 그대로)
  (if (> (bc:cfg cfg "문자폭") 0.0)
    (foreach e ents
      (if (= (cdr (assoc 0 (entget e))) "TEXT")
        (entmod (subst (cons 41 (bc:cfg cfg "문자폭")) (assoc 41 (entget e)) (entget e))))))
  (list el (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents)))

(defun c:FW (/ cfg r bp p en v)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "FW" bc:fw-extra))
  (bc:el-head "FW" cfg nil)
  (setq r (bc:ask-base-el "FW" cfg nil))
  (while (= r "C") (setq cfg (bc:el-cfg "FW" bc:fw-extra) r (bc:ask-base-el "FW" cfg nil)))
  (cond
    ((= r "S") (bc:open-window "FW") (bc:settings-hint "FW"))
    ((and (numberp r) (setq bp (getpoint "\n기준점 지정: ")))
     (setq bp (bc:wcs bp))
     (while (progn (initget "E") (setq p (getpoint "\nEL 표기점 지정 또는 [폴리선 선택(E)]: ")))
       (if (= p "E")
         (if (and (setq en (car (entsel "\n정점에 EL 표기할 선·폴리선 선택: "))) (bc:verts en))
           (foreach v (bc:verts en) (bc:fw-core bp r v cfg)))
         (bc:fw-core bp r (bc:wcs p) cfg)))))
  (bc:end))

;;; ================================================================ FEL 원하는 EL 위치 찾기

(setq bc:fel-extra '(("표시" . "가로선") ("길이" . 10.0)))

(defun bc:fel-core (basept baseel target cfg / y h lay s p len ents)
  ;; 기준점과 같은 X에서 target EL이 되는 Y 위치에 가로선(또는 지시선)과 값을 표기.
  (setq y (+ (cadr basept) (* (- target baseel) (bc:upm (bc:cfg cfg "축척"))))
        p (list (car basept) y (caddr basept))
        h (bc:text-h cfg) lay (bc:cfg cfg "레이어") s (bc:el-str cfg target)
        len (* h (bc:cfg cfg "길이")))
  (if (= (bc:cfg cfg "표시") "지시선")
    (setq ents (list (bc:pline (list p (polar p (/ pi 2) len) (polar (polar p (/ pi 2) len) 0.0 (* h 0.85 (max 4 (strlen s))))) nil lay)
                     (bc:text (polar (polar p (/ pi 2) len) (/ pi 2) (* h 0.3)) s h lay "BL" 0.0)))
    (setq ents (list (bc:line (polar p pi (/ len 2)) (polar p 0.0 (/ len 2)) lay)
                     (bc:text (polar (polar p 0.0 (/ len 2)) 0.0 (* h 0.4)) s h lay "ML" 0.0))))
  (list p (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents)))

(defun c:FEL (/ cfg r bp t1)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "FEL" bc:fel-extra))
  (bc:el-head "FEL" cfg nil)
  (setq r (bc:ask-base-el "FEL" cfg nil))
  (while (= r "C") (setq cfg (bc:el-cfg "FEL" bc:fel-extra) r (bc:ask-base-el "FEL" cfg nil)))
  (cond
    ((= r "S") (bc:open-window "FEL") (bc:settings-hint "FEL"))
    ((and (numberp r) (setq bp (getpoint "\n기준점 지정: ")))
     (setq bp (bc:wcs bp))
     (while (progn (initget "E") (setq t1 (getreal "\n표시할 EL 값 입력 또는 [EL 값 선택(E)]: ")))
       (if (= t1 "E")
         (setq t1 (bc:get-number-or-pick "찾을 EL 문자 선택" "" nil)))
       (if (numberp t1) (bc:fel-core bp r t1 cfg)))))
  (bc:end))

;;; ================================================================ CEE EL 표기 모양 복사 증감

(setq bc:cee-extra '(("소수자동" . 1) ("고정소수" . 2) ("영일때±" . 0) ("속성포함" . 1)))

(defun bc:dec-of (s / i n)
  ;; 문자열 맨 뒤 숫자의 소수 자릿수
  (setq i (strlen s))
  (while (and (> i 0) (not (bc:digit-p (ascii (substr s i 1))))) (setq i (1- i)))
  (setq n 0)
  (while (and (> i 0) (bc:digit-p (ascii (substr s i 1)))) (setq i (1- i) n (1+ n)))
  (if (and (> i 0) (= (substr s i 1) ".")) n 0))

(defun bc:replace-last-num (s v cfg / i e b neg pre post dec num sign)
  ;; s의 맨 뒤 숫자를 v로 바꾼다. 부호 표기((+)/(-)/+/-)는 원래 형식을 따른다.
  (setq i (strlen s))
  (while (and (> i 0) (not (bc:digit-p (ascii (substr s i 1))))) (setq i (1- i)))
  (if (= i 0) s
    (progn
      (setq e i b i)
      (while (and (> b 1) (or (bc:digit-p (ascii (substr s (1- b) 1))) (member (substr s (1- b) 1) '("." ","))))
        (setq b (1- b)))
      (setq pre (substr s 1 (1- b)) post (substr s (1+ e)))
      (setq dec (if (= (bc:cfg cfg "소수자동") 1) (bc:dec-of s) (bc:cfg cfg "고정소수")))
      (setq num (bc:rtos (abs v) 2 dec))
      ;; 부호 표기 형식: 괄호형 (+)(-)(±)은 항상 괄호 부호, 앞에 + 또는 ±가 있던 형식은 양수에도 +,
      ;; 그냥 - 만 있던 음수(EL=-1.50)는 일반 숫자로 보고 양수가 되면 부호 없이.
      (cond
        ((wcmatch pre "*(+),*(-),*(±)")
         (setq pre (substr pre 1 (- (strlen pre) 3))
               sign (cond ((and (equal v 0.0 1e-9) (= (bc:cfg cfg "영일때±") 1)) "(±)") ((< v 0) "(-)") (T "(+)"))))
        ((wcmatch pre "*+,*±")
         (setq pre (substr pre 1 (1- (strlen pre)))
               sign (cond ((and (equal v 0.0 1e-9) (= (bc:cfg cfg "영일때±") 1)) "±") ((< v 0) "-") (T "+"))))
        ((wcmatch pre "*-")
         (setq pre (substr pre 1 (1- (strlen pre))) sign (if (< v 0) "-" "")))
        (T (setq sign (if (< v 0) "-" ""))))
      (strcat pre sign num post))))

(defun bc:cee-core (ents basept pt cfg / d ss new ed s v dy ty out at)
  ;; ents(ename 목록)를 basept→pt로 복사하고, 숫자 있는 문자는 높이 차만큼 값을 바꾼다.
  (setq dy (/ (- (cadr pt) (cadr basept)) (bc:upm (bc:cfg cfg "축척"))))
  (foreach en ents
    (setq new (vla-Copy (vlax-ename->vla-object en)))
    (vla-Move new (vlax-3d-point basept) (vlax-3d-point pt))
    (setq ed (entget (vlax-vla-object->ename new)) ty (cdr (assoc 0 ed)))
    (cond
      ((and (= ty "TEXT") (setq s (cdr (assoc 1 ed))) (setq v (bc:num-in-text s)))
       (entmod (subst (cons 1 (bc:replace-last-num s (+ v dy) cfg)) (assoc 1 ed) ed)))
      ;; MTEXT: 서식 코드 안 숫자(\H0.8x; 등)를 바꾸지 않도록 본문만 꺼내 바꾼다 — 서식은 빠진다
      ((and (= ty "MTEXT") (setq s (bc:text-of (vlax-vla-object->ename new))) (setq v (bc:num-in-text s)))
       (vla-put-TextString new (bc:replace-last-num s (+ v dy) cfg)))
      ((and (= ty "INSERT") (= (bc:cfg cfg "속성포함") 1) (= (vla-get-HasAttributes new) :vlax-true))
       (foreach at (vlax-invoke new 'GetAttributes)
         (if (setq v (bc:num-in-text (setq s (vla-get-TextString at))))
           (vla-put-TextString at (bc:replace-last-num s (+ v dy) cfg))))))
    (setq out (cons (vla-get-Handle new) out)))
  (reverse out))

(defun c:CEE (/ cfg ss ents i bp p r)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "CEE" bc:cee-extra))
  (princ (strcat "\n<현재 설정 : 축척 = " (bc:rtos (bc:cfg cfg "축척") 2 3) ">"))
  (initget "E S")
  (setq r (entsel "\n숫자 있는 문자가 포함된 객체 선택(첫 객체) 또는 [축척 변경(E)/설정 변경(S)]: "))
  (cond
    ((= r "S") (bc:open-window "CEE") (bc:settings-hint "CEE"))
    ((= r "E")
     (if (setq r (getreal "\n축척 입력(1000=m 도면, 1=mm 도면): ")) (bc:cfg-save "CEE" (bc:cfg-set cfg "축척" r)))
     (bc:settings-hint "CEE"))
    (r
     (princ "\n나머지 객체를 더 고르세요(엔터=끝):")
     (setq ents (list (car r)))
     (if (setq ss (ssget))
       (progn (setq i 0) (while (< i (sslength ss)) (if (not (member (ssname ss i) ents)) (setq ents (cons (ssname ss i) ents))) (setq i (1+ i)))))
     (if (setq bp (getpoint "\n기준점 지정(표기된 EL 값의 위치): "))
       (progn
         (setq bp (bc:wcs bp))
         (while (setq p (getpoint bp "\nEL 표기점 지정: "))
           (bc:cee-core ents bp (bc:wcs p) cfg))))))
  (bc:end))

;;; ================================================================ GEL 두 점 사이 EL

(setq bc:gel-extra '(("거리표기" . 0) ("지시선" . 0) ("연속" . 1) ("점생성" . 0) ("점Z적용" . 0)))

(defun bc:gel-at (p1 z1 p2 z2 p / L t1)
  ;; p1(z1)-p2(z2) 직선에 p를 투영한 위치의 EL(연장 포함)과 p1부터 거리
  (setq L (distance (bc:2d p1) (bc:2d p2)))
  (if (< L 1e-9) (list z1 0.0)
    (progn
      (setq t1 (/ (+ (* (- (car p) (car p1)) (- (car p2) (car p1))) (* (- (cadr p) (cadr p1)) (- (cadr p2) (cadr p1)))) (* L L)))
      (list (+ z1 (* t1 (- z2 z1))) (* t1 L)))))

(defun bc:gel-core (p1 z1 p2 z2 p cfg / r el h lay s ents a)
  (setq r (bc:gel-at p1 z1 p2 z2 p) el (car r) h (bc:text-h cfg) lay (bc:cfg cfg "레이어") s (bc:el-str cfg el))
  (if (= (bc:cfg cfg "점생성") 1)
    (setq ents (cons (bc:point (list (car p) (cadr p) (if (= (bc:cfg cfg "점Z적용") 1) el 0.0)) lay) ents)))
  (if (= (bc:cfg cfg "지시선") 1)
    (setq a (polar p (/ pi 4) (* h 3))
          ents (cons (bc:pline (list p a (polar a 0.0 (* h 0.85 (max 4 (strlen s))))) nil lay) ents)
          ents (cons (bc:text (polar a (/ pi 2) (* h 0.3)) s h lay "BL" 0.0) ents))
    (setq ents (cons (bc:text (polar p (/ pi 2) (* h 0.6)) s h lay "BC" 0.0) ents)))
  (if (= (bc:cfg cfg "거리표기") 1)
    (setq ents (cons (bc:text (polar p (* pi 1.5) (* h 0.6)) (strcat "L=" (bc:rtos (/ (cadr r) (bc:upm (bc:cfg cfg "축척"))) 2 3)) h lay "TC" 0.0) ents)))
  (list el (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents)))

(defun bc:gel-interp-ok (en / ed ty)
  ;; 정점 보간이 되는 개체: 호(볼록)가 없는 LWPOLYLINE, 또는 POLYLINE(2D 직선·3D). 아니면 이유 문자열.
  (setq ed (entget en) ty (cdr (assoc 0 ed)))
  (cond ((= ty "LWPOLYLINE")
         (if (vl-some '(lambda (g) (and (= (car g) 42) (/= (cdr g) 0.0))) ed) "호(곡선)가 든 폴리선은 3D 폴리선으로 바꿀 수 없습니다" T))
        ((= ty "POLYLINE") T)
        (T "폴리선만 됩니다")))

(defun bc:gel-interp-verts (en p1 z1 p2 z2 / ed vs d1 d2 out head v)
  ;; 폴리선 정점 보간: 두 점 사이 정점에 곡선 거리 비례로 Z를 넣어 3D 폴리선으로 만든다.
  ;; 원본의 레이어·색·선종류·선굵기·닫힘을 이어받고, 새 폴리선을 다 만든 뒤에만 원본을 지운다.
  (setq ed (entget en) d1 (bc:dist-at en p1) d2 (bc:dist-at en p2) vs (bc:verts en))
  (setq out (mapcar '(lambda (v / d)
                       (setq d (vlax-curve-getDistAtPoint en (vlax-curve-getClosestPointTo en v)))
                       (if (and d (<= (min d1 d2) d (max d1 d2)) (> (abs (- d2 d1)) 1e-9))
                         (list (car v) (cadr v) (+ z1 (* (- z2 z1) (/ (- d d1) (- d2 d1)))))
                         v))
                    vs))
  (setq head (list '(0 . "POLYLINE") (assoc 8 ed) '(66 . 1)
                   (cons 70 (+ 8 (if (= 1 (logand 1 (cdr (assoc 70 ed)))) 1 0))) '(10 0.0 0.0 0.0)))
  (foreach g '(62 6 370 420 48) (if (assoc g ed) (setq head (append head (list (assoc g ed))))))
  (if (and (entmake head)
           (vl-every '(lambda (v) (entmake (list '(0 . "VERTEX") (assoc 8 ed) (cons 10 v) '(70 . 32)))) out)
           (entmake '((0 . "SEQEND"))))
    (progn (entdel en) (entlast))
    nil))

(defun c:GEL (/ cfg m p1 z1 p2 z2 p en t1 t2)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "GEL" bc:gel-extra))
  (initget "P T V S")
  (setq m (getkword "\n방식 [두 점(P)/두 문자(T)/폴리선 정점 보간(V)/설정(S)] <P>: "))
  (if (null m) (setq m "P"))
  (cond
    ((= m "S") (bc:open-window "GEL") (bc:settings-hint "GEL"))
    ((= m "V")
     (if (and (setq en (car (entsel "\n정점 EL 보간할 폴리선 선택: ")))
              (or (= (setq m (bc:gel-interp-ok en)) T) (progn (princ (strcat "\n" m ".")) nil))
              (setq p1 (getpoint "\nEL을 아는 첫 정점 지정: "))
              (setq z1 (bc:get-number-or-pick "그 점의 EL 문자 선택 또는 [EL 값 입력(E)]" "E" nil))
              (setq z1 (if (= z1 "E") (getreal "\nEL 값: ") z1))
              (setq p2 (getpoint "\nEL을 아는 둘째 정점 지정: "))
              (setq z2 (bc:get-number-or-pick "그 점의 EL 문자 선택 또는 [EL 값 입력(E)]" "E" nil))
              (setq z2 (if (= z2 "E") (getreal "\nEL 값: ") z2)))
       (progn (bc:gel-interp-verts en (bc:wcs p1) z1 (bc:wcs p2) z2) (princ "\n정점 Z 보간 완료(3D 폴리선)."))))
    (T
     (if (= m "T")
       (progn
         ;; 첫 선택을 취소하면 둘째를 묻지 않는다. 좌표는 정렬된 문자면 정렬점
         (if (and (setq t1 (car (entsel "\n시작 EL 문자 선택: "))) (setq t2 (car (entsel "\n끝 EL 문자 선택: "))))
           (setq p1 (car (bc:ent-points t1 T)) z1 (bc:num-in-text (bc:text-of t1))
                 p2 (car (bc:ent-points t2 T)) z2 (bc:num-in-text (bc:text-of t2)))))
       (progn
         (if (setq p1 (getpoint "\n시작점 지정: "))
           (progn (setq z1 (bc:get-number-or-pick "시작점 EL 문자 선택 또는 [EL 값 입력(E)]" "E" nil))
                  (if (= z1 "E") (setq z1 (getreal "\nEL 값: ")))))
         (if (and z1 (setq p2 (getpoint p1 "\n끝점 지정: ")))
           (progn (setq z2 (bc:get-number-or-pick "끝점 EL 문자 선택 또는 [EL 값 입력(E)]" "E" nil))
                  (if (= z2 "E") (setq z2 (getreal "\nEL 값: ")))))
         (if p1 (setq p1 (bc:wcs p1))) (if p2 (setq p2 (bc:wcs p2)))))
     (if (and p1 z1 p2 z2)
       (while (and (setq p (getpoint "\nEL 표기점 지정: ")) (progn (bc:gel-core p1 z1 p2 z2 (bc:wcs p) cfg) (= (bc:cfg cfg "연속") 1)))))))
  (bc:end))

;;; ================================================================ SLEL 경사로 평면 EL

(setq bc:slel-extra '(("방식" . "두점") ("경사입력" . "경사기본") ("정렬" . "BL") ("간격" . 0.5) ("여러점" . 1)))

(defun bc:slope-ratio (v mode pct)
  ;; 입력 경사를 높이/거리 비로. 경사 100 = 1:100 = 0.01, 퍼센트 1 = 0.01.
  (if pct (/ v 100.0) (if (zerop v) 0.0 (/ 1.0 v))))

(defun bc:slel-core (basept baseel slope pt en cfg / d el h s lay)
  ;; slope: 높이/거리 비(하향은 음수). en이 있으면 곡선 거리, 없으면 두 점 직선 거리.
  (setq d (if en (abs (- (bc:dist-at en pt) (bc:dist-at en basept))) (distance (bc:2d basept) (bc:2d pt)))
        el (+ baseel (* slope (/ d (bc:upm (bc:cfg cfg "축척")))))
        h (bc:text-h cfg) lay (bc:cfg cfg "레이어") s (bc:el-str cfg el))
  (list el (list (cdr (assoc 5 (entget (bc:text (polar pt (/ pi 4) (* h (bc:cfg cfg "간격"))) s h lay (bc:cfg cfg "정렬") 0.0)))))))

(defun bc:read-slope (cfg / s v mode pct)
  (setq mode (bc:cfg cfg "경사입력"))
  (setq s (getstring (strcat "\n" (cond ((= mode "퍼센트기본") "퍼센트 입력 (경사는 *붙임 예:100*)")
                                          ((= mode "항상퍼센트") "퍼센트 입력")
                                          ((= mode "항상경사") "경사 입력(1:100이면 100)")
                                          (T "경사 입력(1:100이면 100, % 는 *붙임 예:2*)"))
                             " (하향은 -): ")))
  (bc:parse-slope s mode))

(defun bc:parse-slope (s mode / neg p v pct)
  ;; "1:100"·"1/100"·"2%"는 형식 그대로, 숫자만이면 경사 입력 방식(*표시)에 따라. 하향은 앞에 -.
  (setq s (vl-string-trim " " s))
  (if (/= s "")
    (progn
      (setq neg (= (substr s 1 1) "-"))
      (if (member (substr s 1 1) '("-" "+")) (setq s (substr s 2)))
      (setq v (cond ((setq p (vl-string-search ":" s)) (/ (atof (substr s 1 p)) (max 1e-12 (atof (substr s (+ p 2))))))
                    ((setq p (vl-string-search "/" s)) (/ (atof (substr s 1 p)) (max 1e-12 (atof (substr s (+ p 2))))))
                    ((wcmatch s "*%") (/ (atof (vl-string-right-trim "%" s)) 100.0))
                    (T
                     (setq pct (cond ((= mode "항상퍼센트") T) ((= mode "항상경사") nil)
                                     ((= mode "퍼센트기본") (not (wcmatch s "*`*"))) (T (wcmatch s "*`*"))))
                     (bc:slope-ratio (atof (vl-string-trim "*" s)) mode pct))))
      (if neg (- v) v))))

(defun c:SLEL (/ cfg en r sl bp p)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "SLEL" bc:slel-extra))
  (princ (strcat "\n<현재 설정 : 평면축척 = " (bc:rtos (bc:cfg cfg "축척") 2 3) ", 문자높이 = " (bc:rtos (bc:cfg cfg "높이") 2 3)
                 ", 소수자리 = " (itoa (bc:cfg cfg "소수")) ">"))
  (initget "S")
  (setq en (if (= (bc:cfg cfg "방식") "선") (entsel "\n기준 선 선택 (없으면 두 점 선상) 또는 [설정 변경(S)]: ")))
  (cond
    ((= en "S") (bc:open-window "SLEL") (bc:settings-hint "SLEL"))
    (T
     (setq en (if (and en (bc:curve-p (car en))) (car en)))
     ;; 두 점 방식에서도 S로 설정 창을 열 수 있게
     (setq r (bc:get-number-or-pick "기준점 EL 문자 선택 또는 [EL 값 입력(E)/설정 변경(S)]" "E S" nil))
     (cond ((= r "E") (setq r (getreal "\n기준 EL 값: ")))
           ((= r "S") (bc:open-window "SLEL") (bc:settings-hint "SLEL") (setq r nil)))
     (if (and (numberp r) (setq sl (bc:read-slope cfg)) (setq bp (getpoint "\n기준점 지정: ")))
       (progn
         (setq bp (bc:wcs bp))
         (while (and (setq p (getpoint bp "\nEL 산출점 지정: "))
                     (progn (princ (strcat "\nEL = " (bc:rtos (car (bc:slel-core bp r sl (bc:wcs p) en cfg)) 2 4)))
                            (= (bc:cfg cfg "여러점") 1))))))))
  (bc:end))

;;; ================================================================ IEL 삼각망(3DFACE) EL

(setq bc:iel-extra '(("문자X" . 0.0) ("문자Y" . 0.25) ("정렬" . "BC") ("문자Z" . 0)))

(defun bc:face-z (f p / ed d)
  ;; 3DFACE f 안에 p가 있으면 Z, 없으면 nil. 사각 3D면(12≠13)은 두 번째 삼각형(10 12 13)도 본다.
  (setq ed (entget f) d (cdr (assoc 13 ed)))
  (cond ((bc:tri-z (cdr (assoc 10 ed)) (cdr (assoc 11 ed)) (cdr (assoc 12 ed)) p))
        ((not (equal d (cdr (assoc 12 ed)) 1e-9)) (bc:tri-z (cdr (assoc 10 ed)) (cdr (assoc 12 ed)) d p))))

(defun bc:tri-z (a b c p / det l1 l2 l3)
  (setq det (- (* (- (cadr b) (cadr c)) (- (car a) (car c))) (* (- (car b) (car c)) (- (cadr a) (cadr c)))))
  (if (> (abs det) 1e-12)
    (progn
      (setq l1 (/ (- (* (- (cadr b) (cadr c)) (- (car p) (car c))) (* (- (car b) (car c)) (- (cadr p) (cadr c)))) det)
            l2 (/ (- (* (- (cadr c) (cadr a)) (- (car p) (car c))) (* (- (car c) (car a)) (- (cadr p) (cadr c)))) det)
            l3 (- 1.0 l1 l2))
      (if (and (>= l1 -1e-9) (>= l2 -1e-9) (>= l3 -1e-9))
        (+ (* l1 (caddr a)) (* l2 (caddr b)) (* l3 (caddr c)))))))

(defun bc:tin-z (p / ss i z d)
  ;; p 둘레 작은 창 안의 3DFACE 중 p를 품은 것의 Z
  (setq d 0.001)
  (if (setq ss (ssget "_C" (list (- (car p) d) (- (cadr p) d)) (list (+ (car p) d) (+ (cadr p) d)) '((0 . "3DFACE"))))
    (progn (setq i 0)
           (while (and (null z) (< i (sslength ss))) (setq z (bc:face-z (ssname ss i) p) i (1+ i)))))
  (if (null z)
    (if (setq ss (ssget "_X" '((0 . "3DFACE"))))
      (progn (setq i 0)
             (while (and (null z) (< i (sslength ss))) (setq z (bc:face-z (ssname ss i) p) i (1+ i))))))
  z)

(defun bc:iel-core (p cfg / z h s lay e)
  (if (setq z (bc:tin-z p))
    (progn
      (setq h (bc:text-h cfg) lay (bc:cfg cfg "레이어") s (bc:el-str cfg z)
            e (bc:text (list (+ (car p) (* h (bc:cfg cfg "문자X") 4)) (+ (cadr p) (* h (bc:cfg cfg "문자Y") 4))
                             (if (= (bc:cfg cfg "문자Z") 1) z 0.0))
                       s h lay (bc:cfg cfg "정렬") 0.0))
      (list z (list (cdr (assoc 5 (entget e))))))
    (list nil nil)))

(defun c:IEL (/ cfg m p ss i en ed pt)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:el-cfg "IEL" bc:iel-extra))
  (initget "P O S")
  (setq m (getkword "\n방식 [점 지정(P)/객체(블록·원·점) 선택(O)/설정(S)] <P>: "))
  (cond
    ((= m "S") (bc:open-window "IEL") (bc:settings-hint "IEL"))
    ((= m "O")
     (if (setq ss (ssget '((0 . "INSERT,CIRCLE,POINT"))))
       (progn (setq i 0)
              (while (< i (sslength ss))
                (setq en (ssname ss i) ed (entget en) pt (cdr (assoc 10 ed)))
                (if (null (car (bc:iel-core pt cfg))) (princ "\n삼각망 밖 객체를 건너뜀."))
                (setq i (1+ i))))))
    (T
     (while (setq p (getpoint "\n삼각망 안의 EL 표기점 지정: "))
       (if (null (car (bc:iel-core (bc:wcs p) cfg))) (princ "\n그 점을 품은 삼각망(3D면)이 없습니다.")))))
  (bc:end))
