# 梨花扩展

NipaPlay 的 AI 助手梨花的官方扩展仓库。NipaPlay「设置 › 梨花 › 扩展」里的列表读的就是这里的
[`index.json`](index.json)。扩展有两种：

- **技能（skill）**：一份写给梨花的说明（`SKILL.md`）加几个只用 Python 标准库的小脚本。装好后梨花就知道
  有这件事可做，需要时自己用 shell 运行脚本，比如去某个 BT 站找资源、取某一集的弹幕。
- **插件（plugin）**：DeepSeek Harness（DSH）的 npm 插件，比如模型提供方或 AI 订阅转换。只在梨花运行在 DSH 上时生效。

每个扩展一个文件夹；文件夹里的 `README.md` 写着它做什么、怎么问梨花、数据来源、限制和更新日志，
NipaPlay 的扩展详情页显示的就是它。

## 这里的扩展

| 扩展 | 类型 | 分类 | 做什么 |
| --- | --- | --- | --- |
| [動漫花園](skills/dmhy) | 技能 | BT | 在 share.dmhy.org 的公开 RSS 里找资源：磁力、发布者、分类、时间；单个帖子再查大小、种子和文件列表 |
| [ACG.RIP](skills/acgrip) | 技能 | BT | 在 acg.rip 的公开 RSS 里找资源：种子链接、准确大小、时间，可按分类、发布组筛选 |
| [萌番组](skills/bangumi-moe) | 技能 | BT | 在 bangumi.moe 按番剧、字幕组等标签或标题找资源：磁力、发布组、大小、标签 |
| [B 站番剧弹幕](skills/bilibili-bangumi-danmaku) | 技能 | 弹幕 | 把 B 站番剧链接或编号解析成各集，取某一集的公开弹幕 XML 交给 NipaPlay 导入 |

插件暂时还没有。

这些技能只找资料，不替你做决定：梨花把候选拿给你看，你说要下载才下载，你明确要追番才订阅。
它们与梨花自带的 Mikan、Nyaa、AnimeTosho 查询工具互补，不重复。

## 安装

- **扩展列表**：在 NipaPlay 的「设置 › 梨花 › 扩展」里点安装。列表来自这个仓库 `main` 分支的 `index.json`，
  每个文件都按其中的 SHA-256 校验，对不上就不装。条目有 `notices` 时，安装前会先给你看。
  - 技能装到 `<Next 数据目录>/store/skills/<id>/`。NipaPlay 在梨花的系统提示里告诉她每个已安装技能的
    名字、说明和 `SKILL.md` 的绝对路径，她按说明用 shell 运行脚本。
  - 插件的 npm 包按 `index.json` 固定的版本和 SHA-256 下载、解开，DSH 运行环境自带的包（`peers`）由 NipaPlay 链接，
    `dsh` 里的行加入 DSH 的配置。安装时不运行任何安装脚本。
- **任意 npm 包**：同一页面也可以填一个 npm 包名（`name` 或 `name@版本`）。它可以是 DSH 插件，也可以是根目录有
  `SKILL.md` 的技能包。这样装的包没有经过审核，会标记为「未审核」；需要安装脚本、或依赖 DSH 运行环境没有的包的插件装不上。

## 开发与调试

需要 Python 3.9 以上，不需要安装任何依赖。

```sh
python3 skills/dmhy/dmhy.py --help                 # 每个脚本都有 --help
python3 skills/dmhy/dmhy.py search 芙莉莲 --limit 3  # 直接试，输出 JSON
python3 tools/build_index.py                       # 校验所有条目并重新生成 index.json
python3 tools/build_index.py --check               # 只检查：条目有问题或 index.json 过期时退出码为 1
python3 -m unittest discover -s tools              # 构建工具的测试
```

- 试技能时可以把文件夹的绝对路径告诉梨花，让她读 `SKILL.md` 照着用，看她能不能不靠额外提示就用对。
- 改了技能里的任何文件都要重新运行 `tools/build_index.py` 并提交 `index.json`，否则 CI 的 `--check` 不通过，
  安装时的 SHA-256 校验也会失败。
