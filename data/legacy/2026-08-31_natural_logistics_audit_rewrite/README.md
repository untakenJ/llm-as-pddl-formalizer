# Natural Logistics pre-rewrite backup / Natural Logistics 改写前备份

This archive was created before installing the 2026-08-31 audited Natural Logistics problem descriptions.

本目录保存 2026-08-31 审计改写版本覆盖前的 Natural Logistics 完整原始数据，并留档全部逐题审计产物、改写点汇总表和双语 PDF 报告。

## Contents / 内容

- `textual_logistics/Natural_Logistics-100/`: complete pre-install dataset (100 domain files and 100 problem files) / 覆盖前完整数据集
- `audit/natural_logistics_minimal_rewrite_20260831/`: all 100 case audit directories, evidence ledgers, rewritten descriptions, rewrite notes, `change_catalog.csv`, and `case_summary.csv` / 全部逐题审计目录、证据账本、改写说明及汇总表
- `audit/natural_logistics_full_change_points_bilingual_2026-08-31.pdf`: bilingual full change-point report / 中英文全量改写点报告
- `BACKUP_MANIFEST.json`: hashes, counts, changed-case list, and scope verification / 哈希、计数、改写题目及范围验证

Only `data/textual_logistics/Natural_Logistics-100/*_problem.txt` was installed from the audited output. All domain descriptions and every other dataset were preserved.

本次仅以审计产物覆盖 `data/textual_logistics/Natural_Logistics-100/*_problem.txt`；全部 domain 描述和其他数据集均保持不变。

The golden PDDL set at `data/textual_logistics/Logistics-100_PDDL/` was not modified. Its shared domain file and all 100 problem files were independently confirmed to byte-match the golden copies retained by the audit.

`data/textual_logistics/Logistics-100_PDDL/` 中的 golden PDDL 未作任何修改；其共享 domain 文件和全部 100 个 problem 文件均已独立确认与审计留存的 golden 副本逐字一致。
