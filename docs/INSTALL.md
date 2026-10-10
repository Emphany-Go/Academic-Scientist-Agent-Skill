# 安装 Academic-Scientist Agent Skill V0.1

## 1. 解压

解压 `Academic-Scientist Agent Skill V0.1.zip`。进入同时包含README.md、tools和skills的目录；不要把整个开发项目复制到Codex。

## 2. 安装本地skill

打开该目录的PowerShell，运行：

```powershell
python -B -X utf8 tools/install.py
```

默认目标为当前用户的 `.agents/skills/academic-scientist/`。这是官方列出的用户级加载位置。[OpenAI文档](https://learn.chatgpt.com/docs/build-skills)

若你当前Codex的已有个人skill位于 `.codex/skills/`，可使用本包兼容选项：

```powershell
python -B -X utf8 tools/install.py --legacy-codex-home
```

该选项使用CODEX_HOME/skills，未设置时为当前用户的.codex/skills；它来自本机内置skill-installer的兼容布局。两种方式选一种。若已经有同名skill，安装器不会覆盖；先核对/备份旧版，再由你决定升级。

仅在某个项目使用，可指定该项目的 `.agents/skills` 绝对路径：

```powershell
python -B -X utf8 tools/install.py --skills-dir "你的项目绝对路径/.agents/skills"
```

也可手工把本包的 `skills/academic-scientist` 整个文件夹复制到所选skills目录，确保下一层直接是SKILL.md。不要额外套一层V0.1目录，不重命名内部name。手工复制同样要先处理同名冲突。

新开一轮Codex对话，输入 `$academic-scientist` 或查看Skills列表。未出现时重启Codex；识别情况以实际客户端为准。

## 3. 检查运行环境

在Codex中要求：

> 请使用 $academic-scientist，定位该skill实际安装目录，运行scripts/check_environment.py。检查Python/PDF、Excel和绘图能力；如有load_workspace_dependencies请用于查找现有运行库。不要直接安装缺失依赖，先告诉我哪些能力受影响。

独立命令形态：

```powershell
python -B -X utf8 "skill实际路径/scripts/check_environment.py"
```

未传Node运行库位置时，Excel/绘图显示不可用或待定位，并不表示本机一定没有。Agent定位后可传--node、--runtime-package、--browser重查。检查器只读探测，不启动研究、不安装依赖。

| 能力 | 环境要求 |
|---|---|
| 会话、记录、核查流程 | Python 3.10+及jsonschema |
| PDF解析和页面渲染 | pypdf、pypdfium2、Pillow |
| XLSX生成 | Node和宿主已有@oai/artifact-tool |
| 图形PNG/PDF | Node、Playwright及已有Chrome/Chromium |

发布前已在Windows/Python3.11环境验证；其他系统仍应实际检查。Python清单锁定本次已测版本，不代表所有版本组合都兼容。

安装缺少的Python依赖时，先确认，再在研究项目内部建立虚拟环境并使用skill内requirements.txt；不要把依赖装入skill源码目录。Node库不随包分发，尤其不要假定@oai/artifact-tool可从公共npm直接安装。缺少该组件时V0.1不能生成新XLSX；JSON/Markdown流程可以继续。联网工具不可用或官方页面受限时，平台评级按未查到处理。

## 4. 创建研究项目

告诉Codex一个新项目目录、初始研究兴趣和论文位置。Agent先初始化该项目的内部工作目录，再执行已有阶段；不要在skill安装目录中做研究。已存在的旧任务从原工作目录恢复，不自动搬迁。

读写成果从阅读入口开始。Excel事实单元格可改，笔记独立；修改后告诉Agent“请读取我修改的文献整理.xlsx，核查后更新”。内部基线和证据不能手工删除，否则可能无法正确合并。

## 5. 校验安装包

在解压包目录执行：

```powershell
python -B -X utf8 tools/self_check.py
```

校验文件清单、哈希、Python语法、链接和可用时的JSON Schema。它不能替代真实研究测评。SHA256清单用于检测文件改变，不是作者数字签名。
