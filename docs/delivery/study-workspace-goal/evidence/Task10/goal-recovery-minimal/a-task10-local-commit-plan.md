# Task10 精确本地提交准备方案

准备日期2026-11-04，行为证据仍保留原执行日期。当前HEAD `6d5829303f639e50ca15b11a9c8f79ee093caff1`，本准备阶段index为空；未执行任何Git写入。Task10为验收通过待本地提交，尚非DONE。最终状态以执行者新核对的HEAD/index/工作树为准。

## 文件范围

`a-task10-local-commit-manifest.json` 是逐文件清单，不以目录通配符替代。full_file_entries列出完整暂存候选及SHA256/大小/分类；partial_file_entries只允许README选择性补丁。产品文件来自产品OCR冻结范围中modified/added项，覆盖Task10前期实现和A两文件局部修复；未变化的46项上下文无需重复暂存。Task10计划、raw、历史审阅/RED/GREEN/失败/截图、设施脚本及最终真实证据均列入。历史B原方案只作决策留存，不表示实施授权。

约13MB证据以原始文件保留，不删首轮失败，不只挑GREEN；较大的OCR preview/checklist属于本任务审查输入与范围证据，不能以日志体积为由悄悄遗漏。清单生成后如最终文档发生授权变动，先核差异再刷新对应哈希，不把哈希不符自动当作可接受。

明确排除`.superpowers/`（含runtime、工具依赖、私有服务日志/环境/凭据）、`.env`及密钥、用户数据库、node_modules、web/dist、AGENTS.md、Learned、非Task10文档/图片/临时测试目录、docs/asset-inventory.md全部现有34行变更。敏感模式检查仅覆盖JWT/私钥/含口令PG URI且匹配为0，不等于完整密钥审计；执行者仍须复核新增文件及最终cached diff，禁止把私有配置带入。

## README选择性暂存

工作树README包含用户既有154行及此前阶段记录。本轮只追加最终状态段，不覆盖既有内容。现成 `a-task10-readme-selective.patch` 基于上述HEAD版README构造，只在其末尾添加空行与最终状态段。它不含用户154行，也不含本次之前仍未提交的阶段段落；这些保留工作树未暂存。不要执行git add README.md，也不要把整份README写回HEAD版本。

执行者先读补丁并核HEAD未变、index README等于HEAD。先只读预检 `git apply --cached --check <该补丁的绝对路径>`；成功后才在正常授权路径执行 `git apply --cached <该补丁的绝对路径>`。只更新index，工作树不变；若上下文不符则停止核实，不用--reject/--3way或整文件暂存绕过。

## Terra执行顺序（本文件未执行）

1. 核HEAD与清单一致、index为空，核full_file_entries每个文件当前SHA；核产品冻结差异无新改动、明确排除项没有进入清单。
2. 对full_file_entries逐项使用git add -- <明确文件路径>（可按命令长度分批），不使用git add -A或目录级add；README仅按上述补丁处理。清单自身的自指纹为null，仅其文件路径加入，避免自哈希循环。
3. 只读核cached --name-only与完整清单加README严格一致；核cached diff的README只有最终段、asset/私有配置/任务外文件均无；核工作树原内容完整。可读git show :README.md验证index视图，不能以工作树diff替代。
4. 在不修改冻结产品的前提下复用已通过测试/构建及最终审计，不为文档重复全部测试。完成必要的文档/链接/敏感值及暂存范围核对后，以新普通本地commit提交；不amend、不推送、不部署。
5. 实际提交成功后读取真实SHA，再更新Task10账本/README交付状态；不得在提交前虚构SHA/DONE或提前启动Task11。状态追记可作为单独明确文档提交，保留首次交付commit引用；不amend共享HEAD。Task13仍未完成。

如平台故障阻挡，遵守同动作最多一次重试，第二次仍失败即停止Git写入并报告；本准备文件不证明审批通道已执行或可用。