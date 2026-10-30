;;; Copyright © 2026 BUCHO — BUCHO 무료 공개 라이선스 (https://github.com/bucho0110/BC-autocad)
;;; bc_00_guard.lsp — 먼저 있던 같은 이름 명령 기억 (install/build_lisp.py가 만든 파일, 직접 고치지 말 것)
;;; 우리 명령을 정의하기 전에, 같은 이름을 이미 쓰던 다른 리습 명령을 기억해 둔다.
(setq bc:*names* (quote ("FE" "FW" "FEL" "CEE" "GEL" "SLEL" "IEL" "FPEL" "DTIN" "TTP" "CCON" "WCZ" "DCON" "CMOB" "DSEL" "GRP" "CFM" "QCAR" "XY" "ZBC" "WCD" "CEX" "RCE" "CIM" "TTE" "DCP" "DCEN" "DSTA" "STT" "GST" "DIBC" "CST" "NUST" "MIP" "HWLI" "DSLO" "NSLO" "DFB" "SLL" "SLT" "CSS" "CUT" "DRRE" "DCEM" "DDGP" "RCSE" "CSAR" "HWLM" "XYB" "ART" "CTS" "RET" "INN" "CR" "LOL" "LOF" "LON" "OLO" "LFR" "FRE" "LTH" "LLO" "LUL" "ULA" "LOE" "SCL" "CCL" "MUIN" "CALC" "MPL" "MPLOT")))
(setq bc:*cmds* (quote ("FE" "FW" "FEL" "CEE" "GEL" "SLEL" "IEL" "FPEL" "DTIN" "TTP" "CCON" "WCZ" "DCON" "CMOB" "DSEL" "GRP" "CFM" "QCAR" "XY" "ZBC" "WCD" "CEX" "RCE" "CIM" "TTE" "DCP" "DCEN" "DSTA" "STT" "GST" "DIBC" "CST" "NUST" "MIP" "HWLI" "DSLO" "NSLO" "DFB" "SLL" "SLT" "CSS" "CUT" "DRRE" "DCEM" "DDGP" "RCSE" "CSAR" "HWLM" "XYB" "ART" "CTS" "RET" "INN" "CR" "LOL" "LOF" "LON" "OLO" "LFR" "FRE" "LTH" "LLO" "LUL" "ULA" "LOE" "SCL" "CCL" "MUIN" "CALC" "MPL")))
(setq bc:*prior* nil)
(foreach _n bc:*names*
  (setq _f (eval (read (strcat "c:" _n))))
  (if (and _f (not (eq _f (eval (read (strcat "bc:fn-" _n)))))
           (not (eq _f (eval (read (strcat "bc:sw-" _n))))))
    (setq bc:*prior* (cons (cons _n _f) bc:*prior*))))
(setq _n nil _f nil)
