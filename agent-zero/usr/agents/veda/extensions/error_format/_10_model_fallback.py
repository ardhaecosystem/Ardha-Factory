import json
import os
from datetime import datetime, timezone
from python.helpers.extension import Extension

AUDIT_DIR = "/a0/usr/veda-state/audit"

# Error patterns that indicate model/API failure
MODEL_FAILURE_PATTERNS = [
    "timeout",
    "timed out",
    "rate limit",
    "ratelimit",
    "too many requests",
    "service unavailable",
    "503",
    "502",
    "connection error",
    "connection refused",
    "api error",
    "model not found",
    "invalid model",
    "context length exceeded",
    "maximum context",
    "overloaded",
    "capacity",
]

VEDA_STATE_DIR = "/a0/usr/veda-state"
FALLBACK_STATE_FILE = os.path.join(VEDA_STATE_DIR, "model_fallback_state.json")


class VedaModelFallback(Extension):
    """
    Fired at error_format — when the agent encounters an error during monologue.
    Detects model/API failure patterns and injects a structured fallback instruction.

    Fallback chain:
    1. Primary model failure detected
    2. Increment failure counter in fallback_state.json
    3. Inject fallback instruction into error message
    4. Suggest switching to utility model or escalating to Veda

    This is advisory — Veda reads the enriched error and decides the response.
    Actual model switching requires Veda to update settings via the UI or API.

    The fallback state persists across monologue iterations so Veda can track
    repeated failures and take action (e.g. switch model, pause pipeline).
    """

    async def execute(self, msg=None, **kwargs) -> None:
        if msg is None:
            return

        error_text = str(msg.get("message", "")).lower()
        if not error_text:
            return

        # Check if this looks like a model/API failure
        matched_pattern = None
        for pattern in MODEL_FAILURE_PATTERNS:
            if pattern in error_text:
                matched_pattern = pattern
                break

        if not matched_pattern:
            return

        agent_name = getattr(self.agent, "agent_name", "unknown")
        profile = getattr(self.agent.config, "profile", "unknown")
        current_spec = self.agent.get_data("current_spec_id") or "none"
        primary_model = getattr(self.agent.config.chat_model, "name", "unknown")
        utility_model = getattr(self.agent.config.utility_model, "name", "unknown")

        # Load and update fallback state
        state = self._load_fallback_state()
        agent_key = f"{agent_name}:{profile}"
        if agent_key not in state:
            state[agent_key] = {"failure_count": 0, "last_failure": None, "pattern": None}
        state[agent_key]["failure_count"] += 1
        state[agent_key]["last_failure"] = datetime.now(timezone.utc).isoformat()
        state[agent_key]["pattern"] = matched_pattern
        self._save_fallback_state(state)

        failure_count = state[agent_key]["failure_count"]

        # Build fallback instruction based on failure count
        if failure_count == 1:
            fallback_instruction = (
                f"\n[MODEL FAILURE DETECTED] Pattern: '{matched_pattern}'\n"
                f"Primary model '{primary_model}' may be unavailable.\n"
                f"FALLBACK CHAIN — Step 1: Retry the same request once.\n"
                f"If retry fails, escalate to Veda with this error."
            )
        elif failure_count == 2:
            fallback_instruction = (
                f"\n[MODEL FAILURE — 2nd occurrence] Pattern: '{matched_pattern}'\n"
                f"Primary model '{primary_model}' is likely unavailable.\n"
                f"FALLBACK CHAIN — Step 2: Escalate to Veda immediately.\n"
                f"Report: model={primary_model}, failures={failure_count}, "
                f"spec={current_spec}, pattern={matched_pattern}\n"
                f"Veda will assess whether to switch to utility model '{utility_model}' "
                f"or pause the pipeline."
            )
        else:
            fallback_instruction = (
                f"\n[MODEL FAILURE — CRITICAL: {failure_count} failures] "
                f"Pattern: '{matched_pattern}'\n"
                f"PRIMARY MODEL REPEATEDLY UNAVAILABLE: {primary_model}\n"
                f"FALLBACK CHAIN — Step 3: Hard escalation to Veda.\n"
                f"Pipeline for Spec '{current_spec}' should be PAUSED.\n"
                f"Veda must intervene and inform papa of the model outage."
            )

        # Inject into error message
        msg["message"] = msg.get("message", "") + fallback_instruction

        print(
            f"[Veda:ModelFallback] FAILURE #{failure_count}: agent={agent_name} "
            f"pattern='{matched_pattern}' model={primary_model}"
        )

        # Audit the failure
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            audit_file = os.path.join(AUDIT_DIR, f"{date_str}.audit.jsonl")
            entry = {
                "timestamp": now.isoformat(),
                "event_type": "model_failure_detected",
                "agent_name": agent_name,
                "agent_number": self.agent.number,
                "profile": profile,
                "spec_id": current_spec,
                "primary_model": primary_model,
                "utility_model": utility_model,
                "failure_count": failure_count,
                "pattern_matched": matched_pattern,
            }
            with open(audit_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[Veda:ModelFallback] WARN: Audit write failed: {e}")

    def _load_fallback_state(self) -> dict:
        if not os.path.exists(FALLBACK_STATE_FILE):
            return {}
        try:
            with open(FALLBACK_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_fallback_state(self, state: dict) -> None:
        try:
            os.makedirs(VEDA_STATE_DIR, exist_ok=True)
            with open(FALLBACK_STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            print(f"[Veda:ModelFallback] WARN: Could not save fallback state: {e}")
