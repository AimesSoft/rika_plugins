---
name: bilibili-bangumi-danmaku
description: 用户想要 B 站（bilibili）番剧、国创、电影等 PGC 内容的弹幕时使用；把 ep/ss/md 编号、bilibili.com/bangumi 链接或 b23.tv 短链解析成整季各集（含 ep_id 和 cid），再把某一集的公开弹幕 XML 存成新文件，之后交给 danmaku.import。
---

# B 站番剧弹幕

只用 B 站公开接口，不登录、不带 Cookie。`<skill>` 是本技能文件夹的绝对路径；
Windows 用 `python` 代替 `python3`。输出 UTF-8 JSON；出错时 stderr 是 `{"error": ...}`，退出码非零。

弹幕首选已有的弹弹play 剧集身份；用户要 B 站弹幕、或弹弹play 没有时再用本技能。

## 命令

目标（TARGET）可以是 `ep693247`、`ss43164`、`md28339735`，`https://www.bilibili.com/bangumi/play/ep…`、
`…/play/ss…`、`…/media/md…` 链接，或 `b23.tv` 短链。普通视频（BV/av）不是番剧，不支持。

| 命令 | 作用 |
| --- | --- |
| `python3 <skill>/bilibili_bangumi.py episodes TARGET [--sections] [--limit 60] [--offset 0]` | 整季信息和各集，`--sections` 连 PV、SP 等花絮一起列 |
| `python3 <skill>/bilibili_bangumi.py fetch ep693247 --out 文件.xml` | 这一集的弹幕 XML 写到新文件 |
| `python3 <skill>/bilibili_bangumi.py fetch ss43164 --episode 3 --out 文件.xml` | 整季里 `index` 为 3 的那集 |
| `python3 <skill>/bilibili_bangumi.py fetch --cid 875212290 --out 文件.xml` | 已知 cid 时直接取 |

`--out` 必须是不存在的新文件，所在文件夹必须已存在；已有文件绝不覆盖。XML 放在 harness 的 `records/`
等输出目录，不要写进视频所在的共享目录。

## 输出

`episodes`：

- `season`：`season_id`、`media_id`、`title`、`season_title`、`type`（番剧、国创、电影……）、`progress`（如“已完结, 全12话”）、
  `first_aired`、`finished`、`areas`、`area_limit`（B 站原值）、`url`、`related_seasons`（其他季或版本的 `season_id`）。
- `episodes[]`：`index`（B 站的集号文字，如 `1`、`12.5`、`SP`）、`title`、`ep_id`、`cid`、`duration_seconds`、`published`、
  `badge`（如“会员”“受限”）、`section`（正片或花絮分区名）。
- 用 ep 查询时另有 `requested_episode`；`total_episodes`、`total_extras`、`offset`、`returned`、`truncated`；`warnings`。

`fetch`：`path`（写好的文件绝对路径）、`cid`、`comments`（条数）、`maxlimit`、`bytes`、`season`、`episode`、`xml_note`；
0 条时有 `warning`。

## 限制

- 公开 XML 只是该集弹幕池里有上限、以近期为主的一部分（`maxlimit` 只是参考），不是全部历史弹幕。
- 不同网络看到的目录可能不同：地区限制时接口通常返回 -10403 或 -404，脚本如实报错，不代表番剧不存在。
  “受限”只说明播放受限，不说明弹幕能否读取，以 `fetch` 结果为准。
- B 站关闭了弹幕的视频会报错且不写文件；有效但 0 条的 XML 会写入并如实报告 0。
- 集号以 B 站为准，可能与本地文件、弹弹play 或 TMDB 的集数不同（总集篇、分割放送、续季接着编号）。
- 多集时逐集串行获取，不要并发轰炸；被限流（HTTP 412/429）时停下来稍后再试。

## 接下来

- 先确认作品、季和集与本地文件的对应，再导入；有歧义时保留候选并询问用户。
- 导入：先 `./nipa describe danmaku.import` 看实时参数，再把 `path` 交给 `danmaku.import`，回读 `danmaku` 状态核对。
- 只在用户要求时准备弹幕；这一步不下载视频，也不建立订阅。
