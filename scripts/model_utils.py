"""
Shared utility for automatic Anthropic model selection and upgrade detection.

Usage in any script:
    client = anthropic.Anthropic(api_key=...)
    model, was_upgraded, prev_model = get_working_model(client)
    # was_upgraded=True means the preferred model was retired and we auto-switched
"""
import json
import os
from typing import Optional

# Ordered preference list — best/most capable first
MODEL_PRIORITY = [
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-sonnet-4-5",
    "claude-haiku-4-5-20251001",
]

CONFIG_FILE = "data/config.json"


def load_config(config_path: str = CONFIG_FILE) -> dict:
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}


def save_config(config: dict, config_path: str = CONFIG_FILE) -> None:
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def get_working_model(
    client,
    config_path: str = CONFIG_FILE,
) -> tuple[str, bool, Optional[str]]:
    """
    Returns (model_id, was_upgraded, previous_model_id).

    Fetches the list of available models from the Anthropic API and selects the
    highest-priority available model. If the currently-preferred model is still
    available, returns it unchanged (was_upgraded=False). If it has been retired,
    picks the next best option, updates config.json, and returns was_upgraded=True.
    """
    config = load_config(config_path)
    preferred = config.get("preferred_model", MODEL_PRIORITY[0])

    try:
        available_ids = {m.id for m in client.models.list()}
    except Exception:
        # Can't reach the models list endpoint — trust the stored config and
        # let the actual API call surface any real errors.
        return preferred, False, None

    if preferred in available_ids:
        return preferred, False, None

    # Preferred model has been retired — find the next best available
    for model in MODEL_PRIORITY:
        if model in available_ids:
            config["preferred_model"] = model
            save_config(config, config_path)
            return model, True, preferred

    # Nothing in our priority list is available — return preferred and let the
    # caller decide how to handle the downstream error.
    return preferred, False, None
