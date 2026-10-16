# SAT01 — Môi trường và thông tin nộp

Ngày kiểm: 16/10/2026, Asia/Saigon. Đây là bằng chứng bootstrap, không phải
kết quả benchmark hoặc kiểm đúng solver Sudoku.

## Thông tin và yêu cầu (REQ)

| ID | Bằng chứng / trạng thái |
|---|---|
| REQ-001 | Đã đối chiếu toàn bộ trang 1 `Assignment 1 - requirements.pdf` và trang 6 `Module 0 - Introduction.pdf`; bảng yêu cầu dưới đây. |
| REQ-002 | Hạn 23:59 ngày 19/10/2026 giờ Việt Nam do người dùng xác nhận; slide chỉ nêu ngày. Chưa thấy quy định tên gói/kênh nộp trong các tài liệu đã đọc. |
| REQ-003 | Tạ Đình Nguyên, 24021587, INT3301E_4; môn Các vấn đề hiện đại KHMT; HK I 2026–2027 theo đề. **Chưa hoàn tất:** tên giảng viên chưa được xác nhận cho bài nộp. Không dùng tên trên slide hoặc bài mẫu để tự điền. |
| REQ-004 | Hai bản Việt–Anh theo lựa chọn người dùng, dùng chung số liệu; chưa thấy đề bắt buộc hai ngôn ngữ. |
| REQ-005 | Đã lập bảng yêu cầu/phạm vi bên dưới; độ phủ thực nghiệm chưa có, phải cập nhật từ kết quả thật. |
| REQ-006 | Thiếu xác nhận giảng viên, tên file/gói, kênh nộp; runtime thương mại do SAT04 kiểm riêng. Không chờ giấy phép học thuật để bắt đầu core. |

| Yêu cầu từ đề / lựa chọn | Đầu ra cần có / phạm vi dự kiến |
|---|---|
| Bài cá nhân Sudoku | Python, PySAT/Glucose3; `n>=2`, `N=n²`. |
| Thực nghiệm bảng lớn | 4×4, 9×9, 16×16, 25×25; không hứa tất cả solver đều hỗ trợ mọi cỡ. |
| Nhiều AMO (khuyến khích) | Pairwise, sequential counter, bitwise; S80, 3 lần lặp. |
| Đối chứng CP-SAT, Gurobi, CPLEX MIP/CP theo đề | CP-SAT/HiGHS trên B16; Gurobi/CPLEX trên C10/tập giao runtime thực tế. SAT04 xác minh bản miễn phí/Community và `LICENSE_LIMIT` riêng. |
| Báo cáo bài báo | Elsevier `cas-sc`, tùy chọn `a4paper,fleqn`; nguồn và hai PDF Việt–Anh. |
| Data Availability | URL repository thật chứa mã/kết quả; chưa có URL công bố ở bước này. |
| Tái lập | Dependency list, data/cách lấy, CSV/config, bảng/hình, README, nguồn LaTeX. |

Đề gốc: `D:\KHMT\Tài liệu\Assignment 1 - requirements.pdf`.
Lịch: `D:\KHMT\Tài liệu\Module 0 - Introduction.pdf`, trang 6.
Kế hoạch hiện hành: S80/B16/C10, 906 lượt dự kiến, 3 repetitions,
cutoff 10 giây build+setup+solve; trần 2 giờ 31 phút chưa gồm overhead.
Không có benchmark nào được chạy trong SAT01.

## Interpreter, máy và dependency (ENV-001/002/005)

- Interpreter nền: `C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe`, Python 3.13.5 x64.
- Interpreter dự án: `D:\KHMT\Project solo\.venv\Scripts\python.exe`.
- `.venv/pyvenv.cfg`: `include-system-site-packages = false`; smoke ghi `prefix != base_prefix`.
- OS: Windows 11, 10.0.26300, AMD64.
- CPU: AMD Ryzen 7 H 260 w/ Radeon 780M Graphics; 16 logical CPUs.
- RAM vật lý đọc qua `GlobalMemoryStatusEx`: 33.618.251.776 byte (~31,31 GiB).
- Các alias `python`/`py` ban đầu không hoạt động/không nhận interpreter; dùng đường dẫn tuyệt đối.

