;;; bc_core.lsp — 스킬 명령 공통 함수 (UTF-8)
;;; AutoCAD 시작 때 bc_autocad.lsp가 (load)하고, MCP·창은 한 줄 사본을 eval한다.
;;; 전역 *bc-root*(패키지 폴더), *bc-pyw*(pythonw.exe)는 불러오는 쪽이 정한다.

(vl-load-com)

;;; ---------------------------------------------------------------- 설정 파일
;;; %LOCALAPPDATA%/bc-autocad/settings/<명령>.txt — 한 줄에 키=값. 창(파이썬)과 같은 파일.

(defun bc:cfg-path (cmd)
  (strcat (getenv "LOCALAPPDATA") "\\bc-autocad\\settings\\" (strcase cmd) ".txt"))

(defun bc:cfg-load (cmd defaults / f ln pos k v d out)
  ;; defaults: ((키 . 기본값) ...). 저장값은 기본값 형식(문자/정수/실수)으로 바꾼다.
  (setq out defaults)
  (if (and (findfile (bc:cfg-path cmd)) (setq f (open (bc:cfg-path cmd) "r" "utf8")))
    (progn
      (while (setq ln (read-line f))
        (if (setq pos (vl-string-search "=" ln))
          (progn
            (setq k (substr ln 1 pos) v (substr ln (+ pos 2)) d (assoc k out))
            (if d
              (setq out (subst (cons k (bc:as-type v (cdr d))) d out))))))
      (close f)))
  out)

