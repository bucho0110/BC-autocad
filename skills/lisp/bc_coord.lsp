;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_coord.lsp — 좌표 명령 (XY ZBC WCD) + 수정 XYB
;;; 토목 좌표: X = CAD의 Y, Y = CAD의 X. 수학 좌표: CAD 그대로.

(setq bc:xy-defaults
  '(("좌표" . "토목") ("레이어" . "") ("높이" . 2.5) ("DIMSCALE적용" . 0) ("소수" . 3) ("Z표기" . 0) ("Z소수" . 3)
    ("mm를m로" . 0) ("천단위" . 0) ("XY문자" . 1) ("구분" . "=") ("X문자" . "X") ("Y문자" . "Y") ("Z문자" . "Z")
    ("화살표" . 0) ("화살표길이" . 1.0) ("음수를양수로" . 0) ("WCS" . 1) ("방향점지정" . 0) ("축척" . 1000.0)))

(defun bc:xy-h (cfg)
  ;; 좌표 문자 높이는 도면 단위 그대로(축척 환산 없음)
  (if (= (bc:cfg cfg "DIMSCALE적용") 1) (* (getvar "DIMTXT") (max 1e-9 (getvar "DIMSCALE"))) (bc:cfg cfg "높이")))

(defun bc:xy-num (v cfg dec)
  (if (= (bc:cfg cfg "mm를m로") 1) (setq v (/ v 1000.0)))
  (if (= (bc:cfg cfg "음수를양수로") 1) (setq v (abs v)))
  (if (= (bc:cfg cfg "천단위") 1) (bc:fmt-thousands v dec) (bc:rtos v 2 dec)))

(defun bc:xy-strings (p cfg / a b lx ly out)
  ;; p(WCS) → 표기 문자열 목록 (윗줄부터)
  (if (= (bc:cfg cfg "좌표") "토목") (setq a (cadr p) b (car p)) (setq a (car p) b (cadr p)))
  (setq lx (if (= (bc:cfg cfg "XY문자") 1) (strcat (bc:cfg cfg "X문자") (bc:cfg cfg "구분")) "")
        ly (if (= (bc:cfg cfg "XY문자") 1) (strcat (bc:cfg cfg "Y문자") (bc:cfg cfg "구분")) ""))
  (setq out (list (strcat lx (bc:xy-num a cfg (bc:cfg cfg "소수"))) (strcat ly (bc:xy-num b cfg (bc:cfg cfg "소수")))))
  (if (= (bc:cfg cfg "Z표기") 1)
    (setq out (append out (list (strcat (if (= (bc:cfg cfg "XY문자") 1) (strcat (bc:cfg cfg "Z문자") (bc:cfg cfg "구분")) "")
                                        (bc:rtos (caddr p) 2 (bc:cfg cfg "Z소수")))))))
  out)

(defun bc:xy-core (p p2 cfg dpt / h lay ss w dir end y ents i)
  ;; p: 좌표점(WCS), p2: 지시선 꺾임점, dpt: 방향점(nil이면 꺾임점이 좌표점의 어느 쪽인지로).
  ;; 문자는 꺾임점에서 바깥쪽으로 밑줄을 긋고 그 위·아래에 쓴다. 'WCS' 설정이 0이면 현재 UCS 좌표로 쓴다.
  (setq h (bc:xy-h cfg) lay (bc:cfg cfg "레이어")
        ss (bc:xy-strings (if (= (bc:cfg cfg "WCS") 1) p (trans p 0 1)) cfg)
        w (* h 0.85 (apply 'max (mapcar 'strlen ss)))
        dir (if (< (car (if dpt dpt p2)) (car (if dpt p2 p))) pi 0.0)
        end (polar p2 dir w))
  (setq ents (list (bc:pline (list p p2 end) nil lay)))
  (if (= (bc:cfg cfg "화살표") 1)
    (setq ents (cons (bc:arrow p (angle p2 p) (* h (bc:cfg cfg "화살표길이")) lay) ents)))
  (setq ents (cons (bc:text (polar (polar p2 dir (* h 0.3)) (/ pi 2) (* h 0.35)) (car ss) h lay (if (= dir pi) "BR" "BL") 0.0) ents))
  (setq i 1 y (* h 0.35))
  (foreach s (cdr ss)
    (setq ents (cons (bc:text (polar (polar p2 dir (* h 0.3)) (* pi 1.5) (+ y (* (1- i) h 1.6))) s h lay (if (= dir pi) "TR" "TL") 0.0) ents)
          i (1+ i)))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:XY (/ cfg p p2 dp)
  (bc:begin '("ORTHOMODE"))
  (setvar "ORTHOMODE" 0)
  (setq cfg (bc:cfg-load "XY" bc:xy-defaults))
  (princ (strcat "\n<현재 설정 : " (bc:cfg cfg "좌표") " 좌표, 높이 = " (bc:rtos (bc:xy-h cfg) 2 3) ", 소수 = " (itoa (bc:cfg cfg "소수")) ">"))
  (while (progn (initget "S") (setq p (getpoint "\n좌표를 표기할 점 지정 또는 [설정 변경(S)]: ")))
    (if (= p "S")
      (progn (bc:open-window "XY") (bc:settings-hint "XY") (setq p nil))
      (if (setq p2 (getpoint p "\n지시선 다음 점 지정: "))
        (progn
          (setq dp (if (= (bc:cfg cfg "방향점지정") 1) (getpoint p2 "\n지시선 방향점 지정(좌·우만 봄): ")))
          (bc:xy-core (bc:wcs p) (bc:wcs p2) cfg (if dp (bc:wcs dp)))))))
  (bc:end))

