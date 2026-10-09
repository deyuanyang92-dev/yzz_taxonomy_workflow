# yzz 工作流 — Claude 规则

## 怎么干活
- **先用现成模块**：`python3 yzz.py <module> all <Taxon>`。只转述步骤摘要和文件路径，**不读大 TSV/Excel**，不在聊天里贴长表。
- 需要新功能：先查 `modules/*/README.md` 和老脚本（`/mnt/n/codex`、`/mnt/n/claude`、`/mnt/n/大连-臭海蛹-2026/03_脚本`），复用后再写；新代码按 README "新增模块的约定" 放进模块，并更新该模块 REQUIREMENTS.md。
- 用户提出的新需求/纠正：写进对应 `REQUIREMENTS.md`，再改代码。不能只留在对话里。
- 子代理：机械活 haiku，阅读/翻译/地名标准化 sonnet；提示词写明"禁止再开子代理"，结果写文件，回报一行。

- **改完任何脚本必须跑该模块回归测试**（如 `modules/worms/tests/check_polynoidae.py`），全部 PASS 才能向用户报告完成；用户指出的每个错误都要加成一条检查。汇报时不得把未验证的结果说成已完成。

## 数据原则
- 分类事实只来自数据库原值或文献原文；**缺失留空，不猜**。
- UNKNOWN ≠ ABSENT。
- 数据库自身错误（如 WoRMS 环境标记）只在 QC 中提示，不改原值。
- AI 产生的字段（如地名标准化）必须带把握度并可追溯到 WoRMS 记录或文献。
- 分类学内容（表头、地名、描述）**一律英文**。

## WoRMS 要点
- `citation` 字段 ≠ 原始文献；原始文献 = 来源 use="original description"，转属名称取原始组合。
- 标本清单参数 `pid`（不是 tid/tName）。
- 详见 `modules/worms/README.md`。
