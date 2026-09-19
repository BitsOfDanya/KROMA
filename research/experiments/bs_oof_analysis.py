import json
import sys

import numpy as np
from bs_train import calibrate, evaluators, raw_chips, score
from kroma_ml.af_split import group_key
from kroma_ml.bs_data import load_meta
from sklearn.model_selection import GroupKFold

RUNS = sys.argv[1:] or ["cv_ndvi", "cv_dual"]
meta = load_meta()
ids = meta["chip_id"].to_numpy()
folds = [ids[va].tolist() for _, va in GroupKFold(3).split(ids, groups=group_key(meta).to_numpy())]
raws = raw_chips(list(ids))


def load(run):
    out = {}
    for k in (1, 2, 3):
        d = np.load(f"/tmp/bs_oof/{run}_f{k}.npz")
        for cid, lg in zip(d["ids"], d["logits"], strict=True):
            out[str(cid)] = lg
    return out


oof = {r: load(r) for r in RUNS}
order = [c for f in folds for c in f]
trues = [raws[c].mask.astype(np.int64) for c in order]
evals = evaluators([raws[c] for c in order])
fold_of = {c: i for i, f in enumerate(folds) for c in f}


def blend(weights):
    for c in order:
        yield sum(w * oof[r][c].astype(np.float32) for r, w in zip(RUNS, weights, strict=True))


result = {}
candidates = {r: [1.0 if r == q else 0.0 for q in RUNS] for r in RUNS}
if len(RUNS) == 2:
    candidates["blend50"] = [0.5, 0.5]
for name, w in candidates.items():
    logits = list(blend(w))
    entry = {}
    for ev, valids in evals.items():
        raw = score(logits, trues, valids, np.zeros(4))
        entry[ev] = {"pooled_raw": raw}
    logits_by_fold = [
        [lg for lg, c in zip(logits, order, strict=True) if fold_of[c] == k] for k in range(3)
    ]
    for ev, valids in evals.items():
        per = []
        for k in range(3):
            idx = [i for i, c in enumerate(order) if fold_of[c] == k]
            per.append(
                score(
                    [logits[i] for i in idx],
                    [trues[i] for i in idx],
                    [valids[i] for i in idx],
                    np.zeros(4),
                )["bs_score"]
            )
        entry[ev]["fold_raw_bs"] = per
    bias = calibrate(
        [lg[:, ::2, ::2] for lg in logits],
        [t[::2, ::2] for t in trues],
        [v[::2, ::2] for v in evals["all_valid_mask"]],
    )
    entry["global_bias_all_valid"] = bias.tolist()
    for ev, valids in evals.items():
        entry[ev]["pooled_global_cal"] = score(logits, trues, valids, bias)
    result[name] = entry
    a, s = entry["all_valid_mask"], entry["strict_mask"]
    rounded = [round(float(x), 2) for x in bias]
    folds_all = [round(x, 4) for x in a["fold_raw_bs"]]
    print(
        f"{name} all raw {a['pooled_raw']['bs_score']:.4f} "
        f"cal {a['pooled_global_cal']['bs_score']:.4f} | "
        f"strict raw {s['pooled_raw']['bs_score']:.4f} "
        f"cal {s['pooled_global_cal']['bs_score']:.4f} | bias {rounded} | folds {folds_all}",
        flush=True,
    )
json.dump(result, open("research/experiments/bs_oof_analysis.json", "w"), indent=2)