- 构建会拒绝条目文件夹里的隐藏文件（如 `.DS_Store`）和 `__pycache__`。脚本若导入同文件夹的模块，
  调试时设 `PYTHONDONTWRITEBYTECODE=1`。
- 有插件条目时，构建要访问 npm registry；`--offline` 沿用 `index.json` 里已有的记录（版本没变时）。
- CI（`.github/workflows/check.yml`）在每次推送和 PR 上运行 `--check`、单元测试，编译所有技能脚本，
  并在别的目录下运行每个脚本的 `--help`。

## 格式

### 仓库

```
index.json                 由 tools/build_index.py 生成，提交到仓库
skills/<id>/item.json      技能的声明
skills/<id>/SKILL.md       写给梨花的说明
skills/<id>/README.md      写给人看的说明，扩展详情页显示它
skills/<id>/*.py           脚本（也可以有子文件夹）
plugins/<id>/item.json     插件的声明
plugins/<id>/README.md     写给人看的说明
tools/build_index.py       构建与校验
```

`id` 只用小写字母、数字和连字符，以字母或数字开头，最长 48 个字符（`^[a-z0-9][a-z0-9-]{0,47}$`），与文件夹同名；
技能和插件的 `id` 也不能重复。

### 技能的 item.json

```json
{
  "id": "dmhy",
  "name": "動漫花園",
  "version": "1.0.0",
  "description": "让梨花在動漫花園（share.dmhy.org）的公开 RSS 里找番剧资源，给出磁力链接、发布者、分类和发布时间。",
  "author": "AimesSoft",
  "category": "bt",
  "minHostVersion": "1.12.0",
  "notices": ["安装前给用户看的提醒。"]
}
```

- `name` 最长 80 个字符；`description` 是一句中文，一行，最长 120 个字符；`author` 必填。
- `version` 与 `minHostVersion`（NipaPlay 的最低版本，可省略）都是语义化版本号，如 `1.0.0`。
- `category` 只有四种：`bt`、`danmaku`（弹幕）、`model`（模型）、`tool`（工具）。
- `notices` 可省略，最多 8 条中文提醒，每条最长 600 个字符，安装前显示。
- 不认识的字段会让构建失败。

### SKILL.md

开头是 YAML frontmatter，`name` 与 `id` 相同，`description` 一行写清**什么时候用它**；正文是写给梨花的简明中文说明：

```markdown
---
name: dmhy
description: 用户要在動漫花園找番剧 BT 资源时使用；……
---

# 動漫花園

| 命令 | 作用 |
| --- | --- |
| `python3 <skill>/dmhy.py search 关键词 [--limit 20]` | …… |
```

- 用 `<skill>` 代表技能文件夹的绝对路径，写出每个命令的确切用法、输出字段和限制。
- 写明下一步用哪个 `nipa` 动作（如把磁力交给 `download.add`、把弹幕 XML 交给 `danmaku.import`），并提醒先
  `./nipa describe <动作>` 看实时参数。
- 写明推荐不等于下载，订阅要用户明确提出。

### 脚本

- 只用 Python 3.9+ 标准库，不导入技能文件夹以外的任何东西。
- 以 `python3 <绝对路径>/script.py …` 从任意当前目录运行都要正常；不依赖当前目录。
- 标准输出是 UTF-8 JSON（Windows 上也是：启动时把 stdout/stderr 设成 UTF-8）；错误写到 stderr，退出码非零。
- 有 `--help`；返回列表的命令有 `--limit`（0 表示不截断），并报告总数和是否截断。
- 不读取、不索要任何凭据、Cookie 或 NipaPlay 的配置；只访问写明的公开站点，设超时，User-Agent 写明来源
  （如 `NipaPlay-Rika-Skill/1.0`），不并发、不连续抓取。
- 结果只是证据：不下载、不订阅、不替用户选择；保存一律由梨花通过 `nipa` 动作完成。写文件时只写到调用者给的新路径，不覆盖已有文件。

文件规则：每个技能除 `item.json` 与 `README.md` 外最多 64 个文件，每个文件最大 1 MiB；路径只能用
`A-Z a-z 0-9 . _ - /`，不能含 `..`，不能有隐藏文件、符号链接或 `__pycache__`，大小写不同的同名文件也不行。

### 插件的 item.json

