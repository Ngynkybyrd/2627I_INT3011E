# VI-003 / VI-005 — snapshot 2026-10-16

Phạm vi: Experimental Setup và Limitations dùng chung Việt/Anh; đồng bộ đoạn
timing trong workflow và trạng thái đầu vào của document. Không thêm Results,
Abstract hoặc Conclusion khoa học. Không chạy benchmark hoặc sửa đầu vào.

## Nguồn đã đối chiếu

- `diagnostics/runner/pilot-handoff.md`: runner guard, START/END, watchdog,
  cleanup, CP Optimizer, pilot 55 job repetition 1 và lịch chính 906 job.
- `diagnostics/environment.md` và `diagnostics/runner/pilot-20261016-01/run.json`:
  hardware, bindings/native runtime khi có bằng chứng, cutoff và watchdog.
- `data/freeze.json`, manifest và scope đã chọn trước: data80 frozen;
  S80/B16/C10; uniqueness chưa kiểm. Freeze này không phải freeze code/config.

## Nội dung đã tích hợp

- VI-003: cutoff 10 giây; hardware/runtime; preselection S80/B16/C10;
  3 repetitions, 720 + 96 + 90 = 906 job chính; pilot 55 job r1 được tách rõ.
- Timing START–END và Windows Job Object hard guard; startup 60 giây và
  postprocessing 30 giây là watchdog riêng. Native CP Optimizer cooperative
  limit/private preload được mô tả kèm external guard.
- VI-005: generator/source bias, uniqueness unverified, matched subsets,
  timeout censoring và trạng thái lỗi riêng; giới hạn miễn phí chỉ bảo đảm phạm
  vi C10 đã kiểm. Lỗi size CP Optimizer không suy rộng cho mọi bảng 16/25.

## Kiểm tra

`powershell -File report/build.ps1 -Offline` thành công, build
`20261016-192714-681`. `report/verify_pdf.py` PASS: hai PDF 7 trang A4,
không thiếu glyph/reference/citation hoặc overfull box. Kiểm trực quan trang
5–7 của cả hai bản: bảng, đoạn văn và bibliography rõ, không chồng/cắt chữ.
Log: `logs/setup-limitations-build.log`, `logs/verification.json`.

## Còn chờ

Code/config chính chưa freeze, 906 lượt chính chưa chạy. Phải đối chiếu metadata
cuối và nhận CSV/bảng/hình chính trước khi viết Results/Abstract/Conclusion.
Snapshot này không xác nhận hoàn tất thí nghiệm chính hoặc PDF nộp cuối.
