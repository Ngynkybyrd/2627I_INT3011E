# DATA-006 — Chuẩn hóa 20 public theo contract v1

Đã chuyển đúng 20 bản ghi trong `diagnostics/public-selection.csv`, giữ thứ
tự sample seed 20261016 và ID đã đề xuất, thành `data/public/<instance_id>.json`.
Mỗi JSON chỉ có `n=3` và `grid` 9×9 số nguyên; ghi UTF-8 không BOM, LF, indent
hai khoảng trắng, newline cuối. Không thêm nghiệm hoặc metadata vào input.

`scripts/prepare_public.py` kiểm SHA-256 cố định của nguồn và CSV; so từng
bản ghi với source line/source ID/rating/hash/clue count; kiểm 20 chuỗi khác
nhau; không lấy mẫu lại. Việc loại trùng toàn nguồn trước lấy mẫu đã thực
hiện trong `diagnostics/select_public_source.py`: 321.592 chuỗi khác nhau,
0 trùng. Chuẩn hóa này giữ nguyên các ô và không đổi quyết định lấy mẫu.

Index riêng `index.json` giữ sample rank, ID, source line/ID/commit, hash
chuỗi ô và JSON, clue count, bốn ID đề xuất cho B16/C10. Đây chỉ là index
20 public, không phải manifest80 hoặc khóa S80/B16/C10 cuối.

Lệnh chạy từ thư mục dự án, Python 3.13.5:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_public.py'
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_public.py' --check
```

Kết quả đã chạy: **PASS**. `--check` không ghi file: dựng lại bytes trong
bộ nhớ, so với toàn bộ 20 JSON và index rồi gọi `load_puzzle` cho từng JSON,
đối chiếu lại hash chuỗi ô. Lệnh tạo chấp nhận file cũ chỉ khi bytes giống
hệt; từ chối ghi đè file khác nội dung.

Đã tạo lại vào thư mục tạm có khoảng trắng và dấu tiếng Việt bên trong
`diagnostics/public-normalization/`, kiểm bằng `load_puzzle`, so toàn bộ 20
JSON và index với bản chính: **PASS**, byte/checksum giống hệt. Thư mục tạm
đã dọn sau khi xác nhận đường dẫn nằm trong phạm vi được giao.

- SHA-256 CSV selection vẫn là
  `13f6ff47669498070f53a1404ed1f0492b2d740a461401b3605b9d1bd988c96a`.
- SHA-256 index:
  `8f1f236de4e365029fcdfd971fc24472fcb5b980134a380ed396d14480bcbccd`.
- Bốn ID đầu không đổi: `public-se-hard-L069940`,
  `public-se-hard-L293964`, `public-se-hard-L269904`,
  `public-se-hard-L215069`.

**Mức bằng chứng:** DATA-006 hoàn thành chuẩn hóa/loại trùng/chọn cố định
20 public. Parser chỉ xác nhận cấu trúc, không xác nhận SAT. Index giữ
`sat_checked=false`, `uniqueness_checked=false`; tuyên bố uniqueness từ
nguồn chưa được dự án xác minh. DATA-007 vẫn chờ checker độc lập và adapter
tìm nghiệm; DATA-008/DATA-011 chưa hoàn thành cho dataset80/manifest/freeze.
Không tải lại nguồn, sửa CSV, sinh synthetic hoặc chạy benchmark.
