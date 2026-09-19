from pathlib import Path

import joblib
import numpy as np

from kroma_ml.af_data import Chip, load_chip, valid_mask
from kroma_ml.af_features import chip_feature_stack

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[3] / "research" / "experiments" / "af_final_model.joblib"
)


class AFPredictor:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.feature_indices = bundle["feature_indices"]
        self.threshold = float(bundle["threshold"])

    def predict_chip(self, chip: Chip) -> np.ndarray:
        stack = chip_feature_stack(chip)
        valid = valid_mask(chip)
        h, w, c = stack.shape
        flat = stack.reshape(-1, c)[:, self.feature_indices]
        proba = self.model.predict_proba(flat)[:, 1].reshape(h, w)
        mask = (proba >= self.threshold) & valid
        return mask.astype(np.uint8)

    def predict_chip_id(self, chip_id: str, root: str | None = None) -> np.ndarray:
        kwargs = {"with_mask": False}
        if root is not None:
            kwargs["root"] = root
        chip = load_chip(chip_id, **kwargs)
        return self.predict_chip(chip)
