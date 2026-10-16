# SAT01 — Tích hợp runtime thương mại vào môi trường chính

Ngày 16/10/2026, Asia/Saigon. Tiếp nối ENV-003 đã được chat điều phối nghiệm thu
từ probe SAT04; không phát sinh task hoàn tất mới, không benchmark chính.

## Thay đổi môi trường

Giữ nguyên `.venv`, Python 3.13.5 và mọi phiên bản package đã tồn tại.
Thêm chính xác `gurobipy==13.0.3`, `cplex==22.2.0.1`, `docplex==2.32.264`.
Hai runtime native có wheel `cp313-cp313-win_amd64`; docplex là Python thuần,
đã build thành wheel `py3-none-any` bằng setuptools hiện có, không thêm build
dependency. Cả hai lệnh cài dùng `--no-deps`; không upgrade/downgrade core.

```powershell
$env:PYTHONUTF8 = '1'
$env:TEMP = 'D:\KHMT\Project solo\.tmp'
$env:TMP = $env:TEMP
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --only-binary=:all: gurobipy==13.0.3 cplex==22.2.0.1
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --no-build-isolation docplex==2.32.264
& '.\.venv\Scripts\python.exe' -X utf8 diagnostics\runtime-integration\run_integration.py
& '.\.venv\Scripts\python.exe' -m pip freeze --exclude sudoku-sat-btl1
```

Freeze cuối được lưu trong `requirements.txt`, không chứa editable path theo máy.
Lệnh tái cài sạch nằm trong README; không dùng lệnh tạo venv trên môi trường
đang chạy. `pyproject.toml` giữ nguyên và đọc dependencies từ requirements.

## Bằng chứng runtime

Script tích hợp gọi nguyên bản `diagnostics/solvers/probe.py` của SAT04 qua
subprocess với tham số engine, `n=2`, đường dẫn output riêng. Không sửa script
nguồn; SHA-256 nguồn được lưu trong `runtime-integration/summary.json`.
Mỗi ca có solver limit 5 giây, parent guard 25 giây; thời gian diagnostics
không thuộc protocol benchmark 10 giây build+solve.

| Engine | Binding | Runtime | Kết quả 4×4 |
|---|---|---|---|
| Gurobi | gurobipy 13.0.3 | 13.0.3 | SAT, validation PASS, Threads=1 |
| CPLEX MIP | cplex 22.2.0.1 | 22.2.0.0 | SAT, validation PASS, threads=1 |
| CP Optimizer | docplex 2.32.264 | 22.2.0.0 | SAT, validation PASS, EffectiveWorkers=1 |

CP executable thực: `D:\KHMT\Project solo\.venv\Scripts\cpoptimizer.exe`.
Khi triển khai adapter, tìm theo `Path(sys.prefix) / 'Scripts' / 'cpoptimizer.exe'`
trên Windows và truyền `execfile` trực tiếp; không phụ thuộc PATH.

Ca probe có một clue `(0,0)=1`. MIP: 64 biến nhị phân/65 equality; CP: 16 biến
nguyên/13 constraints. Checker cục bộ SAT04 kiểm hàng/cột/khối/clue và tính
nguyên của MIP. Không suy ra độ đúng toàn diện hoặc độ phủ C10 từ smoke này.

- `runtime-integration/packages-before.json` và `packages-after.json`: không package
  đã tồn tại nào đổi phiên bản; `existing_versions_changed: []` trong summary.
- `runtime-integration/pip-check.txt`: `No broken requirements found.`
- `runtime-integration/{gurobi,cplex,cpoptimizer}-4.json` và `.log`: kết quả riêng.
- `runtime-integration/summary.json`: interpreter, binding/runtime, executable và hash nguồn.

Không tài khoản, mua dịch vụ, license key hay license đầy đủ. Giới hạn miễn phí
giữ theo `diagnostics/solvers/availability.md`; lượt này chỉ kiểm 4×4 trong môi
trường chính. Không chỉnh src/tests/report/data hoặc tài liệu điều phối.
Chưa có dependency blocker cho adapter dùng ba runtime này trên ca nhỏ.
