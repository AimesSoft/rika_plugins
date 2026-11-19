# B 站番剧弹幕

让梨花给你在看的番剧补上 B 站的弹幕。把 B 站番剧的链接、短链或编号给她，她会解析出整季
各集（集号、标题、时长，以及取弹幕要用的 cid），再把你要的那一集的公开弹幕存成 XML，
交给 NipaPlay 导入到对应的那一集。

NipaPlay 自带弹弹play 弹幕；这个技能用在你想看 B 站弹幕，或者弹弹play 没有收录的时候。

## 可以这样问梨花

- “这一集用 B 站的弹幕：https://www.bilibili.com/bangumi/play/ep693247”
- “把《孤独摇滚！》第 1 到 3 集的 B 站弹幕都导进来。”
- “B 站这部番一共几集？有没有 PV 和特别篇？”

## 数据来源

- 番剧信息：`https://api.bilibili.com/pgc/view/web/season?ep_id=…` 或 `?season_id=…`
- md 编号换季：`https://api.bilibili.com/pgc/review/user?media_id=…`
- 弹幕：`https://comment.bilibili.com/<cid>.xml`
- b23.tv 短链：只读取跳转地址，不打开页面

都是公开接口，不登录、不使用 Cookie，不绕过会员或地区限制。

## 限制

- 公开接口只给每集有上限、以近期为主的一部分弹幕（通常几千条），不是全部历史弹幕。
- 部分番剧在某些地区看不到，接口会报错；梨花会如实告诉你，而不是说“没有弹幕”。
- B 站的集号可能和你的文件不一样（总集篇、分割放送、续季接着编号），导入前她会先核对。
- 已有的同名文件不会被覆盖。

## 更新日志

### 1.0.0

- 首个版本：`episodes`（ep/ss/md 编号、番剧链接、b23.tv 短链）、`fetch`（按 ep、季内集号或 cid 取公开弹幕 XML）。
