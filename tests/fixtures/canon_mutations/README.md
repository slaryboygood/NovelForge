# canon_mutations fixtures

C11 的 fault injection 语料**不使用巨型 JSON fixture**：
40 个 mutation 全部由 `src/novelforge/story_engine/canon/mutation.py`
里的 builders（`_seed_gate_fact` / `_chapter` / `_beat` / `_intent` 等）现场构造最小错误图。

- 单元 mutation：`tests/test_canon_mutation_unit.py`
- 集成 / P0 mutation：`tests/test_canon_mutation_integration.py`
- 真实执行结果：`docs/CANON_DEFENSE_COVERAGE_MATRIX.md`（由
  `python -m novelforge.story_engine.canon.mutation --output docs/CANON_DEFENSE_COVERAGE_MATRIX.md` 生成）

因此本目录只保留约定说明，不放实例数据。
