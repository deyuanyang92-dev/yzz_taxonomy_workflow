# habitat 模块（生境名录）

按生境（或其他条件）建立一个类群的全球名录：以一篇经典名录为底本，用引文滚雪球加关键词检索补齐之后的文献，由子代理逐篇抽取物种记录，最后用 WoRMS 统一有效名、科和目。需求见 [REQUIREMENTS.md](REQUIREMENTS.md)。

第一个项目：`projects/Polychaeta_nonmarine`，即淡水和半咸水多毛类，底本为 Glasby et al. 2009。

## 步骤

| 步骤 | 命令 | 输入 → 输出（`projects/<Taxon>/02_原始数据/habitat/`） | 执行者 |
|---|---|---|---|
| 01_seed | `yzz.py habitat 01 <T>` | config.seed 的 PDF → `seed.tsv`（逐条目，原文字段 + 页码） | 脚本（解析器在 `parsers/`） |
| 02_worms_match | `yzz.py habitat 02 <T>` | seed → `seed_worms.tsv`（有效名、科、目、WoRMS 路径、环境标记） | 脚本 |
| 03_citing | `03_citing.py <T>` 第 1 轮；`--search` 检索臂；`--next` 下一轮；`--status` | → `works.tsv`、`screen/to_screen_round*.tsv` | 脚本 |
| （筛选） | 子代理按 `SCREENING_RULES_nonmarine.md` 处理每个 `to_screen_*.tsv` | → `screen/decided_*.tsv` | sonnet |
| 04 预过滤 | `04_screen_merge.py <T> --prefilter <round>` | 第 2 轮以后的大批参考文献：没有类群词，也没有“生境词 + 动物词”的文献自动判 no；其余写入 `to_screen_<round>_kw.tsv` | 脚本（已用前几轮人工判定验证召回，有回归检查） |
| 04_screen_merge | `yzz.py habitat 04 <T>` | decided → 写回 `works.tsv` | 脚本 |
| 05_additions | `05_additions.py <T> --todo` 分块；子代理按 `EXTRACT_PROMPT.md` 抽取；再运行 `05_additions.py <T>` 合并 | → `extract/todo_*.tsv` → `extract/found_*.tsv` → `additions.tsv` | sonnet + 脚本 |
| 06_worms_env | `yzz.py habitat 06 <T>` | 相关科中 WoRMS 标为淡水或非海洋、但名录未收的有效种 → `worms_env_candidates.tsv`（只作线索） | 脚本 |
| 07_build | `yzz.py habitat 07 <T>` | → `checklist.tsv` + `04_处理数据/habitat/<T>_checklist_<date>.xlsx` | 脚本 |

**循环**：03 → 筛选 → 04 → 05 → 03 `--next` …… 某一轮新增 yes 文献不再带来新物种时停止。05 合并后看 `additions.tsv` 中新物种数是否为 0。
没有 OpenAlex key 时，用 `03_citing.py <T> --next --productive [--limit N]`：只展开已带来新物种记录的文献，并按新种数降序排列。

**WoRMS 候选核实**：06 之后，把“只在 WoRMS 候选中出现、文献两路都没找到”的种整理成 `worms_only_to_verify.tsv`，分批交给 sonnet 子代理逐种查原始描述。结论写入 `extract/worms_verify_W*.tsv`（收录、排除或待核）；收录的种按 12 列格式写入 `extract/found_W*.tsv`，再运行 05 一并合并。

**三路互证**：引文滚雪球、关键词检索、WoRMS 环境标记各自独立找候选。三路重叠程度可以用来估计还漏了多少（捕获—再捕获思路）。只在 WoRMS 候选表里出现、文献两路都没找到的种，要优先核对。

## 配置 `config.json`

```json
{"seed": {"parser": "glasby2009", "pdf": "...", "citation": "...", "short": "Glasby et al., 2009",
          "doi": "...", "expected_entries": 197},
 "habitat_rule": "...", "seeds_doi": ["..."], "screening_rules": "modules/habitat/SCREENING_RULES_nonmarine.md",
 "search_queries": ["freshwater polychaete", "..."], "search_from_year": 2009,
 "search_max_per_query": 300, "search_crossref_max": 100, "search_s2": false,
 "extra_families": ["Sigalionidae", "..."]}
```

换一个底本时，在 `parsers/` 下新写一个 `parse(text) -> list[dict]`，并在测试里核对条目数是否等于原文摘要给出的数。

## 接口与限额

- **OpenAlex**：从 2025 年起，不带 key 时同一 IP 共用每日额度，很快用完。免费 key 写入 `config/openalex.json`（`{"api_key": "..."}`，已 gitignore）。用完额度会打印提示，并自动跳过 OpenAlex。
- **Semantic Scholar**：不带 key 常返回 429，默认关闭（`search_s2: false`）。
- **Crossref**：不需要 key，检索臂默认使用。
- **WoRMS**：通过 `lib/worms.py` 的共享缓存访问。缓存可能存进失败请求的空结果，`wormsmatch._get()` 遇到空结果会绕过缓存直接重查。

## 已知坑（均有回归检查 `tests/check_nonmarine.py`）

- Glasby 2009 原文把科名印成 “HIstriobdellidae”，科名正则需要大小写宽容。
- 名称与 “Ecology:” 之间可能隔着分页；条目之间也可能没有空行。解析时以 “Ecology:” 为锚点，向上回溯名称行。
- 带括号的作者名如 “(Grube)” 不能当作亚籍。只有紧跟属名的括号才算亚属。
- 并发写 WoRMS 共享缓存会冲突，因此并发数为 3，失败的再顺序重试。
- `worms 01` 调用时用的是 `marine_only=true`，会漏掉纯淡水类群，所以本模块自己用 `marine_only=false` 遍历。
- WoRMS 把 Aeolosomatidae、Potamodrilidae 归入 Annelida incertae sedis，把 Hrabeiella 归入寡毛类，07 会在备注中标出。

**回归测试**：改动任何脚本后，必须运行 `python3 modules/habitat/tests/check_nonmarine.py`，全部 PASS 才算完成。