(defun bc:as-type (s like)
  (cond ((= (type like) 'INT) (atoi s))
        ((= (type like) 'REAL) (atof s))
        (T s)))

(defun bc:cfg-save (cmd cfg / f p)
  (if (setq f (open (bc:cfg-path cmd) "w" "utf8"))
    (progn
      (foreach p cfg
        (write-line (strcat (car p) "=" (bc:str (cdr p))) f))
      (close f))))

(defun bc:cfg (cfg k) (cdr (assoc k cfg)))
(defun bc:cfg-set (cfg k v) (subst (cons k v) (assoc k cfg) cfg))

(defun bc:str (v)
  (cond ((= (type v) 'STR) v)
        ((= (type v) 'INT) (itoa v))
        ((= (type v) 'REAL) (bc:rtos v 2 8))
        ((null v) "")
        (T (vl-princ-to-string v))))

;;; ---------------------------------------------------------------- 숫자·문자

(defun bc:rtos (v m d / z r p)
  ;; DIMZIN(소수 끝 0·앞 0 지우기)에 흔들리지 않는 rtos. 1.0 → "1.00"(d=2)
  ;; 십진(m=2)은 DIMZIN을 건드리지 않고 지워진 0을 다시 채운다 — DIMZIN을 바꿨다 되돌려도 도면이 '수정됨'이 된다.
  (setq z (getvar "DIMZIN") r (rtos v m d))
  (cond
    ((= z 0) r)
    ((= m 2)
     (cond ((= (substr r 1 1) ".") (setq r (strcat "0" r)))
           ((= (substr r 1 2) "-.") (setq r (strcat "-0" (substr r 2)))))
     (if (> d 0)
       (progn
         (if (not (setq p (vl-string-search "." r))) (setq r (strcat r ".") p (1- (strlen r))))
         (while (< (- (strlen r) p 1) d) (setq r (strcat r "0")))))
     r)
    (T (setvar "DIMZIN" 0) (setq r (rtos v m d)) (setvar "DIMZIN" z) r)))

(defun bc:digit-p (c) (and (>= c 48) (<= c 57)))

(defun bc:num-in-text (s / i e b c neg)
  ;; 문자열의 맨 뒤 숫자(부호·소수점·천단위 쉼표 포함)를 실수로. "EL=123m"→123, "123AB456"→456,
  ;; "EL.(-)1.50"→-1.5. 숫자가 없으면 nil.
  (if (= (type s) 'STR)
    (progn
      (setq i (strlen s))
      (while (and (> i 0) (not (bc:digit-p (ascii (substr s i 1))))) (setq i (1- i)))
      (if (> i 0)
        (progn
          (setq e i b i)
          (while (and (> b 1)
                      (or (bc:digit-p (setq c (ascii (substr s (1- b) 1)))) (= c 46) (= c 44)))
            (setq b (1- b)))
          (while (and (< b e) (member (substr s b 1) '("." ","))) (setq b (1+ b)))
          (setq neg (or (and (> b 1) (= (substr s (1- b) 1) "-"))
                        (and (> b 3) (= (substr s (- b 3) 3) "(-)"))))
          (setq c (atof (bc:strip-commas (substr s b (1+ (- e b))))))
          (if neg (- c) c))))))

(defun bc:strip-commas (s / r) (setq r s) (while (vl-string-search "," r) (setq r (vl-string-subst "" "," r))) r)

(defun bc:mtext-plain (s / out i n c d j)
  ;; MTEXT 서식 코드를 걷어낸 본문. 앞에서부터 한 글자씩:
  ;;  \P(줄바꿈) → 공백, \\ \{ \} → 그 글자, \L \l \O \o \K \k \N(두 글자 토글) → 지움,
  ;;  \f…; \H…; \C…; 등(;로 끝나는 코드) → 지움, { } → 지움.
  (setq out "" i 1 n (strlen s))
  (while (<= i n)
    (setq c (substr s i 1))
    (cond
      ((and (= c "\\") (< i n))
       (setq d (substr s (1+ i) 1))
       (cond ((member d '("P" "p")) (setq out (strcat out " ") i (+ i 2)))
             ((member d '("\\" "{" "}")) (setq out (strcat out d) i (+ i 2)))
             ((member d '("L" "l" "O" "o" "K" "k" "N")) (setq i (+ i 2)))
             ((setq j (vl-string-search ";" s i)) (setq i (+ j 2)))
             (T (setq i (+ i 2)))))
      ((member c '("{" "}")) (setq i (1+ i)))
      (T (setq out (strcat out c) i (1+ i)))))
  out)

(defun bc:text-of (en / ed ty s p)
  (setq ed (entget en) ty (cdr (assoc 0 ed)))
  (cond ((member ty '("TEXT" "ATTRIB" "ATTDEF")) (cdr (assoc 1 ed)))
        ((= ty "MTEXT")
         (setq s "")
         (foreach p ed (if (= (car p) 3) (setq s (strcat s (cdr p)))))
         (bc:mtext-plain (strcat s (cdr (assoc 1 ed)))))
        (T nil)))

(defun bc:fmt (v dec plus / s)
  (setq s (bc:rtos v 2 dec))
  (if (and plus (> v 0.0)) (strcat "+" s) s))

(defun bc:fmt-thousands (v dec / s neg ip fp out n)
  ;; 1234567.891 → "1,234,567.891"
  (setq neg (< v 0) s (bc:rtos (abs v) 2 dec))
  (if (setq n (vl-string-search "." s)) (setq ip (substr s 1 n) fp (substr s (1+ n))) (setq ip s fp ""))
  (setq out "")
  (while (> (strlen ip) 3)
    (setq out (strcat "," (substr ip (- (strlen ip) 2)) out) ip (substr ip 1 (- (strlen ip) 3))))
  (strcat (if neg "-" "") ip out fp))

;;; ---------------------------------------------------------------- 축척·문자 높이
;;; 축척 1000 = m 도면(1m = 도면 1), 축척 1 = mm 도면(1m = 도면 1000).

(defun bc:upm (scale) (/ 1000.0 (if (and scale (> scale 0)) scale 1000.0)))

(defun bc:text-h (cfg)
  ;; 설정 "높이"는 축척 1000 기준. "DIMSCALE적용"=1이면 DIMSCALE×DIMTXT.
  (if (= (bc:cfg cfg "DIMSCALE적용") 1)
    (* (getvar "DIMTXT") (max 1e-9 (getvar "DIMSCALE")))
    (* (bc:cfg cfg "높이") (bc:upm (bc:cfg cfg "축척")))))

;;; ---------------------------------------------------------------- 도면 요소

(defun bc:ensure-layer (name color)
  (if (and name (/= name "") (not (tblsearch "LAYER" name)))
    (entmake (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord") '(100 . "AcDbLayerTableRecord")
                   (cons 2 name) '(70 . 0) (cons 62 (if (and color (> color 0)) color 7)) '(6 . "Continuous")))))

(defun bc:layer (name) (if (and name (/= name "")) (progn (bc:ensure-layer name 7) name) (getvar "CLAYER")))

(defun bc:layer-open (name / e)
  ;; 레이어가 있고 잠겨 있지 않으면 T
  (and (setq e (tblsearch "LAYER" name)) (zerop (logand 4 (cdr (assoc 70 e))))))

(defun bc:temp-layer (/ e)
  ;; 임시 개체를 둘 잠기지 않은 레이어: "0", 잠겼으면 BC_TEMP(없으면 만들고, 잠겨 있으면 푼다 — 우리가 쓰는 레이어)
  (cond ((bc:layer-open "0") "0")
        (T (bc:ensure-layer "BC_TEMP" 7)
           (if (not (bc:layer-open "BC_TEMP"))
             (progn (setq e (entget (tblobjname "LAYER" "BC_TEMP")))
                    (entmod (subst (cons 70 (logand (cdr (assoc 70 e)) (~ 4))) (assoc 70 e) e))))
           "BC_TEMP")))

(defun bc:temp-line (p q / ln)
  ;; 교점 계산용 임시 선(vla). 처음부터 잠기지 않은 레이어에 만든다(entmake) — 현재 레이어에 만들고 옮기면 현재 레이어가
  ;; 잠겨 있을 때 옮기지도 지우지도 못해 긴 선이 남는다. 다 쓰면 bc:temp-drop.
  ;; entmake가 실패하면 nil — (entlast)는 사용자의 마지막 개체라 그걸 임시 선으로 알고 지우면 안 된다
  (if (entmake (list '(0 . "LINE") (cons 8 (bc:temp-layer)) (cons 10 p) (cons 11 q)))
    (setq ln (vlax-ename->vla-object (entlast))))
  ln)

(defun bc:temp-drop (ln) (if ln (vl-catch-all-apply 'vla-Delete (list ln))))

;;; 선분과 곡선의 교점을 도면에 아무것도 만들지 않고 계산한다(LINE·LWPOLYLINE). 조회 명령(DIBC 등)이 임시 선을
;;; 만들었다 지우면 도면이 '수정됨'이 되고 REDO가 끊긴다. 다른 종류는 'NA → 부르는 쪽이 임시 선으로 대신한다.

(defun bc:ang-ccw (a0 a1 / d)
  ;; a0에서 a1까지 반시계 각도(0 ~ 2π)
  (setq d (rem (- a1 a0) (* 2 pi)))
  (if (< d 0) (+ d (* 2 pi)) d))

(defun bc:seg-arc-hits (q1 q2 p1 p2 b / o c dd mid ux uy d cx cy r th dx dy fx fy A B2 C2 disc out k x y sw)
  ;; 선분 q1-q2와 볼록 b인 호 p1→p2의 교점들.
  ;; 좌표를 p1 기준으로 옮겨 계산한다 — TM 좌표(수십만 m)에 길이 수 km 선분이면 이차식 오차로 호 끝 교점이 각도
  ;; 판정에서 2π 쪽으로 넘어가 빠졌다(보조 검토 재현). 끝 판정에도 양쪽 1e-9 rad 여유.
  (setq o p1
        q1 (list (- (car q1) (car o)) (- (cadr q1) (cadr o))) q2 (list (- (car q2) (car o)) (- (cadr q2) (cadr o)))
        p2 (list (- (car p2) (car o)) (- (cadr p2) (cadr o))) p1 (list 0.0 0.0))
  (setq c (distance p1 p2) mid (bc:mid p1 p2)
        ux (/ (- (car p2) (car p1)) c) uy (/ (- (cadr p2) (cadr p1)) c)
        d (/ (* c (- 1.0 (* b b))) (* 4.0 b))            ; 현 가운데에서 중심까지(왼쪽 +)
        cx (- (car mid) (* d uy)) cy (+ (cadr mid) (* d ux))
        r (/ (* c (+ 1.0 (* b b))) (* 4.0 (abs b)))
        th (* 4.0 (atan (abs b)))
        dx (- (car q2) (car q1)) dy (- (cadr q2) (cadr q1))
        fx (- (car q1) cx) fy (- (cadr q1) cy)
        A (+ (* dx dx) (* dy dy)) B2 (* 2.0 (+ (* fx dx) (* fy dy))) C2 (- (+ (* fx fx) (* fy fy)) (* r r))
        disc (- (* B2 B2) (* 4.0 A C2)))
  (if (and (> A 1e-24) (>= disc 0.0))
    (foreach k (list (/ (- (- B2) (sqrt disc)) (* 2.0 A)) (/ (+ (- B2) (sqrt disc)) (* 2.0 A)))
      (if (and (>= k -1e-12) (<= k (+ 1.0 1e-12)))
        (progn
          (setq x (+ (car q1) (* k dx)) y (+ (cadr q1) (* k dy))
                sw (if (> b 0) (bc:ang-ccw (angle (list cx cy) p1) (angle (list cx cy) (list x y)))
                               (bc:ang-ccw (angle (list cx cy) (list x y)) (angle (list cx cy) p1))))
          (if (or (<= sw (+ th 1e-9)) (>= sw (- (* 2 pi) 1e-9)))
            (setq out (cons (list (+ x (car o)) (+ y (cadr o)) 0.0) out)))))))
  out)

(defun bc:seg-hits (q1 q2 en / ed ty pts bs closed h out)
  ;; 선분 q1-q2와 곡선 en의 교점 목록(XY, z=0). 계산할 수 없는 종류면 'NA.
  (setq ed (entget en) ty (cdr (assoc 0 ed)) q1 (bc:2d q1) q2 (bc:2d q2))
  (cond
    ((= ty "LINE")
     (if (setq h (inters q1 q2 (bc:2d (cdr (assoc 10 ed))) (bc:2d (cdr (assoc 11 ed))) T)) (list (list (car h) (cadr h) 0.0))))
    ((and (= ty "LWPOLYLINE") (equal (cdr (assoc 210 ed)) '(0.0 0.0 1.0) 1e-12))
     (foreach g ed
       (cond ((= (car g) 10) (setq pts (cons (list (cadr g) (caddr g)) pts) bs (cons 0.0 bs)))
             ((= (car g) 42) (setq bs (cons (cdr g) (cdr bs))))))
     (setq pts (reverse pts) bs (reverse bs) closed (= 1 (logand 1 (cdr (assoc 70 ed)))))
     (if closed (setq pts (append pts (list (car pts)))))
     ;; 구간마다(앞 점, 뒤 점, 앞 점의 볼록) — 정점이 많아도 한 번씩만 훑는다
     (mapcar '(lambda (p1 p2 b)
                (if (> (distance p1 p2) 1e-12)
                  (if (< (abs b) 1e-12)
                    (if (setq h (inters q1 q2 p1 p2 T)) (setq out (cons (list (car h) (cadr h) 0.0) out)))
                    (setq out (append (bc:seg-arc-hits q1 q2 p1 p2 b) out)))))
             pts (cdr pts) bs)
     out)
    (T 'NA)))

(defun bc:hits (q1 q2 en / pts ln r)
  ;; 선분 q1-q2와 곡선 en의 교점 목록. LINE·LWPOLYLINE은 계산으로(도면에 아무것도 안 만듦), 그 밖은 임시 선 + IntersectWith.
  (setq pts (bc:seg-hits q1 q2 en))
  (if (= pts 'NA)
    (progn
      (setq pts nil ln (bc:temp-line q1 q2)
            r (if ln (vl-catch-all-apply 'vlax-invoke (list ln 'IntersectWith (vlax-ename->vla-object en) acExtendNone))))
      (bc:temp-drop ln)
      (if (not (vl-catch-all-error-p r))
        (while r (setq pts (cons (list (car r) (cadr r) (caddr r)) pts) r (cdddr r))))))
  pts)

(defun bc:style-width (/ st)
  (if (setq st (tblsearch "STYLE" (getvar "TEXTSTYLE"))) (max 0.01 (cdr (assoc 41 st))) 1.0))

(defun bc:text (pt s h lay just rot / hj vj)
  ;; just: "L" "C" "R" "ML" "MC" "MR" "TL" "TC" "TR" "BL" "BC" "BR". rot: 라디안.
  (setq hj (cond ((wcmatch just "*L") 0) ((wcmatch just "*C") 1) ((wcmatch just "*R") 2) (T 0))
        vj (cond ((wcmatch just "M?") 2) ((wcmatch just "T?") 3) ((wcmatch just "B?") 1) (T 0)))
  (entmake (list '(0 . "TEXT") (cons 8 (bc:layer lay)) (cons 10 pt) (cons 11 pt) (cons 40 h)
                 (cons 1 s) (cons 50 (if rot rot 0.0)) (cons 41 (bc:style-width))
                 (cons 7 (getvar "TEXTSTYLE")) (cons 72 hj) (cons 73 vj)))
  (entlast))

(defun bc:line (p1 p2 lay)
  (entmake (list '(0 . "LINE") (cons 8 (bc:layer lay)) (cons 10 p1) (cons 11 p2)))
  (entlast))

(defun bc:pline (pts closed lay)
  (entmake (append (list '(0 . "LWPOLYLINE") '(100 . "AcDbEntity") (cons 8 (bc:layer lay))
                         '(100 . "AcDbPolyline") (cons 90 (length pts)) (cons 70 (if closed 1 0)))
                   (mapcar '(lambda (p) (cons 10 (list (car p) (cadr p)))) pts)))
  (entlast))

(defun bc:circle (c r lay)
  (entmake (list '(0 . "CIRCLE") (cons 8 (bc:layer lay)) (cons 10 c) (cons 40 r)))
  (entlast))

(defun bc:point (p lay)
  (entmake (list '(0 . "POINT") (cons 8 (bc:layer lay)) (cons 10 p)))
  (entlast))

(defun bc:solid3 (a b c lay)
  ;; 속이 찬 삼각형(화살표 머리)
  (entmake (list '(0 . "SOLID") (cons 8 (bc:layer lay)) (cons 10 a) (cons 11 b) (cons 12 c) (cons 13 c)))
  (entlast))

(defun bc:arrow (tip dir len lay / a b w)
  ;; tip에서 dir(라디안) 반대쪽으로 길이 len인 채운 화살표
  (setq w (* len 0.18)
        a (polar (polar tip (+ dir pi) len) (+ dir (/ pi 2)) w)
        b (polar (polar tip (+ dir pi) len) (- dir (/ pi 2)) w))
  (bc:solid3 tip a b lay))

;;; ---------------------------------------------------------------- 좌표·곡선

(defun bc:wcs (p) (trans p 1 0))
(defun bc:ucs (p) (trans p 0 1))
(defun bc:2d (p) (list (car p) (cadr p)))

(defun bc:curve-p (en / ty)
  (setq ty (cdr (assoc 0 (entget en))))
  (member ty '("LINE" "LWPOLYLINE" "POLYLINE" "ARC" "SPLINE" "CIRCLE" "ELLIPSE")))

(defun bc:wild-esc (s / out c)
  ;; ssget·wcmatch에서 이름을 글자 그대로 맞추게 특수 문자(# @ . * ? ~ [ ] - , `) 앞에 역따옴표를 붙인다
  (setq out "")
  (foreach c (vl-string->list s)
    (setq out (strcat out (if (member c (vl-string->list "#@.*?~[]-,`")) "`" "") (chr c))))
  out)

(defun bc:vbar (en / v p0 p1)
  ;; 세로 중심선(LINE 또는 꼭짓점 2개짜리 폴리선) → (아래 끝 위 끝). 아니면 nil.
  ;; 세로(가로 차이가 높이의 0.1% 이하)이고 높이가 있는 것만 — 사선·수평선을 중심선으로 잡지 않게
  (setq v (bc:verts en))
  (if (= (length v) 2)
    (progn (setq p0 (car v) p1 (cadr v))
           (if (and (> (abs (- (cadr p1) (cadr p0))) 1e-9)
                    (<= (abs (- (car p1) (car p0))) (* 1e-3 (abs (- (cadr p1) (cadr p0))))))
             (if (> (cadr p0) (cadr p1)) (list p1 p0) (list p0 p1))))))

(defun bc:verts (en / ed ty out v p)
  ;; 선·폴리선의 정점(WCS, 3D). LWPOLYLINE은 고도(38) 적용.
  (setq ed (entget en) ty (cdr (assoc 0 ed)))
  (cond ((= ty "LINE") (list (cdr (assoc 10 ed)) (cdr (assoc 11 ed))))
        ((= ty "LWPOLYLINE")
         (foreach p ed
           (if (= (car p) 10)
             (setq out (cons (trans (list (cadr p) (caddr p) (if (assoc 38 ed) (cdr (assoc 38 ed)) 0.0)) en 0) out))))
         (reverse out))
        ((= ty "POLYLINE")
         (setq v (entnext en))
         (while (and v (= (cdr (assoc 0 (entget v))) "VERTEX"))
           (if (zerop (logand 16 (cdr (assoc 70 (entget v)))))
             (setq out (cons (trans (cdr (assoc 10 (entget v))) en 0) out)))
           (setq v (entnext v)))
         (reverse out))
        (T nil)))

(defun bc:closest (en p) (vlax-curve-getClosestPointTo en p))  ; p는 WCS(호출부가 bc:wcs로 바꿔 넘긴다)
(defun bc:dist-at (en p) (vlax-curve-getDistAtPoint en (bc:closest en p)))

;;; ---------------------------------------------------------------- 입력
;;; 키워드 입력은 영문 대문자 하나(E·S·C …). 엔터·ESC는 nil.

(defun bc:get-number-or-pick (msg kw dflt / r en s v)
  ;; 문자를 고르면 그 안의 숫자, 키워드 E를 치면 직접 입력. 반환: 숫자, 키워드 문자열, 또는 nil.
  (setvar "ERRNO" 0)
  (initget kw)
  (setq r (entsel (strcat "\n" msg (if dflt (strcat " <" (bc:rtos dflt 2 3) ">") "") ": ")))
  (cond ((= (type r) 'STR) r)
        ((and (null r) (= (getvar "ERRNO") 7)) (bc:get-number-or-pick msg kw dflt))
        ((null r) (if (= (getvar "ERRNO") 52) dflt nil))
        ((setq s (bc:text-of (car r)))
         (if (setq v (bc:num-in-text s)) v (progn (princ "\n숫자가 없는 문자입니다.") (bc:get-number-or-pick msg kw dflt))))
        (T (princ "\n문자를 고르세요.") (bc:get-number-or-pick msg kw dflt))))

;;; ---------------------------------------------------------------- 명령 틀
;;; (bc:begin) … (bc:end): UNDO 한 묶음, 오류·ESC 때 시스템 변수 복구.

(setq bc:*saved* nil)

(defun bc:begin (vars)
  (setq bc:*olderr* *error* *error* bc:error)
  (setq bc:*saved* (mapcar '(lambda (v) (cons v (getvar v))) (append '("CMDECHO") vars)))
  (setvar "CMDECHO" 0)
  (vla-StartUndoMark (vla-get-ActiveDocument (vlax-get-acad-object))))

(defun bc:end (/ p)
  (vl-catch-all-apply 'vla-EndUndoMark (list (vla-get-ActiveDocument (vlax-get-acad-object))))
  (foreach p bc:*saved* (vl-catch-all-apply 'setvar (list (car p) (cdr p))))
  (setq bc:*saved* nil)
  (if bc:*olderr* (setq *error* bc:*olderr* bc:*olderr* nil))
  (princ))

(defun bc:error (msg)
  (if (not (wcmatch (strcase msg) "*BREAK*,*CANCEL*,*EXIT*,*취소*"))
    (princ (strcat "\n오류: " msg)))
  (bc:end))

;;; ---------------------------------------------------------------- 창 띄우기

(defun bc:open-window (cmd)
  (if (and *bc-pyw* *bc-root*)
    (progn
      (startapp (strcat "\"" *bc-pyw* "\"") (strcat "\"" *bc-root* "/skills/launch.py\" " cmd))
      (princ (strcat "\n[BC] " cmd " 창을 띄웠습니다.")))
    (princ "\n[BC] 창을 띄울 수 없습니다 — install을 먼저 실행하세요(bc_autocad.lsp 미설정).")))

(defun bc:settings-hint (cmd)
  (princ (strcat "\n[BC] 설정을 바꿨으면 " cmd "를 다시 실행하세요.")))

;;; ---------------------------------------------------------------- 외곽 상자 덤프 (CSAR 등)

(defun bc:bbox (en / o r mn mx)
  ;; (minx miny maxx maxy) 또는 nil
  (setq o (vlax-ename->vla-object en))
  (setq r (vl-catch-all-apply 'vla-GetBoundingBox (list o 'mn 'mx)))
  (if (not (vl-catch-all-error-p r))
    (progn (setq mn (vlax-safearray->list mn) mx (vlax-safearray->list mx))
           (list (car mn) (cadr mn) (car mx) (cadr mx)))))

(defun bc:dump-bbox (ss fp / i en b)
  ;; B<탭>핸들<탭>minx<탭>miny<탭>maxx<탭>maxy
  (if ss
    (progn (setq i 0)
           (while (< i (sslength ss))
             (setq en (ssname ss i) b (bc:bbox en))
             (if b (write-line (strcat "B\t" (cdr (assoc 5 (entget en))) "\t" (bc:rtos (car b) 2 6) "\t" (bc:rtos (cadr b) 2 6)
                                       "\t" (bc:rtos (caddr b) 2 6) "\t" (bc:rtos (cadddr b) 2 6)) fp))
             (setq i (1+ i))))))

(defun bc:copy-move (handles dx dy / out o n)
  ;; 핸들 객체들을 (dx dy)만큼 옮긴 복사본. 새 핸들 목록
  (foreach h handles
    (if (setq o (handent h))
      (progn (setq n (vla-Copy (vlax-ename->vla-object o)))
             (vla-Move n (vlax-3d-point '(0.0 0.0 0.0)) (vlax-3d-point (list dx dy 0.0)))
             (setq out (cons (vla-get-Handle n) out)))))
  (reverse out))
