;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_slope.lsp — 제방·사면 명령 (DSLO NSLO DFB SLL SLT CSS CUT)
;;; 사면 표시(평면): 긴 선(주 표시)은 사면 상단에서 하단까지, 짧은 선(보조 표시)은 상단 쪽에서 짧게.
;;;   쌓기: 처음 고른 선(안쪽, 둑마루·법견)이 상단. 깎기: 나중 고른 선(바깥쪽)이 상단.
;;; 횡단(CSS·CUT·SLL·SLT): H축척·V축척 따로(1000 = 1m가 도면 1). 경사 n은 1:n(수직 1 : 수평 n).

;;; ================================================================ 공통

(defun bc:unit-h (cfg) (/ 1000.0 (max 1e-9 (bc:cfg cfg "H축척"))))
(defun bc:unit-v (cfg) (/ 1000.0 (max 1e-9 (bc:cfg cfg "V축척"))))

(defun bc:ray-hit (p a en len / pts)
  ;; p에서 각도 a로 길이 len인 선분과 곡선 en의 교점 중 p에 가장 가까운 것(p 자신 제외). 없으면 nil.
  (setq pts (vl-remove-if '(lambda (q) (< (distance (bc:2d p) (bc:2d q)) 1e-7)) (bc:hits p (polar p a len) en)))
  (if pts (car (vl-sort pts '(lambda (u v) (< (distance (bc:2d p) (bc:2d u)) (distance (bc:2d p) (bc:2d v))))))))

(defun bc:toward (en p a / c)
  ;; p의 진행 각도 a 기준으로 en이 있는 쪽 수직 각도
  (setq c (vlax-curve-getClosestPointTo en p))
  (if (> (- (* (cos a) (- (cadr c) (cadr p))) (* (sin a) (- (car c) (car p)))) 0) (+ a (/ pi 2)) (- a (/ pi 2))))

(defun bc:slope-layer (cfg) (bc:cfg cfg "레이어"))

(defun bc:num-trim (v dec / s)
  ;; 소수 끝 0과 점을 뗀 숫자 문자: 1.5 → "1.5", 2.0 → "2.0"(정수면 .0 하나는 남긴다 — 1:2.0 관례)
  (setq s (bc:rtos v 2 dec))
  (if (vl-string-search "." s)
    (progn (setq s (vl-string-right-trim "0" s)) (if (wcmatch s "*.") (setq s (strcat s "0")))))
  s)

(defun bc:tick (p q ratio lay)
  ;; p에서 q 쪽으로 길이 비율 ratio만큼
  (bc:line p (mapcar '(lambda (x y) (+ x (* ratio (- y x)))) p q) lay))

;;; ================================================================ DSLO 계획 사면 표시

(setq bc:dslo-defaults
  '(("종류" . "쌓기") ("주간격" . 10.0) ("보조개수" . 4) ("짧은비율" . 0.5) ("축척" . 1000.0) ("레이어" . "")
    ("끝선항상" . 1)))

(defun bc:dslo-core (a b d1 d2 cfg / La step n i dd p ang na q main ents k fill lay ratio last)
  ;; a: 처음 고른 선(안쪽), b: 나중 고른 선(바깥쪽). a 위 거리 d1~d2(도면 단위) 구간에 사면 표시.
  ;; 주 표시 간격(m)을 보조개수+1로 나눈 간격마다 선을 긋는다.
  (setq La (bc:curve-len a) d1 (max 0.0 (min d1 d2)) d2 (min La (max d1 d2))
        n (1+ (bc:cfg cfg "보조개수"))
        step (/ (* (bc:cfg cfg "주간격") (bc:upm (bc:cfg cfg "축척"))) n)
        fill (/= (bc:cfg cfg "종류") "깎기") lay (bc:slope-layer cfg) ratio (bc:cfg cfg "짧은비율")
        i 0 dd d1)
  (while (<= dd (+ d2 1e-9))
    (setq p (vlax-curve-getPointAtDist a dd)
          ang (bc:curve-ang a dd nil)
          na (bc:toward b p ang)
          q (cond ((bc:ray-hit p na b (* 1e3 (+ 1.0 (distance p (vlax-curve-getClosestPointTo b p))))))
                  (T (vlax-curve-getClosestPointTo b p)))
          main (= 0 (rem i n)))
    (setq ents (cons (if fill (bc:tick p q (if main 1.0 ratio) lay) (bc:tick q p (if main 1.0 ratio) lay)) ents))
    (setq last dd i (1+ i) dd (+ d1 (* i step))))
  ;; 끝 지점이 간격에 안 맞아도 사면 선을 하나 긋는다
  (if (and (= (bc:cfg cfg "끝선항상") 1) (> (- d2 last) (* step 0.25)))
    (progn
      (setq p (vlax-curve-getPointAtDist a d2) na (bc:toward b p (bc:curve-ang a d2 nil))
            q (cond ((bc:ray-hit p na b (* 1e3 (+ 1.0 (distance p (vlax-curve-getClosestPointTo b p)))))) (T (vlax-curve-getClosestPointTo b p))))
      (setq ents (cons (bc:line p q lay) ents))))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:DSLO (/ cfg a b p1 p2 k)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "DSLO" bc:dslo-defaults))
  (princ (strcat "\n<현재: " (bc:cfg cfg "종류") ", 주 간격 " (bc:rtos (bc:cfg cfg "주간격") 2 2) "m, 보조 "
                 (itoa (bc:cfg cfg "보조개수")) "개>"))
  (initget "S")
  (setq a (entsel "\n사면 시작선(안쪽: 쌓기면 둑마루·법견) 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= a "S") (bc:open-window "DSLO") (bc:settings-hint "DSLO"))
    ((and a (bc:curve-p (car a)) (setq b (entsel "\n사면 끝선(바깥쪽) 선택: ")) (bc:curve-p (car b)))
     (setq a (car a) b (car b))
     (initget "A")
     (setq p1 (getpoint "\n사면 표시 시작점(시작선 위) 지정 또는 [전체(A)] <전체>: "))
     (if (and p1 (/= p1 "A")) (setq p2 (getpoint p1 "\n사면 표시 끝점 지정: ")))
     (bc:dslo-core a b (if (and p1 (/= p1 "A")) (bc:curve-d a (bc:wcs p1) nil) 0.0)
                   (if p2 (bc:curve-d a (bc:wcs p2) nil) (bc:curve-len a)) cfg)))
  (bc:end))

;;; ================================================================ NSLO 자연(현황) 사면 표시

(setq bc:nslo-defaults
  '(("간격" . 2.0) ("긴길이" . 3.0) ("짧은길이" . 1.5) ("하단선까지" . 0) ("레이어" . "")))

(defun bc:nslo-core (a side-pt b d1 d2 cfg / La dd i p ang na q ents lay len)
  ;; a: 사면 상단선. 간격(도면 단위)마다 긴 선·짧은 선을 번갈아 a에 수직으로 side-pt 쪽으로.
  ;; b가 있고 '하단선까지'면 긴 선은 b까지.
  (setq La (bc:curve-len a) d1 (max 0.0 (min d1 d2)) d2 (min La (max d1 d2)) lay (bc:cfg cfg "레이어") i 0 dd d1)
  (while (<= dd (+ d2 1e-9))
    (setq p (vlax-curve-getPointAtDist a dd) ang (bc:curve-ang a dd nil))
    (setq na (if (> (- (* (cos ang) (- (cadr side-pt) (cadr p))) (* (sin ang) (- (car side-pt) (car p)))) 0)
               (+ ang (/ pi 2)) (- ang (/ pi 2))))
    (setq len (if (= 0 (rem i 2)) (bc:cfg cfg "긴길이") (bc:cfg cfg "짧은길이")))
    (setq q (if (and b (= (bc:cfg cfg "하단선까지") 1) (= 0 (rem i 2)))
              (cond ((bc:ray-hit p na b 1e6)) (T (polar p na len)))
              (polar p na len)))
    (setq ents (cons (bc:line p q lay) ents) i (1+ i) dd (+ d1 (* i (bc:cfg cfg "간격")))))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:NSLO (/ cfg a sp b)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "NSLO" bc:nslo-defaults))
  (initget "S")
  (setq a (entsel "\n사면 상단선 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= a "S") (bc:open-window "NSLO") (bc:settings-hint "NSLO"))
    ((and a (bc:curve-p (car a)) (setq sp (getpoint "\n사면이 내려가는 쪽 점 지정: ")))
     (if (= (bc:cfg cfg "하단선까지") 1) (setq b (car (entsel "\n사면 하단선 선택(없으면 엔터): "))))
     (bc:nslo-core (car a) (bc:wcs sp) b 0.0 (bc:curve-len (car a)) cfg)))
  (bc:end))

;;; ================================================================ DFB 앞성토 사면 (부채꼴)

(setq bc:dfb-defaults '(("주개수" . 2) ("보조개수" . 2) ("짧은비율" . 0.5) ("양끝선" . 1) ("레이어" . "")))

(defun bc:dfb-core (apex en cfg / L tot i q main ents lay)
  ;; apex(사면 시작 한 점)에서 끝선 en을 (주+1)×(보조+1)로 등분한 점들로 부채꼴 사면 표시
  (setq L (bc:curve-len en) tot (* (1+ (bc:cfg cfg "주개수")) (1+ (bc:cfg cfg "보조개수"))) lay (bc:cfg cfg "레이어") i 0)
  (repeat (1+ tot)
    (if (or (and (> i 0) (< i tot)) (= (bc:cfg cfg "양끝선") 1))
      (progn
        (setq q (vlax-curve-getPointAtDist en (* L (/ i (float tot))))
              main (or (= i 0) (= i tot) (= 0 (rem i (1+ (bc:cfg cfg "보조개수"))))))
        (setq ents (cons (bc:tick apex q (if main 1.0 (bc:cfg cfg "짧은비율")) lay) ents))))
    (setq i (1+ i)))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:DFB (/ cfg ap en)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "DFB" bc:dfb-defaults))
  (initget "S")
  (setq ap (getpoint "\n사면 시작점(최상단 한 점) 지정 또는 [설정 변경(S)]: "))
  (cond
    ((= ap "S") (bc:open-window "DFB") (bc:settings-hint "DFB"))
    ((and ap (setq en (entsel "\n사면 끝선(호) 선택: ")) (bc:curve-p (car en)))
     (bc:dfb-core (bc:wcs ap) (car en) cfg)))
  (bc:end))

;;; ================================================================ SLL 경사선 작도 (횡단·종단, 축척 다름)

(setq bc:sll-defaults '(("H축척" . 1000.0) ("V축척" . 1000.0) ("경사입력" . "경사기본") ("레이어" . "")))

(defun bc:sll-core (p slope x2 cfg / dxu dxm dym q)
  ;; p에서 경사 slope(높이/거리, +는 위)로 X가 x2인 곳까지 선
  (setq dxu (- x2 (car p)) dxm (/ (abs dxu) (bc:unit-h cfg)) dym (* slope dxm)
        q (list x2 (+ (cadr p) (* dym (bc:unit-v cfg))) 0.0))
  (cdr (assoc 5 (entget (bc:line p q (bc:cfg cfg "레이어"))))))

(defun c:SLL (/ cfg p sl q)
  (bc:begin '("ORTHOMODE"))
  (setvar "ORTHOMODE" 0)
  (setq cfg (bc:cfg-load "SLL" bc:sll-defaults))
  (princ (strcat "\n<H " (bc:rtos (bc:cfg cfg "H축척") 2 0) " / V " (bc:rtos (bc:cfg cfg "V축척") 2 0) ">"))
  (initget "S")
  (setq p (getpoint "\n시작점 지정 또는 [설정 변경(S)]: "))
  (cond
    ((= p "S") (bc:open-window "SLL") (bc:settings-hint "SLL"))
    (p
     (setq p (bc:wcs p))
     (while (and (setq sl (bc:read-slope cfg)) (setq q (getpoint (bc:ucs p) "\n끝점 지정(X만 씀): ")))
       (bc:sll-core p sl (car (bc:wcs q)) cfg)
       (setq p (list (car (bc:wcs q)) (+ (cadr p) (* sl (/ (abs (- (car (bc:wcs q)) (car p))) (bc:unit-h cfg)) (bc:unit-v cfg))) 0.0)))))
  (bc:end))

;;; ================================================================ SLT 경사 기호 표기

(setq bc:slt-defaults
  '(("H축척" . 1000.0) ("V축척" . 1000.0) ("표기" . "경사비") ("소수" . 2) ("높이" . 2.5) ("레이어" . "") ("간격" . 0.5)
    ("도면표기" . 1)))

(defun bc:slope-of (p q cfg / dx dy)
  ;; (높이/거리 비, 문자) — 1:n 은 수평/수직
  (setq dx (/ (abs (- (car q) (car p))) (bc:unit-h cfg)) dy (/ (- (cadr q) (cadr p)) (bc:unit-v cfg)))
  (if (> (car p) (car q)) (setq dy (- dy)))
  (list (if (< dx 1e-12) 0.0 (/ dy dx))
        (cond ((= (bc:cfg cfg "표기") "퍼센트") (strcat (bc:rtos (* 100.0 (abs (if (< dx 1e-12) 0.0 (/ dy dx)))) 2 (bc:cfg cfg "소수")) "%"))
              ((< (abs dy) 1e-12) "수평")
              ((= (bc:cfg cfg "표기") "모두")
               (strcat "1:" (bc:rtos (/ dx (abs dy)) 2 (bc:cfg cfg "소수")) " (" (bc:rtos (* 100.0 (/ (abs dy) (max dx 1e-12))) 2 (bc:cfg cfg "소수")) "%)"))
              (T (strcat "1:" (bc:rtos (/ dx (abs dy)) 2 (bc:cfg cfg "소수")))))))

(defun bc:slt-core (p q cfg / r a m h e)
  (setq r (bc:slope-of p q cfg) a (angle p q) h (bc:cfg cfg "높이"))
  (if (and (> a (/ pi 2)) (<= a (* pi 1.5))) (setq a (+ a pi)))
  (setq m (polar (bc:mid p q) (+ a (/ pi 2)) (* h (bc:cfg cfg "간격"))))
  (if (= (bc:cfg cfg "도면표기") 1) (setq e (bc:text m (cadr r) h (bc:cfg cfg "레이어") "BC" a)))
  (list (car r) (cadr r) (if e (cdr (assoc 5 (entget e))))))

(defun c:SLT (/ cfg p q r en)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "SLT" bc:slt-defaults))
  (initget "E S")
  (setq p (getpoint "\n첫 점 지정 또는 [선 선택(E)/설정 변경(S)]: "))
  (cond
    ((= p "S") (bc:open-window "SLT") (bc:settings-hint "SLT"))
    ((= p "E")
     (if (and (setq en (entsel "\n선 선택: ")) (bc:curve-p (car en)))
       (progn
         ;; 고른 점이 있는 선분의 양 끝
         (setq q (bc:closest (car en) (bc:wcs (cadr en)))
               p (vlax-curve-getPointAtParam (car en) (fix (vlax-curve-getParamAtPoint (car en) q)))
               q (vlax-curve-getPointAtParam (car en) (min (vlax-curve-getEndParam (car en)) (1+ (fix (vlax-curve-getParamAtPoint (car en) q))))))
         (setq r (bc:slt-core p q cfg)) (princ (strcat "\n경사 = " (cadr r))))))
    ((and p (setq q (getpoint p "\n둘째 점 지정: ")))
     (setq r (bc:slt-core (bc:wcs p) (bc:wcs q) cfg)) (princ (strcat "\n경사 = " (cadr r)))))
  (bc:end))

;;; ================================================================ CSS 횡단 사면 (지반선까지, 소단)

(setq bc:css-defaults
  '(("H축척" . 1000.0) ("V축척" . 1000.0) ("종류" . "자동") ("쌓기경사" . 1.5) ("깎기경사" . 1.0)
    ("소단높이" . 5.0) ("소단폭" . 1.0) ("경사문자" . 1) ("높이" . 2.0) ("레이어" . "") ("문자레이어" . "")))

(defun bc:ground-y (g x / vs a b y)
  ;; 지반선(왼→오른쪽 꼭짓점) X 위치의 Y. 범위 밖이면 nil
  (setq vs (vl-sort (bc:verts g) '(lambda (u v) (< (car u) (car v)))))
  (while (and (cdr vs) (null y))
    (setq a (car vs) b (cadr vs))
    (if (and (<= (car a) x) (<= x (car b)) (> (car b) (car a)))
      (setq y (+ (cadr a) (* (- (cadr b) (cadr a)) (/ (- x (car a)) (- (car b) (car a)))))))
    (setq vs (cdr vs)))
  y)

(defun bc:css-core (g p side cfg / gy fill n hv bw cur pts ent i nxt hit lay txt seg)
  ;; g: 지반선, p: 사면 시작점(법견·법선), side: 1 오른쪽 / -1 왼쪽.
  ;; 쌓기는 아래로 1:쌓기경사, 깎기는 위로 1:깎기경사. 소단높이(m)마다 소단폭(m) 수평. 지반선을 만나면 끝.
  (setq gy (bc:ground-y g (car p))
        fill (cond ((= (bc:cfg cfg "종류") "쌓기") T) ((= (bc:cfg cfg "종류") "깎기") nil) (T (and gy (> (cadr p) gy))))
        n (if fill (bc:cfg cfg "쌓기경사") (bc:cfg cfg "깎기경사"))
        hv (* (bc:cfg cfg "소단높이") (bc:unit-v cfg)) bw (* (bc:cfg cfg "소단폭") (bc:unit-h cfg))
        lay (bc:cfg cfg "레이어") cur p pts (list p) i 0)
  (while (and (< i 30) (null hit))
    ;; 비탈 한 단
    (setq nxt (list (+ (car cur) (* side n (bc:cfg cfg "소단높이") (bc:unit-h cfg))) (+ (cadr cur) (if fill (- hv) hv)) 0.0))
    (if (setq hit (bc:seg-hit cur nxt g))
      (setq pts (cons hit pts))
      (progn
        (setq pts (cons nxt pts) cur nxt)
        ;; 소단
        (setq nxt (list (+ (car cur) (* side bw)) (cadr cur) 0.0))
        (if (setq hit (bc:seg-hit cur nxt g)) (setq pts (cons hit pts)) (setq pts (cons nxt pts) cur nxt))))
    (setq i (1+ i)))
  (setq ent (bc:pline (reverse pts) nil lay))
  (if (= (bc:cfg cfg "경사문자") 1)
    (progn
      (setq seg (list (car (reverse pts)) (cadr (reverse pts))))
      (setq txt (bc:text (polar (bc:mid (car seg) (cadr seg)) (+ (angle (car seg) (cadr seg)) (if (= side 1) (/ pi 2) (- (/ pi 2))))
                                (* 0.5 (bc:cfg cfg "높이")))
                         (strcat "1:" (bc:num-trim n 3)) (bc:cfg cfg "높이")
                         (if (/= (bc:cfg cfg "문자레이어") "") (bc:cfg cfg "문자레이어") lay) "BC"
                         (if (= side 1) (angle (car seg) (cadr seg)) (angle (cadr seg) (car seg)))))))
  (list (if fill "쌓기" "깎기") (if hit T nil) (cdr (assoc 5 (entget ent))) (if txt (cdr (assoc 5 (entget txt))))))

(defun bc:seg-hit (a b g) (if (> (distance a b) 1e-9) (bc:ray-hit a (angle a b) g (distance a b))))

(defun c:CSS (/ cfg g p sp)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "CSS" bc:css-defaults))
  (initget "S")
  (setq g (entsel "\n지반선 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= g "S") (bc:open-window "CSS") (bc:settings-hint "CSS"))
    ((and g (bc:curve-p (car g)))
     (while (and (setq p (getpoint "\n사면 시작점(법견·법선) 지정: ")) (setq sp (getpoint p "\n사면이 나갈 쪽 점 지정: ")))
       (setq p (bc:wcs p) sp (bc:wcs sp))
       (princ (strcat "\n" (car (bc:css-core (car g) p (if (> (car sp) (car p)) 1 -1) cfg)) " 사면을 그렸습니다.")))))
  (bc:end))

;;; ================================================================ CUT 층따기

(setq bc:cut-defaults
  '(("H축척" . 1000.0) ("V축척" . 1000.0) ("층높이" . 1.0) ("배수경사" . 0.0) ("최소높이" . 0.3) ("제외경사" . 4.0)
    ("레이어" . "") ("숨은선" . 0) ("선축척" . 1.0)))

(defun bc:x-at-y (g y x0 dir / vs a b x)
  ;; x0에서 dir(+1/-1) 쪽으로 가며 지반선이 높이 y가 되는 첫 X
  (setq vs (vl-sort (bc:verts g) '(lambda (u v) (if (> dir 0) (< (car u) (car v)) (> (car u) (car v))))))
  (while (and (cdr vs) (null x))
    (setq a (car vs) b (cadr vs))
    (if (and (if (> dir 0) (>= (car b) x0) (<= (car b) x0))
             (or (<= (cadr a) y (cadr b)) (>= (cadr a) y (cadr b))) (/= (cadr a) (cadr b)))
      (progn
        (setq x (+ (car a) (* (- (car b) (car a)) (/ (- y (cadr a)) (- (cadr b) (cadr a))))))
        (if (if (> dir 0) (< x (- x0 1e-9)) (> x (+ x0 1e-9))) (setq x nil))))
    (setq vs (cdr vs)))
  x)

(defun bc:cut-core (g p1 p2 cfg / xl xh yl yh dir hv cur pts xt yt nx guard steep dxm dym lay e made)
  ;; 지반선 g의 p1~p2 X 구간을 낮은 쪽에서 높은 쪽으로 계단(수평 디딤 + 수직 챌판)으로 깎는다.
  ;; 디딤 끝 = 지반이 (현재 높이 + 층높이)가 되는 곳. 그 사이 지반 경사가 1:제외경사보다 완만하면 건너뛴다.
  (setq yl (bc:ground-y g (car p1)) yh (bc:ground-y g (car p2)))
  (if (and yl yh)
    (progn
      (if (> yl yh) (setq cur (list (car p2) yh 0.0) xh (car p1) dir (if (< (car p1) (car p2)) -1 1))
                    (setq cur (list (car p1) yl 0.0) xh (car p2) dir (if (< (car p1) (car p2)) 1 -1)))
      (setq hv (* (bc:cfg cfg "층높이") (bc:unit-v cfg)) lay (bc:cfg cfg "레이어") guard 0 made nil)
      (while (and (< guard 500) cur)
        (setq yt (+ (cadr cur) hv) xt (bc:x-at-y g yt (car cur) dir) guard (1+ guard))
        (if (or (null xt) (if (> dir 0) (> xt xh) (< xt xh)))
          ;; 끝: 남은 높이가 최소높이 이상이면 끝 지점까지 마지막 계단
          (progn
            (setq yh (bc:ground-y g xh))
            (if (and yh (> (- yh (cadr cur)) (* (bc:cfg cfg "최소높이") (bc:unit-v cfg))))
              (setq made (cons (bc:pline (list cur (list xh (cadr cur) 0.0) (list xh yh 0.0)) nil lay) made)))
            (setq cur nil))
          (progn
            (setq dxm (/ (abs (- xt (car cur))) (bc:unit-h cfg)) dym (bc:cfg cfg "층높이")
                  steep (or (<= (bc:cfg cfg "제외경사") 0.0) (> (/ dym (max dxm 1e-9)) (/ 1.0 (bc:cfg cfg "제외경사")))))
            (if steep
              (progn
                (setq nx (list xt (+ (cadr cur) (* (bc:cfg cfg "배수경사") 0.01 dxm (bc:unit-v cfg))) 0.0))
                (setq made (cons (bc:pline (list cur nx (list xt yt 0.0)) nil lay) made))))
            (setq cur (list xt yt 0.0)))))
      (if (= (bc:cfg cfg "숨은선") 1)
        (foreach en made
          (if (bc:ltype-ok "HIDDEN") (entmod (append (entget en) (list '(6 . "HIDDEN") (cons 48 (bc:cfg cfg "선축척"))))))))
      (length made))
    0))

(defun c:CUT (/ cfg g p1 p2)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "CUT" bc:cut-defaults))
  (initget "S")
  (setq g (entsel "\n지반선 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= g "S") (bc:open-window "CUT") (bc:settings-hint "CUT"))
    ((and g (bc:curve-p (car g)) (setq p1 (getpoint "\n층따기 시작점 지정: ")) (setq p2 (getpoint p1 "\n층따기 끝점 지정: ")))
     (princ (strcat "\n층따기 " (itoa (bc:cut-core (car g) (bc:wcs p1) (bc:wcs p2) cfg)) "단을 그렸습니다."))))
  (bc:end))
