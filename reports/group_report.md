# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Mọi con số lấy từ file do script sinh ra (`out/*/run_info.json`, `out/poc/coverage.csv`).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G01-T006 |
| Challenge | T01 · Coverage Planner: chọn đủ cảnh cần thu |
| Thành viên | Phạm Thanh Tùng - 03159 (làm cá nhân, tất cả vai trò) |
| Git URL | https://github.com/tungpham1824/K5-Day6-L2-03159-PhamThanhTung-DataGovernanceAndPrivacy.git |
| Tag `demo-180m` (commit) | f0983d1 |
| Tag `final-24h` (commit) | TODO |
| Deadline (giờ VN) | 14/11/2026 |

## 01 · Problem statement

- **Ai bị ảnh hưởng:** Đội thu thập dữ liệu (capture team) — nếu chọn clip sai, phải quay lại thu thêm, tốn thời gian và chi phí. Mô hình ML downstream thiếu dữ liệu ở scenario hiếm sẽ giảm hiệu suất.
- **Điểm nghẽn cụ thể:** Từ 120 clip ứng viên, chọn K=30 clip để phủ tối đa 15 ô coverage mục tiêu (route × weather × light × object, có trọng số rủi ro). Metadata có ~2.3% tag `unknown` gây nhiễu.
- **Đầu vào → đầu ra:** `candidates.csv` (120 clip) + `targets.csv` (15 ô mục tiêu) → `pick.csv` (30 clip đã chọn) + `coverage.csv` (trạng thái 15 ô) + `review_queue.csv` + `decision.json`.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - GO: Tất cả 15 ô đều có ≥1 clip chắc chắn (CONF_SURE) phủ.
  - HOLD: Còn ô chưa phủ và chưa được human review.
  - REWORK: Còn ô chưa phủ, đã được human review, cần quay bổ sung theo capture plan.
- **Giả định cần DPO/legal xác nhận:** Dữ liệu fixture là synthetic, CC0. Nếu dùng dữ liệu thật (BDD100K), cần xác nhận license cho mục đích sử dụng cụ thể. Không tuyên bố đạt GDPR / luật VN từ checklist tự động.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev (candidates) | 120 clip | `fixtures/t01_coverage/candidates.csv` | CC0 | Có |
| eval / heldout | 25 clip | `fixtures/t01_coverage/holdout_candidates.csv` | CC0 | Có |
| targets | 15 ô | `fixtures/t01_coverage/targets.csv` | CC0 | Có |

- **Schema & class mapping:** `clip_id, route, weather, light, object, risk, cost_min, duration_s`. 4 chiều match: route (urban/highway/alley), weather (clear/rain/fog/unknown), light (day/night/dusk/unknown), object (car/pedestrian/motorbike/motorbike_occluded/unknown).
- **Seed:** 42 · Chia split: holdout tách riêng file `holdout_candidates.csv`, không overlap với `candidates.csv`.
- `manifest.csv` verified (sha256): **có** — pipeline kiểm sha256 ở bước `load()` qua `verify_manifest()`.
- Dữ liệu thật: **không dùng** trong bài nộp này.

## 03 · Research & design

- **References:**
  1. BDD100K (CVPR 2020) — xem ngày 14/11/2026 — dataset đa dạng cảnh lái xe, cấu trúc metadata tham khảo cho coverage planner.
  2. Google Data Cards Playbook — xem ngày 14/11/2026 — hướng dẫn documentation data provenance.
  3. Greedy weighted set cover — thuật toán cổ điển O(n·m), đảm bảo (1-1/e) approximation ratio.
