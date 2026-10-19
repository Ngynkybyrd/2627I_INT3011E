# SAT05 final provenance — PASS, 20/10/2026

Đầu ra cho SAT08/SAT09/SAT10 qua root: counts.json, provenance-vi.md,
provenance-en.md; receipt.json pin hash của các output và audit.py.
Chỉ namespace này được ghi; không sửa data/core/raw/README hoặc report.

- Dataset main16.000: N9=10.000 public (2.500/nhóm), N16=5.000/N25=1.000 synthetic.
- 1.200 root: N16=500 permutation+500 row_cycle, N25=100+100; 5 masks/root.
  Hai bảng seed nguồn; 1.200 final root khác seed tương ứng theo hash chính xác.
- 600 proper-cycle trades: N16 có248 độ dài2 và252 độ dài4; N25 có100 độ dài5.
  Đã kiểm inverse swap khớp pre-trade hash, same-band và trọn chu trình.
- Mỗi mức20/30/40/50/60% có1.000 N16 hoặc200 N25; số clue thực tương ứng:
  N16=51/77/102/128/154; N25=125/188/250/313/375. Chi tiết root_id/strata/histogram
  và source rating gốc có trong counts.json.
- Uniqueness:10.000 source_claimed,6.000 unverified,0 tự chứng minh. Nguồn
  QQWing/Sukaku Explainer, public domain theo README/LICENSE đã pin. Acquisition
  public30s tách benchmark10s; witness tồn tại không bảo đảm mọi benchmark SAT.
- Exact duplicate inputs/roots=0, input overlap S80/pilot=0. 100 batches×160,
  không tách5 masks/root. Distinct root/mask không đồng nghĩa độc lập, đồng đều,
  không đẳng cấu hay độ khó tăng theo N/giảm clue; nguồn khác nhau gây confounding.

Input chính: results/expanded/wave3-20261019-212023-main/dataset-index.json,
SHA256 `89495c913a6fefdcf4595bae7fbb7f54436a44e272bf0f13ea8948df935e6b3b`.
Dataset freeze: data/expanded/wave3-20261019-212023/main/freeze.json,
SHA256 `79b8e003bae4cf7b65314e1cfcfb44ab644fd12845bdf4dc93c8886bf2cb75a4`.
Tất cả source URL/commit/SHA và input dependency hashes có trong counts.json.

Lệnh focused audit từ thư mục dự án:
`& '.\.venv\Scripts\python.exe' -B '.\diagnostics\expansion\final-provenance\audit.py'`
PASS: index bằng manifest/roots;16.000 actual input hashes/clues;10.000 selected
source lines;1.200 root hashes/600 inverse trades; frozen metadata/evidence binding;
crosschecks tổng/strata/VI–EN. Không chạy lại checker trên16.000 witness vì root
đã có data QA: báo cáo chỉ nhận witness metadata/proof đã khóa, không claim mới.
Không solver, web, thêm đề hoặc fullsuite. Không sửa benchmark hay suy ra kết quả
110k từ composition; rep1/ERROR/TIMEOUT thuộc phần QA/analysis07–08 riêng.

Không còn blocker provenance; không có mâu thuẫn quota/family/uniqueness.
