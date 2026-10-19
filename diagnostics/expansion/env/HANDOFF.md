# EXP-01 — Inventory, fingerprint và ngân sách lưu trữ

Snapshot **17:59:50 ngày 19/10/2026, Asia/Saigon** (UTC trong JSON).
Chỉ đọc môi trường và ghi trong thư mục này. Không đổi venv, cài package,
chạy solver/pilot/benchmark/fullsuite hoặc sửa dữ liệu/kết quả cũ.

## Môi trường và tài nguyên máy

Python 3.13.5 x64, interpreter chính `.venv/Scripts/python.exe`; Windows 11
10.0.26300, AMD Ryzen 7 H 260, 16 CPU logic. RAM vật lý **31,31 GiB**, RAM
khả dụng snapshot **9,43 GiB**. Đây là snapshot, không phải bảo đảm RAM rảnh
trong pilot; runner vẫn chỉ chạy tuần tự một worker và tránh job nặng cạnh tranh.

| Ổ đĩa | Trống (byte) | Trống (GiB) | Mục đích |
|---|---:|---:|---|
| D: | 87.987.003.392 | 81,94 | Project, DB/witness/log/export mới |
| C: | 27.275.182.080 | 25,40 | Interpreter nền; tránh chuyển staging lớn về TEMP mặc định |

`inventory.json` lưu byte chính xác, timestamp và snapshot máy; disk/RAM động
không được đưa vào fingerprint ổn định để tránh vô hiệu resume chỉ vì dung lượng đổi.

Các binding hiện có: python-sat 1.9.dev16, OR-Tools 9.15.6755, highspy 1.15.1,
SciPy 1.18.1, gurobipy 13.0.3, cplex 22.2.0.1, docplex 2.32.264.
Matplotlib 3.11.2, pytest 9.1.1. Danh sách đủ **32 distribution** trong environment.json.

Native resource version đọc được: Gurobi DLL **13.0.3.0**, CPLEX DLL **22.2.0.0**.
CP executable thực: `.venv/Scripts/cpoptimizer.exe`; fingerprint có SHA-256 byte
của executable. File này không cung cấp Windows version resource trong lần kiểm;
không chạy nó để hỏi version. Runtime CP đã chạy 22.2.0.0 theo bằng chứng lịch sử
`diagnostics/runtime-integration/cpoptimizer-4.json`; EXP-04 xác nhận khả dụng hiện hành.
highspy/SciPy extension cũng không có version resource: ghi binding version và
hash byte, không suy bản HiGHS nhúng của SciPy từ highspy.

## Fingerprint cho EXP-04/07/10

SHA-256 canonical JSON, schema **sat-expanded-env-v1**:

`c325ecf008027c531d2900dd288813c35386ca0c21ea4e0ac6387b3484ed094e`

- `environment.json`: Python/platform, hash interpreter nền/venv, python313.dll,
  pyvenv.cfg, tên/phiên bản distribution và digest file thực của từng package.
- `installed-files.json`: **7.827 file** đã băm, không chỉ tin hash RECORD; không có
  file RECORD bắt buộc bị thiếu. Loại pyc/pyo để cache không làm đổi fingerprint.
- `native-runtime.json`: **277 DLL/PYD/EXE**, version resource nếu có và SHA-256.
- Hash chính phủ toàn bộ package manifest và native digest. Không có timestamp,
  free space hay RAM khả dụng trong hash. Đường dẫn interpreter là tuyệt đối;
  fingerprint chủ ý dành cho resume cùng môi trường/máy đã khóa.
- Editable source Sudoku không được coi là môi trường; EXP-07 phải freeze/hash
  code/data/config riêng. Không có claim fingerprint gồm toàn bộ Windows DLL
  hoặc toàn bộ thư viện chuẩn Python; scope interpreter/package/native đã nêu.
- Không hash/lưu license key, token hoặc cấu hình xác thực. Việc đọc phiên bản/hash
  không thay preflight license/runtime; EXP-04 vẫn quyết định ma trận khả dụng.