插件文件夹里只有 `item.json` 和 `README.md`，代码来自 npm：

```json
{
  "id": "example-provider",
  "name": "示例模型",
  "version": "1.0.0",
  "description": "一句中文说明。",
  "author": "作者",
  "category": "model",
  "notices": ["使用这个插件可能违反某服务的使用条款，账号有被封禁的风险。"],
  "npm": {"name": "@scope/example-provider", "version": "1.2.3"},
  "peers": ["@deepseek-ai/cordis"],
  "dsh": [{"id": "example-provider", "package": "@scope/example-provider", "config": {}}]
}
```

- `npm.version` 是确切版本，不能是范围或 `latest`。
- `peers` 是 DSH 运行环境自带、由 NipaPlay 链接的包。v1 规则：插件的运行时依赖（`dependencies` 和必需的
  `peerDependencies`）必须都在 `peers` 里或打包在插件内（`bundleDependencies`）；带 `preinstall`、`install`、
  `postinstall` 脚本或需要原生编译的包不收。
- `dsh` 是加入 DSH 配置的 1 到 8 行：`id` 用小写字母、数字和 `._-`，不能以 `nipa-` 开头；`package` 必须是插件的
  npm 包名，由 NipaPlay 解析成安装后的入口文件；`config`（对象）与 `inject`（字符串列表）可省略。

构建时从 `https://registry.npmjs.org/<包名>/<版本>` 读取信息，下载 `dist.tarball`，按 `dist.integrity`（sha512）
核对，再记下 SHA-256 和大小；不符合上面规则时构建失败并说明原因。

### index.json

由构建工具生成，不要手改。条目按 `category`、再按 `id` 排序，键的顺序固定，两格缩进，以换行结尾；
`url` 相对于仓库根目录（NipaPlay 在前面加上 raw 地址），npm 包的 `url` 相对于 registry 根目录。

```json
{
  "version": 1,
  "items": [
    {
      "id": "dmhy", "kind": "skill", "name": "動漫花園", "version": "1.0.0", "description": "……",
      "author": "AimesSoft", "category": "bt", "notices": ["……"],
      "readme": {"url": "skills/dmhy/README.md", "sha256": "……", "bytes": 1234},
      "files": [{"path": "SKILL.md", "url": "skills/dmhy/SKILL.md", "sha256": "……", "bytes": 2345}]
    },
    {
      "id": "example-provider", "kind": "plugin", "……": "与技能相同的公共字段",
      "readme": {"url": "plugins/example-provider/README.md", "sha256": "……", "bytes": 456},
      "packages": [{"path": "node_modules/@scope/example-provider", "name": "@scope/example-provider",
                    "version": "1.2.3", "url": "@scope/example-provider/-/example-provider-1.2.3.tgz",
                    "sha256": "……", "bytes": 7890}],
      "peers": ["@deepseek-ai/cordis"],
      "dsh": [{"id": "example-provider", "package": "@scope/example-provider", "config": {}}]
    }
  ]
}
```

技能的 `files` 列出文件夹里除 `item.json`、`README.md` 以外的所有文件，按路径排序；`minHostVersion` 只在设置时出现。

## 审核规则

合并前维护者会逐行读代码，确认：

- 技能只访问写明的公开站点，只用标准库，不碰凭据和 Cookie，不绕过会员、付费墙、DRM 或地区限制；
  不自动下载、订阅或替用户做选择，输出如实区分“查到了”“没有”和“出错了”。
- 插件版本固定，代码（包括打包进去的依赖）经过阅读；可能违反第三方服务条款、导致封号或泄露数据的风险
  写进 `notices`，让用户安装前就知道。
- `README.md` 说清用途、数据来源、限制和更新日志；`index.json` 与文件一致，CI 通过。

投稿方法见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 提交扩展

1. 在 `skills/` 或 `plugins/` 下新建一个以 `id` 命名的文件夹，按上面的格式放好文件。
2. 运行 `python3 tools/build_index.py`，再运行 `python3 tools/build_index.py --check` 与测试。
3. 更新时改 `item.json` 的 `version`，在 `README.md` 里写一条更新日志，并重新生成 `index.json`。
4. 自己用梨花试过，再提交 Pull Request，说明用途和测试情况。
