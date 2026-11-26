"""All tunables, including the OPEN DECISIONS of DESIGN.md section 4 (numbered as there)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    risk_display: str = "verbal_scaled"  # 1  (consumed by M2 confirmations)
    chain_actions_cost_separate_turns: bool = True  # 2  each chained action advances the clock 1 tick
    death_mode: str = "penalty"  # 3  "penalty" | "permadeath"
    death_lockout: str = "next_real_day"
    turn_timer_seconds: int = 90  # 4  (M3)
    afk_after_ticks: int = 10  # 5  (M5)
    logout_linger_ticks: int = 30  # 6  (M5)
    look_image_turn_cost: float = 0.5  # 7  (M4)
    gossip_distortion_chance: float = 0.15  # 8  (M3)
    dc_normal: int = 12  # 9
    dc_hard: int = 16
    unarmed_attack_penalty: int = 6  # 10
    unarmed_damage: int = 1
    repeat_dc_step: int = 2  # 11
    repeat_window_ticks: int = 1440
    wanted_severity: dict = field(  # 12
        default_factory=lambda: {"theft": 1, "trespass": 1, "burglary": 2, "assault": 2, "murder": 4})
    ticks_per_day: int = 1440  # 13  1 tick = 1 in-game minute

    # ---- M2 harness
    confirm_irreversible: bool = True  # irreversible verbs need a confirmed second submit (BRIEF §5.5)
    escalate_below: float = 0.8  # decision confidence below this -> ask the LLM (if any); irreversible -> clarify
    clarify_below: float = 0.65  # below this even reversible actions are offered as "Did you mean...?", not run
    risk_xp_steps: tuple = (100, 1000)  # verbal_scaled: xp thresholds for coarse -> fine -> numeric estimates
    llm_model: str = "claude-opus-5-5"  # decision + narration model when an LLM is configured
    llm_effort: str = "low"

    # ---- encounters (BRIEF §7)
    encounters: bool = True  # turn mode after hostile acts; M1 rule tests switch it off to isolate single actions
    npc_flee_below: float = 0.5  # non-guard NPCs flee when hp/max_hp is at or below this