- **Sơ đồ data flow:** `load(candidates+targets)` → `process(greedy set cover 2 phase)` → `rank(top-3 risky cells)` → `review(human override + audit log)` → `decide(GO/HOLD/REWORK)` → output.
- **Thành phần offline:** Không dùng model pretrained. Thuật toán hoàn toàn rule-based (greedy weighted set cover).
- **Trade-offs:**
  - Phase 1 (expected weighted gain): tối ưu coverage nhưng có thể bỏ qua ô khó nếu clip ít.
  - Phase 2 (backup for thin cells): bổ sung cho ô mỏng nhưng tăng chi phí.
  - Clip `unknown` tag: gán confidence 0.5 (CONF_MAYBE) thay vì bỏ qua hoàn toàn — chấp nhận risk false coverage.

## 04 · Baseline vs PoC

- **Baseline 1 (Random):** Random chọn K clip, seed 42, cùng pool. Pipeline: `src.examples.random_baseline`.
- **Baseline 2 (Greedy chuẩn):** Thuật toán tham lam cổ điển tối đa hóa trọng số ô chưa phủ.
- **PoC:** Weighted greedy set cover 2 phase + noisy-tag handling (CONF_SURE 1.0, CONF_MAYBE 0.5). Pipeline: `src.pipeline`.
- **Cùng budget / cùng heldout / cùng seed:** xác nhận ✅ (K=30, seed=42, pool=120 clip).

> **Nói thẳng về thuật toán:** PoC bằng Greedy về độ phủ theo metadata (cùng đạt 0.8125 tại K=30 do trần pool chỉ phủ tối đa được 13/15 ô, 2 ô còn lại là C15 không có clip và C13 chỉ có clip unknown). Điểm vượt trội thực chất của PoC so với greedy thuần nằm ở:
> 1. **Xử lý nhãn nhiễu:** Gán trọng số tin cậy 0.5 (CONF_MAYBE) cho clip có tag `unknown`, không ngộ nhận là đã phủ an toàn.
> 2. **Pha 2 dự phòng (Phase 2 backup):** Sau khi đã phủ các ô ở pha 1, các slot còn lại (15 slot) được phân bổ có chủ đích để bọc lót cho các ô mỏng (thin cells có ít hơn 2 clip chắc chắn) qua công thức `val = sum(sure * w / (1 + n_sure))`, thay vì chọn trùng lặp kịch bản vô ích.

**Bảng 1 · So sánh chi tiết Random Baseline vs Greedy vs PoC:**

| Chỉ số đánh giá | Random Baseline | Greedy chuẩn | PoC (2-pha của nhóm) | Nhận xét & Đơn vị |
|---|:---:|:---:|:---:|---|
| **Primary: Coverage@30** | 0.3750 (8/15) | 0.8125 (13/15) | **0.8125 (13/15)** | PoC vượt trội Random (+0.4375), ngang Greedy |
| Coverage@10 | 0.0625 (2/15) | 0.5833 (8/15) | **0.5833 (8/15)** | Greedy/PoC phát huy tối đa ở budget nhỏ |
| Coverage@20 | 0.2083 (5/15) | 0.8125 (13/15) | **0.8125 (13/15)** | Bão hòa từ K=20 do giới hạn pool |
| **Rare-scenario Recall (is_hard=1, 4 ô)** | 0/4 (0%) | 4/4 (100%) | **4/4 (100%)** | Phủ toàn bộ 4 ô hiểm (C08, C09, C10, C11) |
| **Số clip dự phòng cho ô mỏng** | 0 clip | 0 clip | **15 clip** | PoC bảo vệ ô fragile chống rủi ro clip lỗi |
| **Chi phí thời gian / ô phủ được** | 31.0 min/ô | 16.31 min/ô | **16.31 min/ô** | Tiết kiệm 47% chi phí thời gian quay |
| Tổng chi phí thời gian (K=30) | 248 phút | 212 phút | **212 phút** | PoC ưu tiên clip chi phí thấp khi hòa gain |
| Holdout Coverage@6 | 0.1667 | 0.3333 | **0.3333** | Đánh giá độc lập 1 lần trên 25 clip heldout |
| Runtime / 100 items | — | ~0.02s | **0.0208s** | CPU only, cực nhanh |

