# Day 06 · T01 Coverage Planner — PoC Presentation
**Field-to-Release Data Governance & Privacy Lab**
*Học viên thực hiện:* Phạm Thanh Tùng - MSSV: 03159

---

## Slide 1: Bài toán & Điểm nghẽn (Problem Statement)
* **Mục tiêu:** Từ pool 120 video clip ứng viên (`candidates.csv`), chọn tối ưu $K=30$ clip để phủ tối đa 15 ô kịch bản mục tiêu (`targets.csv`) theo 4 chiều:
  $$\text{Route} \times \text{Weather} \times \text{Light} \times \text{Object}$$
* **Hậu quả nếu sai sót:** Thiếu dữ liệu các tình huống nguy hiểm hiếm gặp làm mô hình tự lái mất an toàn; chọn sai clip gây lãng phí ngân sách và thời gian thu thập lại.
* **Thách thức thực tế:**
  1. Metadata bị nhiễu (~2.3% tag mang giá trị `unknown`).
  2. Ràng buộc ngân sách thời gian quay ($K$ có hạn).
  3. Có những ô mục tiêu không tồn tại trong tập ứng viên hiện có.

---

## Slide 2: Kiến trúc Pipeline & Thuật toán 2 Pha (PoC)
* **Luồng xử lý 5 bước chuẩn contract:**
  $$\text{Load} \rightarrow \text{Process} \rightarrow \text{Rank} \rightarrow \text{Review} \rightarrow \text{Decide}$$
* **Cơ chế xác thực (Noisy-tag handling):**
  * Khớp hoàn toàn mọi chiều: $\text{Confidence} = 1.0$ (`CONF_SURE`).
  * Khớp nhưng có chiều bị `unknown`: $\text{Confidence} = 0.5$ (`CONF_MAYBE`).
* **Thuật toán Weighted Greedy Set Cover 2 pha:**
  * **Pha 1 (Coverage Gain):** Lựa chọn tham lam clip tối đa hóa độ phủ trọng số kỳ vọng $\sum (M \cdot w \cdot \text{miss})$ trừ chi phí thời gian. Phủ hết các ô khả thi ở $K=15$.
  * **Pha 2 (Backup Thin Cells):** 15 slot còn lại được phân bổ thông minh để chọn clip dự phòng cho các ô mỏng:
    $$\text{val} = \sum \frac{\text{sure} \cdot w}{1 + n_{\text{sure}}}$$
    tránh chọn lặp kịch bản dư thừa.

---

## Slide 3: Kết quả thực nghiệm (So sánh Baseline vs PoC)
*Minh họa đồ thị:* `demo/t01_baseline_vs_poc_barchart.png`

| Tiêu chí | Random Baseline | Greedy chuẩn | PoC (Nhóm cài đặt) |
|---|:---:|:---:|:---:|
| **Weighted Coverage@30** | 0.3750 (8/15) | 0.8125 (13/15) | **0.8125 (13/15)** |
| **Hard Scenarios Recall** | 0/4 (0%) | 4/4 (100%) | **4/4 (100%)** |
| **Clip dự phòng ô mỏng** | 0 | 0 | **15 clips** |
| **Chi phí thời gian / ô phủ** | 31.0 min/ô | 16.31 min/ô | **16.31 min/ô** |
| **Holdout Coverage@6** | 0.1667 | 0.3333 | **0.3333** |

* **Độ ổn định trước nhiễu (100 seeds mô phỏng 12% unknown):** Coverage trung bình đạt $0.7071 \pm 0.0811$.

---

## Slide 4: Failure Cases & Vòng Thẩm định Người (Human-in-the-loop)
* **3 Failure Modes thực tế được phát hiện:**
  1. **UNCOVERABLE (Cell C15 - Alley/Rain/Dusk/Pedestrian):** 0 clip trong pool có thể đáp ứng $\rightarrow$ Bắt buộc lập kế hoạch quay bổ sung (Shot List).
  2. **MAYBE_ONLY (Cell C13 - Urban/Fog/Night/Pedestrian):** Chỉ có `clip_093` khớp nhưng tag `light=unknown` $\rightarrow$ Đưa vào review queue, gán nhãn Escalate.
  3. **FRAGILE (Cell C08, C09):** Ô chỉ có đúng 1 clip chắc chắn duy nhất trong pool $\rightarrow$ Rủi ro cao nếu clip bị lỗi.
* **Human-in-the-loop Gate:**
  * Review queue top-3 ô rủi ro xuất ra `contact_sheet.html` và `review_queue_reviewed.csv`.
  * Ghi nhận đầy đủ nhật ký bất biến `audit_log.jsonl` do Phạm Thanh Tùng ký duyệt.
  * Ban hành quyết định kỹ thuật: **REWORK** (`CAPTURE_PLAN_APPROVED`) kèm Shot list.

---

## Slide 5: Chuẩn bị phản biện (Adversarial Q&A Defense)

* **Câu hỏi 1: Vì sao PoC không vượt qua Greedy chuẩn về chỉ số Coverage theo metadata?**
  * *Trả lời:* Độ phủ metadata đạt trần ở **0.8125 (13/15 ô)** ngay từ $K=20$. Trong pool 120 clip, ô C15 hoàn toàn không có clip nào (0 trong pool), và ô C13 chỉ có clip mang tag `unknown`. Không thuật toán nào có thể đạt >0.8125 trên tập dev mà không "ăn gian" nhãn ẩn.
  * Sự vượt trội của PoC thể hiện ở **Độ bền vững (Robustness)**: Pha 2 của PoC cung cấp 15 clip dự phòng bọc lót cho các ô mỏng, đảm bảo khi kiểm thử trên Ground Truth thật hoặc có clip lỗi, hệ số suy giảm độ phủ là thấp nhất.

* **Câu hỏi 2: Vì sao chọn hệ số tin cậy 0.5 cho tag `unknown` mà không phải 0.0 hay 1.0?**
  * *Trả lời:*
    * Nếu chọn $1.0$: Pipeline sẽ xem ô có clip unknown là đã phủ an toàn $\rightarrow$ False Confidence (bỏ sót lỗi nguy hiểm).
    * Nếu chọn $0.0$: Pipeline sẽ vứt bỏ hoàn toàn các clip có tag unknown $\rightarrow$ Lãng phí ứng viên tiềm năng ở các tình huống hiếm (như C13).
    * Chọn $0.5$: Vừa ưu tiên clip chắc chắn trước, vừa giữ lại clip nghi ngờ nếu không còn lựa chọn nào khác, đồng thời đẩy ô đó vào Review Queue để con người quyết định.
