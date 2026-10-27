# Task9 round1 独立计划审查

审查者task8_plan_review；原SHA581e1d1e6ef75069f5a7f3ab9dcecabe0cb7aedd950f35b6eee49bd7c4679a72。结论NEEDS REVISION。

1. Knowledge/Profile真实自带nav，必须最小纳入允许文件去重复导航并验证。
2. auth刷新恢复须子树请求前同步初始化唯一generation，不只login/logout。
3. 顶层cursor和每组next_session_cursor分开，每组loading/error/sequence与groupKey/cursor票据校验，防并发页串组。
4. ProfilePage/ProfileDetail真实DTO；create返回profile.id，两POST间核身份，createdProfileId绑定主题表单，防部分成功后改名错绑。
5. /chat壳路由清activeSessionId，防旧发送与高亮不一致。

审查者原只读cell9–13均terminal成功；无产品修改。修订仍限Task9，不提前Task10。
