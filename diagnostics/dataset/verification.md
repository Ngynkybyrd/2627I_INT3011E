# Dataset generation — 16/10/2026

**Cập nhật sau DATA-007:** toàn bộ 20 public đã qua production adapter và
checker; DATA-011 đã khóa dữ liệu. Bằng chứng mới nhất tại
[public-verification.md](public-verification.md). Mô tả provisional và hash
bên dưới là snapshot lượt sinh ban đầu; hiện manifest/scopes `frozen=true`.

## Đầu ra và interface

`scripts/prepare_data.py` cung cấp `completed_grid(n)`, `candidate(n, density_percent,
seed)`, `synthetic_records(existing_fingerprints)`, `build_outputs(project_root)`
và `prepare(project_root, check=False)`. Chỉ dùng standard library, parser
`sudoku.model` và checker độc lập `sudoku.validation.check_solution`.

- `data/synthetic/`: 60 input JSON chỉ có n/grid.
- `data/witnesses/`: 60 JSON n/solution, lưu tách input solver. Runner lấy
  input theo trường `file` trong manifest, không quét thư mục witnesses.
- `data/manifest.json`: 80 bản ghi nguồn, n/N, clue count, seed yêu cầu/thực
  dùng, checksum input và fingerprint n/grid; synthetic có đường dẫn/hash
  witness. Public giữ source commit/line/ID và sample rank đã khóa.
- `data/scopes.json`: danh sách ứng viên S80/B16/C10 đúng 80/16/10 ID.
  Chọn synthetic min(actual_seed, instance_id) trong từng nhóm; public giữ
  bốn mẫu đầu. C10 ⊂ B16 ⊂ S80; chưa freeze cuối.
- `generation.json`: cấu hình generator, phiên bản Python và log seed trùng.

Generator tổng quát dùng giá trị `(n*(r%n)+r//n+c)%N+1`, kiểm đầy đủ trước
hoán vị và sau hoán vị giá trị/band/hàng trong band/stack/cột trong stack.
RNG riêng từng đề: `random.Random(f'{n}:{density_percent}:{actual_seed}')`.
Mask chọn đúng `(density_percent*N*N+50)//100` ô. Witness được checker kiểm
với puzzle sau mask, bao gồm giữ clues. Không chứng nhận uniqueness/độ khó.

Quét nhóm theo n=2/3/4/5, density=30/50/70 và seed yêu cầu=0..4. Nếu trùng
fingerprint với public hoặc synthetic trước đó, tăng actual_seed từng đơn
vị, log lần bị loại; tối đa 1000 lần mỗi đề để không treo. Lần sinh thực tế:
**0 lần trùng**, seed thực dùng đều 0..4. Test đã ép xảy ra trùng để kiểm
nhánh tăng seed và log. Fingerprint gồm n/grid, không gộp theo đối xứng.

## Bằng chứng kiểm

Python 3.13.5; chạy từ thư mục dự án:

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_data.py'
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_data.py' --check
& '.\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider '.\tests\test_data_generation.py'
```

Kết quả: generator/check **PASS**, **4 tests passed** (0,49 giây trong lượt
đã chạy; không phải thời gian solver/benchmark). Kiểm gồm:

- Mỗi nhóm 5 seed, đủ 60 đề distinct, chính xác clue count 30/50/70%:
  N=4: 5/8/11; N=9: 24/41/57; N=16: 77/128/179; N=25: 188/313/438.
- Checker chấp nhận bảng đầy và witness giữ clues; input không chứa solution.
- Bảng đầy n=6 (36×36) cũng được checker chấp nhận để kiểm tổng quát; đây
  chỉ là ca kiểm trong bộ nhớ, không thêm vào dataset hoặc thực nghiệm.
- Seed trùng được tăng xác định và ghi log; input bị sửa bị từ chối ghi đè.
- Tạo lại ở đường dẫn tạm có dấu/khoảng trắng: tất cả bytes/checksum và
  scopes trùng bản chính, 20 public không thay đổi. Thư mục tạm đã được dọn.
- `--check` chỉ tạo lại trong bộ nhớ rồi so bytes, không sửa output.

SHA-256 của bản bàn giao:

| File | SHA-256 |
|---|---|
| data/manifest.json | 9a6ad7031aeaf9acd992ce8d6a349f33584469a4d4a51e5c96b66437ca4a7010 |
| data/scopes.json | af634269341d22e52f8a7904685c143fb5aa2d28f2d92539f25bc941fa24478d |
| diagnostics/dataset/generation.json | 3b041591e9753eafeaed9bf388d9cd197545e389bdcd7c2e4584d4f796989a9f |

Manifest có cả khóa `n` và `N`; dùng parser JSON phân biệt hoa/thường.
PowerShell cần `ConvertFrom-Json -AsHashtable` nếu đọc trực tiếp.

## Mức hoàn thành

DATA-001..004, DATA-008..010 có đầu ra và bằng chứng; phần tái lập/chọn ID
của DATA-011 đã làm. Synthetic được ghi SAT bằng witness đã kiểm độc lập,
không dùng đáp án đó để ràng buộc solver. Ở lượt sinh ban đầu, public giữ
`NOT_CHECKED`, manifest/scopes giữ `frozen=false`. Lượt tiếp theo hoàn tất
DATA-007 qua production adapter, nâng manifest thành 80 SAT và khóa dữ liệu
DATA-011. Không xác minh uniqueness, chạy benchmark hoặc thay mẫu theo runtime.
