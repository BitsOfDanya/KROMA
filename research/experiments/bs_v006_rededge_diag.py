import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_contour_diag import CROP, GRASS
from bs_v006_prep import V005_OOF
from kroma_ml.bs_cv import valid_mask
from kroma_ml.bs_data import load_chip, load_meta
from kroma_ml.bs_physics import _nd
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v006_rededge_diag.json"
EDGES = np.linspace(-0.6, 0.6, 241)
DLOW_BINS = np.array([-np.inf, 0.0, 0.03, 0.06, 0.1, 0.15, np.inf])
FEATS = ("dB5", "dB6", "dB7", "dNDRE5", "dNDRE6", "dNDRE7", "NDRE7_post", "dnbr")
POPS = ("c1", "bg_burnlike", "v005_fp")


def rededge(chip) -> dict:
    def s(w, b):
        return chip.s2(w, b) / 10000.0

    out = {}
    for b in ("B5", "B6", "B7"):
        out[f"d{b}"] = s("post", b) - s("pre", b)
    for i, b in ((5, "B5"), (6, "B6"), (7, "B7")):
        pre = _nd(s("pre", "B8A"), s("pre", b))
        post = _nd(s("post", "B8A"), s("post", b))
        out[f"dNDRE{i}"] = pre - post
        if i == 7:
            out["NDRE7_post"] = post
    out["dnbr"] = _nd(s("pre", "B8A"), s("pre", "B12")) - _nd(s("post", "B8A"), s("post", "B12"))
    return out


def auc_hist(hp: np.ndarray, hn: np.ndarray) -> float:
    if hp.sum() == 0 or hn.sum() == 0:
        return float("nan")
    pp, pn = hp / hp.sum(), hn / hn.sum()
    below = np.concatenate([[0.0], np.cumsum(pn)[:-1]])
    return float((pp * (below + 0.5 * pn)).sum())


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    slices = ("all", "crop", "grass")
    hist = {
        s: {
            f: {p: np.zeros((len(DLOW_BINS) - 1, len(EDGES) - 1), np.int64) for p in POPS}
            for f in FEATS
        }
        for s in slices
    }
    for cid in load_meta().chip_id:
        chip = load_chip(cid)
        gt = chip.mask.astype(np.int64)
        re = rededge(chip)
        refl_lc = chip.band("landcover")
        lc = group_map(refl_lc, th)
        tmap = threshold_map(refl_lc, th)
        org = organizer_severity(re["dnbr"], tmap)
        d_low = re["dnbr"] - tmap[0]
        scl_pre, scl_post = chip.s2("pre", "SCL"), chip.s2("post", "SCL")
        va = ~np.isin(scl_pre, (0, 1)) & ~np.isin(scl_post, (0, 1))
        v5burn = np.load(V005_OOF / f"{cid}.npz")["burn"]
        pops = {
            "c1": va & (gt == 1),
            "bg_burnlike": va & (gt == 0) & (org >= 1),
            "v005_fp": va & (gt == 0) & v5burn,
        }
        sl = {"all": va, "crop": lc == CROP, "grass": lc == GRASS}
        dbin = np.clip(np.digitize(d_low, DLOW_BINS) - 1, 0, len(DLOW_BINS) - 2)
        for s, smask in sl.items():
            for p, pmask in pops.items():
                m = pmask & smask
                if not m.any():
                    continue
                for f in FEATS:
                    vb = np.clip(
                        np.searchsorted(EDGES, re[f][m], side="right") - 1, 0, len(EDGES) - 2
                    )
                    np.add.at(hist[s][f][p], (dbin[m], vb), 1)
    out = {}
    for s in slices:
        out[s] = {}
        for f in FEATS:
            h = hist[s][f]
            res = {}
            for neg in ("bg_burnlike", "v005_fp"):
                raw_auc = auc_hist(h["c1"].sum(0), h[neg].sum(0))
                w, acc = 0.0, 0.0
                for b in range(len(DLOW_BINS) - 1):
                    a = auc_hist(h["c1"][b], h[neg][b])
                    n = min(h["c1"][b].sum(), h[neg][b].sum())
                    if np.isfinite(a) and n > 100:
                        acc += n * abs(a - 0.5)
                        w += n
                res[f"c1_vs_{neg}_auc"] = round(raw_auc, 4)
                res[f"c1_vs_{neg}_within_dlow_bins_abs_auc_minus_0.5"] = round(acc / max(w, 1), 4)
            out[s][f] = res
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")
    for s in slices:
        for f in FEATS:
            print(s, f, out[s][f])


if __name__ == "__main__":
    main()
