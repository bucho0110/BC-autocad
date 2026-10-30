;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_layer.lsp — 레이어 켜기·끄기·동결·잠금·현재 레이어 명령 13개
;;; 레이어 상태는 레이어 테이블 레코드를 entmod로 바꾼다: 62(색) 음수 = 꺼짐, 70 비트 1 = 동결, 비트 4 = 잠금.
;;; 현재 레이어는 동결할 수 없으므로 건너뛰거나(LFR) 고른 레이어로 먼저 바꾼다(LOL·FRE·OLO).
;;; 핵심 함수(bc:*-core)는 레이어 이름 목록을 받아 바꾼 레이어 수를 돌려준다(MCP skill_run도 같은 함수를 쓴다).

(defun bc:lay-all (/ r out)
  (setq r (tblnext "LAYER" T))
  (while r (setq out (cons (cdr (assoc 2 r)) out) r (tblnext "LAYER")))
  (reverse out))

(defun bc:lay-in (name names) (member (strcase name) (mapcar 'strcase names)))

(defun bc:lay-cur-p (name) (= (strcase name) (strcase (getvar "CLAYER"))))

(defun bc:lay-mod (name key / en ed c f new)
  ;; key: "on" "off" "freeze" "thaw" "lock" "unlock". 상태가 실제로 바뀌면 T
  (if (and (setq en (tblobjname "LAYER" name)) (setq ed (entget en)))
    (progn
      (setq c (cdr (assoc 62 ed)) f (cdr (assoc 70 ed)))
      (setq new
        (cond ((and (= key "on") (< c 0)) (subst (cons 62 (abs c)) (assoc 62 ed) ed))
              ((and (= key "off") (> c 0)) (subst (cons 62 (- c)) (assoc 62 ed) ed))
              ((and (= key "freeze") (= 0 (logand f 1)) (not (bc:lay-cur-p name))) (subst (cons 70 (logior f 1)) (assoc 70 ed) ed))
              ((and (= key "thaw") (= 1 (logand f 1))) (subst (cons 70 (- f 1)) (assoc 70 ed) ed))
              ((and (= key "lock") (= 0 (logand f 4))) (subst (cons 70 (logior f 4)) (assoc 70 ed) ed))
              ((and (= key "unlock") (= 4 (logand f 4))) (subst (cons 70 (- f 4)) (assoc 70 ed) ed))))
      (if new (progn (entmod new) T)))))

(defun bc:lay-count (names key / n)
  (setq n 0)
  (foreach l names (if (bc:lay-mod l key) (setq n (1+ n))))
  n)

(defun bc:lay-current (name)
  ;; 동결·꺼진 레이어는 현재 레이어로 할 수 없거나 보이지 않으므로 먼저 풀고 켠다
  (bc:lay-mod name "thaw") (bc:lay-mod name "on")
  (setvar "CLAYER" name))

(defun bc:lay-regen () (vla-Regen (vla-get-ActiveDocument (vlax-get-acad-object)) 1))

(defun bc:lay-of (enames / out l)
  ;; 객체들의 레이어 이름(중복 없이, 고른 순서)
  (foreach e enames
    (setq l (cdr (assoc 8 (entget e))))
    (if (not (bc:lay-in l out)) (setq out (append out (list l)))))
  out)

(defun bc:lay-missing (names / bad)
  ;; 도면에 없는 레이어 이름이 있으면 그 목록 문자열(MCP 인자 검사용)
  (foreach l names (if (not (tblsearch "LAYER" l)) (setq bad (cons l bad))))
  (if bad (strcat "도면에 없는 레이어: " (bc:join (reverse bad) ", "))))

(defun bc:join (lst sep / s)
  (setq s "")
  (foreach x lst (setq s (if (= s "") x (strcat s sep x))))
  s)

;;; ---------------------------------------------------------------- 핵심 함수

(defun bc:lol-core (names / n)
  ;; 고른 레이어만 켜고 나머지는 끈다
  (if (not (bc:lay-in (getvar "CLAYER") names)) (bc:lay-current (car names)))
  (setq n 0)
  (foreach l (bc:lay-all) (if (bc:lay-mod l (if (bc:lay-in l names) "on" "off")) (setq n (1+ n))))
  n)

(defun bc:lof-core (names) (bc:lay-count names "off"))

(defun bc:lon-core () (bc:lay-count (bc:lay-all) "on"))

(defun bc:olo-core (/ offs n)
  ;; 꺼진 레이어만 켜고, 켜져 있던 레이어는 끈다(꺼진 레이어가 없으면 그대로 0)
  (foreach l (bc:lay-all) (if (< (cdr (assoc 62 (tblsearch "LAYER" l))) 0) (setq offs (cons l offs))))
  (if offs (bc:lol-core (reverse offs)) 0))

(defun bc:lfr-core (names / n)
  ;; 현재 레이어는 동결할 수 없어 건너뛴다
  (setq n (bc:lay-count names "freeze"))
  (bc:lay-regen)
  n)

(defun bc:fre-core (names / n)
  ;; 고른 레이어 외 전부 동결(고른 레이어는 동결 해제)
  (if (not (bc:lay-in (getvar "CLAYER") names)) (bc:lay-current (car names)))
  (setq n 0)
  (foreach l (bc:lay-all) (if (bc:lay-mod l (if (bc:lay-in l names) "thaw" "freeze")) (setq n (1+ n))))
  (bc:lay-regen)
  n)

(defun bc:lth-core (/ n) (setq n (bc:lay-count (bc:lay-all) "thaw")) (bc:lay-regen) n)

(defun bc:llo-core (names) (bc:lay-count names "lock"))

(defun bc:lul-core (names) (bc:lay-count names "unlock"))

(defun bc:ula-core () (bc:lay-count (bc:lay-all) "unlock"))

(defun bc:loe-core (names / n)
  ;; 고른 레이어 외 전부 잠금(고른 레이어는 잠금 해제)
  (setq n 0)
  (foreach l (bc:lay-all) (if (bc:lay-mod l (if (bc:lay-in l names) "unlock" "lock")) (setq n (1+ n))))
  n)

(defun bc:scl-core (name) (bc:lay-current name) (getvar "CLAYER"))

(defun bc:ccl-core (enames / cur n ed lay)
  ;; 객체를 현재 레이어로 옮긴다. 잠긴 레이어의 객체는 바꿀 수 없어 건너뛴다
  (setq cur (getvar "CLAYER") n 0)
  (foreach e enames
    (setq ed (entget e) lay (tblsearch "LAYER" (cdr (assoc 8 ed))))
    (if (and (= 0 (logand 4 (cdr (assoc 70 lay)))) (not (bc:lay-cur-p (cdr (assoc 8 ed)))))
      (if (entmod (subst (cons 8 cur) (assoc 8 ed) ed)) (setq n (1+ n)))))
  n)

;;; ---------------------------------------------------------------- AutoCAD 명령

(defun bc:lay-pick (msg / ss i out)
  ;; 객체를 골라 그 객체들의 엔티티 목록
  (princ msg)
  (if (setq ss (ssget))
    (progn (setq i 0) (while (< i (sslength ss)) (setq out (cons (ssname ss i) out) i (1+ i))) (reverse out))))

(defun bc:lay-run (msg fn done / es names n)
  ;; 객체를 골라 레이어 이름을 모으고 fn(이름 목록)을 부른 뒤 결과를 알린다
  (bc:begin nil)
  (if (setq es (bc:lay-pick msg))
    (progn
      (setq names (bc:lay-of es) n (apply fn (list names)))
      (princ (strcat "\n[BC] " (bc:join names ", ") " — " done " (" (itoa n) "개 레이어 바뀜)"))))
  (bc:end))

(defun bc:lay-run0 (fn done / n)
  (bc:begin nil)
  (setq n (apply fn nil))
  (princ (strcat "\n[BC] " done " (" (itoa n) "개 레이어 바뀜)"))
  (bc:end))

(defun c:LOL () (bc:lay-run "\n켜 둘 레이어의 객체 선택: " 'bc:lol-core "이 레이어만 켰습니다"))
(defun c:LOF () (bc:lay-run "\n끌 레이어의 객체 선택: " 'bc:lof-core "레이어를 껐습니다"))
(defun c:LON () (bc:lay-run0 'bc:lon-core "모든 레이어를 켰습니다"))
(defun c:OLO () (bc:lay-run0 'bc:olo-core "꺼져 있던 레이어만 켰습니다(꺼진 레이어가 없으면 그대로)"))
(defun c:LFR () (bc:lay-run "\n동결할 레이어의 객체 선택: " 'bc:lfr-core "레이어를 동결했습니다(현재 레이어는 제외)"))
(defun c:FRE () (bc:lay-run "\n남겨 둘 레이어의 객체 선택: " 'bc:fre-core "이 레이어 외 모두 동결했습니다"))
(defun c:LTH () (bc:lay-run0 'bc:lth-core "모든 레이어의 동결을 풀었습니다"))
(defun c:LLO () (bc:lay-run "\n잠글 레이어의 객체 선택: " 'bc:llo-core "레이어를 잠갔습니다"))
(defun c:LUL () (bc:lay-run "\n잠금을 풀 레이어의 객체 선택: " 'bc:lul-core "레이어 잠금을 풀었습니다"))
(defun c:ULA () (bc:lay-run0 'bc:ula-core "모든 레이어 잠금을 풀었습니다"))
(defun c:LOE () (bc:lay-run "\n잠그지 않을 레이어의 객체 선택: " 'bc:loe-core "이 레이어 외 모두 잠갔습니다"))

(defun c:SCL (/ s)
  (bc:begin nil)
  (if (setq s (entsel "\n현재 레이어로 할 객체 선택: "))
    (princ (strcat "\n[BC] 현재 레이어: " (bc:scl-core (cdr (assoc 8 (entget (car s))))))))
  (bc:end))

(defun c:CCL (/ es n)
  (bc:begin nil)
  (if (setq es (bc:lay-pick "\n현재 레이어로 옮길 객체 선택: "))
    (progn
      (setq n (bc:ccl-core es))
      (princ (strcat "\n[BC] " (itoa n) "개 객체를 현재 레이어(" (getvar "CLAYER") ")로 옮겼습니다"
                     (if (< n (length es)) " — 잠긴 레이어이거나 이미 현재 레이어인 객체는 그대로" "")))))
  (bc:end))
