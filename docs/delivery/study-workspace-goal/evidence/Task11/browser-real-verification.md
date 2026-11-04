# Task11 真实页面知识库与画像验收补证（2026-11-04）

## 主会话真实浏览器观察

主会话报告：知识库搜索不存在的关键词显示暂无资料；搜索正文“分数”命中资源 2。页面新建 `Task11页面新建可删除资料`，填写说明和正文并保存，再通过页面删除与确认；清空查询后列表仅有资源 2（截图 `browser-knowledge-crud.png`）。

从会话 A 的侧栏进入学习画像，URL 包含相应 profile/session；页面详情与摘要均显示 REV1、待评估、0/2，呈现两个真实知识点、无关系及来源（`browser-profile-real.png`）。选择空主题后仅以 URL 切换查看，显示 REV1、待评估和暂无知识点（`browser-profile-empty.png`）。这些为主会话页面观察。

## 真实 HTTP 只读复核

以本次专用账号读取：资源 3 返回 404，本人资源列表仅 ID 2；会话 A snapshot 返回 200，与此前 `real-http-responses.json` 中同会话快照相比，profile_id、active_node_id、state_version 均未变化（分别为 `09db3ddf-3084-48df-8645-3983fba7a4ab`、`ab28edbc-5443-43e4-8c13-8359ccc336a7`、0）。

主题详情、summary 和空主题详情、summary 均 HTTP 200。主画像 detail 的 profile.revision、profile_revision 与 summary.profile_revision 均为 1；summary 两个活动节点、assessed_count=0、total_count=2、mastery_score=null、edges 与 recent_evidence 均空。空主题 summary revision=1、total_count=0、mastery_score=null、nodes 和 edges 均空。脱敏核对结果见 `browser-real-api-readback.json`。

## 专用 PostgreSQL 与日志只读复核

本次隔离服务日志中页面新建后的 `DELETE /api/knowledge/3` 返回 200；数据库序列 last_value=3、资源表当前仅 ID 2。结合浏览器操作与独立 HTTP 的 ID 3=404，支持本轮新建资源 ID 3 已删除；日志未提供新建响应体，不单凭日志将 POST 响应与 ID 3 直接绑定。

专用库中会话 A 仍绑定上述画像与活动节点，state_version=0；另一同主题会话仍绑定该画像、活动节点为空且 state_version=0。未修改任何数据。

本次观察没有非空关系、已评分节点或来源链接，不能宣称对应真实浏览器场景通过。图片尺寸、其他账号 UI 和网络故障以各自记录为准。
