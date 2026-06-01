from dataclasses import dataclass

from app.harness.enums import TeachingMode, ActionKind, MasteryLevel


@dataclass
class ObservationSet:
    """回合屏障后送入 Policy 的完整观察集（§3.5.3）。"""
    mastery: MasteryLevel | None = None
    confusion: bool = False
    contradiction: bool = False
    prereq_weak: bool = False
    prereq_basis: str | None = None      # "historical" | "observed"
    rag_quality_low: bool = False
    repeat_count: int = 0
    topic_complete: bool = False
    turn_over_limit: bool = False        # turn > MAX_TURNS（熔断）


class TeachingPolicy:
    """§4.2 完整状态转移表 + 历史记录。

    next(obs) → (target_mode, action) —— 纯函数化的状态机：根据当前模式与
    完整观察集裁决唯一目标模式与触发动作。历史供 §5 评估「模式切换合理性」。
    """

    MAX_REPEAT = 2

    def __init__(self, initial: TeachingMode = TeachingMode.SOCRATIC):
        self.current_mode: TeachingMode = initial
        self.history: list[TeachingMode] = [initial]

    def next(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        target, action = self._decide(obs)
        if target != self.current_mode:
            self.current_mode = target
            self.history.append(target)
        return target, action

    def _decide(self, obs: ObservationSet) -> tuple[TeachingMode, ActionKind]:
        if obs.turn_over_limit:
            return self.current_mode, ActionKind.LOOP_EXIT

        # 全局优先级（§2.4 / §3.4）：前置缺失 observed > contradiction >
        # confusion > mastery weak/partial/mastered
        if obs.prereq_weak and obs.prereq_basis == "observed":
            return TeachingMode.REGRESS, ActionKind.REGRESS_TO_PREREQ
        if obs.contradiction:
            return self.current_mode, ActionKind.TUTOR_CORRECT
        if obs.prereq_weak and obs.prereq_basis == "historical":
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_PROBE_PREREQ

        if self.current_mode == TeachingMode.SOCRATIC:
            return self._from_socratic(obs)
        if self.current_mode == TeachingMode.FEYNMAN:
            return self._from_feynman(obs)
        if self.current_mode == TeachingMode.ANALOGY:
            return self._from_analogy(obs)
        if self.current_mode == TeachingMode.REGRESS:
            return self._from_regress(obs)
        return self.current_mode, ActionKind.TUTOR_ASK

    def _from_socratic(self, obs):
        if obs.mastery == MasteryLevel.MASTERED and obs.topic_complete:
            return self.current_mode, ActionKind.LOOP_EXIT
        if obs.confusion:
            return TeachingMode.ANALOGY, ActionKind.TUTOR_OFFER_ANALOGY
        if obs.mastery == MasteryLevel.PARTIAL:
            return TeachingMode.FEYNMAN, ActionKind.TUTOR_REQUEST_RECAP
        if obs.mastery == MasteryLevel.WEAK and obs.repeat_count < self.MAX_REPEAT:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_RE_EXPLAIN
        return self.current_mode, ActionKind.TUTOR_ASK

    def _from_feynman(self, obs):
        if obs.mastery == MasteryLevel.MASTERED:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        if obs.confusion:
            return TeachingMode.ANALOGY, ActionKind.TUTOR_OFFER_ANALOGY
        if obs.mastery == MasteryLevel.WEAK:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_RE_EXPLAIN
        return self.current_mode, ActionKind.TUTOR_REQUEST_RECAP

    def _from_analogy(self, obs):
        if obs.mastery in (MasteryLevel.PARTIAL, MasteryLevel.MASTERED):
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        if obs.mastery == MasteryLevel.WEAK:
            return TeachingMode.REGRESS, ActionKind.REGRESS_TO_PREREQ
        return self.current_mode, ActionKind.TUTOR_OFFER_ANALOGY

    def _from_regress(self, obs):
        if obs.mastery == MasteryLevel.MASTERED:
            return TeachingMode.SOCRATIC, ActionKind.TUTOR_ASK
        return self.current_mode, ActionKind.REGRESS_TO_PREREQ
