# 萌番组

让梨花在[萌番组](https://bangumi.moe)找番剧资源。萌番组用标签整理种子：每部番剧、每个字幕组、
语言、分辨率都是一个标签。梨花先按名字或别名找到标签，再列出同时带这些标签的种子，
把标题、磁力、发布组、上传者、大小和标签拿给你看；也能按标题词搜索，或看全站最新发布。

技能只负责找，不会自己下载或订阅：下哪一个、要不要追番，都由你说了算。

## 可以这样问梨花

- “萌番组上有哪些《葬送的芙莉莲》的资源？”
- “只看喵萌奶茶屋发的。”
- “萌番组今天更新了什么？”
- “下那个 1080p 的合集。”（这时她才会交给 NipaPlay 的下载器）

## 数据来源

萌番组网页自己使用的公开 JSON 接口：

- `POST https://bangumi.moe/api/tag/search`：找标签
- `POST https://bangumi.moe/api/torrent/search`：按标签列种子
- `POST https://bangumi.moe/api/v2/torrent/search`：标题搜索
- `GET https://bangumi.moe/api/torrent/latest`、`/api/torrent/page/<n>`：最新发布
- `POST https://bangumi.moe/api/team/fetch`、`/api/user/fetch`、`/api/tag/fetch`：补上发布组、上传者和标签的名字

不登录、不读取任何账号或 Cookie。列种子时连同补名字最多四次请求，名字是一次批量查完的。

## 限制

- 标题搜索按整词匹配，中文标题常常搜不全，所以梨花会优先用标签。
- 大小是站点给的文字；做种数是萌番组自己的统计，常为 0，不代表别处没有人做种。
- 发布组、标签由上传者填写，可能缺失或不准；从标题推测的集数、分辨率只是线索。
- 站点改版、出现验证页或连不上时会如实报错，不会当作“没有资源”。

## 更新日志

### 1.0.0

- 首个版本：`tags`、`torrents`（按标签组合）、`search`（标题）、`latest`。