;;; ================================================================ ZBC 경계 좌표표

(setq bc:zbc-defaults
  '(("좌표" . "토목") ("레이어" . "") ("높이" . 2.5) ("소수" . 3) ("번호표기" . 1) ("번호머리" . "") ("시작번호" . 1)
    ("행높이배수" . 2.0) ("DIMSCALE적용" . 0)))

(defun bc:zbc-core (en tp cfg / vs h lay rh cw n x0 y0 i a b ents row p r c v)
  ;; en 폴리선 정점 좌표를 tp(표 왼쪽 위)에 [번호|X|Y] 표로 그린다. 정점에도 번호를 쓴다.
  (setq vs (bc:verts en) h (bc:xy-h cfg) lay (bc:cfg cfg "레이어")
        rh (* h (bc:cfg cfg "행높이배수")) cw (list (* h 5) (* h 12) (* h 12))
        n (bc:cfg cfg "시작번호") x0 (car tp) y0 (cadr tp))
  ;; 머리글
  (setq row (list "No" "X" "Y"))
  (setq i 0)
  (foreach r (cons row (mapcar '(lambda (v / s) (setq s (if (= (bc:cfg cfg "좌표") "토목") (list (cadr v) (car v)) (list (car v) (cadr v))))
                                   (list nil (bc:rtos (car s) 2 (bc:cfg cfg "소수")) (bc:rtos (cadr s) 2 (bc:cfg cfg "소수")))) vs))
    (setq a (- y0 (* i rh)) b x0)
    (setq ents (cons (bc:text (list (+ b (/ (car cw) 2)) (- a (/ rh 2)) 0.0)
                              (if (car r) (car r) (strcat (bc:cfg cfg "번호머리") (itoa (+ n i -1)))) h lay "MC" 0.0) ents))
    (setq ents (cons (bc:text (list (+ b (car cw) (/ (cadr cw) 2)) (- a (/ rh 2)) 0.0) (cadr r) h lay "MC" 0.0) ents))
    (setq ents (cons (bc:text (list (+ b (car cw) (cadr cw) (/ (caddr cw) 2)) (- a (/ rh 2)) 0.0) (caddr r) h lay "MC" 0.0) ents))
    (setq i (1+ i)))
  ;; 칸 선
  (setq i 0)
  (repeat (1+ (1+ (length vs)))
    (setq ents (cons (bc:line (list x0 (- y0 (* i rh)) 0.0) (list (+ x0 (apply '+ cw)) (- y0 (* i rh)) 0.0) lay) ents) i (1+ i)))
  (setq b x0)
  (foreach c (cons 0.0 cw)
    (setq b (+ b c))
    (setq ents (cons (bc:line (list b y0 0.0) (list b (- y0 (* (1+ (length vs)) rh)) 0.0) lay) ents)))
  ;; 정점 번호
  (if (= (bc:cfg cfg "번호표기") 1)
    (progn (setq i 0)
           (foreach v vs
             (setq ents (cons (bc:text (polar v (/ pi 4) (* h 0.8)) (strcat (bc:cfg cfg "번호머리") (itoa (+ n i))) h lay "BL" 0.0) ents)
                   i (1+ i)))))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:ZBC (/ cfg en tp)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "ZBC" bc:zbc-defaults))
  (initget "S")
  (setq en (entsel "\n경계 폴리선 선택 또는 [설정 변경(S)]: "))
  (cond ((= en "S") (bc:open-window "ZBC") (bc:settings-hint "ZBC"))
        ((and en (bc:verts (car en)) (setq tp (getpoint "\n좌표표 왼쪽 위 점 지정: ")))
         (bc:zbc-core (car en) (bc:wcs tp) cfg)))
  (bc:end))

;;; ================================================================ WCD 도곽 경계 좌표 쓰기

(setq bc:wcd-defaults '(("좌표" . "토목") ("레이어" . "") ("높이" . 2.5) ("소수" . 0) ("간격" . 1.0) ("DIMSCALE적용" . 0)))

(defun bc:wcd-core (en cfg / vs h lay g mn mx ents xs ys c)
  ;; 사각 경계(폴리선) 네 모서리 바깥에 좌표를 쓴다. 가로변에는 CAD X, 세로변에는 CAD Y.
  (setq vs (bc:verts en) h (bc:xy-h cfg) lay (bc:cfg cfg "레이어") g (* h (bc:cfg cfg "간격"))
        xs (mapcar 'car vs) ys (mapcar 'cadr vs)
        mn (list (apply 'min xs) (apply 'min ys) 0.0) mx (list (apply 'max xs) (apply 'max ys) 0.0))
  (foreach c (list (list (car mn) (cadr mn)) (list (car mx) (cadr mn)) (list (car mx) (cadr mx)) (list (car mn) (cadr mx)))
    (setq ents (cons (bc:text (list (car c) (if (= (cadr c) (cadr mn)) (- (cadr c) g) (+ (cadr c) g)) 0.0)
                              (strcat (if (= (bc:cfg cfg "좌표") "토목") "Y=" "X=") (bc:rtos (car c) 2 (bc:cfg cfg "소수")))
                              h lay (if (= (cadr c) (cadr mn)) "TC" "BC") 0.0) ents))
    (setq ents (cons (bc:text (list (if (= (car c) (car mn)) (- (car c) g) (+ (car c) g)) (cadr c) 0.0)
                              (strcat (if (= (bc:cfg cfg "좌표") "토목") "X=" "Y=") (bc:rtos (cadr c) 2 (bc:cfg cfg "소수")))
                              h lay (if (= (car c) (car mn)) "MR" "ML") 0.0) ents)))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:WCD (/ cfg en)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "WCD" bc:wcd-defaults))
  (initget "S")
  (setq en (entsel "\n사각 도곽 경계(폴리선) 선택 또는 [설정 변경(S)]: "))
  (cond ((= en "S") (bc:open-window "WCD") (bc:settings-hint "WCD"))
        ((and en (bc:verts (car en))) (bc:wcd-core (car en) cfg)))
  (bc:end))

;;; ================================================================ XYB X·Y 축척 다르게

(defun bc:xyb-check (enames sx sy / bad lay)
  ;; 원본을 지우기 전에 막을 것: 축척 0, 잠긴 레이어(지울 수 없어 일부만 바뀐 채 멈춘다 —). 문제면 이유 문자열.
  (cond ((or (equal sx 0.0 1e-12) (equal sy 0.0 1e-12)) "X·Y 축척은 0이 될 수 없습니다")
        ((vl-some '(lambda (e) (setq lay (tblsearch "LAYER" (cdr (assoc 8 (entget e)))))
                     (and lay (= 4 (logand 4 (cdr (assoc 70 lay)))))) enames)
         "잠긴 레이어의 객체가 섞여 있습니다. 잠금을 풀고 다시 하세요")
        (T nil)))

(defun bc:xyb-core (enames base sx sy / doc blks name blk objs arr ins exp out o why)
  ;; 객체들을 임시 블록으로 묶어 X·Y 축척을 다르게 삽입한 뒤 폭파한다. 원본·임시 블록은 지운다.
  ;; 폭파가 끝난 뒤에만 원본을 지운다. 검사에 걸리면 아무것도 바꾸지 않고 오류.
  (if (setq why (bc:xyb-check enames sx sy)) (progn (princ (strcat "\n" why ".")) (exit)))
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object))
        blks (vla-get-Blocks doc)
        name (strcat "BC_XYB_" (bc:rtos (getvar "CDATE") 2 8)))
  (setq name (vl-string-translate "." "_" name))
  (setq blk (vla-Add blks (vlax-3d-point base) name))
  (setq objs (mapcar 'vlax-ename->vla-object enames))
  (setq arr (vlax-make-safearray vlax-vbObject (cons 0 (1- (length objs)))))
  (vlax-safearray-fill arr objs)
  (vla-CopyObjects doc arr blk)
  (setq ins (vla-InsertBlock (vla-get-ModelSpace doc) (vlax-3d-point base) name sx sy 1.0 0.0))
  ;; Explode가 돌려주는 배열은 비균일 축척일 때 원소 접근이 실패한다(실측) — 새로 생긴 개체를 entnext로 모은다.
  (setq exp (entlast))
  (vla-Explode ins)
  (while (setq exp (entnext exp))
    (if (not (member (cdr (assoc 0 (entget exp))) '("ATTRIB" "VERTEX" "SEQEND")))
      (setq out (cons (cdr (assoc 5 (entget exp))) out))))
  (vla-Delete ins)
  (foreach o objs (vla-Delete o))
  (vl-catch-all-apply 'vla-Delete (list blk))
  (reverse out))

(defun c:XYB (/ ss l i base sx sy)
  (bc:begin nil)
  (princ "\nX·Y 축척을 다르게 할 객체 선택: ")
  (if (and (setq ss (ssget))
           (setq base (getpoint "\n기준점 지정: "))
           (setq sx (getreal "\nX 축척: "))
           (setq sy (getreal "\nY 축척: ")))
    (progn
      (setq i 0)
      (while (< i (sslength ss)) (setq l (cons (ssname ss i) l) i (1+ i)))
      (bc:xyb-core l (bc:wcs base) sx sy)
      (princ (strcat "\n" (itoa (length l)) "개 객체를 X " (bc:rtos sx 2 4) ", Y " (bc:rtos sy 2 4) " 배로 바꿨습니다."))))
  (bc:end))

;;; ================================================================ 좌표 덤프 (CEX 창·MCP가 쓴다)

(defun bc:ent-points (en usealign / ed ty)
  ;; 객체 종류별 좌표(WCS): 선·폴리선=정점, 문자=삽입점(또는 정렬점), 점·블록=삽입점, 원·호=중심
  (setq ed (entget en) ty (cdr (assoc 0 ed)))
  (cond ((member ty '("LINE" "LWPOLYLINE" "POLYLINE")) (bc:verts en))
        ((= ty "TEXT")
         (list (trans (if (and usealign (or (/= 0 (cdr (assoc 72 ed))) (/= 0 (cdr (assoc 73 ed)))))
                        (cdr (assoc 11 ed)) (cdr (assoc 10 ed))) en 0)))
        ((= ty "MTEXT") (list (cdr (assoc 10 ed))))
        ((member ty '("POINT")) (list (cdr (assoc 10 ed))))
        ((member ty '("INSERT" "CIRCLE" "ARC")) (list (trans (cdr (assoc 10 ed)) en 0)))
        (T nil)))

(defun bc:dump-ent (en usealign fp / ed tx p)
  ;; ENT<탭>핸들<탭>종류<탭>레이어<탭>문자 , 이어서 P<탭>x<탭>y<탭>z 줄들
  (setq ed (entget en) tx (bc:text-of en))
  (write-line (strcat "ENT\t" (cdr (assoc 5 ed)) "\t" (cdr (assoc 0 ed)) "\t" (cdr (assoc 8 ed)) "\t"
                      (if tx (vl-string-translate "\t\n\r" "   " tx) "")) fp)
  (foreach p (bc:ent-points en usealign)
    (write-line (strcat "P\t" (bc:rtos (car p) 2 10) "\t" (bc:rtos (cadr p) 2 10) "\t" (bc:rtos (if (caddr p) (caddr p) 0.0) 2 10)) fp)))

(defun bc:dump-ss (ss usealign fp / i)
  (if ss (progn (setq i 0) (while (< i (sslength ss)) (bc:dump-ent (ssname ss i) usealign fp) (setq i (1+ i))))))
