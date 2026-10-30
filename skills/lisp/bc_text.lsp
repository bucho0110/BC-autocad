;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_text.lsp — 문자 정렬 명령
;;; CR: 고른 문자들을 두 점으로 정한 사각형(또는 고른 객체)의 가운데로 옮기고 가운데(MC) 정렬로 바꾼다.
;;;     여러 문자를 고르면 묶음 전체의 가운데를 맞추므로 문자 사이 간격은 그대로다.
;;; ART: 문자 정렬점을 바꾼 뒤(보이는 자리는 그대로) 지정 점에 수평·수직으로 맞추거나 간격을 고르게 한다.
;;; CTS: 문자를 조금 비켜 복사해 그림자를 만들고 원본 뒤로 보낸다.

(defun bc:cr-box (e / o mn mx)
  ;; 객체 외곽 상자(WCS) ((xmin ymin z) (xmax ymax z))
  (setq o (vlax-ename->vla-object e))
  (vla-GetBoundingBox o 'mn 'mx)
  (list (vlax-safearray->list mn) (vlax-safearray->list mx)))

(defun bc:mid2 (a b) (list (/ (+ (car a) (car b)) 2.0) (/ (+ (cadr a) (cadr b)) 2.0) 0.0))

(defun bc:obj-center (e / ed ty)
  ;; 원·호·타원은 중심, 나머지는 외곽 상자 가운데
  (setq ed (entget e) ty (cdr (assoc 0 ed)))
  (if (member ty '("CIRCLE" "ARC" "ELLIPSE"))
    (trans (cdr (assoc 10 ed)) (if (= ty "ELLIPSE") 0 e) 0)
    (apply 'bc:mid2 (bc:cr-box e))))

(defun bc:cr-core (enames target / boxes lo hi dx dy n ed bb p)
  ;; enames: TEXT·MTEXT. target: 옮길 가운데(WCS). 바꾼 문자 수
  (setq boxes (mapcar 'bc:cr-box enames))
  (setq lo (list (apply 'min (mapcar 'caar boxes)) (apply 'min (mapcar 'cadar boxes)))
        hi (list (apply 'max (mapcar 'caadr boxes)) (apply 'max (mapcar '(lambda (b) (cadadr b)) boxes))))
  (setq dx (- (car target) (/ (+ (car lo) (car hi)) 2.0))
        dy (- (cadr target) (/ (+ (cadr lo) (cadr hi)) 2.0)) n 0)
  (foreach e enames
    (setq ed (entget e) bb (bc:cr-box e)
          p (list (+ dx (/ (+ (caar bb) (caadr bb)) 2.0)) (+ dy (/ (+ (cadar bb) (cadadr bb)) 2.0)) 0.0))
    (cond ((= (cdr (assoc 0 ed)) "TEXT")
           (setq p (trans p 0 (cdr (assoc 210 ed))))
           (setq ed (subst (cons 72 1) (assoc 72 ed) ed) ed (subst (cons 73 2) (assoc 73 ed) ed))
           (setq ed (subst (cons 11 p) (assoc 11 ed) ed) ed (subst (cons 10 p) (assoc 10 ed) ed))
           (if (entmod ed) (setq n (1+ n))))
          ((= (cdr (assoc 0 ed)) "MTEXT")
           (setq ed (subst (cons 71 5) (assoc 71 ed) ed) ed (subst (cons 10 p) (assoc 10 ed) ed))
           (if (entmod ed) (setq n (1+ n))))))
  n)

(defun c:CR (/ ss es i p1 p2 o target n)
  (bc:begin nil)
  (princ "\n가운데로 옮길 문자 선택: ")
  (if (setq ss (ssget '((0 . "TEXT,MTEXT"))))
    (progn
      (setq i 0)
      (while (< i (sslength ss)) (setq es (cons (ssname ss i) es) i (1+ i)))
      (initget "E")
      (setq p1 (getpoint "\n첫 번째 모서리 점 지정 또는 [객체 선택(E)]: "))
      (cond ((= p1 "E")
             (if (setq o (entsel "\n기준 객체 선택: ")) (setq target (bc:obj-center (car o)))))
            (p1
             (if (setq p2 (getcorner p1 "\n두 번째 모서리 점 지정: "))
               (setq target (bc:mid2 (trans p1 1 0) (trans p2 1 0))))))
      (if target
        (progn
          (setq n (bc:cr-core es target))
          (princ (strcat "\n[BC] 문자 " (itoa n) "개를 가운데로 옮겼습니다(가운데 정렬)."))))))
  (bc:end))

;;; ================================================================ ART 문자 정렬

(setq bc:art-defaults
  '(("방식" . "수평 정렬") ("정렬점" . "중간 중심") ("간격함께" . 0) ("간격방식" . "수직 줄 간격") ("간격" . 0.0)
    ("이격" . 0.0)))

;; 이름 → (72 가로, 73 세로, MTEXT 71)
(setq bc:art-justs
  '(("왼쪽 위" 0 3 1) ("중심 위" 1 3 2) ("오른쪽 위" 2 3 3) ("왼쪽 중간" 0 2 4) ("중간 중심" 1 2 5) ("오른쪽 중간" 2 2 6)
    ("왼쪽 아래" 0 1 7) ("중심 아래" 1 1 8) ("오른쪽 아래" 2 1 9) ("왼쪽" 0 0 7) ("중심" 1 0 8) ("오른쪽" 2 0 9)))

(defun bc:art-just (e name / ed j tb h lx ly r p0 p bb)
  ;; 정렬점을 바꾸되 보이는 자리는 그대로 둔다. 새 정렬점(WCS)을 돌려준다.
  ;; TEXT: 10은 늘 왼쪽 기준선 점이고, 글자 좌표계에서 가운데 = 글자 상자 가운데, 중간 = 높이/2, 위 = 높이,
  ;;       아래 = 글자 상자 아래(내림 글자 끝), 기준선 = 0 (AutoCAD 정렬 규칙과 같다).
  (setq ed (entget e) j (cdr (assoc name bc:art-justs)))
  (cond
    ((= (cdr (assoc 0 ed)) "TEXT")
     (setq tb (textbox ed) h (cdr (assoc 40 ed)) r (cdr (assoc 50 ed)) p0 (cdr (assoc 10 ed))
           lx (cond ((= (car j) 0) (car (car tb))) ((= (car j) 1) (/ (+ (car (car tb)) (car (cadr tb))) 2.0)) (T (car (cadr tb))))
           ly (cond ((= (cadr j) 0) 0.0) ((= (cadr j) 1) (cadr (car tb))) ((= (cadr j) 2) (/ h 2.0)) (T h))
           p (list (+ (car p0) (- (* lx (cos r)) (* ly (sin r)))) (+ (cadr p0) (+ (* lx (sin r)) (* ly (cos r)))) (caddr p0)))
     (setq ed (subst (cons 72 (car j)) (assoc 72 ed) ed) ed (subst (cons 73 (cadr j)) (assoc 73 ed) ed))
     (setq ed (if (assoc 11 ed) (subst (cons 11 p) (assoc 11 ed) ed) (append ed (list (cons 11 p)))))
     (entmod ed)
     (trans p e 0))
    ((= (cdr (assoc 0 ed)) "MTEXT")
     (setq bb (bc:cr-box e)
           p (list (nth (car j) (list (caar bb) (/ (+ (caar bb) (caadr bb)) 2.0) (caadr bb)))
                   (cond ((= (cadr j) 3) (cadadr bb)) ((= (cadr j) 2) (/ (+ (cadar bb) (cadadr bb)) 2.0)) (T (cadar bb)))
                   (caddr (cdr (assoc 10 ed)))))
     (entmod (subst (cons 10 p) (assoc 10 ed) (subst (cons 71 (caddr j)) (assoc 71 ed) ed)))
     p)))

(defun bc:art-move (e a b)
  (vla-Move (vlax-ename->vla-object e) (vlax-3d-point a) (vlax-3d-point b)))

(defun bc:art-space (items how gap / srt fst lst n k cur prev bb pb)
  ;; items: ((e . 정렬점) ...). 간격 조정 후 옮긴 수
  (setq n 0)
  (cond
    ((wcmatch how "수직*")
     (setq srt (vl-sort items '(lambda (a b) (> (cadr (cdr a)) (cadr (cdr b)))))))
    (T (setq srt (vl-sort items '(lambda (a b) (< (car (cdr a)) (car (cdr b))))))))
  (setq fst (cdr (car srt)) lst (cdr (last srt)) k 0 prev nil)
  (foreach it srt
    (setq cur (cdr it))
    (cond
      ((= k 0))
      ((= how "수직 줄 간격") (bc:art-move (car it) cur (list (car cur) (- (cadr fst) (* k gap)) (caddr cur))) (setq n (1+ n)))
      ((= how "수직 맨 위·아래 등간격")
       (bc:art-move (car it) cur (list (car cur) (+ (cadr fst) (* k (/ (- (cadr lst) (cadr fst)) (1- (length srt))))) (caddr cur)))
       (setq n (1+ n)))
      ((= how "수직 문자 사이 간격")
       (setq bb (bc:cr-box (car it)) pb (bc:cr-box (car prev)))
       (bc:art-move (car it) cur (list (car cur) (+ (cadr cur) (- (cadar pb) gap (cadadr bb))) (caddr cur))) (setq n (1+ n)))
      ((= how "수평 줄 간격") (bc:art-move (car it) cur (list (+ (car fst) (* k gap)) (cadr cur) (caddr cur))) (setq n (1+ n)))
      ((= how "수평 맨 앞·뒤 등간격")
       (bc:art-move (car it) cur (list (+ (car fst) (* k (/ (- (car lst) (car fst)) (1- (length srt))))) (cadr cur) (caddr cur)))
       (setq n (1+ n))))
    (setq prev it k (1+ k)))
  n)

(defun bc:art-core (enames pt cfg / mode j d items n ap)
  ;; 정렬점 바꾸기 → 수평(Y 맞춤)·수직(X 맞춤) 정렬 → (간격). 바꾼 문자 수.
  ;; 이격: 수직 정렬은 왼쪽 정렬 +X·오른쪽 −X, 수평 정렬은 위 정렬 −Y·아래·기준선 +Y 쪽으로 띄운다(가운데·중간은 0).
  (setq mode (bc:cfg cfg "방식") j (cdr (assoc (bc:cfg cfg "정렬점") bc:art-justs)) d (bc:cfg cfg "이격"))
  (foreach e enames (if (setq ap (bc:art-just e (bc:cfg cfg "정렬점"))) (setq items (cons (cons e ap) items))))
  (setq items (reverse items))
  (if (and pt (/= mode "간격 조정"))
    (setq items
      (mapcar '(lambda (it / a b)
                 (setq a (cdr it))
                 (setq b (if (= mode "수직 정렬")
                           (list (+ (car pt) (cond ((= (car j) 0) d) ((= (car j) 2) (- d)) (T 0.0))) (cadr a) (caddr a))
                           (list (car a) (+ (cadr pt) (cond ((= (cadr j) 3) (- d)) ((= (cadr j) 2) 0.0) (T d))) (caddr a))))
                 (bc:art-move (car it) a b)
                 (cons (car it) b))
              items)))
  (if (and (cdr items) (or (= mode "간격 조정") (= (bc:cfg cfg "간격함께") 1)))
    (bc:art-space items (bc:cfg cfg "간격방식") (bc:cfg cfg "간격")))
  (length items))

(defun bc:art-needs-gap (cfg)
  (and (or (= (bc:cfg cfg "방식") "간격 조정") (= (bc:cfg cfg "간격함께") 1))
       (not (wcmatch (bc:cfg cfg "간격방식") "*등간격"))))

(defun c:ART (/ cfg ss pt g)
  (bc:begin '("OSMODE"))
  (setq cfg (bc:cfg-load "ART" bc:art-defaults))
  (princ (strcat "\n<" (bc:cfg cfg "방식") ", " (bc:cfg cfg "정렬점") "> 정렬할 문자 선택(설정은 엔터 후 S): "))
  (if (setq ss (ssget '((0 . "TEXT,MTEXT"))))
    (progn
      (if (/= (bc:cfg cfg "방식") "간격 조정") (setq pt (getpoint "\n정렬 기준점 지정: ")))
      (if (and (bc:art-needs-gap cfg) (<= (bc:cfg cfg "간격") 0.0))
        (if (setq g (getdist "\n간격 입력 또는 두 점 지정: ")) (setq cfg (bc:cfg-set cfg "간격" g))))
      (if (or pt (= (bc:cfg cfg "방식") "간격 조정"))
        (princ (strcat "\n[BC] 문자 " (itoa (bc:art-core (bc:ss-list ss) (if pt (bc:wcs pt)) cfg)) "개를 정렬했습니다."))))
    (progn (initget "S") (if (= (getkword "\n[설정 변경(S)] <끝>: ") "S") (progn (bc:open-window "ART") (bc:settings-hint "ART")))))
  (bc:end))

;;; ================================================================ CTS 문자 그림자

(setq bc:cts-defaults '(("X" . 0.08) ("Y" . -0.08) ("그림자색" . 8) ("원본색" . 0) ("레이어" . "")))

(defun bc:cts-core (enames cfg / doc o c h st n)
  ;; 문자를 (X, Y) × 문자 높이만큼 비켜 복사하고 원본 바로 뒤로 보낸다. 만든 그림자 수.
  (setq doc (vla-get-ActiveDocument (vlax-get-acad-object)) n 0)
  (foreach e enames
    (setq o (vlax-ename->vla-object e) h (cdr (assoc 40 (entget e))) c (vla-Copy o))
    (vla-Move c (vlax-3d-point 0 0 0) (vlax-3d-point (* h (bc:cfg cfg "X")) (* h (bc:cfg cfg "Y")) 0))
    (vla-put-Color c (bc:cfg cfg "그림자색"))
    (if (/= (bc:cfg cfg "레이어") "") (progn (bc:ensure-layer (bc:cfg cfg "레이어") 7) (vla-put-Layer c (bc:cfg cfg "레이어"))))
    (if (> (bc:cfg cfg "원본색") 0) (vla-put-Color o (bc:cfg cfg "원본색")))
    (setq st (bc:sortents (vla-ObjectIDToObject doc (vla-get-OwnerID o))))
    (vlax-invoke st 'MoveBelow (list c) o)
    (setq n (1+ n)))
  n)

(defun bc:sortents (blk / d r)
  ;; 블록(모형·배치 공간)의 그리기 순서 표
  (setq d (vla-GetExtensionDictionary blk) r (vl-catch-all-apply 'vla-GetObject (list d "ACAD_SORTENTS")))
  (if (vl-catch-all-error-p r) (vla-AddObject d "ACAD_SORTENTS" "AcDbSortentsTable") r))

(defun c:CTS (/ cfg ss)
  (bc:begin nil)
  (setq cfg (bc:cfg-load "CTS" bc:cts-defaults))
  (princ "\n그림자 넣을 문자 선택(설정은 엔터 후 S): ")
  (if (setq ss (ssget '((0 . "TEXT,MTEXT"))))
    (princ (strcat "\n[BC] 그림자 " (itoa (bc:cts-core (bc:ss-list ss) cfg)) "개를 만들었습니다."))
    (progn (initget "S") (if (= (getkword "\n[설정 변경(S)] <끝>: ") "S") (progn (bc:open-window "CTS") (bc:settings-hint "CTS")))))
  (bc:end))
