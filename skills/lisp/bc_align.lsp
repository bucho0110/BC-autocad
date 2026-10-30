;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_align.lsp — 선형(중심선)·측점 명령 (DCP DCEN GST STT CST NUST MIP)
;;; 측점 표기
;;;  - Station: 누가거리 1250.5 → "1+250.5" (km + m). 0+000 형식 유지 옵션.
;;;  - Number : 간격 20일 때 1250.5 → "62+10.5" (번호 + 나머지). 머리말 기본 "No."
;;; 거리는 m. 도면 단위 = m × (1000 / 축척).

;;; ================================================================ 측점 문자

(setq bc:sta-defaults
  '(("측점구분" . "Station") ("측점간격" . 20.0) ("시작거리" . "0") ("축척" . 1000.0) ("소수" . 0)
    ("000유지" . 1) ("머리말" . "No.")))

(defun bc:pad3 (s / ip)
  ;; "5.5" → "005.5", "25" → "025"
  (setq ip (if (vl-string-search "." s) (substr s 1 (vl-string-search "." s)) s))
  (strcat (substr "000" 1 (max 0 (- 3 (strlen ip)))) s))

(defun bc:sta-str (d cfg / mode iv dec km m s neg)
  ;; 누가거리 d(m) → 측점 문자(머리말 포함)
  (setq mode (bc:cfg cfg "측점구분") dec (bc:cfg cfg "소수") neg (< d 0) d (abs d))
  ;; 반올림을 먼저 해서 999.9996 → 1+000 이 되게 한다
  (setq d (atof (bc:rtos d 2 dec)))
  (if (= mode "Number")
    (progn
      (setq iv (bc:cfg cfg "측점간격") km (fix (/ (+ d 1e-9) iv)) m (- d (* km iv)))
      (if (< m 1e-9) (setq m 0.0))
      (setq s (strcat (itoa km) "+" (bc:rtos m 2 dec))))
    (progn
      (setq km (fix (/ (+ d 1e-9) 1000.0)) m (- d (* km 1000.0)))
      (if (< m 1e-9) (setq m 0.0))
      (setq s (bc:rtos m 2 dec))
      (if (= (bc:cfg cfg "000유지") 1) (setq s (bc:pad3 s)))
      (setq s (strcat (itoa km) "+" s))))
  (strcat (bc:cfg cfg "머리말") (if neg "-" "") s))

(defun bc:sta-parse (s cfg / t1 p a b mode)
  ;; 측점 문자 또는 숫자 → 누가거리(m). "No.12+5"(Number, 간격) / "1+250.5"(Station) / "1250.5". 못 읽으면 nil.
  (setq mode (bc:cfg cfg "측점구분"))
  (if (numberp s) (float s)
    (progn
      (setq t1 (vl-string-trim " " (strcase s)))
      (foreach pre '("STA." "STA" "NO." "NO" "NO ")
        (if (= (substr t1 1 (strlen pre)) pre) (setq t1 (vl-string-trim " " (substr t1 (1+ (strlen pre)))))))
      (if (setq p (vl-string-search "+" t1))
        (progn
          (setq a (atof (substr t1 1 p)) b (atof (bc:strip-commas (substr t1 (+ p 2)))))
          (if (= mode "Number") (+ (* a (bc:cfg cfg "측점간격")) b) (+ (* a 1000.0) b)))
        (if (wcmatch t1 "#*,-#*,.#*") (atof (bc:strip-commas t1)) nil)))))

(defun bc:sta-start (cfg / v)
  (setq v (bc:sta-parse (bc:cfg cfg "시작거리") cfg))
  (if v v 0.0))

;;; ================================================================ 선형 공통

(defun bc:curve-len (en) (vlax-curve-getDistAtParam en (vlax-curve-getEndParam en)))

(defun bc:curve-pt (en d rev / L)
  ;; 시점에서 d(도면 단위) 위치의 점. rev면 끝에서부터.
  (setq L (bc:curve-len en))
  (vlax-curve-getPointAtDist en (max 0.0 (min L (if rev (- L d) d)))))

(defun bc:curve-ang (en d rev / L dd v a)
  ;; 진행 방향 각도(라디안). rev면 반대 방향.
  (setq L (bc:curve-len en) dd (max 0.0 (min L (if rev (- L d) d))))
  (setq v (vlax-curve-getFirstDeriv en (vlax-curve-getParamAtDist en dd)))
  (setq a (atan (cadr v) (car v)))
  (if rev (+ a pi) a))

(defun bc:curve-d (en p rev / d)
  ;; 점 p에서 선형에 내린 수선의 발까지 진행 방향 거리(도면 단위)
  (setq d (vlax-curve-getDistAtPoint en (vlax-curve-getClosestPointTo en p)))
  (if rev (- (bc:curve-len en) d) d))

(defun bc:side (en p rev / d a q)
  ;; p가 진행 방향 왼쪽이면 1, 오른쪽이면 -1
  (setq d (bc:curve-d en p rev) a (bc:curve-ang en d rev) q (bc:curve-pt en d rev))
  (if (> (- (* (cos a) (- (cadr p) (cadr q))) (* (sin a) (- (car p) (car q)))) 0) 1 -1))

(defun bc:pick-align (msg / r en)
  ;; 선형 고르기 → (ename rev). 고른 점이 끝점 쪽이면 묻지 않고 그대로, "반대(R)" 키워드로 뒤집기.
  (setq r (entsel (strcat "\n" msg ": ")))
  (if (and r (bc:curve-p (car r)))
    (progn
      (setq en (car r))
      (initget "Y N")
      (list en (= (getkword "\n선형 진행 방향이 그려진 방향과 같습니까? [예(Y)/아니오(N)] <Y>: ") "N")))
    (if r (progn (princ "\n선·폴리선·호를 고르세요.") (bc:pick-align msg)))))

(defun bc:upm-sta (cfg) (bc:upm (bc:cfg cfg "축척")))

;;; ================================================================ DCP 두 선의 중심선 작도

