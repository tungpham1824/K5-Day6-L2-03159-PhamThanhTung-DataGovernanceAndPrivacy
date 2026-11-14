import numpy as np
import pandas as pd
from pathlib import Path

D = Path("fixtures/t01_coverage")
DIMS = ["route", "weather", "light", "object"]
cands = pd.read_csv(D / "candidates.csv")
targets = pd.read_csv(D / "targets.csv")
W = targets["weight"].to_numpy(float)

def match(clip, cell):
    """1.0 = khớp chắc, 0.5 = khớp nếu tag unknown hoá ra đúng, 0 = không khớp"""
    unk = False
    for d in DIMS:
        t = cell[d]
        if t == "*":
            continue
        v = clip[d]
        if v == "unknown":
            unk = True
        elif v != t:
            return 0.0
    return 0.5 if unk else 1.0

clips = cands.to_dict("records")
cells = targets.to_dict("records")
M = np.array([[match(c, t) for t in cells] for c in clips])  # 120 x 15

print("=== Mỗi ô có bao nhiêu clip khớp ===")
for j, t in enumerate(cells):
    sure = int((M[:, j] == 1.0).sum())
    maybe = int((M[:, j] == 0.5).sum())
    flag = "  <-- KHÔNG THỂ PHỦ" if sure == 0 and maybe == 0 else (
           "  <-- chỉ có clip nghi ngờ" if sure == 0 else "")
    print(f"{t['cell_id']} w={t['weight']} hard={t['is_hard']}: chắc={sure} nghi_ngờ={maybe}{flag}")

def coverage(idx):
    covered = (M[idx] == 1.0).any(axis=0)
    return float(W[covered].sum() / W.sum())

def greedy(k):
    chosen, covered = [], np.zeros(len(cells), bool)
    for _ in range(k):
        gain = ((M == 1.0) & ~covered).astype(float) @ W
        gain[chosen] = -1
        best = int(np.argmax(gain))
        chosen.append(best)
        covered |= M[best] == 1.0
    return chosen

rng = np.random.default_rng(42)
print("\n=== Coverage theo metadata (chưa kiểm chứng) ===")
for k in (10, 20, 30):
    rnd = rng.choice(len(clips), k, replace=False)
    print(f"K={k}: random={coverage(rnd):.3f}  greedy={coverage(greedy(k)):.3f}")