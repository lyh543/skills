# Skills Workspace: 使用说明

将包含子模块的 Git 仓库克隆到本地（目标路径为 `~/.agents/skills`）：

克隆并同时初始化子模块：

```bash
git clone --recurse-submodules git@github.com:lyh543/skills.git ~/.agents/skills
# or use HTTPS
git clone --recurse-submodules https://github.com/lyh543/skills.git ~/.agents/skills
```
  
如果已克隆但未初始化子模块：

```bash
git clone git@github.com:lyh543/skills.git ~/.agents/skills
# or use HTTPS
git clone https://github.com/lyh543/skills.git ~/.agents/skills

cd ~/.agents/skills
git submodule update --init --recursive
```

常用更新命令：

- 拉取主仓库并让子模块匹配 superproject 指定的提交：

```bash
git pull
git submodule update --init --recursive
```

- 将所有子模块更新为它们各自远端分支的最新提交（注意：会移动子模块指向）：

```bash
git submodule update --init --recursive --remote
```

添加或移除子模块的简要命令：

```bash
# 添加
git submodule add <submodule_repo_url> <path>
git commit -m "Add submodule"

# 移除
git submodule deinit -f <path>
git rm -f <path>
rm -rf .git/modules/<path>
git commit -m "Remove submodule"
```
