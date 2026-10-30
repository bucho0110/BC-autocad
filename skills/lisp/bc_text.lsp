;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_text.lsp — 문자 정렬 명령
;;; CR: 고른 문자들을 두 점으로 정한 사각형(또는 고른 객체)의 가운데로 옮기고 가운데(MC) 정렬로 바꾼다.
;;;     여러 문자를 고르면 묶음 전체의 가운데를 맞추므로 문자 사이 간격은 그대로다.

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
