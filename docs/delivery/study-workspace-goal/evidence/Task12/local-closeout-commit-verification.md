# Task12 第一笔本地提交核验

核验对象：产品提交 `4e1d15b0ba0a065af4d6246bcd5e7e4b21679791`；直接父提交 `a6117c48c1ff7e8877806d0862e69ff0e42f13f4`。依据 [第一笔明确清单](local-closeout-commit-manifest.json)对提交实际路径使用 Git 的 NUL 分隔输出逐项比较，预期与实际均为 98 项，无新增或遗漏；README 仅纳入经审自有 Task12 片段。

- 第一笔提交后、第二笔材料准备前，索引为空。
- 以第一笔 HEAD 对工作树 README 的实际增删行（保留内容及顺序）与外部保存的用户差异基线逐行比较：均为 162 条新增行，完全相同；比较不依赖 hunk 行号或上下文。该用户差异基线含用户原始内容，不纳入提交。
- 工作树 README 前 87830 字节 SHA256：`c91dd44f501a4ed370b64fd36e24f7986a3e71f1dc7312c7ae89ea068dead70b`；资产清单完整 SHA256：`41462288eb1a53ebf320126a3a77047b9e2242fa497ec951ac8d29701248de1b`。二者均与收口计划记录一致，资产清单未纳入第一笔。
- Task12 功能验收和已知限制见[验收摘要](acceptance-summary.md)及[独立审计](acceptance-audit.md)；摘要中未提交状态是第一笔提交前历史检查点。

本记录仅核验第一笔；第二笔账本提交及其父链、文件集、空索引和用户差异须在第二笔实际提交后另行核验，不能预写其 SHA。Task13 保持 PENDING，完成第二笔实核后推进规划。

第二笔预期白名单：`README.md`（仅独立补丁对应的自有 Task12 状态变更）、`docs/delivery/study-workspace-goal/status.json`、`docs/delivery/study-workspace-goal/progress.md`、本核验文件。独立补丁和用户差异基线仅作为本地操作材料，不纳入白名单。
