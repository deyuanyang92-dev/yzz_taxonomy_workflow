# ps-claude：让 AI 操作修图软件抠图（调研记录）

记录日期：2026-10-09。状态：调研阶段，尚未安装或实测任何项目。

## 需求（用户原话整理）

- 不是"AI 模型直接抠图"（rembg / BiRefNet 这类），而是 **AI 操作修图软件**，用软件自带的工具抠图（魔棒、前景选择、羽化、蒙版等）。
- 用户判断：软件抠图可能比 AI 抠图更好。
- 希望用一条中文指令驱动；优先开源、对标 Photoshop 的软件。

## 可用方案（来自聚合网站与项目页面，未逐一核实仓库，安装前需确认最新状态）

### GIMP 3（开源，首选）

| 项目 | 说明 | 来源 |
|---|---|---|
| maorcc/gimp-mcp | 原始项目，GPLv3，可接 Claude Code / Claude Desktop | https://glama.ai/mcp/servers/%40maorcc/gimp-mcp |
| gimp3-mcp（PyPI） | maorcc 的分支，针对 GIMP 3.2，约 80 个工具（选区、图层、调色、文字、批量导出）；安装 `uvx gimp3-mcp install-plugin`（先启动一次 GIMP） | https://pypi.org/project/gimp3-mcp/ |
| GIMP 3.2 导出修复分支 | 修复 3.2 中 file-*-save 名称变化导致导出总是变成 PNG 的问题 | https://glama.ai/mcp/servers/ldsr3l26ai |
| abelduarte/gimp-mcp | 自动启动后台无界面 GIMP；默认 macOS，Linux 需改插件安装路径 | https://glama.ai/mcp/servers/abelduarte/gimp-mcp |
| shriinivas/gimpmcp | 通过 D-Bus 连接（GIMP 内 Filters > Development > MCP D-Bus - Start） | https://lobehub.com/mcp/shriinivas-gimpmcp |

### 其他软件

| 软件 | 项目 | 说明 | 来源 |
|---|---|---|---|
| Krita（开源） | krita-codex-mcp | MIT；Windows 优先；验证于 Krita 5.3.2.1；可创建图层、蒙版、导出 | https://socket.dev/pypi/package/krita-codex-mcp |
| Photoshop（非开源） | alisaitteke/photoshop-mcp | 社区项目，非 Adobe 官方；跨平台；`npx -y @alisaitteke/photoshop-mcp` | https://mcpservers.org/servers/alisaitteke/photoshop-mcp |
| Photoshop | loonghao/photoshop-python-api-mcp-server | 仅 Windows（COM 接口），测试于 CC2017–2024 | https://github.com/loonghao/photoshop-python-api-mcp-server |
| Photopea（网页版） | photopea-mcp-server | 34 个工具；无需 PS 授权 | （搜索结果中提及，未取得链接） |

### 参考：纯 AI 抠图（用户已表示不是首选，仅备查）

- Krita + krita-vision-tools（BiRefNet 去背景、SAM 选区）：https://krita-artists.org/t/vision-tools-selection-background-removal/139960
- GIMP 3 + withoutBG 插件（本地，需 Docker 后台）：https://www.gimp-forum.net/Thread-Open-source-GIMP-3-plugin-for-local-AI-background-removal
- rembg 命令行：`rembg i in.jpg out.png`；`rembg p in_dir/ out_dir/`（边缘有轻微侵蚀）

## 关键判断

- AI 操作软件 = 调用软件工具与参数，**不能像人一样手动描边**。
- **纯色背景**（如标本照）：魔棒 / 按颜色选区 + 羽化 + 收缩边缘，效果好、可重复、可批量。
- **复杂背景**：GIMP 前景选择需要粗略框出主体，AI 只能给近似范围，效果不一定优于 AI 抠图。
- 更简单的替代路线：不装 MCP，直接写 **GIMP Python-Fu 批处理脚本**（无界面后台运行），一条命令按固定参数处理整个文件夹，结果可重复。

## 待定 / 下一步

1. 用户主要处理什么照片？（纯色底标本照 → 推荐 GIMP 批处理脚本；复杂背景 → 再评估 MCP 或 AI 模型）
2. 用户提供 2–3 张样图，在本机（WSL）安装 GIMP 3 实测。
3. 选定路线后：MCP 路线 → 装 gimp3-mcp 并接入 Claude Code；脚本路线 → 写批处理脚本（参数：容差、羽化半径、边缘收缩、输出格式），放本目录。
4. 实测前核对各仓库许可证（多为 GPLv3）与维护状态。