*Minh họa đồ thị so sánh:* Xem biểu đồ chi tiết tại `demo/t01_baseline_vs_poc_barchart.png`.

## 05 · Evaluation protocol

- **Công thức primary metric:** Weighted Coverage@K = Σ weight(ô được phủ) / Σ weight(tất cả ô) = numerator / 48. Ô được phủ nếu ≥1 clip đã chọn có tag khớp chính xác trên mọi chiều (hoặc ô có `*`). Clip `unknown` không tính là phủ chắc.
- **Threshold / budget K:** K=30 (chính), báo thêm K=10, K=20. Heldout K=6. Chốt trước khi chạy eval.
- **Độ bất định:** N=15 ô nên báo đếm (e.g. 13/15). Mô phỏng nhiễu ~12% unknown tag trên 100 seed: mean coverage = 0.7071 ± 0.0811 (min=0.4792, max=0.8125).
- **Lệnh evaluate:** `python -m src.evaluate --track t01 --pred out/poc/pick.csv` (cần gt/ của giảng viên).

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| is_hard=0 (11 ô) | 11 | 8/11 | 9/11 | PoC thiếu C13 (MAYBE_ONLY) và C15 (UNCOVERABLE) |
| is_hard=1 (4 ô) | 4 | 0/4 | **4/4** | PoC phủ tất cả ô hard |
| K=10 | 120→10 | 0.0625 | **0.5833** | Greedy hiệu quả nhất ở budget thấp |
| K=20 | 120→20 | 0.2083 | **0.8125** | Bão hòa từ K=20 (coverage = K=30) |
| Noise 12% unknown | 100 seeds | — | 0.7071±0.0811 | Coverage giảm ~10pp do nhiễu |

- **Failure case 1 — UNCOVERABLE (C15):** Cell `alley/rain/dusk/pedestrian` (weight=4). Không có clip nào trong pool 120 clip khớp. Root cause: tổ hợp hiếm chưa được thu thập. → Đã đưa vào capture plan "Quay thêm 1 clip" (minh họa tại `demo/t01_target_cells_status.png`).
- **Failure case 2 — MAYBE_ONLY (C13):** Cell `urban/fog/night/pedestrian` (weight=5). Chỉ 1 clip (clip_093) match nhưng tag `light=unknown` → confidence=0.5 không đủ tin cậy. Root cause: metadata noise. → Escalate, cần quay thêm clip xác nhận (minh họa tại `demo/t01_target_cells_status.png`).
- **Failure case 3 — FRAGILE (C08, C09):** Ô `alley/*/night/*` và `urban/rain/night/motorbike` — mỗi ô chỉ có 1 clip chắc chắn duy nhất trong toàn bộ pool. Nếu clip đó bị lỗi, coverage mất.
- **Latency / compute:** 0.0208s toàn bộ pipeline (120 clips × 15 cells), Intel i7, Windows 11, Python 3.12.

## 07 · Human & decision

- **Review queue:** `out/poc/review_queue.csv`, B=3 (top 3 risky cells, không phải clips), ưu tiên theo `weight × risk_score`.
- **Cách override + audit log:** Reviewer (Phạm Thanh Tùng) điền `reviewer`, `reviewer_decision`, `review_note` vào `review_queue_reviewed.csv`. Pipeline đọc lại, ghi vào `out/poc/audit_log.jsonl` (JSONL append-only).
- **Decision policy:**
  - `reason_code=ALL_CELLS_COVERED` → GO
  - `reason_code=CAPTURE_PLAN_APPROVED` → REWORK (human đã duyệt, cần quay thêm clip)
  - `reason_code=MISSING_CELLS_AWAIT_REVIEW` → HOLD
- **Kết quả:** Decision = **REWORK** (`CAPTURE_PLAN_APPROVED`) — 3/3 ô rủi ro đã được review bởi Phạm Thanh Tùng:
  - C13: escalate — cần quay thêm clip urban/fog/night/pedestrian.
  - C15: approve capture plan — cần quay thêm clip alley/rain/dusk/pedestrian.
  - C09: approve — chấp nhận risk với 1 clip chắc chắn.
