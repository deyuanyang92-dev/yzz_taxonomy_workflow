# maps 模块

| 步骤 | 输入 → 输出（`projects/<Taxon>/05_图表/maps/`） |
|---|---|
| 01_worms_type_localities | worms 模块 names + coordinates → 有效种模式产地图（实心=original，空心=approximate 地点，灰点=Low 区域中心点；颜色=亚科）+ 作图源数据 TSV |
| 02_obis_occurrences | occurrences 模块 obis.tsv → OBIS 分布记录图（与 WoRMS 图分开；未质控，初步） |

```bash
python3 yzz.py maps all <Taxon>
```

计划：陆地点检查（land check）；MEOW realm 着色（同臭海蛹 Fig. 1）；按属分面板；OBIS 质控（obistools 式：陆地点、重复、离群）后再出图。
