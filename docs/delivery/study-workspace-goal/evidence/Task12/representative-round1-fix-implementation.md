# Task12 代表性首轮修复实施交接

## 状态与边界

实施范围为已审 PASS 的 `representative-round1-fix-plan.md`（SHA256 `F55DEC17511648F07E956166ECA8954D614AC148744E3C05648E0A891185460C`）；HEAD 基线 `a6117c48c1ff7e8877806d0862e69ff0e42f13f4`。修复前已有 25 项首轮真实结果 22 通过、3 失败；此处没有伪造新的 RED。独立 OCR 和正式浏览器复验尚未执行，不能宣称布局缺口或三个代表链已通过。

Chat 仅加静态 class 和标题 tabIndex；侧栏新增可滚动的顶部区域，列表与账号 footer 为兄弟；CSS 对标题、侧栏、消息换行、代码块、输入及账号菜单作局部约束。M2 区分离开后重新进入焦点，M4 两处关闭定位精确匹配；M3 保留原样本并添加真实区域、命中、滚动、代码块以及同态锚定断言。未更改 hooks/ref、消息、恢复及教学算法。

## 验证（进程终态）

- `npm.cmd --prefix web test -- --run src/pages/Chat.test.tsx src/components/workspace/WorkspaceLayout.test.tsx`：退出 0，2 文件、301 测试通过；见 `representative-round1-fix-target.log`。
- `npm.cmd --prefix web test`：退出 0，16 文件、426 测试通过；见 `representative-round1-fix-web-test.log`。
- `npm.cmd --prefix web run build`：最终退出 0；见 `representative-round1-fix-build-final.log`。
- `npm.cmd --prefix web run e2e -- --list`：退出 0，收集 25 项；见 `representative-round1-fix-collect.log`。这仅收集测试，未运行浏览器功能。
- 本轮未新增依赖，独立 E2E TypeScript 检查沿用之前记录的 Node 类型限制，未宣称通过。受控双倍字体不是原生浏览器缩放。

## 本轮改变的文件：SHA256

| 路径 | 前 | 后 |
|---|---|---|
| `web/e2e/workspace-layout.spec.ts` | `294B268A46EDC19726D04DEF3C2E46E38A72757E56BEB836C477205DD1BB87E0` | `9F26C8C60C00941E62A67BFB80AB0795F99819751E84A7AAE7AD933E7E0CD652` |
| `web/src/index.css` | `3FFB098D423A77E2621B715B17E98F427C6537CC7C769448B3E47E530E0C191E` | `6962089ED491BD4A07433423B92C1FE531D986F0C7D0194BE72D302876C46884` |
| `web/src/pages/Chat.tsx` | `18DA362010833A963F96D95C8D17B5C494D57D750ECC19A148A44EDB93AB1018` | `51E84FF4FD50A56B04D3C020BE54282184F0B4B36A18380CE0D215181377F2F4` |
| `web/src/components/workspace/SessionSidebar.tsx` | `4578490D2EE376995EB402AD3A4FF00C8A7216803C28351F4D628F0B2153870C` | `DA327ED887FB090501209360D1613E8ECCD2BEFF6619A167C978569E7A3871F5` |

冻结清单共 20 项；另 16 项前后 SHA256 相同：
- `web/package-lock.json`：`E7CE02A042A9B0CE8F962A95EB777258D86889BC39FDD0E38CE7FF686321AEBB`
- `web/package.json`：`DC9DB132D15BDBC0A9B339BFE3B143EFD285B092829A40F0842227DAC1EF35E7`
- `web/playwright.config.ts`：`9C03B46A8CB2968F53DBC56358199853DA99E943F0F8D52CBB757393A695793E`
- `web/src/components/profile/FloatingProfile.test.tsx`：`E9E3375884371ACCF50B331D79F05D52D28E4AFC95737CC0178E74D91E33DD2D`
- `web/src/components/profile/FloatingProfile.tsx`：`EEA5AC731E93509956ADA2E041058F99F7FFE2F9A44997EE9776130475323E26`
- `web/src/components/profile/ProfileSummaryCard.test.tsx`：`29B006F3EB76A19227108F5B872B5BBB83CF87EBB20BEB22C08E1B1BDCA7F0F8`
- `web/src/components/profile/ProfileSummaryCard.tsx`：`9E5B3DD6503422AA6F5EEF18FA9F4572BD8179D5D44300FE4F7BD930D8510B8D`
- `web/src/components/workspace/WorkspaceLayout.test.tsx`：`EB7A69E714461295BD6F553B4966813F831F73A4926FE2D2D5F6BA46341539BB`
- `web/src/components/workspace/WorkspaceLayout.tsx`：`91938A21ECC0A9AD8F10791CEE9F33A07C159749E0B22F966CC026CBF9F55CF8`
- `web/src/hooks/useFloatingProfile.test.ts`：`FB13F79D2593D863AB25857B558A140238223F8EBCDFD1D2C4EC39828606CCA7`
- `web/src/hooks/useFloatingProfile.ts`：`5B102104D093044CCDC8F287132726BD16DD9C4E061882E5C7C1B1F926ED5668`
- `web/src/pages/Chat.test.tsx`：`FC8E1BFE963C06B1D0783ECE34214D4058026D557B800C6F653805F5E207EAF5`
- `web/src/store/workspace.test.ts`：`CD2DE4F76A17D156B35398AF7D637E97C3210DEE3BEE9C51740E1A3B2E8CA0FF`
- `web/src/store/workspace.ts`：`CC346518CC85313DB2A7B103728C533D48524796A285E873A5A76F9A3ADFB761`
- `web/src/store/workspaceController.ts`：`70B4E02227C09A3FB7B7415FD2307B391B216F1B089A0E6E3CB2BEB71C23B6C1`
- `web/vite.config.ts`：`392843735B4FCC7265E8493D2931AFCA2356E852D785E562A9BF694FCF8C2BD2`

前后全文以 `representative-round1-fix-before-*.txt`、`representative-round1-fix-after-*.txt` 保存；四份 `representative-round1-fix-increment-*.diff` 为本轮精确增量；`representative-round1-fix-hash-check.json` 保存全部核对。原工作区已有修改保留，修改前 HEAD 差异见 `representative-round1-fix-before-git.diff`；未 stage/commit。README 与状态账本由主会话维护。

## 待主会话处理

对四个改动文件和新增验收断言执行独立 OCR 增量审阅；通过后再按计划在隔离环境运行 25 项至终态并保留实际截图和观测。不得把此次静态测试、受控数据或收集数量当作真实浏览器行为通过；Task12 仍为进行中，Task13 与 L1–L4 限制不变。
