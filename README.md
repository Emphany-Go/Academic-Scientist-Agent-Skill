# Academic-Scientist Agent Skill V0.1

为 Codex 提供有证据的文献阅读与研究讨论工作流：从模糊研究兴趣出发，通过三轮真实问答明确阅读切入点，整理给定论文、形成可编辑文献表和学习建议，再生成单路线研究方案及三类可编辑流程图。

**内部调用名称：`$academic-scientist`；许可证：MIT。** V0.1是发布版本，与内部不同阶段的数据Schema版本分开。

## 能做什么

- 三轮逐步头脑风暴，保留未知，不替用户回答。
- 按给定论文抽取研究目标、方法/模型、实验条件、指标和结论，记录原文页码与证据；事实不足时明确保留缺失。
- 独立查询官方发表平台定位与最新可核实评级；未查到显示“尚未查阅到相关官方评级”，不检索第三方评级。
- 导出Markdown和可编辑Excel；事实单元格修改需回看原文，笔记独立维护，冲突不静默覆盖。
- 按方法、背景、实验设计、模型选择说明借鉴理由，不进行量化评分或推荐强弱排序。
- 明确单一研究路线后交付整体框架、关键模块详图和实验流程图，中文说明配必要英文术语；提供draw.io、SVG、PNG和PDF（渲染能力可用时）。

## 安装和开始

解压发布包后，在该目录运行：

```powershell
python -B -X utf8 tools/install.py
```

默认安装到当前用户的 `.agents/skills/academic-scientist`，遇到已有同名skill会停止并保留旧版。部分客户端使用 `.codex/skills`，可按 [安装说明](docs/INSTALL.md) 选择兼容位置；不要同时安装两份同名skill。安装器只复制本包skill，不安装依赖、不修改Codex全局配置。

在Codex中使用：

> 使用 $academic-scientist。我想研究……，现在还不清楚具体问题。请先检查环境，在我指定的研究项目目录中开展三轮讨论；读取我提供的论文，逐项保留依据。遇到影响研究内容的未知选择先问我。

Codex加载skill的方式与位置依据 [OpenAI官方说明](https://learn.chatgpt.com/docs/build-skills)。这是本地skill包，不是已上架的插件。

## 使用时的文件

```text
我的研究项目/
├─ 阅读入口.md
├─ 研究档案.md
├─ 文献整理.xlsx
├─ 阅读建议.md
├─ 研究方案.md
├─ 论文阅读卡/
├─ 流程图/
└─ .academic-scientist/  # 证据、状态、历史及审阅过程
```

成果随工作完成出现；用户无需浏览内部目录。旧研究记录不会自动搬迁。浏览器临时目录在新渲染结束后清理，证据和必要审查记录长期保留。用户改过的文件不会被自动覆盖。

## 环境与边界

需要支持本地脚本和文件/视觉阅读的Codex环境。Python依赖清单在 [requirements.txt](skills/academic-scientist/requirements.txt)；Excel渲染依赖宿主已有 `@oai/artifact-tool`，图形预览依赖Node、Playwright和Chrome/Chromium。**这些运行库没有包含在ZIP中；安装skill不等于安装运行环境。** 无法使用相应组件时明确报告缺项，不把降级输出当成完整交付。

本地脚本负责状态、结构校验和导出；语义阅读、官方检索和判断仍由Codex执行。不会自动训练模型或执行研究实验，不声明自动验证新颖性、无幻觉或论文可直接投稿。原生draw.io应用兼容、不同机器部署和未覆盖评测场景仍需实际核对，详见 [版本说明](docs/RELEASE_NOTES.md)。

## 项目文件

- [安装与环境检查](docs/INSTALL.md)
- [GitHub上传教程](docs/GITHUB.md)
- [V0.1版本说明](docs/RELEASE_NOTES.md)
- [发布验证范围](VALIDATION.md)
- [许可证](LICENSE)与[依赖/参考说明](NOTICE.md)

安装内容位于 `skills/academic-scientist/`。研究论文、个人问答、旧Excel、测试工作区、浏览器缓存和开发历史均不包含在本包中。