| Package / engine | Phiên bản đã chạy |
|---|---|
| python-sat / Glucose3 | 1.9.dev16; native Glucose3 không có version API được dùng trong probe, không tự gán số bản engine |
| OR-Tools / CP-SAT | 9.15.6755 |
| SciPy / MILP HiGHS nhúng | SciPy 1.18.1; không suy ra phiên bản engine nhúng từ highspy |
| highspy / HiGHS | 1.15.1 / engine 1.15.1 |
| Matplotlib | 3.11.2 |
| pytest | 9.1.1, đã cài; không chạy test suite Sudoku chưa tồn tại |
| NumPy | 2.5.4 |
| pip / setuptools | 25.1.1 / 84.0.0 |

Toàn bộ dependency gián tiếp được khóa trong `requirements.txt`.
Package `sudoku-sat-btl1==0.1.0` cài editable từ `pyproject.toml`;
`import sudoku` trỏ đúng `src/sudoku/__init__.py` của dự án.
Không thêm editable local path vào requirements để tránh khóa theo máy.

## Smoke thực chạy (ENV-004 và phần HiGHS của ENV-003)

```powershell
& '.\.venv\Scripts\python.exe' -m pip install --no-build-isolation --no-deps -e .
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -X utf8 diagnostics\smoke_environment.py
```

- Editable install: thành công; `pip check`: **No broken requirements found**.
- Glucose3: `[x]` SAT và nghiệm chứa x; `[x] ∧ [¬x]` UNSAT: PASS.
- CP-SAT: biến Boolean `x=1`: OPTIMAL, nghiệm 1; thêm `x=0`: INFEASIBLE. `num_search_workers=1`.
- SciPy MILP: biến nhị phân `0<=x<=1`, `x>=1`: status 0 và nghiệm 1; `x>=2`: status 2.
- highspy: cùng ca MILP, `kOptimal`/`kInfeasible`; đặt và đọc lại `threads=1` thành công.
- HiGHS direct được chọn cho khả năng điều khiển số luồng rõ ràng. Smoke SciPy không chứng minh SciPy chạy một luồng; adapter baseline phải dùng cơ chế đã kiểm.
- Matplotlib Agg: xuất `diagnostics/smoke_plot.png`, đã xem trực quan, không cắt nhãn.
- Ghi/đọc UTF-8 trong tên đường dẫn tiếng Việt có dấu cách: PASS; file probe tự xóa sau kiểm.
- Kết quả máy đọc được: `diagnostics/smoke_results.json`; lỗi/assert làm script exit khác 0.

## Cấu trúc, UTF-8 và tái cài (ENV-006/007/008)

Đã tạo `src/sudoku`, `tests`, `data`, `results`; `report/` chỉ bảo đảm thư mục
tồn tại, SAT09 sở hữu toàn bộ nội dung. SAT01 không tạo core Sudoku.

`.gitignore` bỏ qua `.venv`, cache Python/pytest/Matplotlib, `.tmp`, egg-info,
build artifacts và file trung gian LaTeX; giữ dữ liệu/kết quả/PDF cần nộp.
README ghi lệnh PowerShell, kích hoạt tùy chọn, `PYTHONUTF8=1`, `-X utf8`,
đường dẫn có dấu cách và cài lại từ requirements. Không thay execution policy,
Python hệ thống hoặc runtime Codex dùng chung.

Lỗi thiết lập đã xử lý: ensurepip gặp quyền ghi tại TEMP sandbox, chuyển TEMP/TMP
của process sang `.tmp` trong dự án rồi thành công. Tải PyPI trong sandbox bị DNS;
lệnh tải dependency được chạy với quyền mạng được duyệt và hoàn tất.

## Ranh giới còn lại

**Cập nhật sau bootstrap:** chat điều phối đã nghiệm thu ENV-003 theo probe SAT04.
SAT01 đã tích hợp đúng ba binding vào `.venv` chính, không đổi phiên bản core,
và kiểm lại ba runtime trên 4×4; xem `environment-integration.md` cùng JSON/log
trong `runtime-integration/`. Đây là tích hợp bổ sung, không tính thêm task.
Chưa xác nhận toolchain LaTeX;
SAT09 sở hữu. Thiếu các thông tin nộp nêu trong REQ-003/006 không chặn môi trường.

SAT01 không sửa SAT-TODO/SAT-STATUS; chat điều phối cập nhật checkbox theo bằng chứng.