(setq bc:dcp-defaults '(("레이어" . "") ("선종류" . "") ("반복" . 1) ("표본수" . 0) ("허용오차" . 0.001) ("끝연장" . 0)))

(defun bc:mid (p q) (mapcar '(lambda (x y) (/ (+ x y) 2.0)) p q))

(defun bc:pt-line-dist (p a b / L)
  ;; 점 p에서 a-b 직선까지 거리(XY)
  (setq L (distance (bc:2d a) (bc:2d b)))
  (if (< L 1e-12) (distance (bc:2d p) (bc:2d a))
    (/ (abs (- (* (- (car b) (car a)) (- (cadr a) (cadr p))) (* (- (car a) (car p)) (- (cadr b) (cadr a))))) L)))

(defun bc:pt-seg-dist (p a b / L k)
  ;; 점 p에서 선분 a-b까지 거리(XY). 되돌아오는 꺾임(0,0→500,0→1,0)을 무한 직선 거리로 재면 0이 되어 지워진다.
  (setq L (+ (expt (- (car b) (car a)) 2) (expt (- (cadr b) (cadr a)) 2)))
  (if (< L 1e-24) (distance (bc:2d p) (bc:2d a))
    (progn
      (setq k (/ (+ (* (- (car p) (car a)) (- (car b) (car a))) (* (- (cadr p) (cadr a)) (- (cadr b) (cadr a)))) L)
            k (max 0.0 (min 1.0 k)))
      (distance (bc:2d p) (list (+ (car a) (* k (- (car b) (car a)))) (+ (cadr a) (* k (- (cadr b) (cadr a)))))))))

(defun bc:simplify (pts tol / n arr keep stack seg i j k mx at d out)
  ;; 더글러스-포이커: 양 끝을 잇는 선에서 가장 먼 점이 tol 넘으면 그 점을 남기고 두 쪽을 다시 본다.
  ;; 점을 배열(safearray)에 두고 할 일 목록(stack)으로 돈다 — 재귀·nth로는 점 수천 개에서 느리고 깊이 한도에 걸릴 수 있다.
  (setq n (length pts))
  (if (< n 3) pts
    (progn
      (setq arr (bc:pts->array pts)
            keep (vlax-make-safearray vlax-vbInteger (cons 0 (1- n))))
      (vlax-safearray-put-element keep 0 1)
      (vlax-safearray-put-element keep (1- n) 1)
      (setq stack (list (cons 0 (1- n))))
      (while stack
        (setq seg (car stack) stack (cdr stack) i (car seg) j (cdr seg) mx -1.0 k (1+ i))
        (while (< k j)
          (if (> (setq d (bc:pt-seg-dist (bc:arr-pt arr k) (bc:arr-pt arr i) (bc:arr-pt arr j))) mx)
            (setq mx d at k))
          (setq k (1+ k)))
        (if (and (> j (1+ i)) (> mx tol))
          (progn (vlax-safearray-put-element keep at 1)
                 (setq stack (cons (cons i at) (cons (cons at j) stack))))))
      (setq i 0)
      (foreach p pts
        (if (= (vlax-safearray-get-element keep i) 1) (setq out (cons p out)))
        (setq i (1+ i)))
      (reverse out))))

(defun bc:pts->array (pts / n a i)
  ;; 점 목록 → 2차원 실수 배열 (점 번호, 0=x 1=y)
  (setq n (length pts) a (vlax-make-safearray vlax-vbDouble (cons 0 (1- n)) '(0 . 1)) i 0)
  (foreach p pts
    (vlax-safearray-put-element a i 0 (float (car p)))
    (vlax-safearray-put-element a i 1 (float (cadr p)))
    (setq i (1+ i)))
  a)

(defun bc:arr-pt (a i) (list (vlax-safearray-get-element a i 0) (vlax-safearray-get-element a i 1)))


(defun bc:lerp (p q k) (mapcar '(lambda (x y) (+ x (* k (- y x)))) p q))

(defun bc:eq-gap (a b m)
  ;; (a까지 거리) − (b까지 거리)
  ;; 평면(XY) 거리 — 고도가 다른 두 선(예: 38번 고도 50과 0)에서 3D 거리로 재면 평면 중심이 밀린다
  (- (distance (bc:2d m) (bc:2d (vlax-curve-getClosestPointTo a m)))
     (distance (bc:2d m) (bc:2d (vlax-curve-getClosestPointTo b m)))))

(defun bc:eq-point (a b p q / len lo hi flo fhi k t1 m f side eps)
  ;; 선분 p(선 a 위)→q(선 b 위)에서 두 선까지 거리가 같은 점.
  ;; p에서는 a까지 0·b까지 양수(차이 음수), q에서는 반대라서 부호가 바뀌는 점이 반드시 있다.
  ;; 일리노이 방식(할선으로 좁히되 같은 쪽이 두 번 남으면 그쪽 값을 반으로)으로 찾고, 구간이 1e-7 도면 단위 안이거나
  ;; 차이가 1e-9 안이면 멈춘다. 예전의 이분법 50번은 실도면 제방선 2.4km에서 6분 걸렸다(실측 2026-10-29).
  (setq len (distance p q) lo 0.0 hi 1.0 flo (bc:eq-gap a b p) fhi (bc:eq-gap a b q) k 0 side 0 m p)
  (cond
    ((< len 1e-12) p)
    ((>= flo 0.0) p)
    ((<= fhi 0.0) q)
    (T
     ;; 멈춤 폭은 좌표 크기에 맞춘다 — mm 단위 TM 좌표(2억)에서 1e-7은 배정밀도로 구분할 수 있는 간격의 몇 배뿐이라
     ;; 매번 100회까지 돌았다(보조 검토 지적)
     (setq eps (max 1e-7 (* 1e-14 (+ (abs (car p)) (abs (cadr p))))))
     (while (and (< k 100) (> (* (- hi lo) len) eps))
       (setq t1 (- hi (/ (* fhi (- hi lo)) (- fhi flo))))
       (if (or (<= t1 lo) (>= t1 hi)) (setq t1 (/ (+ lo hi) 2.0)))
       (setq m (bc:lerp p q t1) f (bc:eq-gap a b m) k (1+ k))
       (cond ((< (abs f) (* eps 1e-2)) (setq lo t1 hi t1))
             ((< f 0.0) (setq lo t1 flo f) (if (= side -1) (setq fhi (/ fhi 2.0))) (setq side -1))
             (T (setq hi t1 fhi f) (if (= side 1) (setq flo (/ flo 2.0))) (setq side 1))))
     (if (= lo hi) m (bc:lerp p q (/ (+ lo hi) 2.0))))))

(defun bc:dcp-refine (a b m)
  ;; m 근처의 중심선 점: m에서 두 선에 내린 수선의 발을 잇는 선분 위의 같은 거리 점.
  ;; (가까운 점들의 가운데로 반복해서 옮기는 방식은 중심선을 따라 미끄러져 엉뚱한 점에 모였다 — 실측 2026-10-29)
  (bc:eq-point a b (vlax-curve-getClosestPointTo a m) (vlax-curve-getClosestPointTo b m)))

(defun bc:dcp-fill (a b p q depth tol / c r)
  ;; p→q 사이: 가운데를 다듬은 점 r이 직선 p-q에서 tol 넘게 벗어나면 r에서 나눠 다시. 반환은 q까지(p 제외)
  ;; r은 중심선을 따라 c 옆으로 미끄러질 수 있으므로 c까지 거리가 아니라 현(p-q)까지 거리로 판단한다
  ;; (c까지 거리로 보면 곧은 구간도 끝까지 쪼개 2.4km 제방에서 9만 6천 점이 됐다 — 실측 2026-10-29)
  (setq c (bc:mid p q) r (bc:dcp-refine a b c))
  (if (and (> depth 0) (> (bc:pt-line-dist r p q) tol))
    (append (bc:dcp-fill a b p r (1- depth) tol) (bc:dcp-fill a b r q (1- depth) tol))
    (list q)))

(defun bc:dcp-sort (a b La Lb rb pts)
  ;; 중심선 점 순서: 두 선 위 진행 거리(비율)의 합은 중심선을 따라 한 방향으로만 늘어난다
  ;; (한쪽 꼭짓점에 수선의 발이 몰려도 다른 쪽이 갈라 준다).
  (mapcar 'cdr
          (vl-sort (mapcar '(lambda (m / da db)
                              (setq da (vlax-curve-getDistAtPoint a (vlax-curve-getClosestPointTo a m))
                                    db (vlax-curve-getDistAtPoint b (vlax-curve-getClosestPointTo b m)))
                              (cons (+ (/ da La) (/ (if rb (- Lb db) db) Lb)) m))
                           pts)
                   '(lambda (x y) (< (car x) (car y))))))

(defun bc:dcp-auto-n (La w nv)
  ;; 자동 표본 수: 정점 수×4(최소 50)와, 간격이 두 선 사이 폭 w의 1/100 이하가 되는 수 중 큰 것. 최대 2만.
  (min 20000 (max 50 (* 4 nv) (if (> w 1e-9) (fix (+ 0.999 (/ La (/ w 100.0)))) 0))))

(defun bc:dcp-closed (en)
  (< (distance (bc:2d (vlax-curve-getStartPoint en)) (bc:2d (vlax-curve-getEndPoint en))) 1e-9))

(defun bc:dcp-beyond (en foot p / s e tg sg v vl)
  ;; foot이 en의 끝점이고 p가 그 끝 너머(끝 접선 방향으로 나가 있음)면 T — 그런 점은 en과 마주 보지 않는다.
  ;; 두 선 끝이 같은 횡단선에 맞춰 잘린 경우(p가 끝에서 수직)는 마주 보는 것으로 본다.
  (setq s (vlax-curve-getStartPoint en) e (vlax-curve-getEndPoint en))
  (cond ((< (distance (bc:2d foot) (bc:2d s)) 1e-7)
         (setq tg (vlax-curve-getFirstDeriv en (vlax-curve-getStartParam en)) sg -1.0))
        ((< (distance (bc:2d foot) (bc:2d e)) 1e-7)
         (setq tg (vlax-curve-getFirstDeriv en (vlax-curve-getEndParam en)) sg 1.0)))
  (if tg
    (progn
      (setq v (list (- (car p) (car foot)) (- (cadr p) (cadr foot))) vl (distance '(0 0) v))
      (> (* sg (/ (+ (* (car v) (car tg)) (* (cadr v) (cadr tg))) (max 1e-12 (distance '(0 0) (bc:2d tg)))))
         (+ 1e-9 (* 1e-6 vl))))))

(defun bc:dcp-facing (a b pa pb)
  ;; pa(선 a 위)와 pb(선 b 위)가 서로 마주 보는 짝인가: 어느 쪽도 상대 선의 끝 너머에 있지 않다.
  ;; 한쪽에서만 보면 U자 만곡의 안쪽 제방 끝에서 바깥 제방 꼬리와 짝지어 중심선 끝이 비스듬히 휘었다.
  (not (or (bc:dcp-beyond b pb pa) (bc:dcp-beyond a pa pb)
           (bc:dcp-beyond a (vlax-curve-getClosestPointTo a pb) pb)
           (bc:dcp-beyond b (vlax-curve-getClosestPointTo b pa) pa))))

(defun bc:dcp-end-p (en p)
  (or (< (distance p (bc:2d (vlax-curve-getStartPoint en))) 1e-7)
      (< (distance p (bc:2d (vlax-curve-getEndPoint en))) 1e-7)))

(defun bc:dcp-cross (a b / r p hit)
  ;; 두 선이 서로 만나거나 겹치면 T. 두 선이 끝점 하나를 함께 쓰는 것(V자)은 만나는 것으로 보지 않는다
  ;; (두 제방선이 상류 끝·구조물에서 끝점을 함께 쓰는 경우 — 그 사이 중심선은 맞닿는 점까지 하나로 정해진다).
  ;; 한쪽 끝이 다른 선 중간에 닿는 것(T자·겹침)은 만나는 것이다.
  (setq r (vlax-invoke (vlax-ename->vla-object a) 'IntersectWith (vlax-ename->vla-object b) acExtendNone))
  (while (and r (not hit))
    (setq p (list (car r) (cadr r)) r (cdddr r))
    (if (not (and (bc:dcp-end-p a p) (bc:dcp-end-p b p))) (setq hit T)))
  hit)

(defun bc:dcp-overlap (a pts / z)
  ;; 두 선에 붙은(거리 0) 중심점이 한 점이 아니라 길게 이어지면 두 선이 겹친 것(IntersectWith가 겹침을 못 볼 때 대비)
  (foreach m pts
    (if (< (distance (bc:2d m) (bc:2d (vlax-curve-getClosestPointTo a m))) 1e-7) (setq z (cons m z))))
  (and z (vl-some '(lambda (p) (> (distance (bc:2d p) (bc:2d (car z))) 1e-6)) z)))

(defun bc:dcp-flat (en / zs)
  ;; 고도가 한 값인 선인가(정점 z가 모두 같음). 고도가 변하는 3D 선은 가장 가까운 점이 3D로 잡혀 평면 중심이 밀린다.
  (setq zs (mapcar 'caddr (bc:verts en)))
  (or (null zs) (vl-every '(lambda (z) (equal z (car zs) 1e-9)) zs)))

(defun bc:dcp-mixed (crv pts / pos neg f tg s)
  ;; pts가 곡선 crv의 양쪽에 다 있으면 T(맞닿은 곳 근처처럼 선에 거의 붙은 점은 세지 않는다).
  ;; 한 선이 다른 선을 감싸거나(U자 안에 짧은 선) 평면에서만 교차(고도가 달라 IntersectWith가 못 봄)하면 중심점이
  ;; 양쪽에 생겨 정렬하면 지그재그가 된다(보조 검토 재현) — 이때는 그리지 않는다.
  (setq pos 0 neg 0)
  (foreach m pts
    (setq f (vlax-curve-getClosestPointTo crv m)
          tg (vlax-curve-getFirstDeriv crv (vlax-curve-getParamAtPoint crv f))
          s (/ (- (* (car tg) (- (cadr m) (cadr f))) (* (cadr tg) (- (car m) (car f))))
               (max 1e-12 (distance '(0 0) (bc:2d tg)))))
    (cond ((> s 1e-7) (setq pos (1+ pos))) ((< s -1e-7) (setq neg (1+ neg)))))
  (and (> pos 0) (> neg 0)))

(defun bc:dcp-reach (p q ends / u L k mx)
  ;; p에서 q→p 방향(끝 접선)으로 ends 중 가장 멀리 나간 점까지의 거리(없으면 0)
  (setq u (list (- (car p) (car q)) (- (cadr p) (cadr q))) L (distance '(0 0) u) mx 0.0)
  (if (> L 1e-12)
    (foreach e ends
      (setq k (/ (+ (* (- (car e) (car p)) (car u)) (* (- (cadr e) (cadr p)) (cadr u))) L) mx (max mx k))))
  (if (> L 1e-12) (list mx (mapcar '(lambda (x) (/ x L)) u)) (list 0.0 '(1 0))))

(defun bc:dcp-extend (out e0 e1 / r p)
  ;; 끝 처리 "끝연장": 중심선 양 끝을 끝 접선 방향으로 늘여 두 선의 해당 끝점 중 더 나간 쪽과 나란하게 한다
  ;; (끝점에서 중심선 방향에 내린 수선의 발까지). 마주 보는 구간만 그리는 기본값으로는 한 선이 더 길면 중심선이 짧다.
  (if (> (length out) 1)
    (progn
      (setq p (car out) r (bc:dcp-reach p (cadr out) e0))
      (if (> (car r) 1e-6) (setq out (cons (list (+ (car p) (* (car r) (car (cadr r)))) (+ (cadr p) (* (car r) (cadr (cadr r))))) out)))
      (setq out (reverse out) p (car out) r (bc:dcp-reach p (cadr out) e1))
      (if (> (car r) 1e-6) (setq out (cons (list (+ (car p) (* (car r) (car (cadr r)))) (+ (cadr p) (* (car r) (cadr (cadr r))))) out)))
      (reverse out))
    out))

(defun bc:dcp-core (a b cfg / La Lb n i rb m pa pb mids lay pl out va vb prev tol w)
  ;; 두 선(a, b) 사이 중심선(양쪽까지 거리가 같은 점들). 반환: 새 폴리선 핸들, 못 그리면 nil.
  ;; 1) 닫힌 선·길이 0은 받지 않는다.
  ;; 2) 각 선을 일정 간격으로 나눈 점마다 맞은편 선에 수선의 발을 내리고, 그 둘을 잇는 선분 위에서 같은 거리 점을 찾는다
  ;;    (a에서 b로, b에서 a로 양쪽 다). 수선의 발이 맞은편 선 끝 너머로 나가면(마주 보지 않는 구간) 버린다.
  ;;    길이 비율로 짝짓던 방식은 U자 만곡에서 아예 못 그리거나 합류부에서 시점이 꼬였다(보조 검토 재현).
  ;;    표본수 0 = 자동: 정점 수×4, 최소 50, 간격이 두 선 사이 폭의 1/100 이하(최대 2만, 선마다).
  ;;    정점 수만으로는 2.4km 제방에서 간격 6m라 중심선이 2~8mm 벗어났다 — 폭/100이면 1mm 안(실측 2026-10-29).
  ;; 3) 두 선의 정점마다 같은 식으로 점을 넣는다(원래 선이 꺾이는 곳).
  ;; 4) 진행 거리 비율 합으로 정렬 → 이웃한 두 점 사이 가운데가 직선에서 허용오차 넘게 벗어나면 점을 끼운다(보강).
  ;; 5) 거의 일직선인 중간 점은 뺀다(더글러스-포이커, 허용오차/2). 거리는 모두 평면(XY) 기준.
  (setq La (bc:curve-len a) Lb (bc:curve-len b) va (bc:verts a) vb (bc:verts b) tol (bc:cfg cfg "허용오차"))
  (cond
    ((or (< La 1e-9) (< Lb 1e-9)) (princ "\n길이가 0인 선입니다.") nil)
    ((or (bc:dcp-closed a) (bc:dcp-closed b)) (princ "\n닫힌 선(폐합 폴리선·원)은 두 선 사이 중심선을 그리지 않습니다.") nil)
    ;; 서로 만나거나 겹치는 두 선 사이에는 하나의 중심선이 없다(만나는 곳에서 갈라진다)
    ((bc:dcp-cross a b)
     (princ "\n두 선이 서로 만나거나 겹칩니다 — 중심선을 그리지 않습니다.") nil)
    ((not (and (bc:dcp-flat a) (bc:dcp-flat b)))
     (princ "\n고도가 변하는 3D 선입니다 — 평면 선(LWPOLYLINE 등)으로 바꾼 뒤 다시 하세요.") nil)
    (T
     (setq rb (> (+ (distance (vlax-curve-getStartPoint a) (vlax-curve-getStartPoint b))
                    (distance (vlax-curve-getEndPoint a) (vlax-curve-getEndPoint b)))
                 (+ (distance (vlax-curve-getStartPoint a) (vlax-curve-getEndPoint b))
                    (distance (vlax-curve-getEndPoint a) (vlax-curve-getStartPoint b)))))
     ;; 아래는 곡선 계산만 하므로 vla 개체로 한 번 바꿔 둔다(ename을 넘기면 vlax-curve가 부를 때마다 바꾼다)
     (setq a (vlax-ename->vla-object a) b (vlax-ename->vla-object b))
     ;; 폭: a의 1/4·1/2·3/4 지점에서 b까지 거리의 평균
     (setq w 0.0)
     (foreach k '(0.25 0.5 0.75)
       (setq pa (vlax-curve-getPointAtDist a (* La k))
             w (+ w (/ (distance (bc:2d pa) (bc:2d (vlax-curve-getClosestPointTo b pa))) 3.0))))
     ;; a 쪽 표본 → b의 수선의 발
     (setq n (if (> (bc:cfg cfg "표본수") 0) (bc:cfg cfg "표본수") (bc:dcp-auto-n La w (+ (length va) (length vb)))) i 0)
     (repeat (1+ n)
       (setq pa (vlax-curve-getPointAtDist a (* La (/ i (float n)))) pb (vlax-curve-getClosestPointTo b pa) i (1+ i))
       (if (bc:dcp-facing a b pa pb) (setq mids (cons (bc:eq-point a b pa pb) mids))))
     ;; b 쪽 표본 → a의 수선의 발
     (setq n (if (> (bc:cfg cfg "표본수") 0) (bc:cfg cfg "표본수") (bc:dcp-auto-n Lb w (+ (length va) (length vb)))) i 0)
     (repeat (1+ n)
       (setq pb (vlax-curve-getPointAtDist b (* Lb (/ i (float n)))) pa (vlax-curve-getClosestPointTo a pb) i (1+ i))
       (if (bc:dcp-facing a b pa pb) (setq mids (cons (bc:eq-point a b pa pb) mids))))
     ;; 정점에서 나온 점
     (foreach v va
       (setq v (trans v 0 0) pb (vlax-curve-getClosestPointTo b v))
       (if (bc:dcp-facing a b v pb) (setq mids (cons (bc:eq-point a b v pb) mids))))
     (foreach v vb
       (setq v (trans v 0 0) pa (vlax-curve-getClosestPointTo a v))
       (if (bc:dcp-facing a b pa v) (setq mids (cons (bc:eq-point a b pa v) mids))))
     (cond
      ((< (length mids) 2)
       (princ "\n두 선이 서로 마주 보는 구간이 없습니다.") nil)
      ((bc:dcp-overlap a mids)
       (princ "\n두 선이 서로 만나거나 겹칩니다 — 중심선을 그리지 않습니다.") nil)
      ((or (bc:dcp-mixed a mids) (bc:dcp-mixed b mids))
       (princ "\n한 선이 다른 선을 감싸거나 평면에서 서로 지나갑니다(중심이 양쪽에 생김) — 중심선을 그리지 않습니다.") nil)
      (T
         (setq mids (bc:dcp-sort a b La Lb rb mids))
         ;; 보강
         (setq out (list (car mids)) prev (car mids))
         (foreach m (cdr mids)
           (setq out (append (reverse (bc:dcp-fill a b prev m 8 tol)) out) prev m))
         ;; 보강 점까지 다시 순서대로, 겹친 점 정리, 일직선 점 빼기
         (setq mids (bc:dcp-sort a b La Lb rb out) out nil)
         (foreach m mids
           (if (or (null out) (> (distance (bc:2d m) (bc:2d (car out))) 1e-6))
             (setq out (cons m out))))
         (setq out (bc:simplify (reverse out) (/ tol 2.0)))
         (if (= (bc:cfg cfg "끝연장") 1)
           (setq out (bc:dcp-extend out (list (vlax-curve-getStartPoint a) (if rb (vlax-curve-getEndPoint b) (vlax-curve-getStartPoint b)))
                                    (list (vlax-curve-getEndPoint a) (if rb (vlax-curve-getStartPoint b) (vlax-curve-getEndPoint b))))))
         (setq lay (bc:cfg cfg "레이어"))
         (setq pl (bc:pline out nil lay))
         (if (and (/= (bc:cfg cfg "선종류") "") (bc:ltype-ok (bc:cfg cfg "선종류")))  ; 없으면 표준 .lin에서 불러온다
           (entmod (append (entget pl) (list (cons 6 (bc:cfg cfg "선종류"))))))
         (cdr (assoc 5 (entget pl))))))))

(defun c:DCP (/ cfg a b)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "DCP" bc:dcp-defaults))
  (while (progn (initget "S") (setq a (entsel "\n첫 번째 선 선택 또는 [설정 변경(S)]: ")))
    (if (= a "S")
      (progn (bc:open-window "DCP") (bc:settings-hint "DCP") (setq a nil))
      (if (and (bc:curve-p (car a)) (setq b (entsel "\n두 번째 선 선택: ")) (bc:curve-p (car b)))
        (progn (bc:dcp-core (car a) (car b) cfg) (princ "\n중심선을 그렸습니다."))))
    (if (/= (bc:cfg cfg "반복") 1) (setq a nil)))
  (bc:end))

;;; ================================================================ DCEN 원·호·두 선 중심선 표시

(setq bc:dcen-defaults '(("레이어" . "") ("선종류" . "CENTER") ("연장" . 2.0) ("선축척" . 1.0)))

(defun bc:ltype-ok (name)
  (or (= name "") (tblsearch "LTYPE" name)
      (progn (vl-catch-all-apply 'vla-Load (list (vla-get-Linetypes (vla-get-ActiveDocument (vlax-get-acad-object)))
                                                  name (if (= (getvar "MEASUREMENT") 1) "acadiso.lin" "acad.lin")))
             (tblsearch "LTYPE" name))))

(defun bc:cline (p1 p2 cfg / e lt)
  (setq e (bc:line p1 p2 (bc:cfg cfg "레이어")) lt (bc:cfg cfg "선종류"))
  (if (and (/= lt "") (bc:ltype-ok lt))
    (entmod (append (entget e) (list (cons 6 lt) (cons 48 (bc:cfg cfg "선축척"))))))
  (cdr (assoc 5 (entget e))))

(defun bc:dcen-circle (en cfg / ed c r x)
  (setq ed (entget en) c (trans (cdr (assoc 10 ed)) en 0) r (cdr (assoc 40 ed)) x (+ r (bc:cfg cfg "연장")))
  (list (bc:cline (polar c pi x) (polar c 0.0 x) cfg) (bc:cline (polar c (* pi 1.5) x) (polar c (/ pi 2) x) cfg)))

(defun bc:dcen-two (a b cfg / a1 a2 b1 b2 m1 m2 ang x)
  ;; 두 선(LINE)의 같은 쪽 끝끼리 짝지어 중점을 잇고 양 끝을 연장
  (setq a1 (vlax-curve-getStartPoint a) a2 (vlax-curve-getEndPoint a)
        b1 (vlax-curve-getStartPoint b) b2 (vlax-curve-getEndPoint b))
  (if (> (+ (distance a1 b1) (distance a2 b2)) (+ (distance a1 b2) (distance a2 b1))) (setq x b1 b1 b2 b2 x))
  (setq m1 (mapcar '(lambda (p q) (/ (+ p q) 2.0)) a1 b1) m2 (mapcar '(lambda (p q) (/ (+ p q) 2.0)) a2 b2)
        ang (angle m1 m2) x (bc:cfg cfg "연장"))
  (list (bc:cline (polar m1 (+ ang pi) x) (polar m2 ang x) cfg)))

(defun c:DCEN (/ cfg m r a b)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "DCEN" bc:dcen-defaults))
  (initget "O T S")
  (setq m (getkword "\n방식 [원·호 선택(O)/두 선 사이(T)/설정(S)] <O>: "))
  (cond
    ((= m "S") (bc:open-window "DCEN") (bc:settings-hint "DCEN"))
    ((= m "T")
     (while (and (setq a (car (entsel "\n첫 번째 선 선택: "))) (setq b (car (entsel "\n두 번째 선 선택: "))))
       (bc:dcen-two a b cfg)))
    (T
     (princ "\n원·호 선택: ")
     (if (setq r (ssget '((0 . "CIRCLE,ARC"))))
       (progn (setq m 0) (while (< m (sslength r)) (bc:dcen-circle (ssname r m) cfg) (setq m (1+ m)))))))
  (bc:end))

;;; ================================================================ GST 지정점 측점 확인

(setq bc:gst-defaults
  (append bc:sta-defaults
          '(("도면표기" . 1) ("높이" . 2.5) ("레이어" . "") ("문자위치" . "지정점수평") ("간격" . 3.0) ("거리표기" . "측점"))))

(defun bc:sta-label (d cfg / s)
  (setq s (bc:sta-str d cfg))
  (cond ((= (bc:cfg cfg "거리표기") "거리") (bc:rtos d 2 (bc:cfg cfg "소수")))
        ((= (bc:cfg cfg "거리표기") "모두") (strcat s " (" (bc:rtos d 2 (bc:cfg cfg "소수")) "m)"))
        (T s)))

(defun bc:place-sta-text (en rev dd p s cfg pos / a q h g lay)
  ;; 측점 문자 배치. pos: 지정점수평 / 선형방향좌 / 선형방향우 / 수직좌 / 수직좌반대 / 수직우 / 수직우반대 / 수직중간앞 / 수직중간뒤
  (setq a (bc:curve-ang en dd rev) q (bc:curve-pt en dd rev) h (bc:cfg cfg "높이") g (* h (bc:cfg cfg "간격"))
        lay (bc:cfg cfg "레이어"))
  (cond
    ((= pos "지정점수평") (bc:text p s h lay "BL" 0.0))
    ((= pos "선형방향좌") (bc:text (polar q (+ a (/ pi 2)) g) s h lay "BC" a))
    ((= pos "선형방향우") (bc:text (polar q (- a (/ pi 2)) g) s h lay "TC" a))
    ((= pos "수직좌") (bc:text (polar q (+ a (/ pi 2)) g) s h lay "ML" (+ a (/ pi 2))))
    ((= pos "수직좌반대") (bc:text (polar q (+ a (/ pi 2)) g) s h lay "MR" (- a (/ pi 2))))
    ((= pos "수직우") (bc:text (polar q (- a (/ pi 2)) g) s h lay "MR" (+ a (/ pi 2))))
    ((= pos "수직우반대") (bc:text (polar q (- a (/ pi 2)) g) s h lay "ML" (- a (/ pi 2))))
    ((= pos "수직중간앞") (bc:text (polar q (+ a pi) (* h 0.4)) s h lay "BC" (+ a (/ pi 2))))
    (T (bc:text (polar q a (* h 0.4)) s h lay "TC" (+ a (/ pi 2))))))

(defun bc:gst-core (en rev p cfg / dd d s e)
  ;; p에서 선형에 내린 수선의 발의 측점. 반환 (누가거리m 측점문자 핸들|nil)
  (setq dd (bc:curve-d en p rev)
        d (+ (bc:sta-start cfg) (/ dd (bc:upm-sta cfg)))
        s (bc:sta-label d cfg))
  (if (= (bc:cfg cfg "도면표기") 1)
    (setq e (bc:place-sta-text en rev dd p s cfg (bc:cfg cfg "문자위치"))))
  (list d s (if e (cdr (assoc 5 (entget e))))))

(defun c:GST (/ cfg al p r)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "GST" bc:gst-defaults))
  (initget "S")
  (setq al (entsel "\n선형 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= al "S") (bc:open-window "GST") (bc:settings-hint "GST"))
    ((and al (bc:curve-p (car al)))
     (initget "Y N")
     (setq al (list (car al) (= (getkword "\n선형 진행 방향이 그려진 방향과 같습니까? [예(Y)/아니오(N)] <Y>: ") "N")))
     (while (setq p (getpoint "\n조회 점 지정: "))
       (setq r (bc:gst-core (car al) (cadr al) (bc:wcs p) cfg))
       (princ (strcat "\n측점 = " (cadr r) "  (누가거리 " (bc:rtos (car r) 2 4) " m)")))))
  (bc:end))

;;; ================================================================ STT 측점 인출선

(setq bc:stt-defaults
  (append bc:sta-defaults
          '(("방식" . "한점") ("높이" . 2.5) ("레이어" . "") ("인출시작" . 2.0) ("인출끝" . 15.0) ("인출선" . 1)
            ("점표기" . 1) ("점지름" . 0.8) ("표기명칭" . "") ("연장소수" . 2) ("연장머리" . "L=") ("연장꼬리" . "m")
            ("방향" . "L") ("구간구분" . " ~ ") ("구간소수" . 0) ("구간거리" . 6.0) ("줄간격" . 1.45) ("문자스타일" . ""))))

(defun bc:stt-one (en rev dd cfg side name / a q h p1 p2 s lay ents)
  ;; 측점 dd(도면 거리)에서 선형 수직으로 side(1 좌, -1 우) 쪽에 인출선 + 측점 문자(+ 명칭)
  (setq a (bc:curve-ang en dd rev) q (bc:curve-pt en dd rev) h (bc:cfg cfg "높이") lay (bc:cfg cfg "레이어")
        p1 (polar q (+ a (* side (/ pi 2))) (* h (bc:cfg cfg "인출시작")))
        p2 (polar q (+ a (* side (/ pi 2))) (* h (bc:cfg cfg "인출끝")))
        s (bc:sta-str (+ (bc:sta-start cfg) (/ dd (bc:upm-sta cfg))) cfg))
  (if (= (bc:cfg cfg "인출선") 1) (setq ents (cons (bc:line p1 p2 lay) ents)))
  (if (= (bc:cfg cfg "점표기") 1)
    (setq ents (cons (bc:circle p1 (/ (* h (bc:cfg cfg "점지름")) 2.0) lay) ents)))
  ;; 문자는 인출선 끝쪽, 선을 따라(위로 읽히게)
  (setq ents (cons (bc:text (polar (polar p2 (+ a (* side (/ pi 2))) (* h -0.2)) a (* h -0.3)) s h lay (if (= side 1) "BR" "BL")
                            (+ a (* side (/ pi 2)) (if (= side 1) 0.0 pi))) ents))
  (if (and name (/= name ""))
    (setq ents (cons (bc:text (polar (polar p2 (+ a (* side (/ pi 2))) (* h -0.2)) a (* h 0.3)) name h lay (if (= side 1) "TR" "TL")
                              (+ a (* side (/ pi 2)) (if (= side 1) 0.0 pi))) ents)))
  ents)

(defun bc:stt-style (e st / ed s)
  ;; 문자 스타일을 st로(도면에 그 스타일이 있을 때만)
  (if (and e (/= st "") (setq s (tblsearch "STYLE" st)))
    (progn (setq ed (entget e) ed (subst (cons 7 st) (assoc 7 ed) ed)
                 ed (subst (cons 41 (max 0.01 (cdr (assoc 41 s)))) (assoc 41 ed) ed))
           (entmod ed) (entupd e)))
  e)

(defun bc:stt-range (en rev dds cfg sides name / h lay st L s1 s2 tw w d1 d2 ends a q up rot c g out)
  ;; 구간 표기(평면도 지구명 견본): 구간 양 끝 안쪽에 두 줄 문자, 선형을 따라(위로 읽히게).
  ;;   명칭 L=1,208m
  ;;   (No.18+076 ~ No.19+270)
  ;; 구간이 문자보다 짧으면 가운데 한 곳에만 쓴다. 인출선·Dot은 쓰지 않는다(견본에 없음).
  (setq h (bc:cfg cfg "높이") lay (bc:cfg cfg "레이어") st (bc:cfg cfg "문자스타일")
        d1 (min (car dds) (cadr dds)) d2 (max (car dds) (cadr dds))
        L (/ (- d2 d1) (bc:upm-sta cfg))
        s1 (strcat (if (and name (/= name "")) (strcat name " ") "") (bc:cfg cfg "연장머리")
                   (bc:fmt-thousands L (bc:cfg cfg "구간소수")) (bc:cfg cfg "연장꼬리"))
        s2 (strcat "(" (bc:sta-str (+ (bc:sta-start cfg) (/ d1 (bc:upm-sta cfg))) cfg) (bc:cfg cfg "구간구분")
                   (bc:sta-str (+ (bc:sta-start cfg) (/ d2 (bc:upm-sta cfg))) cfg) ")")
        tw (if (and (/= st "") (tblsearch "STYLE" st)) st (getvar "TEXTSTYLE"))
        w (apply 'max (mapcar '(lambda (s / b) (setq b (textbox (list (cons 1 s) (cons 40 h) (cons 7 tw)
                                                                       (cons 41 (max 0.01 (cdr (assoc 41 (tblsearch "STYLE" tw))))))))
                                 (- (car (cadr b)) (car (car b))))
                              (list s1 s2)))
        g (* h (bc:cfg cfg "줄간격") 0.5)
        ends (if (> (- d2 d1) (* 2.0 w)) (list (+ d1 (/ w 2.0)) (- d2 (/ w 2.0))) (list (/ (+ d1 d2) 2.0))))
  (foreach dd ends
    (setq a (bc:curve-ang en dd rev) q (bc:curve-pt en dd rev)
          ;; 위로 읽히게: 90°~270°면 뒤집는다
          rot (if (and (> (rem (+ a (* 4 pi)) (* 2 pi)) (+ (/ pi 2) 1e-9)) (<= (rem (+ a (* 4 pi)) (* 2 pi)) (+ (* 1.5 pi) 1e-9))) (+ a pi) a)
          up (+ rot (/ pi 2)))
    (foreach sd sides
      (setq c (polar q (+ a (* sd (/ pi 2))) (* h (bc:cfg cfg "구간거리"))))
      (setq out (cons (bc:stt-style (bc:text (polar c up g) s1 h lay "MC" rot) st) out)
            out (cons (bc:stt-style (bc:text (polar c up (- g)) s2 h lay "MC" rot) st) out))))
  (reverse out))

(defun bc:stt-core (en rev dds cfg sides name / out)
  ;; dds: 도면 거리 목록, sides: (1) (-1) (1 -1). 두 점이면 명칭에 연장을 붙인다. 구간이면 견본 형식 두 줄 문자.
  (if (and (= (length dds) 2) (= (bc:cfg cfg "방식") "구간"))
    (setq out (bc:stt-range en rev dds cfg sides name) dds nil))
  (if (and (= (length dds) 2) (= (bc:cfg cfg "방식") "두점"))
    (setq name (strcat (if name name "") (if (and name (/= name "")) " " "")
                       (bc:cfg cfg "연장머리")
                       (bc:rtos (/ (abs (- (cadr dds) (car dds))) (bc:upm-sta cfg)) 2 (bc:cfg cfg "연장소수"))
                       (bc:cfg cfg "연장꼬리"))))
  (foreach dd dds (foreach sd sides (setq out (append out (bc:stt-one en rev dd cfg sd name)))))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) out))

(defun bc:stt-sides (k) (cond ((= k "R") '(-1)) ((= k "A") '(1 -1)) (T '(1))))

(defun c:STT (/ cfg al p p2 k)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "STT" bc:stt-defaults))
  (initget "S")
  (setq al (entsel "\n선형 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= al "S") (bc:open-window "STT") (bc:settings-hint "STT"))
    ((and al (bc:curve-p (car al)))
     (initget "Y N")
     (setq al (list (car al) (= (getkword "\n선형 진행 방향이 그려진 방향과 같습니까? [예(Y)/아니오(N)] <Y>: ") "N")))
     (setq k (bc:cfg cfg "방향"))
     (while (setq p (getpoint (if (member (bc:cfg cfg "방식") '("두점" "구간")) "\n첫 번째 점(시점) 지정: " "\n인출선 표기할 점 지정: ")))
       (setq p2 (if (member (bc:cfg cfg "방식") '("두점" "구간")) (getpoint "\n두 번째 점(종점) 지정: ")))
       (initget "L R A")
       (setq k (cond ((getkword (strcat "\n표기 방향 [좌(L)/우(R)/모두(A)] <" k ">: "))) (T k)))
       (bc:stt-core (car al) (cadr al)
                    (vl-remove nil (list (bc:curve-d (car al) (bc:wcs p) (cadr al)) (if p2 (bc:curve-d (car al) (bc:wcs p2) (cadr al)))))
                    cfg (bc:stt-sides k) (bc:cfg cfg "표기명칭")))
     (bc:cfg-save "STT" (bc:cfg-set cfg "방향" k))))
  (bc:end))

;;; ================================================================ CST 두 측점 사이 거리

(setq bc:cst-defaults (append bc:sta-defaults '(("문자표기" . 0) ("높이" . 2.5) ("레이어" . "") ("연장머리" . "L=") ("연장꼬리" . "m") ("연장소수" . 2))))

(defun c:CST (/ cfg a b da db p L)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "CST" bc:cst-defaults))
  (initget "S")
  (setq a (entsel "\n첫 번째 측점 문자 선택 또는 [설정 변경(S)]: "))
  (cond
    ((= a "S") (bc:open-window "CST") (bc:settings-hint "CST"))
    ((and a (setq b (entsel "\n두 번째 측점 문자 선택: ")))
     (setq da (bc:sta-parse (bc:text-of (car a)) cfg) db (bc:sta-parse (bc:text-of (car b)) cfg))
     (if (and da db)
       (progn
         (setq L (abs (- db da)))
         (princ (strcat "\n" (bc:text-of (car a)) " ~ " (bc:text-of (car b)) " : " (bc:rtos L 2 4) " m"))
         (if (and (= (bc:cfg cfg "문자표기") 1) (setq p (getpoint "\n연장 문자 위치 지정: ")))
           (bc:text (bc:wcs p) (strcat (bc:cfg cfg "연장머리") (bc:rtos L 2 (bc:cfg cfg "연장소수")) (bc:cfg cfg "연장꼬리"))
                    (bc:cfg cfg "높이") (bc:cfg cfg "레이어") "BC" 0.0)))
       (princ "\n측점 문자를 읽지 못했습니다(측점 구분·간격 설정 확인)."))))
  (bc:end))

;;; ================================================================ NUST 측점 문자 ↔ 숫자

(setq bc:nust-defaults (append bc:sta-defaults '(("변환" . "측점→숫자") ("숫자소수" . 2) ("앞문자" . "") ("뒤문자" . ""))))

(defun bc:nust-one (en cfg / ed s d new)
  ;; 반환: 실제로 바꾼 새 문자(잠긴 레이어라 못 바꿨으면 nil). MTEXT는 서식 코드를 뗀 글자로 읽는다.
  (setq ed (entget en) s (bc:text-of en))
  (if (and s (setq d (bc:sta-parse (if (= (bc:cfg cfg "변환") "측점→숫자") s (bc:strip-commas s)) cfg)))
    (progn
      (setq new (strcat (bc:cfg cfg "앞문자")
                        (if (= (bc:cfg cfg "변환") "측점→숫자") (bc:rtos d 2 (bc:cfg cfg "숫자소수")) (bc:sta-str d cfg))
                        (bc:cfg cfg "뒤문자")))
      ;; 긴 MTEXT는 앞부분이 3번 그룹들에 나뉘어 있다 — 1번만 바꾸면 옛 앞부분이 남으므로 3번 그룹은 지운다
      (setq ed (vl-remove-if '(lambda (g) (= (car g) 3)) (subst (cons 1 new) (assoc 1 ed) ed)))
      (if (entmod ed) (progn (entupd en) new)))))

(defun c:NUST (/ cfg ss i n)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "NUST" bc:nust-defaults))
  (princ (strcat "\n<현재: " (bc:cfg cfg "변환") ", " (bc:cfg cfg "측점구분") "> 바꿀 문자 선택(설정은 NUST 창: 엔터 후 S): "))
  (if (setq ss (ssget '((0 . "TEXT,MTEXT"))))
    (progn (setq i 0 n 0)
           (while (< i (sslength ss)) (if (bc:nust-one (ssname ss i) cfg) (setq n (1+ n))) (setq i (1+ i)))
           (princ (strcat "\n" (itoa n) "개 바꿈.")))
    (progn (initget "S") (if (= (getkword "\n[설정 변경(S)] <끝>: ") "S") (progn (bc:open-window "NUST") (bc:settings-hint "NUST")))))
  (bc:end))

;;; ================================================================ MIP 원곡선 선형 IP

(setq bc:mip-defaults '(("높이" . 2.5) ("레이어" . "") ("IP선" . 1) ("소수" . 3) ("머리말" . "IP.") ("시작번호" . 1)))

(defun bc:lw-segs (en / ed out p b prev)
  ;; LWPOLYLINE → ((p1 p2 bulge) ...)
  (setq ed (entget en))
  (foreach g ed
    (cond ((= (car g) 10) (if p (setq out (cons (list p (list (cadr g) (caddr g)) b) out))) (setq p (list (cadr g) (caddr g)) b 0.0))
          ((= (car g) 42) (setq b (cdr g)))))
  (reverse out))

(defun bc:inters-inf (a1 a2 b1 b2) (inters a1 a2 b1 b2 nil))

(defun bc:mip-core (en cfg / segs i s prev nxt ip h lay n ents ia r tl cl c txt)
  ;; 호 구간(볼록 ≠ 0)마다 앞뒤 직선(없으면 호 끝 접선)의 교점 = IP. R·IA·TL·CL 표기.
  (setq segs (bc:lw-segs en) h (bc:cfg cfg "높이") lay (bc:cfg cfg "레이어") n (bc:cfg cfg "시작번호") i 0)
  (foreach s segs
    ;; 반원(볼록 ±1, 교각 180°)은 두 접선이 나란해 IP가 없다 — 건너뛴다
    (if (and (/= (caddr s) 0.0) (> (abs (- (abs (caddr s)) 1.0)) 1e-9))
      (progn
        (setq ia (* 4.0 (atan (abs (caddr s))))                       ; 교각 = 중심각
              c (distance (car s) (cadr s))
              r (/ c (* 2.0 (sin (/ ia 2.0))))
              tl (* r (/ (sin (/ ia 2.0)) (cos (/ ia 2.0))))
              cl (* r ia))
        ;; 시작·끝 접선 방향
        (setq prev (angle (car s) (cadr s)))
        (setq ip (bc:inters-inf (car s) (polar (car s) (- prev (* (if (> (caddr s) 0) 1 -1) (/ ia 2.0))) 1.0)
                                (cadr s) (polar (cadr s) (+ prev (* (if (> (caddr s) 0) 1 -1) (/ ia 2.0))) 1.0)))
        (if ip
          (progn
            (setq ip (list (car ip) (cadr ip) 0.0))
            (if (= (bc:cfg cfg "IP선") 1)
              (setq ents (cons (bc:pline (list (car s) ip (cadr s)) nil lay) ents)))
            (setq txt (list (strcat (bc:cfg cfg "머리말") (itoa n))
                            (strcat "IA=" (angtos ia 1 4))
                            (strcat "R=" (bc:rtos r 2 (bc:cfg cfg "소수")))
                            (strcat "TL=" (bc:rtos tl 2 (bc:cfg cfg "소수")))
                            (strcat "CL=" (bc:rtos cl 2 (bc:cfg cfg "소수")))))
            (setq i 0)
            (foreach t1 txt (setq ents (cons (bc:text (list (+ (car ip) h) (- (cadr ip) (* i h 1.6)) 0.0) t1 h lay "ML" 0.0) ents) i (1+ i)))
            (setq n (1+ n)))))))
  (mapcar '(lambda (e) (cdr (assoc 5 (entget e)))) ents))

(defun c:MIP (/ cfg en)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "MIP" bc:mip-defaults))
  (initget "S")
  (setq en (entsel "\n원곡선 선형(폴리선) 선택 또는 [설정 변경(S)]: "))
  (cond ((= en "S") (bc:open-window "MIP") (bc:settings-hint "MIP"))
        ((and en (= (cdr (assoc 0 (entget (car en)))) "LWPOLYLINE")) (bc:mip-core (car en) cfg))
        (en (princ "\nLWPOLYLINE(호가 들어간 폴리선)만 됩니다.")))
  (bc:end))

;;; ================================================================ 선형 표본 (DSTA·DIBC 창·MCP가 쓴다)

(defun bc:samples (en rev dds fp / p a)
  ;; 도면 거리 목록 dds의 점·진행 각도를 S<탭>거리<탭>x<탭>y<탭>각도 줄로
  (foreach dd dds
    (setq p (bc:curve-pt en dd rev) a (bc:curve-ang en dd rev))
    (write-line (strcat "S\t" (bc:rtos dd 2 10) "\t" (bc:rtos (car p) 2 10) "\t" (bc:rtos (cadr p) 2 10) "\t" (bc:rtos a 2 12)) fp)))

(defun bc:normal-hit (p a others al / q1 q2 best ip d en ob sp L)
  ;; p에서 진행 각도 a의 수직선(양쪽)과 others(ename 목록)의 교점 중 가까운 것 → ((거리 부호) ...) 각 선마다
  ;; al(기준 선형)이 있으면 교점 u에서 al로 내린 가장 가까운 점이 al을 따라 p에서 |pu| 안에 있는 교점만 센다 —
  ;; 대상 선이 그 측점 옆에 없을 때 수직선이 수 km 밖에서 대상 선을 만나 엉뚱한 거리를 냈다(실제 하천 도면 실측 2026-10-29).
  ;; 가장 가까운 점이 꼭 p여야 한다고 하면 꺾임점 앞뒤 d·tan(꺾임각/2) 안쪽 대상 선이 빈칸이 된다(보조 검토 재현).
  ;; 수직선 길이: 도면 범위의 2배(최소 1e5) — mm 도면에서 1e5는 100m뿐이다.
  (setq L (min 1e9 (max 1e5 (* 2.0 (distance (bc:2d (getvar "EXTMIN")) (bc:2d (getvar "EXTMAX"))))))
        q1 (polar p (+ a (/ pi 2)) L) q2 (polar p (- a (/ pi 2)) L))
  (if al (setq sp (vlax-curve-getDistAtPoint al (vlax-curve-getClosestPointTo al p))))
  (mapcar
    '(lambda (en / pts)
       (setq pts (bc:hits q1 q2 en))
       (if pts
         (progn
           (if al
             (setq pts (vl-remove-if-not
                         '(lambda (u) (< (abs (- (vlax-curve-getDistAtPoint al (vlax-curve-getClosestPointTo al u)) sp))
                                         (+ 1e-4 (distance (bc:2d p) (bc:2d u)))))
                         pts)))
           (if pts
             (progn
               (setq best (car (vl-sort pts '(lambda (u v) (< (distance (bc:2d p) (bc:2d u)) (distance (bc:2d p) (bc:2d v)))))))
               (list (distance (bc:2d p) (bc:2d best))
                     (if (> (- (* (cos a) (- (cadr best) (cadr p))) (* (sin a) (- (car best) (car p)))) 0) 1 -1)))))
         nil))
    others))
