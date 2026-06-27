# SQLAlchemy + SQLite 持久化陷阱

> 最后更新：2026-06-09

记录在 SQLAlchemy ORM + SQLite/PG 双模式下，**时间字段**两个隐蔽且「在 PG 上测不出、切 SQLite 才暴露」的陷阱。来源：存储底座 spec 的源码核验 review（updated_at 排序失真 / 历史消息顺序错乱）。

## 目录

- [Q1: onupdate=func.now() 的 updated_at 为什么有时不刷新？](#q1-onupdatefuncnow-的-updated_at-为什么有时不刷新)
- [Q2: SQLite 下按 created_at 排序，为什么同一时刻插入的多行顺序会乱？](#q2-sqlite-下按-created_at-排序为什么同一时刻插入的多行顺序会乱)

---

## Q1: onupdate=func.now() 的 updated_at 为什么有时不刷新？

**日期**：2026-06-09

**问题**：

模型这样定义，期望每次 UPDATE 自动刷新 `updated_at`：

```python
class SessionTable(Base):
    state_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

upsert 逻辑里每轮都 `row.state_json = json.dumps(state); await db.commit()`。但实测发现：当 `state` 恒为 `{}` 时，多轮 commit 后 `updated_at` **一直停在首次创建时间**，导致「按 updated_at 倒序」的最近活跃列表排序失真。

**回答**：

**根因——`onupdate` 只在真正 emit UPDATE 语句时才求值。**

SQLAlchemy 的 `Column(onupdate=...)` 是 **ORM/client 端**的 update 默认值（注意：它**不是** DB 端的 `ON UPDATE` 子句）。它的求值时机绑定在「unit of work 为这一行生成了一条 UPDATE 语句」上：

- flush 时，SQLAlchemy 比较每个映射列的当前值与已加载值（committed value）。
- 赋一个**等于原值**的新值（`"{}"` → `"{}"`），该列被判定为**无净变化**，不进入 UPDATE 的 SET 子句。
- 若该行**所有**列都无净变化 → SQLAlchemy **根本不发出 UPDATE 语句** → `onupdate` 不被求值 → `updated_at` 纹丝不动。

所以这不是「可能」，而是「当一轮里没有任何列产生真实变化时，**必定**不刷新」。`state_json` 恒为 `{}`、`user_id` 不变，正好命中。

**对策（按推荐度）**：

1. **在 UPDATE 路径显式赋值，不依赖 onupdate**（最稳）：

   ```python
   row.state_json = json.dumps(state)
   row.updated_at = func.now()   # 赋 SQL 函数表达式，无法在 client 端比较相等 → 必然进入 SET → 必发 UPDATE
   ```

   赋 `func.now()`（ClauseElement）或 `datetime.utcnow()`（每次都不同的标量）都能强制该列变 dirty，从而保证 emit UPDATE。

2. **改排序数据源，绕开「父行不变」**：若只是要「最近活跃」排序，可用关联子表的 `MAX(child.id)` / `MAX(child.created_at)`（如每轮都新增的 messages 行），而不依赖父 session 行的 updated_at。

3. （不推荐）确保每轮确有列变化——不可控，且把「排序正确性」耦合到「业务字段恰好会变」上，脆弱。

**如何确认/复现**：

- 开 `create_async_engine(..., echo=True)`，看 commit 时**有没有打印 `UPDATE` 语句**——没打印就是被 skip 了。
- 写回归单测：同一行连续 commit 两次（中间不改任何列值），断言 `updated_at` **不变**即复现；加上对策 1 后断言它推进。

**怀疑链 / 边界**：

- 这是 **ORM unit-of-work 的 dirty 检测**行为，与「DB 层是否支持 `ON UPDATE`」无关；用裸 SQL `UPDATE ... SET ...` 显式写 `updated_at` 不受此影响。
- `server_default=func.now()` 只管 **INSERT** 默认值，与 UPDATE 刷新是两码事，别把它当成「更新也会自动填」。
- 该行为与方言无关（PG/SQLite 都如此），但**后果**常在「state 列恒定」这类场景才显现。

---

## Q2: SQLite 下按 created_at 排序，为什么同一时刻插入的多行顺序会乱？

**日期**：2026-06-09

**问题**：

同一会话同一轮顺序插入两条消息（user、assistant），`list_by_session` 用 `ORDER BY created_at ASC` 返回，期望 user 在前。但偶发 assistant 排到了 user 前面，对话历史顺序错乱。字段定义：

```python
created_at = Column(DateTime, server_default=func.now())
```

**回答**：

**根因——SQLite 的 `CURRENT_TIMESTAMP` 是秒级精度，同一秒内多行时间戳完全相同。**

`func.now()` 在 SQLite 上编译为 `CURRENT_TIMESTAMP`，格式 `YYYY-MM-DD HH:MM:SS`，**无小数秒**。同一轮里两条消息在毫秒内连续 INSERT，`created_at` 取到**完全一样**的值。此时 `ORDER BY created_at` 是**不稳定排序**——时间相同的行，返回顺序由实现决定，不保证等于插入顺序。

**对照（这是个「双模式」陷阱：换库才暴露）**：

| 维度 | SQLite | PostgreSQL |
|---|---|---|
| `func.now()` 编译为 | `CURRENT_TIMESTAMP` | `now()` / `CURRENT_TIMESTAMP` |
| 时间精度 | **秒级**（无小数秒） | **微秒级** |
| 同轮两行 created_at | 极可能相同 → 排序乱 | 几乎不会相同 → 不易暴露 |
| 后果 | 开发/测试用 SQLite 复现 | 生产 PG 上「看起来没事」 |

→ 典型「在 PG 上测不出、切 SQLite 才炸」，反过来若只在 SQLite 调通也可能掩盖逻辑缺陷。

**对策**：

- **排序用单调自增主键 `id`**（`autoincrement` 严格按插入顺序单调）：

  ```python
  select(MessageTable).where(...).order_by(MessageTable.id.asc())
  ```

- 若业务上确实想按时间、又要稳定，用**复合排序** `ORDER BY created_at, id`（时间为主，id 兜底稳定）。
- （可选）想保留毫秒时间戳：SQLite 可用 `STRFTIME('%Y-%m-%d %H:%M:%f','now')`，但不如直接用 `id` 简单可靠。

**怀疑链 / 边界**：

- `id` 单调的前提是 autoincrement 自增主键；若用 UUID 等非单调主键，则**不能**用 id 排序，需回到带毫秒的时间列或显式序号列（如 `turn_index` + 行内序）。
- 用 `id`（或 `created_at, id`）排序对 SQLite 和 PG **都安全**，是双模式下更稳的统一做法——别让排序正确性依赖底层时间精度。
- 跨进程/分布式自增（如多写节点）下 id 单调性可能被打破，那是另一个话题；单库 autoincrement 不涉及。
