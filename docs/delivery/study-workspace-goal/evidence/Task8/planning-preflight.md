# Task8规划前核查

基线75be601（Task7产品c07bb0a），app/tests无未提交差异；README原142行/asset34行保护。Task8主计划与raw已批准，用户SC-002仅继续Task8。

当前ProfileMasteryStore无apply_assessment_delta，主计划需落实新增；现chat与stream分开加载旧SQLAlchemyMasteryStore，未接Task7context，persist_turn仍state={}、按消息数计算turn_index/整图save；main仅init_db无service装配。Task3请求Store已有claim/renew/interrupt/retry，interrupt先attempt+1、retry再+1，不应误改。

独立测试PG容器studyagent-goal-test-pg原生只读观察Up、映射127.0.0.1:55440，pg_isready实际accepting connections。仅连接预检，未运行随机子库/业务并发/重启验收；不触业务库。只读工具调用有等待，保持原cell142/143/144至返回，未重复运行、未据此编造平台故障。

冻结round1计划SHA256: 079bd5182e32b8c513624efe7d4f02f892aec007617453ed15977ab7eb1a8846
完整三层计划交task8_plan_review只读审查；产品未改。
