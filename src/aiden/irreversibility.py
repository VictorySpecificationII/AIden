"""Guardedness: before AIden changes anything, can it be undone?

The first construct of the reasoning engine, from the user's "Engineering Note on
Irreversibility". Code, not a model, makes the call:

- Rule 1, never enter a state without an exit vector: every action is assessed for
  its exit (the A.1 test): what reverses it, who can trigger that, which signals demand
  it, and what degrades with waiting. An action with no known exit is refused: "if you
  cannot write these in plain sentences, you do not have an exit, you have hope".
- Rule 2, prefer gradients over cliffs: an action is a *gradient* (it can be walked back),
  a *cliff* (the previous state can't be reached again, or only by a path AIden can't take
  alone), or has *no exit*.
- Rule 4, if you cannot simulate rollback, don't commit: the exit is checked against the
  steward's current state (the model to return to is on disk and known), not assumed.
- B.2, small reversible steps can compose into an irreversible path: a second switch takes
  the protection off the model the first switch kept. If that model couldn't be fetched
  again, that is a cliff.
- A.3, the two-person rule: a cliff is never crossed by AIden alone. It is recorded as
  needing the user, who owns that exit.

Assessments are recorded as experience (kind "guard"), so the reflection and the user can
see AIden being careful, or not.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

import experience

logger = logging.getLogger("aiden.irreversibility")
api = APIRouter()

GRADIENT, CLIFF, NO_EXIT = "gradient", "cliff", "no exit"


def refetchable(model: Optional[Dict[str, Any]], limits: Dict[str, Any]) -> bool:
    """Could the steward fetch this model again? (Its source is in the allowed organisation.)"""
    source = (model or {}).get("source") or ""
    return bool(source) and source.split("/")[0] == limits.get("org")


def exit_vector(reverse: str, who: str, signals: List[str], degrades: str) -> Dict[str, Any]:
    return {"reverse": reverse, "who": who, "signals": signals, "degrades": degrades}


def assess(action: str, args: Dict[str, Any], state: Dict[str, Any], rollback_window_h: float = 24) -> Dict[str, Any]:
    """The verdict on one action against the steward's state: gradient, cliff or no exit,
    with its exit vector and what would be lost."""
    devices, models, limits = state.get("devices", {}), state.get("models", {}), state.get("limits", {})
    device, name = args.get("device"), args.get("name")
    slots = devices.get(device, {})
    result: Dict[str, Any] = {"action": action, "args": args, "loses": [], "problems": []}

    if action in ("pull", "trial", "end_trial"):
        result.update(verdict=GRADIENT, exit=exit_vector(
            "end the trial and delete the download", "AIden", ["the candidate fails its checks"], "nothing"))
    elif action == "rollback":
        if not slots.get("previous"):
            result["problems"].append("there is no previous model to return to")
        result.update(verdict=GRADIENT if not result["problems"] else NO_EXIT, exit=exit_vector(
            "activate the model that was rolled back from, if it is still on disk", "AIden or the user",
            ["the previous model does worse"], "nothing: a rollback is itself the exit"))
    elif action == "activate":
        active, previous = slots.get("active"), slots.get("previous")
        # Simulate the rollback this switch relies on: back to today's active model
        if slots.get("trial") != name:
            result["problems"].append(f"{name} is not loaded on trial on the {device}")
        if not active or active not in models:
            result["problems"].append("the model to roll back to is not known to the steward")
        if previous and previous != active:
            # B.2: the model kept from the last switch loses its protection
            result["loses"].append(f"{previous} stops being the protected rollback model")
            if not refetchable(models.get(previous), limits) and not (models.get(previous) or {}).get("adopted"):
                result["problems"].append(f"{previous} could be deleted and couldn't be fetched again")
        cliff = any("couldn't be fetched" in p for p in result["problems"])
        result.update(verdict=CLIFF if cliff else (NO_EXIT if result["problems"] else GRADIENT), exit=exit_vector(
            f"roll back to {active}", "AIden on its own (failed probes, worse quality) or the user",
            ["2 failed probes after the switch", "worse ratings, more unsure answers or fallbacks"],
            f"AIden rolls back on its own only within {rollback_window_h:.0f} hours; later it needs a new trial"))
    elif action == "delete":
        model = models.get(name)
        if not model:
            result["problems"].append(f"no model {name}")
        elif model.get("adopted"):
            result["problems"].append(f"{name} was adopted (found already in place, not downloaded by the steward, which never deletes it)")
        elif not refetchable(model, limits):
            result["problems"].append(f"{name} couldn't be fetched again")
        in_use = {n for s in devices.values() for n in s.values() if isinstance(n, str)}
        if name in in_use:
            result["problems"].append(f"{name} is in use")
        size = (model or {}).get("size_gb")
        result.update(verdict=GRADIENT if not result["problems"] else CLIFF, exit=exit_vector(
            f"fetch {(model or {}).get('source', name)} again" + (f" ({size:.1f} GB)" if size else ""), "AIden or the user",
            ["the model is wanted again"], "nothing, as long as the source stays published"))
    else:
        result.update(verdict=NO_EXIT, exit=None, problems=[f"no known way to undo '{action}'"])
    return result


def check(action: str, args: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assess with the steward's current state and record it; proceed only on a gradient."""
    import models
    state = state if state is not None else (models.state(max_age_s=0) or {})
    result = assess(action, args, state, models.ROLLBACK_WINDOW_S / 3600)
    result["proceed"] = result["verdict"] == GRADIENT
    if not result["proceed"]:
        result["needs"] = "the user" if result["verdict"] == CLIFF else "an exit"  # A.3: the user owns a cliff's exit
        logger.warning("Not doing %s %s: %s (%s)", action, args, result["verdict"], "; ".join(result["problems"]))
    if action in ("activate", "delete") or not result["proceed"]:
        experience.record("guard", result)
    return result


@api.get("/guard/assess", summary="Could this model action be undone? (gradient, cliff or no exit; changes nothing)")
def assess_endpoint(action: str, device: str = "", name: str = ""):
    import models
    args = {k: v for k, v in {"device": device, "name": name}.items() if v}
    return assess(action, args, models.state(max_age_s=0) or {}, models.ROLLBACK_WINDOW_S / 3600)
