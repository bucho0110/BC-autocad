;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_terrain.lsp — 지형 명령 (WCZ DSEL DCON)
;;; WCZ: 낮은 쪽→높은 쪽 두 점을 지나는 등고선마다 높이를 등고선 방향으로 쓴다.
;;; DSEL: 고른 객체의 점 중 EL 조건에 맞는 곳에 원(과 연결선)을 그린다.
;;; DCON: 등고선을 높이 간격별 레이어(머리말+높이)로 나누고 높이 순으로 명도가 낮아지는 색을 준다.
;;; 등고선 높이: LWPOLYLINE은 고도(38), LINE·SPLINE은 첫 점 Z, 3D 폴리선은 첫 정점 Z.

;;; ================================================================ 공통

(defun bc:con-z (en / ed ty)
  (setq ed (entget en) ty (cdr (assoc 0 ed)))
  (cond ((= ty "LWPOLYLINE") (if (assoc 38 ed) (cdr (assoc 38 ed)) 0.0))
        ((member ty '("LINE" "SPLINE")) (cadddr (assoc 10 ed)))
        ((= ty "POLYLINE") (caddr (car (bc:verts en))))
        (T nil)))

(defun bc:multiple-p (v step)
  ;; v가 step의 배수인가(step ≤ 0이면 늘 참)
  (or (<= step 0.0) (< (abs (- (/ v step) (fix (+ (/ v step) (if (< v 0) -0.5 0.5))))) 1e-6)))

(defun bc:num-str (v / s)
  ;; 끝 0을 뺀 숫자 글자: 25.0 → "25", 12.5 → "12.5"
  (setq s (bc:rtos v 2 6))
  (if (vl-string-search "." s)
    (progn (while (= (substr s (strlen s)) "0") (setq s (substr s 1 (1- (strlen s)))))
           (if (= (substr s (strlen s)) ".") (setq s (substr s 1 (1- (strlen s)))))))
  s)

(defun bc:ss-list (ss / i out)
  (if ss (progn (setq i (sslength ss)) (while (> i 0) (setq i (1- i) out (cons (ssname ss i) out)))))
  out)

;;; ================================================================ WCZ 등고선 높이 쓰기

(setq bc:wcz-defaults
  '(("높이" . 1.0) ("소수" . 0) ("레이어" . "등고선_표고") ("색" . 7) ("단위만" . 0) ("단위" . 5.0)
    ("마스크" . 0) ("마스크비율" . 1.5) ("Z0제외" . 1) ("등고선레이어" . "")))

(defun bc:wcz-text (pt s h lay rot cfg)
  (if (= (bc:cfg cfg "마스크") 1)
    (progn
      (entmake (list '(0 . "MTEXT") '(100 . "AcDbEntity") (cons 8 (bc:layer lay)) '(100 . "AcDbMText")
                     (cons 10 pt) (cons 40 h) (cons 41 0.0) (cons 71 5) (cons 1 s) (cons 7 (getvar "TEXTSTYLE"))
                     (cons 50 rot) (cons 90 3) (cons 63 256) (cons 45 (bc:cfg cfg "마스크비율")) (cons 441 0)))
      (entlast))
    (bc:text pt s h lay "MC" rot)))

(defun bc:wcz-core (p1 p2 cfg / flt ss en z hits seen pt prm dv rot n up lay)
  ;; p1(낮은 쪽)→p2(높은 쪽) 선분이 지나는 등고선마다 높이 문자를 등고선 방향으로, 글자 위쪽이 높은 쪽을 보게 쓴다.
  ;; 쓴 문자 수.
  (setq flt (list (cons 0 "LWPOLYLINE,POLYLINE,SPLINE,LINE") (cons 410 "Model")) n 0 up (angle p1 p2)
        lay (bc:cfg cfg "레이어"))
  (if (/= (bc:cfg cfg "등고선레이어") "") (setq flt (append flt (list (cons 8 (bc:cfg cfg "등고선레이어"))))))
  (if (/= lay "") (bc:ensure-layer lay (bc:cfg cfg "색")))
  (foreach en (bc:ss-list (ssget "_X" flt))
    (setq z (bc:con-z en))
    (if (and z (not (and (= (bc:cfg cfg "Z0제외") 1) (<= z 0.0)))
             (or (/= (bc:cfg cfg "단위만") 1) (bc:multiple-p z (bc:cfg cfg "단위"))))
      (progn
        (setq hits (bc:hits (list (car p1) (cadr p1) z) (list (car p2) (cadr p2) z) en) seen nil)
        (foreach h hits
          (if (not (vl-some '(lambda (q) (< (distance (bc:2d q) (bc:2d h)) 1e-9)) seen))
            (progn
              (setq seen (cons h seen)
                    pt (vlax-curve-getClosestPointTo en (list (car h) (cadr h) z))
                    prm (vlax-curve-getParamAtPoint en pt)
                    dv (if prm (vlax-curve-getFirstDeriv en prm)))
              (setq rot (if dv (angle '(0.0 0.0) (list (car dv) (cadr dv))) (+ up (/ pi 2))))
              ;; 글자 위쪽(rot + 90°)이 높은 쪽(up)을 보게
              (if (< (cos (- (+ rot (/ pi 2)) up)) 0.0) (setq rot (+ rot pi)))
              (bc:wcz-text (list (car h) (cadr h) 0.0) (bc:rtos z 2 (bc:cfg cfg "소수")) (bc:cfg cfg "높이") lay rot cfg)
              (setq n (1+ n))))))))
  n)

(defun c:WCZ (/ cfg p1 p2 n)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "WCZ" bc:wcz-defaults) n 0)
  (initget "S")
  (setq p1 (getpoint "\n낮은 쪽 점 지정 또는 [설정 변경(S)]: "))
  (if (= p1 "S")
    (progn (bc:open-window "WCZ") (bc:settings-hint "WCZ"))
    (while (and p1 (setq p2 (getpoint p1 "\n높은 쪽 점 지정: ")))
      (setq n (+ n (bc:wcz-core (bc:wcs p1) (bc:wcs p2) cfg)))
      (princ (strcat "\n[BC] 높이 문자 " (itoa n) "개."))
      (setq p1 (getpoint "\n다음 낮은 쪽 점 지정 (끝내려면 엔터): "))))
  (bc:end))

;;; ================================================================ DSEL EL 조건 점 표시

(setq bc:dsel-defaults
  '(("대상점" . 1) ("대상블록" . 1) ("대상선" . 1) ("대상문자" . 0) ("제외레이어" . "") ("조건" . "=") ("EL" . 0.0)
    ("원" . 1) ("반지름" . 1.0) ("연결선" . 0) ("레이어" . "EL조건표시") ("색" . 1)))

(defun bc:dsel-filter (cfg / ty)
  (setq ty "")
  (foreach k '(("대상점" . "POINT") ("대상블록" . "INSERT") ("대상선" . "LINE,LWPOLYLINE,POLYLINE") ("대상문자" . "TEXT,MTEXT"))
    (if (= (bc:cfg cfg (car k)) 1) (setq ty (strcat ty (if (= ty "") "" ",") (cdr k)))))
  (append (list (cons 0 (if (= ty "") "POINT" ty)))
          (if (/= (bc:cfg cfg "제외레이어") "")
            (list '(-4 . "<NOT") (cons 8 (bc:cfg cfg "제외레이어")) '(-4 . "NOT>")))))

(defun bc:dsel-match (z cfg / el c)
  (setq el (bc:cfg cfg "EL") c (bc:cfg cfg "조건"))
  (cond ((= c "=") (equal z el 1e-9)) ((= c "<>") (not (equal z el 1e-9)))
        ((= c ">") (> z (+ el 1e-9))) ((= c ">=") (>= z (- el 1e-9)))
        ((= c "<") (< z (- el 1e-9))) ((= c "<=") (<= z (+ el 1e-9)))
        (T nil)))

(defun bc:dsel-find (enames cfg / out)
  ;; 조건에 맞는 점(WCS, 같은 점은 한 번) 목록
  (foreach en enames
    (foreach p (bc:ent-points en nil)
      (if (and (bc:dsel-match (if (caddr p) (caddr p) 0.0) cfg)
               (not (vl-some '(lambda (q) (equal q p 1e-9)) out)))
        (setq out (cons p out)))))
  (reverse out))

(defun bc:dsel-core (enames center cfg / pts lay)
  ;; 찾은 점에 원, center가 있으면 그 점에서 각 점으로 연결선. 찾은 점 수.
  (setq pts (bc:dsel-find enames cfg) lay (bc:cfg cfg "레이어"))
  (if (/= lay "") (bc:ensure-layer lay (bc:cfg cfg "색")))
  (foreach p pts
    (if (= (bc:cfg cfg "원") 1) (bc:circle p (bc:cfg cfg "반지름") lay))
    (if center (bc:line center p lay)))
  (length pts))

(defun c:DSEL (/ cfg ss pts c)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "DSEL" bc:dsel-defaults))
  (princ (strcat "\n<EL " (bc:cfg cfg "조건") " " (bc:num-str (bc:cfg cfg "EL")) "> 점 찾을 객체 선택(설정은 엔터 후 S): "))
  (if (setq ss (ssget (bc:dsel-filter cfg)))
    (progn
      (setq pts (bc:dsel-find (bc:ss-list ss) cfg))
      (if (and pts (= (bc:cfg cfg "연결선") 1)) (setq c (getpoint "\n찾은 점을 이을 연결선 위치 점 지정: ")))
      (princ (strcat "\n[BC] 조건에 맞는 점 "
                     (itoa (bc:dsel-core (bc:ss-list ss) (if c (bc:wcs c)) cfg)) "개를 표시했습니다.")))
    (progn (initget "S") (if (= (getkword "\n[설정 변경(S)] <끝>: ") "S") (progn (bc:open-window "DSEL") (bc:settings-hint "DSEL")))))
  (bc:end))

;;; ================================================================ DCON 등고선 높이별 레이어

(setq bc:dcon-defaults
  '(("간격" . 5.0) ("머리말" . "CON-") ("색단계" . 1) ("시작색" . "247,253,247") ("명도단계" . 2.0)))

(defun bc:rgb->hsl (r g b / mx mn l d s h)
  (setq r (/ r 255.0) g (/ g 255.0) b (/ b 255.0) mx (max r g b) mn (min r g b) l (/ (+ mx mn) 2.0))
  (if (equal mx mn 1e-12)
    (list 0.0 0.0 l)
    (progn
      (setq d (- mx mn) s (if (> l 0.5) (/ d (- 2.0 mx mn)) (/ d (+ mx mn))))
      (setq h (cond ((equal mx r 1e-12) (+ (/ (- g b) d) (if (< g b) 6.0 0.0)))
                    ((equal mx g 1e-12) (+ (/ (- b r) d) 2.0))
                    (T (+ (/ (- r g) d) 4.0))))
      (list (/ h 6.0) s l))))

(defun bc:hue (p q tt)
  (if (< tt 0.0) (setq tt (+ tt 1.0)))
  (if (> tt 1.0) (setq tt (- tt 1.0)))
  (cond ((< tt (/ 1.0 6)) (+ p (* (- q p) 6.0 tt))) ((< tt 0.5) q)
        ((< tt (/ 2.0 3)) (+ p (* (- q p) (- (/ 2.0 3) tt) 6.0))) (T p)))

(defun bc:hsl->rgb (h s l / q p)
  (if (<= s 0.0)
    (list (fix (+ (* l 255) 0.5)) (fix (+ (* l 255) 0.5)) (fix (+ (* l 255) 0.5)))
    (progn
      (setq q (if (< l 0.5) (* l (+ 1.0 s)) (- (+ l s) (* l s))) p (- (* 2.0 l) q))
      (mapcar '(lambda (v) (fix (+ (* v 255) 0.5)))
              (list (bc:hue p q (+ h (/ 1.0 3))) (bc:hue p q h) (bc:hue p q (- h (/ 1.0 3))))))))

(defun bc:parse-rgb (s / out)
  (foreach v (vl-remove "" (bc:split-comma s)) (setq out (cons (atoi v) out)))
  (if (= (length out) 3) (reverse out) '(247 253 247)))

(defun bc:split-comma (s / p out)
  (while (setq p (vl-string-search "," s)) (setq out (cons (vl-string-trim " " (substr s 1 p)) out) s (substr s (+ p 2))))
  (reverse (cons (vl-string-trim " " s) out)))

(defun bc:layer-truecolor (name rgb / e)
  (setq e (entget (tblobjname "LAYER" name)))
  (setq e (vl-remove-if '(lambda (x) (= (car x) 420)) e))
  (entmod (append e (list (cons 420 (+ (* 65536 (car rgb)) (* 256 (cadr rgb)) (caddr rgb)))))))

(defun bc:dcon-core (enames cfg / step zs lv hsl i name n rgb)
  ;; 간격의 배수 높이 등고선만 '머리말+높이' 레이어로 옮긴다. 옮긴 객체 수.
  (setq step (bc:cfg cfg "간격") n 0)
  (foreach en enames
    (if (and (setq lv (bc:con-z en)) (bc:multiple-p lv step) (not (member lv zs))) (setq zs (cons lv zs))))
  (setq zs (vl-sort zs '<) hsl (apply 'bc:rgb->hsl (bc:parse-rgb (bc:cfg cfg "시작색"))) i 0)
  (foreach lv zs
    (setq name (strcat (bc:cfg cfg "머리말") (bc:num-str lv)))
    (bc:ensure-layer name 7)
    (if (= (bc:cfg cfg "색단계") 1)
      (bc:layer-truecolor name (bc:hsl->rgb (car hsl) (cadr hsl)
                                            (max 0.0 (- (caddr hsl) (* i (/ (bc:cfg cfg "명도단계") 100.0)))))))
    (setq i (1+ i)))
  (foreach en enames
    (if (and (setq lv (bc:con-z en)) (bc:multiple-p lv step)
             (not (vl-catch-all-error-p (vl-catch-all-apply 'vla-put-Layer
                     (list (vlax-ename->vla-object en) (strcat (bc:cfg cfg "머리말") (bc:num-str lv)))))))
      (setq n (1+ n))))
  n)

(defun c:DCON (/ cfg ss)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "DCON" bc:dcon-defaults))
  (princ (strcat "\n<간격 " (bc:num-str (bc:cfg cfg "간격")) "m> 높이별 레이어로 나눌 등고선 선택(설정은 엔터 후 S): "))
  (if (setq ss (ssget '((0 . "LWPOLYLINE,POLYLINE,SPLINE,LINE"))))
    (princ (strcat "\n[BC] 등고선 " (itoa (bc:dcon-core (bc:ss-list ss) cfg)) "개를 높이별 레이어로 옮겼습니다."))
    (progn (initget "S") (if (= (getkword "\n[설정 변경(S)] <끝>: ") "S") (progn (bc:open-window "DCON") (bc:settings-hint "DCON")))))
  (bc:end))
