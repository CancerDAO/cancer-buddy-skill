# 安装

## 一行安装

```bash
npx skills add CancerDAO/cancer-buddy-skill -g --all
```

`--all` 会装上全部模块。只想装部分模块时，**`cancer-buddy` 必须装**——其他模块共用它的脚本和规则。

作为 Claude Code 插件安装时，本仓库也提供 `.claude-plugin/`（插件名 `cancer-buddy`，市场名 `cancerdao-marketplace`）。

## 运行要求

| 需要 | 用途 | 必需？ |
|---|---|---|
| Python ≥ 3.9 | 全部脚本（只用标准库，无需 pip 安装任何包） | 必需 |
| PyMuPDF（`pip install pymupdf`）**或** poppler（`pdftoppm` / `pdftotext` / `pdfinfo`） | 处理 PDF：逐页渲染图片、抽取文本层 | 有 PDF 时需要其一 |
| macOS 自带 `sips` | 把 iPhone 的 HEIC 照片转成 JPG | 有 HEIC 时需要 |
| Node.js + Chrome | `web-access` 的 CDP 模式（需要浏览器才能打开的网站） | 可选 |

poppler 安装：macOS `brew install poppler`；Debian/Ubuntu `sudo apt install poppler-utils`。

不需要 OCR 引擎：图片和扫描页由多模态模型直接阅读。

## 数据位置

默认 `~/CancerDAO/patients/`。可用环境变量改：

```bash
export CANCER_BUDDY_PATIENTS_DIR=/path/to/patients
```

可选的本地指南资料库：`~/CancerDAO/library/`，或用 `CANCER_BUDDY_GUIDELINES` 指向一个带 `index.json` 的目录。

## 检查安装

```bash
python3 -m unittest discover -s tests
```
