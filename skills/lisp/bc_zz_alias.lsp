;;; bc_zz_alias.lsp — BC 이름(BCFE…)과 짧은 이름(FE…) (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)
;;; 기본은 BC 이름만. 짧은 이름은 BCHELP 창에서 체크한 명령만 켠다(모두 끄기: BCOFF).
(setq bc:*short-extra* (quote (("MPL" "MPLOT"))))
;; 단축키 파일의 이름 목록. 주석·빈 줄과 이름 글자(영문·숫자·_·-)가 아닌 것(파일 앞 BOM 등)은 뺀다
(defun bc:pgp-names (p / f l i n out)
  (if (and p (setq f (open p "r")))
    (progn
      (while (setq l (read-line f))
        (setq l (vl-string-trim " \t" l))
        (if (and (/= l "") (/= (substr l 1 1) ";") (setq i (vl-string-search "," l))
                 (/= (setq n (strcase (vl-string-trim " \t" (substr l 1 i)))) "")
                 (not (wcmatch n "*[~A-Z0-9_`-]*")))
          (setq out (cons n out))))
      (close f)))
  out)
;; 짧은 이름 설정 파일: 켠 명령 이름을 한 줄에 하나
(defun bc:short-path () (strcat (getenv "LOCALAPPDATA") "\\bc-autocad\\settings\\shortnames.txt"))
(defun bc:short-read (/ f l out)
  (if (and (findfile (bc:short-path)) (setq f (open (bc:short-path) "r" "utf8")))
    (progn
      (while (setq l (read-line f))
        (setq l (strcase (vl-string-trim " \t\r" l)))
        (if (and (member l bc:*cmds*) (not (member l out))) (setq out (cons l out))))
      (close f)))
  (reverse out))
(defun bc:short-write (names / d f)
  (setq d (strcat (getenv "LOCALAPPDATA") "\\bc-autocad"))
  (vl-mkdir d) (vl-mkdir (strcat d "\\settings"))
  (if (setq f (open (bc:short-path) "w" "utf8"))
    (progn (foreach n names (write-line n f)) (close f) T)))
;; 명령 하나의 짧은 이름들(MPL이면 MPLOT까지)
(defun bc:short-names (n) (cons n (cdr (assoc n bc:*short-extra*))))
;; 짧은 이름으로 실행하면 어느 명령이 돌았는지 한 줄 남긴다
(defun bc:run-short (n s) (princ (strcat "\n[BC] BC" n)) (eval (list (read (strcat "bc:fn-" s)))))
(defun bc:short-on (n)
  (foreach s (bc:short-names n)
    (if (null (eval (read (strcat "bc:sw-" s))))
      (eval (read (strcat "(defun bc:sw-" s " () (bc:run-short \"" n "\" \"" s "\"))"))))
    (set (read (strcat "c:" s)) (eval (read (strcat "bc:sw-" s))))))
;; 끄면 먼저 있던 다른 리습 명령으로 되돌리거나(없으면) 지운다 — 같은 이름의 단축키·프로그램 명령이 다시 산다
(defun bc:short-off (n)
  (foreach s (bc:short-names n) (set (read (strcat "c:" s)) (cdr (assoc s bc:*prior*)))))
;; 설정 파일대로 이 도면에 켜고 끈다. 켠 목록을 bc:*short*에 둔다
(defun bc:short-apply ()
  (setq bc:*short* (bc:short-read))
  (foreach n bc:*cmds* (if (member n bc:*short*) (bc:short-on n) (bc:short-off n)))
  bc:*short*)
;; 이 PC에서 이미 쓰는 이름: ((이름 . 무엇) ...) — 켜기 전에 창이 경고용으로 부른다
(defun bc:short-conflicts (names / pgp out)
  (setq pgp (bc:pgp-names (findfile "acad.pgp")))
  (foreach n names
    (foreach s (bc:short-names n)
      (cond ((member s pgp) (setq out (cons (list n s "단축키 파일(acad.pgp)") out)))
            ((getcname s) (setq out (cons (list n s "프로그램 명령") out)))
            ((assoc s bc:*prior*) (setq out (cons (list n s "다른 리습") out))))))
  (reverse out))
(defun c:BCOFF ()
  (bc:short-write nil) (bc:short-apply)
  (princ "\n[BC] 단축 이름(FE 등)을 모두 해제했습니다. 이후에는 BCFE처럼 접두어 BC를 붙여 입력하십시오.")
  (princ "\n     이미 열려 있는 다른 도면은 다시 열 때 해제됩니다.")
  (princ))
;; 우리 함수를 잡아 두고 짧은 이름은 일단 원래대로
(foreach _n bc:*names*
  (set (read (strcat "bc:fn-" _n)) (eval (read (strcat "c:" _n))))
  (set (read (strcat "c:" _n)) (cdr (assoc _n bc:*prior*))))
;; BC 이름은 항상
(setq _pgp (bc:pgp-names (findfile "acad.pgp")))
(foreach _n bc:*cmds*
  (setq _a (strcat "BC" _n))
  (if (and (eval (read (strcat "bc:fn-" _n)))
           (not (getcname _a)) (not (member _a _pgp))
           (or (null (eval (read (strcat "c:" _a)))) (member _a bc:*aliases*)))
    (progn
      (eval (read (strcat "(defun c:" _a " () (bc:fn-" _n "))")))
      (if (not (member _a bc:*aliases*)) (setq bc:*aliases* (cons _a bc:*aliases*))))))
;; 체크해 둔 짧은 이름만 켠다
(if (bc:short-apply)
  (princ (strcat "\n[BC] 단축 이름 " (itoa (length bc:*short*)) "개가 활성화되어 있습니다(해제: BCOFF).")))
(setq _n nil _a nil _pgp nil)
