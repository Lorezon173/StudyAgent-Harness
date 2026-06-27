# pytest-asyncio strict 模式静默 skip 陷阱

> 最后更新：2026-06-10

记录一个「测试看着全绿、实际整批没跑」的隐蔽陷阱：装了 pytest-asyncio 但没配 `asyncio_mode`，`async def` 测试被静默 skip。来源：存储底座实施计划 review 时，发现计划拟用的 async fixture 范式与全项目现存范式冲突。

## 目录

- [Q1: 装了 pytest-asyncio，async def 测试为什么被静默跳过（假绿）？](#q1-装了-pytest-asyncioasync-def-测试为什么被静默跳过假绿)

---

## Q1: 装了 pytest-asyncio，async def 测试为什么被静默跳过（假绿）？

**日期**：2026-06-10

**问题**：

`pyproject.toml` 里有 `pytest-asyncio>=0.24.0`，于是直接写：

```python
async def test_something():
    result = await store.add(...)
    assert result == 1
```

`pytest` 跑完显示 passed，但断言其实**一次都没执行**——把 assert 改成必失败也照样"绿"。为什么？

**回答**：

**根因——pytest-asyncio 默认 `asyncio_mode = strict`，未显式标记的 async 测试不会被它接管。**

pytest 本身**不会 await 协程**。一个 `async def test_*` 函数被调用时只返回一个 coroutine 对象，pytest 拿到这个"返回值非 None / 非测试结果"的对象，**既不 await、也不报错**，测试体内的 `await` 和 `assert` 全部没运行。需要 pytest-asyncio 这类插件把 coroutine 跑起来。

而 pytest-asyncio 有三种 `asyncio_mode`：

| mode | 行为 | 未标记的 async 测试 |
|---|---|---|
| `strict`（**默认**） | 只接管带 `@pytest.mark.asyncio` 的测试 | **不接管 → 静默跳过/告警，常被忽略 → 假绿** |
| `auto` | 自动接管所有 `async def test_*` | 正常运行 |
| `legacy`（旧版，渐废弃） | 类 auto，带 deprecation 警告 | 运行 |

没配 `asyncio_mode`（pyproject/pytest.ini/setup.cfg 都没写）就是 strict。此时裸写 `async def test_*` 不加 mark：新版 pytest-asyncio 会发一条 warning 然后 **skip**，warning 淹在输出里极易被当成绿。

**两条修复路线**：

1. **启用 auto 模式**（想用原生 `async def test`）：

   ```toml
   # pyproject.toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   ```

   代价：这是**全局**配置，会改变该仓库所有 async 测试的接管方式——若项目里已有大量用 `asyncio.run()` 手动跑的 async 测试，需回归确认它们不被双重驱动或冲突。

2. **不依赖插件接管，手动跑协程**（最省事、零全局影响）：

   ```python
   def test_something():            # 注意是普通 def
       async def _test():
           result = await store.add(...)
           assert result == 1
       asyncio.run(_test())
   ```

   把 async 逻辑包进内层 `async def _test()`，外层同步测试用 `asyncio.run(_test())` 驱动。pytest 看到的是普通同步函数，正常执行、断言生效，**完全不碰 pytest-asyncio 的 mode**。

**怎么选**：

- 项目**已统一**用某种范式 → **跟现状**。如全项目都是 `asyncio.run(_test())` / `run_until_complete`、零 `@pytest.mark.asyncio`，新测试就照抄路线 2，别为了"现代写法"去动全局 `asyncio_mode`——一改就波及存量所有 async 测试，回归面巨大。
- 新项目 / 没有历史包袱 → 直接配 `asyncio_mode = "auto"`（路线 1），写法最干净。

**如何识别"假绿"**：

- 把某条 async 测试的 assert **故意改成必失败**（`assert False`），重跑——若仍"passed"，说明该测试根本没被执行。
- 看 pytest 输出里的 **skipped 数 / warnings 段**，搜 `async def functions are not natively supported` 一类告警。
- 看 `-rsx` 报告（显示 skip 原因）。

**怀疑链 / 边界**：

- 这是 **pytest-asyncio 特有**的 mode 机制；用 `anyio` 插件的 `anyio_mode`、或 `aiohttp` 的 test utils 行为不同，别套用。
- `asyncio.run()` 路线每条测试起一个**新事件循环**，若测试间要共享 loop / 共享连接（如 `:memory:` SQLite 跨 loop）需另行处理；多数单测无此需求。
- 同步驱动协程还有 `loop.run_until_complete()`（旧范式），但 `asyncio.get_event_loop()` 在新 Python 里对"无运行 loop"已告警/将废弃，新代码优先 `asyncio.run()`。