## Dự trù 330.000 lượt (chưa có schema SQLite cuối)

9×9: 240.000; 16×16: 75.000; 25×25: 15.000 lượt. Tổng 100 đợt × 3.300.
`capacity-budget.json` lưu toàn bộ giả định và công thức bằng byte.
Không tạo DB hay dữ liệu giả, không coi đây là kích thước đã đo hoặc giới hạn cứng.

| Thành phần (GiB) | Compact | Planning | Stress |
|---|---:|---:|---:|
| SQLite metadata/index + witness | 2,52 | 4,15 | 12,59 |
| Log | 0,63 | 5,54 | 40,28 |
| Một CSV hiện hành (không chứa witness) | 0,63 | 1,26 | 2,52 |
| Input + witness dataset | 0,08 | 0,08 | 0,08 |
| WAL reservation | 1,00 | 1,04 | 3,15 |
| Một bản sao DB + một lần xuất lại CSV | 3,15 | 5,41 | 15,11 |
| **Tổng kể cả 25% headroom** | **10,01** | **21,86** | **92,16** |

Giả định mỗi attempt: metadata/index 4/8/16 KiB; log 2/16/64 KiB; CSV mỗi job
2/4/8 KiB. Attempt multiplier 1/1,1/2 là dự phòng dung lượng crash/interruption,
**không** cho phép tự retry TIMEOUT/ERROR. Witness mọi attempt được dự trù đầy đủ:
JSON tối đa 4 byte/giá trị + 512 byte envelope, làm tròn 4 KiB; cả bảng 25 vẫn
trong 4 KiB theo giả định này. CSV không nhúng grid; nếu export witness riêng,
runner cần cộng thêm dung lượng. Không lưu CNF từng job hoặc debug dump không giới hạn.

**Planning khoảng 23,47 GB (21,86 GiB) vừa với D: trống 87,99 GB. Stress khoảng
98,95 GB (92,16 GiB) vượt D: trống hiện tại.** Không nhận đủ tài nguyên cho
log/attempt/WAL vô hạn. Sau pilot, EXP-07 đo byte/attempt và WAL thực, số attempt,
độ dài log/export rồi tính lại dự báo; giới hạn log dài và kiểm free space trước đợt.
WAL reservation chỉ là khoản dự phòng: long-lived readers/transaction có thể làm
WAL vượt dự kiến, cần checkpoint policy của runner. Đề xuất dừng nhận job mới khi
free space thấp hơn phần còn lại dự báo + headroom; mức sàn vận hành gợi ý 10 GiB,
để root/EXP-07 chốt theo schema/pilot. Không tự xóa lịch sử attempt để lấy chỗ.
Giữ TEMP/staging của đợt trên D:, snapshot cũ giữ nguyên. Thêm bản sao/ZIP, full
log, xuất witness lặp hoặc phân tích trung gian phải cộng riêng theo policy EXP-10.

## Tái tạo và kiểm evidence

Tại project, dùng interpreter sẵn có (không gọi pip hoặc import solver):

```powershell
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics\expansion\env\inventory.py
& '.\.venv\Scripts\python.exe' -B -X utf8 diagnostics\expansion\env\verify.py
```

Inventory băm package đọc đĩa một lần, không nên lặp khi chưa cần freeze/resume.
Verification kiểm canonical hash/manifest, versions so requirements, ba binary
runtime, arithmetic và sự nhất quán artifacts; không phải correctness/fullsuite.
Evidence `verification.json` ghi kết quả. Không dùng dự trù dung lượng để hứa ETA;
thời gian và số đợt trước hạn chỉ kết luận sau pilot EXP-04/07.

Bàn giao: EXP-04 nhận interpreter/package/native inventory; EXP-07 nhận fingerprint,
disk snapshot/ngân sách/quy tắc tính lại sau pilot; EXP-10 nhận scope freeze và
dung lượng snapshot/export. Chưa tự mở các gói phụ thuộc hoặc nhắn chat khác.
