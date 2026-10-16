# DATA-007 và DATA-011 — Xác minh public và khóa dữ liệu

Ngày 16/10/2026 (Asia/Saigon). Giữ nguyên mẫu và thứ tự đã chọn trước kết quả.

## API và kết quả

`scripts/verify_public.py` gọi `sudoku.sat.prepare_backend()` rồi
`solve_sat(puzzle, 'pairwise', cutoff_seconds=10.0)` cho đúng 20 public,
mỗi đề một lần. Đây là kiểm tồn tại nghiệm DATA-007, không phải lượt benchmark.
Adapter dùng Glucose3, python-sat 1.9.dev16, Python 3.13.5.

**20 SAT**, raw status `True` cho cả 20; **0 TIMEOUT/ERROR/UNSAT/UNAVAILABLE**.
Mọi nghiệm qua production checker và được `check_solution` kiểm lại với
puzzle gốc: 20 validation pass. Không tìm nghiệm thứ hai hay công bố uniqueness.
Witness lưu riêng tại `data/witnesses/public-se-hard-L*.json`, không vào input.

`data/public-validation.json` giữ ID theo sample order, input/witness hash,
SolveResult thật (status/raw status, nghiệm, validation, thời gian adapter),
phiên bản và hash adapter/checker tại lúc kiểm. Hash code chỉ là provenance,
không khóa code và không thay số liệu benchmark.
SHA-256 evidence: `772a90d0f66c122a71c1e48abf3f2a42a49e5c94c4e1d5269c37891043e8fc74`.

## Khóa dữ liệu và tái lập

Manifest hiện có **80 SAT**: 60 synthetic bằng witness đã kiểm và 20 public
bằng production adapter/checker. Uniqueness vẫn unverified. Manifest/scopes/
generation đều `frozen=true`. `data/freeze.json` khóa ID S80/B16/C10 (80/16/10)
và hash 169 file dữ liệu/bằng chứng: 80 input, 80 witness, manifest/scopes/
generation, evidence public, nguồn/README/LICENSE, CSV selection và index
chuẩn hóa. Đây là freeze dữ liệu, không freeze code hoặc RUN-012.

| File | SHA-256 hiện hành |
|---|---|
| data/manifest.json | fd77c28e3934bdaa9b4989e3579a330d6999abe7b976bc9b13bf5f20213e2c9b |
| data/scopes.json | 7c88bfe9e6763b025dd6070eadf16f8a0c6f10ee9ba2e54e42b2484e716f7358 |
| data/freeze.json | fd84c10458d41fde0e2de0ebb204b68ea0b95f587cf6a19e00d4e1cb58de2e25 |
| diagnostics/dataset/generation.json | 573b258785bc1a468b33f3898e1ef8c1d4ef5f1a5a66d34fa8d1d9707fc7d273 |

Input và witness synthetic, public input/selection cùng thứ tự ID giữ nguyên.
Chỉ thêm evidence/witness public và nâng metadata từ bản provisional đã biết.
Generator không giải lại: đọc evidence lưu, đối chiếu hash, kiểm lại witness,
dựng lại metadata rồi so bytes/freeze. Rerun verify khi đã có evidence cũng
không tự giải lại. Các snapshot chuẩn bị cũ ghi trạng thái tại thời điểm đó;
manifest và tài liệu này là trạng thái nghiệm thu mới nhất.

Lệnh đã chạy từ thư mục dự án:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\verify_public.py'
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_data.py' --check
& '.\.venv\Scripts\python.exe' -B '.\scripts\verify_public.py' --check
& '.\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider '.\tests\test_data_generation.py'
```

Kết quả: cả hai `--check` **PASS**, **5 tests passed** (1,43 giây ở lượt
đã chạy; không phải benchmark). Test mới tạo lại provisional trên đường
dẫn có dấu, áp dụng evidence/witness đã lưu, finalize dữ liệu, so tất cả
output và freeze byte-for-byte với bản chính: PASS. Sửa một ô nghiệm trong
evidence bị checker từ chối: PASS. Thư mục test tạm đã dọn sau khi kiểm phạm vi.

DATA-007/DATA-011 đủ bằng chứng hoàn thành; không còn blocker dataset.
Runner dùng ID trong scopes và trường `file` trong manifest, không dùng
witness để buộc solver trả một nghiệm cụ thể.
