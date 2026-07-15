# AI 封面结构助手

从飞书封面案例库中维护可检索的视觉结构索引，并根据已经确定的中文封面文案，推荐合适的结构、排版和参考图。

这个项目不是只给 Codex 使用。核心由一份可移植的 Agent 工作流（`SKILL.md`）和一个输出 JSON 的 Python CLI 组成；任何能够读取 Markdown、执行本地命令并查看图片的 Agent 都可以接入。

## 它解决什么问题

收藏高点击封面不等于真正会使用它们。只有关键词或“适用场景”时，Agent 很难判断一张图能否承载新的文案。

这个工具为每张封面补充统一的视觉结构标注，包括：

- 文案容量和适合的主标题行数；
- 文字区、人物或产品的位置；
- 信息层级、视觉元素和风格；
- 情绪钩子、内容类型和画面 OCR；
- 一句便于人快速阅读的中文结构概览。

收到新文案后，它会优先按文案长短、行数、层级和版式匹配，再参考主题与情绪，最后下载并展示最合适的库内案例。

## Agent 无关的设计

项目分为三层：

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 通用工作流 | `SKILL.md` | 告诉 Agent 何时审计、标注、检索、复核和展示结果 |
| 确定性工具 | `scripts/cover_library.py` | 读写飞书、分析文案、计算初选分数、下载图片，统一输出 JSON |
| 可选适配器 | `agents/openai.yaml` | Codex/OpenAI 客户端的显示元数据，不参与核心逻辑 |

因此，其他 Agent 不需要调用 OpenAI API，也不需要读取 `agents/openai.yaml`。只要它能按照 `SKILL.md` 调用 CLI，就能使用同一套封面库和匹配规则。

## 运行要求

- Python 3.10 或更高版本；
- 已安装并登录 `lark-cli`；
- 对目标飞书文档及其中嵌入的多维表格有读写权限；
- Agent 能执行 shell 命令；
- 当出现新增、替换或未标注图片时，Agent 需要具备看图能力才能补齐结构标注。

如果索引已经完整，只做文案检索时不要求 Agent 每次重新看完全部图片。

## 快速开始

```bash
git clone https://github.com/NoMooncake/recommend-cover-layout.git
cd recommend-cover-layout
python3 scripts/cover_library.py audit --doc-url "<飞书文档链接>"
python3 scripts/cover_library.py recommend \
  --doc-url "<飞书文档链接>" \
  --text "你的封面文案" \
  --top 8
```

仓库中配置了作者当前案例库作为默认来源。其他用户或其他库应始终显式传入 `--doc-url`。

多行文案可以通过标准输入传入，避免 shell 转义破坏原始换行：

```bash
printf '%s' $'第一行\n第二行' | \
  python3 scripts/cover_library.py recommend \
  --doc-url "<飞书文档链接>" \
  --text - \
  --top 8
```

## 接入不同 Agent

### 支持 Skill 的 Agent

把整个仓库安装到该 Agent 的 Skill 目录，并确保目录名为 `recommend-cover-layout`。不同客户端的 Skill 路径并不统一，请以对应客户端的安装规则为准。

触发示例：

```text
使用 recommend-cover-layout，根据下面已经确定的封面文字，
从飞书封面库中推荐并展示 3 个最合适的排版参考：

<封面文字>
```

### 通用命令行 Agent

把仓库路径和任务一起交给 Agent：

```text
先完整读取 /path/to/recommend-cover-layout/SKILL.md，
严格按照其中的流程处理这段封面文案：<封面文字>。
使用的飞书文档是：<飞书文档链接>。
```

### Tool calling / 工作流平台

也可以把 CLI 包装成一个工具函数。推荐的最小输入是：

```json
{
  "doc_url": "<飞书文档链接>",
  "text": "<已经确定的封面文案>",
  "top": 8
}
```

底层命令：

```bash
python3 scripts/cover_library.py recommend \
  --doc-url "<doc_url>" \
  --text "<text>" \
  --top <top>
```

CLI 的标准输出是 JSON，适合被 Agent、自动化工作流或上层服务继续解析。初选分数用于扩大召回范围，不应直接替代 Agent 的视觉复核。

## Agent 标准调用流程

1. 原样接收已经确定的封面文案，不擅自改写。
2. 执行 `audit` 检查全部结构标注及图片版本。
3. 如果存在 `missing`、`stale` 或 `invalid`，先看图并补齐标注。
4. 执行 `recommend` 取得候选案例。
5. 按 `references/matching-rubric.md` 重新判断文案结构、画面可行性和情绪匹配。
6. 下载最终选中的案例并向用户展示图片。
7. 给出具体的文字映射、排版建议、风险和一个首选方案。

完整行为约束见 [`SKILL.md`](SKILL.md)，标注格式见 [`references/annotation-schema.md`](references/annotation-schema.md)。

## 常用命令

```bash
# 查看案例库
python3 scripts/cover_library.py list --doc-url "<飞书文档链接>"

# 检查索引完整性和图片版本
python3 scripts/cover_library.py audit --doc-url "<飞书文档链接>"

# 缺少字段时创建 AI结构标注
python3 scripts/cover_library.py ensure-field --doc-url "<飞书文档链接>"

# 写入一条经过看图确认的结构标注
python3 scripts/cover_library.py annotate \
  --doc-url "<飞书文档链接>" \
  --cover-id 46 \
  --annotation '<JSON object>'

# 把旧的纯 JSON 单元格转换成中文在上、机器索引在下
python3 scripts/cover_library.py format-index --doc-url "<飞书文档链接>"

# 下载最终选中的参考图
python3 scripts/cover_library.py download \
  --doc-url "<飞书文档链接>" \
  --cover-id 35 \
  --cover-id 32 \
  --output-dir .cover-layout-recommendations
```

## 飞书案例库要求

目标文档需要嵌入一张飞书多维表格，并至少包含以下字段：

| 字段 | 用途 |
| --- | --- |
| `编号` | 案例的稳定编号 |
| `封面` | 封面图片附件 |
| `关键字` | 主题、风格等辅助信息 |
| `适用场景` | 已有的人工使用建议 |
| `AI结构标注` | 自动维护；中文概览在上，机器索引在下 |

Skill 只会自动维护 `AI结构标注`，不会修改封面、关键词、适用场景或其他业务字段。

## 当前边界

- 当前数据源适配器是飞书文档中的多维表格；
- CLI 依赖本机的 `lark-cli` 登录状态，不是托管 API；
- 新图片的准确标注依赖具备视觉能力的 Agent；
- 推荐结果来自案例库中的真实图片，不会虚构不存在的案例；
- 除非库中保存了点击率数据，否则结果只能称为“收录的参考案例”，不能声称具体点击率。

后续可以在保持 Agent 调用协议不变的前提下，继续增加其他图库适配器、HTTP/MCP 封装和更多 Agent 的原生安装包。
