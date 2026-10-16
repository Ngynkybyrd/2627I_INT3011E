# REF-002 / REF-003 — frozen-source delta acceptance

16/10/2026. Chỉ sửa report/. Không benchmark, không sửa frozen source/raw/data,
README hoặc checklist/status/registry. Không nhắn chat khác.

## Đạt trong phạm vi được giao

- REF-002: citation solver/dataset/library đối chiếu actual main run.json,
  execution-freeze.json, requirements và installed metadata. Five baselines:
  CP-SAT, Gurobi, CPLEX MIP trực tiếp, CP Optimizer qua DOcplex.CP, HiGHS qua
  highspy; SAT dùng Glucose3. Thêm đúng nguồn official CPLEX Python API; không
  dùng DOcplex.MP để mô tả adapter MIP. Phân biệt distribution/interface/native
  version, không suy snapshot PySAT upstream là installed binary.
- REF-003: bibliography chung 20 key; code/source-use ledger, notices của các
  bản sao thực có và hash provenance được lưu. Không phát hiện block source
  upstream cần bổ sung notice trong frozen code qua inspection được mô tả;
  không biến kiểm tra này thành lời chứng tác quyền tuyệt đối. Không yêu cầu
  vendor toàn dependency chỉ vì sử dụng API; không tự cấp license repository.
- Giữ DOI/năm paper đã kiểm trước; living docs n.d., access date riêng; không
  tải thêm literature. Official verification bổ sung duy nhất là trang IBM
  Meet the Python API (banner 22.1.2; không gán nhầm thành runtime 22.2).

## Tái lập và bằng chứng

Từ project root, chạy Python standard library với `-B -X utf8`:
`report/reading/verify-frozen-references.py`.
PASS: 32 hash frozen, run.json hash, requirements và run packages khớp installed
metadata, installed PySAT notice/metadata copy nguyên byte. Không gọi solver.
Log: `frozen-reference-verification.json`.

`report/reading/check-references.ps1`: offline PASS 20/20 bibitem,
BibTeX warnings=0; `reference-verification.json` giữ build path/hash.
Build prototype offline và verify_pdf.py kiểm tích hợp citation; kết quả cuối
ghi trong `verification.json`, compiler console `frozen-references-build.log`.
Build `20261016-195733-395`: hai prototype 7 trang A4, kiểm máy PASS, không
warning/citation/glyph/overfull. Đã xem trang 5–7 cả hai ngôn ngữ (và trang 4
liền trước): citation mới và bibliography không bị chồng/cắt chữ.

Nguồn/ledger hiện hành: `../reading/FROZEN-CODE-ATTRIBUTION.md`.
REF-ACCEPTANCE.md cũ giữ nguyên như snapshot trước freeze.

## Còn chờ

URL repository thật chưa được cung cấp; không điền giả hoặc tự công bố/nộp.
Không nhận VI-007 hoàn tất. Findings SAT08 chưa khóa nên không viết Results,
VI-004/VI-006, Abstract/Conclusion hoặc nhận EN/PDF nộp cuối. Các đoạn setup
trong prototype vẫn là snapshot trước main, phải cập nhật ở gói tích hợp sau;
build citation lần này không chứng nhận nội dung báo cáo cuối đã đồng bộ.
