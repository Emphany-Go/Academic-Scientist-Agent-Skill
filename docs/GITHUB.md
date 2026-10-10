# 将 V0.1 上传到你的 GitHub 仓库

本教程只需要上传解压后的发布包内容。**不要上传整个原始开发目录**：里面有论文、真实研究资料和大量评测缓存。发布包已把这些排除。

## 方法一：浏览器上传，适合第一次发布

1. 登录GitHub。已有仓库就打开目标仓库；没有则点击右上角“+”→New repository，名称可用 `Academic-Scientist-Agent-Skill`，按你已决定的公开共享选择Public。为了避免同名文件冲突，新建时可不勾选README、license或.gitignore，包内已经包含。
2. 打开解压后的 `Academic-Scientist Agent Skill V0.1` 目录。你应看到 `README.md`、`LICENSE`、`NOTICE.md`、`skills/`、`docs/`、`tools/` 等文件。
3. 在仓库选择 **Add file → Upload files**；空仓库也可点击“uploading an existing file”。把上一步目录里的内容拖进去，保留内部子目录层次。不是把ZIP当唯一源码文件上传，也不是再套一层外部V0.1目录。
4. 检查待上传列表。根层应该有README.md；skill入口应为 `skills/academic-scientist/SKILL.md`。如果仓库已有同名内容，先比较，再决定在新分支更新，不直接覆盖不明旧文件。
5. 提交说明填 `Release Academic-Scientist Agent Skill V0.1`，点击 **Commit changes**。如果选择了新分支，按GitHub提示创建并检查Pull Request后再合并。
6. 回到仓库首页，确认README正常显示、skills目录完整。隐藏的.gitignore未被拖入时，单独上传或用Add file创建，内容复制包内.gitignore。

GitHub网页支持拖放文件/文件夹，每次最多100个文件、单文件25MiB；本包规模按此方式准备。如果浏览器没有保留目录、文件较多或被仓库规则阻止，使用方法二。[官方文件上传说明](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)

## 创建可下载安装的 Release

1. 在仓库右侧点击 **Releases**，选择 **Create a new release** / **Draft a new release**。
2. Tag填写 `v0.1`，选择要发布的已提交分支；标题填写 `Academic-Scientist Agent Skill V0.1`。
3. 描述可复制本包docs/RELEASE_NOTES.md中的功能和限制。不要将尚未验证的功能写成已通过。
4. 在附件区域上传本次生成的 `Academic-Scientist Agent Skill V0.1.zip` 和同目录的 `.zip.sha256` 文件。源码已在仓库中，ZIP放在Release中方便下载安装。
5. 检查后点击 **Publish release**。用户今后从Releases下载ZIP，按INSTALL.md安装。[官方Release操作](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

## 方法二：GitHub Desktop，适合后续更新

1. 从GitHub官方下载并安装GitHub Desktop，登录你的账户。
2. 已有远程仓库：File → Clone repository，选择目标仓库和本地保存目录。没有仓库：File → New repository，命名后选择本地目录创建；随后可用Publish repository公开发布。
3. 将干净发布包的内容复制到这个本地仓库目录，保留.git目录；已有同名文件先比较。不要将原开发项目整个复制进去。
4. 回到GitHub Desktop，在Changes中检查变更，Summary填版本说明，点击Commit to main（或你的分支名）。
5. 已有远程仓库点击Push origin；新仓库点击Publish repository，并按你公开共享的选择取消“Keep this code private”。发布后用Repository → View on GitHub查看。[官方Desktop教程](https://docs.github.com/en/desktop/overview/creating-your-first-repository-using-github-desktop)

MIT许可证已经放入包内；不需要在GitHub再生成不同的许可证。版权标注使用项目贡献者名称，未擅自使用你的真实姓名。项目说明和代码已经公开不代表测试论文或第三方运行库也获得MIT授权，本包不包含这些资料。

如果以后希望他人用Codex从仓库安装，可以告诉他们：使用内置 `$skill-installer`，提供你的仓库链接、版本tag `v0.1` 和目录 `skills/academic-scientist`。如果只在GitHub上传ZIP而没有源码目录，这种路径安装无法直接定位skill。此包是本地skill发布，不表示已进入OpenAI插件目录。
