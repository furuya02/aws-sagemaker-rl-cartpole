"""SageMaker PyTorch inference handler for Stable-Baselines3 PPO model."""
import json
import os
from typing import Any

import numpy as np
from stable_baselines3 import PPO


def model_fn(model_dir: str) -> PPO:
    model_path: str = os.path.join(model_dir, "cartpole_ppo.zip")
    return PPO.load(model_path)


def input_fn(request_body: str, content_type: str = "application/json") -> np.ndarray:
    payload: dict[str, Any] = json.loads(request_body)
    return np.array(payload["observation"], dtype=np.float32)


def predict_fn(observation: np.ndarray, ppo_model: PPO) -> dict[str, Any]:
    action, _states = ppo_model.predict(observation, deterministic=True)
    return {"action": int(action)}


def output_fn(prediction: dict[str, Any], accept: str = "application/json") -> str:
    return json.dumps(prediction)
