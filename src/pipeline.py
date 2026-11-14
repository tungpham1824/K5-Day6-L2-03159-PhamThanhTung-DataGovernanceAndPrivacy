"""T01 Coverage Planner - PoC pipeline (weighted greedy set cover with noisy-tag handling).

Rules frozen BEFORE looking at results:
  * clip matches a cell fully            -> confidence 1.0 (CONF_SURE)
  * match only because a tag is 'unknown' -> confidence 0.5 (CONF_MAYBE)
  * phase 1: pick clip with the largest expected weighted gain (ties -> cheaper clip)
  * phase 2: remaining slots go to backup clips for thin cells (cells with few sure clips)
  * review queue = top-3 risky cells (not clips); capture plan = cells not safely covered
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track

DIMS = ["route", "weather", "light", "object"]
CONF_SURE = 1.0
CONF_MAYBE = 0.5

_CELLS = pd.DataFrame()   # cell table, shared between process() / rank() / decide()


def _match(clip: dict, cell: dict) -> float:
    unknown = False
    for d in DIMS:
        t = cell[d]
        if t == "*":
            continue
        v = clip[d]
        if v == "unknown":
            unknown = True
        elif v != t:
            return 0.0
    return CONF_MAYBE if unknown else CONF_SURE


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    cand_file = str(ctx.param("candidates_file", "candidates.csv"))
    cands = pd.read_csv(ctx.input_dir / cand_file)
    targets = pd.read_csv(ctx.input_dir / "targets.csv")
    need = ["clip_id", "cost_min"] + DIMS
    miss = [c for c in need if c not in cands.columns]
    if miss:
        raise ValueError(f"{cand_file} is missing columns: {miss}")
    return {"manifest": pd.read_csv(manifest), "cands": cands, "targets": targets}


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    global _CELLS
    cands, targets = data["cands"], data["targets"]
    k = int(ctx.param("k", 30))
    clips = cands.to_dict("records")
    cells = targets.to_dict("records")
    w = targets["weight"].to_numpy(float)
    cost = cands["cost_min"].to_numpy(float)
    M = np.array([[_match(c, t) for t in cells] for c in clips])
    sure = (M == CONF_SURE).astype(float)

    chosen: list[int] = []
    why: dict[int, str] = {}
    gains: dict[int, float] = {}
    miss = np.ones(len(cells))

    # phase 1: expected weighted gain
    while len(chosen) < min(k, len(clips)):
        gain = (M * (w * miss)).sum(axis=1)
        gain[chosen] = -1.0
        best = int(np.argmax(gain - 1e-3 * cost))
        if gain[best] <= 1e-9:
            break
        chosen.append(best)
        why[best] = "coverage_gain"
        gains[best] = float(gain[best])
        miss *= (1 - M[best])

    # phase 2: backup clips for thin cells
    n_sure = sure[chosen].sum(axis=0) if chosen else np.zeros(len(cells))
    while len(chosen) < min(k, len(clips)):
        val = (sure * (w / (1 + n_sure))).sum(axis=1)
        val[chosen] = -1.0
        best = int(np.argmax(val - 1e-3 * cost))
        chosen.append(best)
        why[best] = "backup_for_thin_cells"
        gains[best] = float(val[best])
        n_sure = n_sure + sure[best]

    # cell table + capture plan
    sel = np.array(chosen, dtype=int)
    n_sure_sel = (M[sel] == CONF_SURE).sum(axis=0)
    n_maybe_sel = (M[sel] == CONF_MAYBE).sum(axis=0)
    pool_any = (M > 0).sum(axis=0)
    rows = []
    for j, t in enumerate(cells):
        if n_sure_sel[j] >= 2:
            status, risk = "COVERED", 0.0
        elif n_sure_sel[j] == 1:
            status, risk = "FRAGILE", 0.5
        elif n_maybe_sel[j] > 0:
            status, risk = "MAYBE_ONLY", 1.0
        elif pool_any[j] == 0:
            status, risk = "UNCOVERABLE_IN_POOL", 1.0
        else:
            status, risk = "NOT_COVERED", 1.0
        plan = ""
        if status in ("MAYBE_ONLY", "NOT_COVERED", "UNCOVERABLE_IN_POOL"):
            plan = "Quay them 1 clip: " + ", ".join(f"{d}={t[d]}" for d in DIMS) + " (* = bat ky)"
        rows.append({"cell_id": t["cell_id"], "weight": t["weight"], "is_hard": t["is_hard"],
                     "n_sure_selected": int(n_sure_sel[j]), "n_maybe_selected": int(n_maybe_sel[j]),
                     "n_in_pool": int(pool_any[j]), "status": status,
                     "score": float(t["weight"] * risk), "capture_plan": plan})
    _CELLS = pd.DataFrame(rows)
    _CELLS.to_csv(ctx.out("coverage.csv"), index=False)

    covered_w = float(w[n_sure_sel >= 1].sum())
    ctx.stats["weighted_coverage_metadata"] = round(covered_w / float(w.sum()), 4)
    ctx.stats["k"] = k

    out = cands.iloc[chosen][["clip_id"]].copy()
    out["rank"] = range(1, len(out) + 1)
    out["score"] = [gains[i] for i in chosen]
    out["reason"] = [why[i] for i in chosen]
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Review queue = top risky CELLS (default 3), not clips."""
    budget = int(ctx.param("review_budget", 3))
    risky = _CELLS[_CELLS["score"] > 0][["cell_id", "score", "status", "capture_plan"]].rename(
        columns={"status": "reason"})
    q = make_review_queue(risky, id_col="cell_id", score_col="score", budget=budget, reason_col="reason")
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    ctx.stats["n_reviewed"] = 0
    if reviewed_path.exists():
        rv = pd.read_csv(reviewed_path)
        for col in ("reviewer", "reviewer_decision"):
            if col not in rv.columns:
                raise ValueError(f"review_queue_reviewed.csv is missing column '{col}'")
        id_col = rv.columns[0]
        n = 0
        for _, r in rv.iterrows():
            if pd.isna(r["reviewer_decision"]) or str(r["reviewer_decision"]).strip() == "":
                continue
            if pd.isna(r["reviewer"]) or str(r["reviewer"]).strip() == "":
                raise ValueError(f"row {r[id_col]} has a decision but no reviewer")
            ctx.audit.log(actor=str(r["reviewer"]), action=f"review_{r['reviewer_decision']}",
                          item_id=str(r[id_col]),
                          after={"override_value": None if pd.isna(r.get("override_value")) else str(r.get("override_value")),
                                 "note": None if pd.isna(r.get("review_note")) else str(r.get("review_note"))})
            n += 1
        ctx.stats["n_reviewed"] = n
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = ctx.config.get("owner", "TODO-owner")
    missing = _CELLS[_CELLS["status"].isin(["UNCOVERABLE_IN_POOL", "NOT_COVERED", "MAYBE_ONLY"])]
    ids = ",".join(missing["cell_id"].tolist())
    if missing.empty:
        return Decision(status="GO", reason_code="ALL_CELLS_COVERED",
                        reason="All target cells are safely covered by the selected clips",
                        owner=owner, scope=ctx.track)
    if ctx.stats.get("n_reviewed", 0) > 0:
        return Decision(status="REWORK", reason_code="CAPTURE_PLAN_APPROVED",
                        reason=f"Cells still missing ({ids}); capture plan reviewed by human, shoot extra clips",
                        owner=owner, scope=ctx.track)
    return Decision(status="HOLD", reason_code="MISSING_CELLS_AWAIT_REVIEW",
                    reason=f"Cells not safely covered ({ids}); waiting for human review of capture plan",
                    owner=owner, scope=ctx.track)


def run(ctx: RunContext) -> None:
    if ctx.track != "t01":
        raise NotImplementedError(f"Pipeline only supports t01, not {ctx.track}")
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))