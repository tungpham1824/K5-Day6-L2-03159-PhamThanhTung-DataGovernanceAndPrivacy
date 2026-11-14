# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T01 Coverage Planner |
| Primary metric (tên đúng như evaluator in ra) | Weighted Coverage@K |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | ô mục tiêu (cell) trong `targets.csv`, 15 ô |
| Công thức + numerator / denominator | Numerator = tổng `weight` của các ô được phủ bởi ít nhất 1 clip đã chọn. Denominator = tổng `weight` của cả 15 ô (= 48). Một clip phủ ô khi tag khớp cả 4 chiều (route, weather, light, object) hoặc ô có `*`. Clip có tag `unknown` ở chiều không phải `*` KHÔNG được tính là phủ chắc. |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép theo `clip_id`; so khớp chính xác từng chiều tag, `*` khớp mọi giá trị. Không có tolerance. |
| Candidate pool cố định | `fixtures/t01_coverage/candidates.csv`, 120 clip. Heldout: `holdout_candidates.csv`, 25 clip. |
| Review budget B / K | K = 30 (chính). Báo thêm K = 10 và K = 20. Heldout: K = 6. Người duyệt: 3 ô rủi ro. |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Không có threshold học từ dữ liệu. Hệ số tin cậy của clip có `unknown` (khớp chắc = 1.0, khớp nghi ngờ = 0.5) được chốt TRƯỚC khi chạy PoC và không chỉnh sau khi xem kết quả. Thuật toán gồm 2 pha: Pha 1 chọn clip tối đa hóa expected weighted gain; Pha 2 phân bổ các slot còn lại để chọn clip dự phòng (backup) cho các ô mỏng (thin cells có ít clip chắc chắn, công thức `val = sum(sure * w / (1 + n_sure))`) nhằm giảm thiểu rủi ro khi có clip hỏng/lỗi. |
| Eval split (không dùng để tune) | `holdout_candidates.csv` (K=6) chỉ chạy 1 lần cuối, không dùng để chỉnh tham số. |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | (1) Ô `is_hard` không được phủ (miss). (2) Ô bị tưởng đã phủ do tag nhiễu nhưng thực tế chưa phủ (false coverage). (3) Ô không có clip nào trong pool (không thể phủ, phải đưa vào capture plan). |
| Slices sẽ báo cáo (≥2) | (a) ô `is_hard=1` so với `is_hard=0`. (b) budget K = 10 / 20 / 30. (c) clip có tag `unknown` so với clip tag đầy đủ. |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Chỉ có 15 ô nên báo số ô phủ dạng đếm (ví dụ 13/15) kèm trọng số. Vì không có tag đã kiểm chứng, mô phỏng nhiễu ~12% tag trên 100 seed khác nhau và báo trung bình ± độ lệch chuẩn. |
| Ngày giờ chốt + người chốt | 14/11/2026, 17:00, Phạm Thanh Tùng - 03159 |

Baseline: (1) Random K clip, seed 42, cùng pool. (2) Greedy weighted set-cover trên metadata. Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

Ghi chú protocol: repo học viên không có `gt/verified_tags.csv`, nên Weighted Coverage được tính trên metadata hiện có (tag `unknown` không tính là phủ) và bằng mô phỏng nhiễu. Số này là mức coverage "theo metadata", không phải coverage đã kiểm chứng thật.