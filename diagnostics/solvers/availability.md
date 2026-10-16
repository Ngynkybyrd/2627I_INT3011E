# Solver runtime probes — SAT04

Ngày kiểm: 16/10/2026 (Việt Nam). Đây là chẩn đoán runtime độc lập, **không phải benchmark, production adapter hoặc kết quả trên C10**.

## Kết quả thực chạy

| Engine | Runtime / binding | Đã giải và checker PASS | Giới hạn thực thấy |
|---|---|---|---|
| Glucose3 | python-sat 1.9.dev16; bundled Glucose3 (không có API version runtime riêng trong probe) | 4×4 | Chưa probe bảng lớn |
| CP-SAT | OR-Tools 9.15.6755 | 4×4, 1 worker | Chưa probe bảng lớn |
| Gurobi | runtime/binding 13.0.3 | 4×4, 9×9; Threads=1 | 16×16: `Model too large for size-limited license` |
| CPLEX MIP | runtime 22.2.0.0; binding cplex 22.2.0.1 | 4×4, 9×9; threads=1 | 16×16: error 1016, Community Edition size limit |
| CP Optimizer | executable runtime 22.2.0.0; docplex 2.32.264 | 4×4, 9×9; Workers=1, EffectiveWorkers=1 | 16×16 và 25×25: Community search space limit `2^1000` |

HiGHS binding highspy 1.15.1 được cài trong môi trường probe nhưng **chưa chạy**, không tính là đã xác nhận khả dụng. BASE vẫn chưa triển khai.

Mỗi probe Sudoku có đúng một clue `(0,0)=1`, các ô còn lại trống. Không dùng dataset chính hoặc bảng đáp án. Checker cục bộ kiểm miền số, hàng, cột, khối và clue; nghiệm MIP phải gần số nguyên trong dung sai 1e-6 và mỗi ô có đúng một giá trị. Không suy ra tính đúng toàn diện từ smoke test này; ca UNSAT/invalid và checker production vẫn phụ thuộc SAT03.

| N | MIP variables N³ | MIP equalities 4N²+1 | CP integer variables | CP constraints 3N+1 |
|---|---:|---:|---:|---:|
| 4 | 64 | 65 | 16 | 13 |
| 9 | 729 | 325 | 81 | 28 |
| 16 | 4096 | 1025 | 256 | 49 |
| 25 | 15625 | 2501 | 625 | 76 |

MIP 25×25 chỉ là số đếm lý thuyết, không gọi solve vì đã vượt giới hạn biến. Giới hạn chính thức Gurobi là 2000 biến/2000 ràng buộc tuyến tính, CPLEX MIP Community là 1000/1000. Với tối đa N² clues, 4×4/9×9 có tối đa 80/405 ràng buộc; mô hình đầy đủ vẫn nằm trong cả hai giới hạn. Cần kiểm C10 thật trước khi nhận LIC-005 hoàn tất. Giới hạn CP phụ thuộc không gian tìm kiếm và mô hình; không suy từ lỗi của bảng ít clue rằng mọi bảng 16×16/25×25 đều bị chặn.

## Cài đặt và tái lập riêng biệt

- Interpreter gốc đọc từ runtime Codex: `C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`, Python 3.12.14 x64.
- Venv riêng: `D:\KHMT\Project solo\tmp\solver-probe\.venv`.
- Temp riêng: `D:\KHMT\Project solo\tmp\solver-probe\temp`.
- Package lấy từ `https://pypi.org/simple`, không thay môi trường chính. `install-network.log` ghi cài thành công; `install.log` ghi lần đầu thất bại DNS trong sandbox.
- `requirements-probe.txt` là freeze riêng; `versions.json` ghi interpreter/binding.
- Cài miễn phí theo lệnh: `<probe-python> -m pip install --index-url https://pypi.org/simple --no-cache-dir gurobipy cplex docplex python-sat ortools highspy`.
- Chạy lại: `& 'D:\KHMT\Project solo\diagnostics\solvers\run-probe.ps1'`.
- Chạy một ca: `<probe-python> -B probe.py cpoptimizer 2 cpoptimizer-4.json` (tham số 2 là cạnh khối n).
- CP executable thực: `D:\KHMT\Project solo\tmp\solver-probe\.venv\Scripts\cpoptimizer.exe` do package IBM cài. Probe chỉ định đường dẫn trực tiếp, không dựa vào PATH.

Mỗi engine/kích thước có JSON kết quả và log cùng tên. JSON lưu count, raw status/error, nghiệm và validation. `diagnostic_seconds` gồm import/build/solve/checker; giới hạn solver là 5 giây, parent guard 25 giây. **Không dùng các thời gian này để so hiệu năng hoặc thay protocol cutoff 10 giây build+setup+solve của runner.** Probe chạy tuần tự, không phải benchmark 906 lượt.

## Giấy phép và việc người dùng cần làm

Không nhập license key, không đăng ký account, không mua hoặc xin academic license. Các bản giới hạn đóng gói đã chạy được trên máy, nên hiện **không cần thao tác đăng nhập của người dùng**. Không có thủ thuật bypass, phân rã bài toán hoặc thay engine. Các lỗi giới hạn được ghi `LICENSE_LIMIT`, không ghi UNSAT/TIMEOUT.

Nguồn chính thức:

- [Gurobi: license size-limited kèm pip/conda và giới hạn](https://support.gurobi.com/hc/en-us/articles/360051597492-How-do-I-resolve-a-Model-too-large-for-size-limited-Gurobi-license-error).
- [IBM: runtime Community qua pip/conda và tìm engine CPLEX/CPO](https://ibmdecisionoptimization.github.io/docplex-doc/getting_started.html).
- [IBM: CPLEX và CP Optimizer runtimes cài bằng pip](https://www.ibm.com/docs/en/icos/22.1.2?topic=rnco2-cplex-python-api-now-installed-using-pip-conda).
- [IBM Community miễn phí, giới hạn MIP và đường tải](https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing).

Nếu môi trường khác cần bộ cài đầy đủ: chọn Community Edition → Try free edition ở trang IBM; chỉ khi trang yêu cầu mới để người dùng tự đăng nhập/chấp nhận điều khoản. Không chọn Developer Subscription. Không cần đường này cho các probe hiện tại.

## Bàn giao task và phần còn thiếu

- LIC-002, LIC-003: đủ bằng chứng probe 4×4/9×9 chạy được và 16×16 bị giới hạn, xem JSON tương ứng.
- LIC-004: đủ bằng chứng tìm/cài executable miễn phí, runtime version, solve 4×4/9×9 và giới hạn riêng CP.
- LIC-001: đã có inventory cả năm engine; Glucose3 ghi phiên bản binding, không bịa phiên bản runtime riêng. Phạm vi chỉ đúng các ca đã chạy trong bảng.
- LIC-005: chưa hoàn tất, cần tập C10 đã khóa và interface/checker; chưa so matched subset dữ liệu chính.
- LIC-006: nhánh tìm thay thế chưa kích hoạt vì runtime miễn phí đã chạy. Không có bằng chứng hoặc giả định tài nguyên trường/lab.
- BASE-001..010: chưa làm theo phạm vi gói độc lập. Cần contract input/result/checker/runner và môi trường chính từ SAT01 trước tích hợp.

Không sửa TODO, STATUS, README, report, pyproject, requirements chung hoặc .venv chính. Không gửi sang chat khác. Các bản miễn phí đã đủ để bắt đầu đối chứng nhỏ khi được giao triển khai; vẫn phải giữ đúng điều kiện sử dụng và rà điều kiện công bố kết quả trước xuất bản benchmark.
