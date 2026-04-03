# 安装指南 | Installation Guide

## 最小安装（5 分钟）

只需 Claude Code + 本 Skill，9 个阶段中 8 个开箱即用。

```bash
git clone https://github.com/CancerDAO/cancer-buddy-skill ~/.claude/skills/cancer-buddy
```

打开 Claude Code，输入 `/cancer-buddy`，搞定。

---

## 推荐安装（10 分钟）— 中国患者必装

### chictr-mcp-server

**为什么需要？** 没有它，搭子只能搜 ClinicalTrials.gov（以欧美试验为主）。装了之后，同时搜中国临床试验注册中心（ChiCTR），不会漏掉国内的试验。

**安装方式：**

1. 确保已安装 Node.js 18+：
```bash
node --version  # 应该显示 v18.x 或更高
```

2. 在你的 Claude Code 配置中添加 MCP server。

**方式 A：项目级配置**（只在当前项目生效）

在项目根目录创建或编辑 `.mcp.json`：
```json
{
  "mcpServers": {
    "chictr": {
      "command": "npx",
      "args": ["-y", "chictr-mcp-server"]
    }
  }
}
```

**方式 B：全局配置**（所有项目都能用）

编辑 `~/.claude.json`，在 `mcpServers` 下添加：
```json
{
  "mcpServers": {
    "chictr": {
      "command": "npx",
      "args": ["-y", "chictr-mcp-server"]
    }
  }
}
```

3. 重启 Claude Code 会话。

4. 验证：在 Claude Code 中输入 `/cancer-buddy`，然后说"帮我找临床试验"，看输出是否同时包含 NCT 和 ChiCTR 编号的试验。

详见：https://github.com/PancrePal-xiaoyibao/chictr-mcp-server

---

## 完整安装（20 分钟）— 可选增强

以下是可选的增强工具，不装不影响核心功能。

### PDF 文本提取工具

搭子可以直接用 Claude 的原生能力读 PDF 和图片。如果你需要处理大量病历文件，安装以下工具可以加速：

**macOS：**
```bash
brew install poppler tesseract
```

**Ubuntu/Debian：**
```bash
sudo apt-get install poppler-utils tesseract-ocr
```

**Python 包（可选）：**
```bash
pip install PyPDF2 python-docx pytesseract
```

---

## 各功能 × 依赖对照表

| Phase | 功能 | 无额外依赖 | + chictr-mcp | + PDF 工具 |
|-------|------|:----------:|:-----------:|:----------:|
| 0 | 病历处理 | ✅ Claude 原生读取 | — | ⚡ 加速 |
| 1 | 病情解读 | ✅ | — | — |
| 2 | 诊断规划 | ✅ | — | — |
| 3 | 报告解读 | ✅ | — | — |
| 4 | 治疗路径（国际试验） | ✅ 搜 ClinicalTrials.gov | — | — |
| 4 | 治疗路径（中国试验） | ❌ 搜不到 ChiCTR | ✅ 双源搜索 | — |
| 5 | 准入导航 | ✅ | — | — |
| 6 | 治疗管理 | ✅ | — | — |
| 7 | 数据金库 | ✅ | — | — |
| 8 | 患者教育 | ✅ | — | — |

---

## 常见问题

**Q: 我不在中国，需要装 chictr-mcp-server 吗？**
A: 不需要。ClinicalTrials.gov 覆盖全球试验，对非中国患者已经足够。

**Q: 我没有 Node.js，怎么装？**
A: macOS: `brew install node`，或去 https://nodejs.org 下载。

**Q: 装了之后 Claude Code 里看不到 chictr 工具？**
A: 重启 Claude Code 会话。如果还不行，检查 `.mcp.json` 的 JSON 格式是否正确。

**Q: 我的病历是图片格式（手机拍的），搭子能处理吗？**
A: 能。Claude 原生支持图片识别，直接上传即可，不需要额外安装 OCR 工具。
