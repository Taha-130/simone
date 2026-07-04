"""Boucle principale : un persona tente d'accomplir un objectif sur un site."""
from dataclasses import dataclass, field

from .personas import PERSONAS, cognitive_cost


@dataclass
class Step:
    page: str
    monologue: str
    action: str
    target: str = ""
    ok: bool = True
    frictions: list = field(default_factory=list)


@dataclass
class RunResult:
    persona_key: str
    persona_display: str
    goal: str
    success: bool
    steps: list                    # list[Step]
    fail_reason: str = ""
    budget_left: float | None = None

    @property
    def n_steps(self):
        return len(self.steps)


def run_persona(driver, brain, persona_key: str, goal: str,
                start_url: str, success_marker: str, max_steps: int | None = None) -> RunResult:
    persona = PERSONAS[persona_key]
    driver.goto(start_url)
    history, steps = [], []
    budget = persona.confusion_budget
    steps_limit = max_steps or persona.max_steps
    last_sig, repeat_count = None, 0

    for _ in range(steps_limit):
        state = driver.snapshot()

        # condition de succès : le marqueur apparaît dans le titre ou le texte
        if success_marker.lower() in (state.title + " " + state.raw_text).lower():
            return RunResult(persona_key, persona.display, goal, True, steps,
                             budget_left=budget)

        # persona moteur : ne perçoit que les éléments atteignables au clavier
        if persona_key == "moteur":
            reachable_ids = {getattr(n, "node_id", None) for n in driver.keyboard_reachable()} \
                if hasattr(driver, "keyboard_reachable") else set()
            for n in state.nodes:
                if reachable_ids and n.node_id not in reachable_ids:
                    n.focusable = False

        decision = brain.decide(persona, goal, state, history)
        mono = decision.get("monologue", "")
        try:
            idx = int(decision.get("index", -1))
        except (TypeError, ValueError):
            idx = -1
        action = decision.get("action", "give_up")

        step = Step(page=state.title, monologue=mono, action=action)

        if action == "give_up":
            step.ok = False
            steps.append(step)
            return RunResult(persona_key, persona.display, goal, False, steps,
                             fail_reason=decision.get("reason_if_give_up") or mono,
                             budget_left=budget)

        if 0 <= idx < len(state.nodes):
            node = state.nodes[idx]
            step.target = node.label()

            # persona cognitif : payer le coût de friction AVANT d'agir
            if persona_key == "cognitif":
                cost, reasons = cognitive_cost(state, node.name)
                step.frictions = reasons
                budget -= cost
                if budget <= 0:
                    step.ok = False
                    step.monologue += " … C'est trop confus, je laisse tomber."
                    steps.append(step)
                    return RunResult(persona_key, persona.display, goal, False, steps,
                                     fail_reason="budget de confusion épuisé : "
                                                 + " ; ".join(reasons),
                                     budget_left=0)

            prev_url = state.url
            step.ok = driver.act(node, "fill" if action == "fill" else "click",
                                 decision.get("value", ""))
            new_url = driver.snapshot().url if step.ok else prev_url
            page_changed = step.ok and new_url != prev_url
            if action == "fill" and step.ok:
                history.append(f"fill:{node.node_id}")
            if page_changed:
                history.append(f"PAGE->{new_url}")

            sig = (action, node.node_id)
            repeat_count = repeat_count + 1 if step.ok and not page_changed and sig == last_sig else 0
            last_sig = sig if step.ok else None
            if repeat_count >= 2:
                step.ok = False
                step.monologue += " … Je répète la même action sans que rien ne change, j'arrête."
                steps.append(step)
                return RunResult(persona_key, persona.display, goal, False, steps,
                                 fail_reason=f"boucle détectée : « {action} » sur "
                                             f"{step.target} répété sans effet",
                                 budget_left=budget)
        steps.append(step)
        history.append(f"{action} sur {step.target or '?'} -> {'ok' if step.ok else 'échec'}")

    return RunResult(persona_key, persona.display, goal, False, steps,
                     fail_reason="nombre maximal d'étapes atteint sans aboutir",
                     budget_left=budget)