- **Khi nào HOLD/REWORK:** Khi còn ô mục tiêu chưa được phủ chắc chắn, pipeline tự động HOLD chờ human review. Sau khi review → REWORK nếu cần quay thêm.

### Bảng Shot List đề xuất quay bổ sung (ưu tiên theo chi phí & trọng số)

| Ưu tiên | Ô thiếu | Kịch bản yêu cầu (route, weather, light, object) | Weight | Lý do thiếu / Trạng thái | Ước tính chi phí |
|:---:|:---:|---|:---:|---|:---:|
| **P1** | **C13** | `route=urban, weather=fog, light=night, object=pedestrian` | 5 (rất cao) | Clip duy nhất trong pool (`clip_093`) bị `unknown` tag light; cần quay xác nhận | ~10 phút |
| **P2** | **C15** | `route=alley, weather=rain, light=dusk, object=pedestrian` | 4 (cao) | Hoàn toàn không có clip nào trong pool 120 clip; bắt buộc quay mới | ~14 phút |

*Tổng ngân sách quay bổ sung:* ~24 phút ghi hình thực tế để đạt 100% độ phủ (15/15 ô mục tiêu).

## 08 · Reproduce & tests

```bash
make setup          # python -m venv .venv && pip install -r requirements.txt
python -m src.main --input fixtures/t01_coverage --config configs/lab.yaml --output out/poc --offline --seed 42
python -m src.main --track t01 --output out/baseline --run-name baseline --pipeline src.examples.random_baseline --offline
pytest -q --basetemp=tmp_test
```

- **Output của `pytest -q`:** tất cả tests pass (0 failed), bao gồm 2 test tự viết trong `tests/test_t01_pipeline.py`.
- **Máy / CPU / OS / Python:** Intel i7 12th Gen · Windows 11 (10.0.26200) · Python 3.12.10 · git sha: f0983d1

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII / license:** Dữ liệu fixture hoàn toàn synthetic (CC0), không chứa người/biển số thật. Nếu mở rộng với BDD100K hoặc dữ liệu thật, cần kiểm tra license và PII.
- **Điều chưa biết:** Khi metadata noise tăng (>12%), coverage có thể giảm đáng kể (mean 0.7071 vs 0.8125 lý tưởng). Cell C15 không thể phủ bằng pool hiện tại.
- **Nếu scale 10×:** Greedy set cover O(n·m) vẫn khả thi (1200 clips × 150 cells ~ vài giây). Nhưng cần cơ chế active learning để chọn clip cần verify tag.
- **Không tuyên bố "đạt GDPR / luật Việt Nam"** từ checklist tự động; giả định cần DPO/legal xác nhận trước khi deploy.
- **Kế hoạch cải tiến:** (1) Active tag verification cho clip unknown, (2) Cost-aware selection tối ưu chi phí/ô, (3) Greedy set-cover đa mục tiêu (coverage + diversity + cost).

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (làm cá nhân — đối chiếu với `reports/team_contributions.csv`)

| Học viên | MSSV | Module / vai trò | Trình bày? |
|---|---|---|---|
| Phạm Thanh Tùng | 03159 | Tất cả: pipeline, tests, review, report, failure analysis, metric contract | Có |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa |
|---|---|---|
| BDD100K dataset (CVPR 2020) | 14/11/2026 | Dataset đa dạng cảnh lái xe, cấu trúc metadata dùng làm tham chiếu cho coverage planner |
| Google Data Cards Playbook | 14/11/2026 | Hướng dẫn documentation data provenance, data cards cho ML datasets |
| ISO/IEC TR 5259-6:2026 | 14/11/2026 | Tiêu chuẩn quốc tế về data quality cho AI, tham khảo cho quy trình QC |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [x] Thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.
