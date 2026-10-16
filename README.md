# Sudoku SAT — BTL1 cá nhân

Chương trình Python cho Sudoku tổng quát, dùng mô hình Boolean ô–giá trị và
ba AMO encoding: `pairwise`, `seqcounter`, `bitwise`. Parser, mapping, CNF,
production adapters và CLI đã được kiểm riêng. Benchmark chính đã chạy và được
phân tích; số liệu/phạm vi được tóm tắt trong phần Trạng thái bàn giao.

Sinh viên: Tạ Đình Nguyên — 24021587 — INT3301E_4.
Môn: Các vấn đề hiện đại KHMT; học kỳ I, năm học 2026–2027.
Hạn do người dùng xác nhận: **23:59 ngày 19/10/2026, Asia/Saigon**.
Giảng viên: TS. Tô Vân Khánh. Repository công khai: [Ngynkybyrd/2627I_INT3011E](https://github.com/Ngynkybyrd/2627I_INT3011E), nhánh `main`, khởi tạo tại commit `f45d37894cfb19fe3bb890e8f0e06f13b472c2a2`. Kênh/quy cách nộp chưa xác nhận; việc nộp bài vẫn hoãn.

## Cài đặt (Windows PowerShell, Python 3.13)

Không cần thay Python hệ thống hoặc kích hoạt môi trường để chạy các lệnh:

```powershell
Set-Location 'D:\KHMT\Project solo'
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
$env:TEMP = (Resolve-Path .tmp).Path
$env:TMP = $env:TEMP
& 'C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' -m pip install --no-build-isolation --no-deps -e .
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -X utf8 diagnostics\smoke_environment.py
```

Tuỳ chọn kích hoạt trong PowerShell: `. .\.venv\Scripts\Activate.ps1`.
Nếu execution policy chặn script, dùng đường dẫn Python trực tiếp như trên;
không cần đổi policy toàn máy. Trên máy khác, thay đường dẫn interpreter
bằng Python 3.13 đã cài. `requirements.txt` khoá cả dependency gián tiếp;
môi trường đã kiểm là Windows x64/Python 3.13.5.

`highspy` được dùng để điều khiển và đọc lại `threads=1` qua API trực tiếp.
SciPy MILP cũng được smoke riêng; không suy ra bản HiGHS nhúng trong SciPy
đồng phiên bản hoặc cùng cấu hình với `highspy`.

## Phạm vi và cấu trúc

- `src/sudoku/model.py`: `Puzzle`, parser JSON, mapping ID và bốn họ EXO.
- `src/sudoku/sat.py`: `encode_amo`, `build_cnf` và số đếm trước preprocessing;
  `build_cnf` dựng CNF, không tự giải Sudoku.
- `docs/contracts.md`: contract v1 về input, CNF, checker/result và thời gian.
- `tests/`, `data/`, `results/`: bộ kiểm, dữ liệu đóng băng, raw run và summary đã audit.
- `report/`: nguồn `cas-sc`, bibliography, bảng/hình, báo cáo Việt–Anh và PDF hiện hành.
- `diagnostics/`: bằng chứng môi trường, chạy benchmark, kiểm dữ liệu và report.

Quy ước chung: `n >= 2`, `N=n²`, bảng `N×N`, khối `n×n`, `0` là ô trống.
Ba AMO: pairwise, sequential counter, bitwise; SAT dùng Glucose3. Kế hoạch hiện
hướng tới 80 đề, ba lần lặp và cutoff 10 giây build+setup+solve. Tập mỗi solver
có thể khác nhau do giới hạn runtime; chỉ benchmark runner mới tạo kết quả so
sánh; benchmark chính đã chạy theo cấu hình khóa và có audit final.

`requirements.txt` khóa dependency đầy đủ cho môi trường đã kiểm: Python 3.13.5
x64 trên Windows, gồm `python-sat==1.9.dev16`, `ortools==9.15.6755`,
`gurobipy==13.0.3`, `cplex==22.2.0.1`, `docplex==2.32.264`,
`highspy==1.15.1`, `scipy==1.18.1`, `matplotlib==3.11.2` và `pytest==9.1.1`,
cùng các dependency gián tiếp đã pin. Các lệnh cài ở phần trên dùng file này.
Không cần cài binding riêng lần nữa trong môi trường mới.

Gurobi, CPLEX MIP và CP Optimizer đã được SAT04 probe riêng; production
adapters và CLI cũng đã tích hợp. Lệnh kiểm tích hợp ban đầu trong môi trường
đã bootstrap là:

```powershell
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --only-binary=:all: gurobipy==13.0.3 cplex==22.2.0.1
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --no-build-isolation docplex==2.32.264
& '.\.venv\Scripts\python.exe' -X utf8 diagnostics\runtime-integration\run_integration.py
```

Script tích hợp dùng snapshot `packages-before.json` đã lưu để kiểm không đổi
phiên bản cũ và gọi nguyên bản probe SAT04 chỉ trên 4×4. Trên máy khác,
cài đầy đủ từ requirements rồi chạy từng probe trực tiếp nếu không dùng snapshot:

```powershell
& '.\.venv\Scripts\python.exe' -B diagnostics\solvers\probe.py gurobi 2 diagnostics\runtime-integration\gurobi-4.json
& '.\.venv\Scripts\python.exe' -B diagnostics\solvers\probe.py cplex 2 diagnostics\runtime-integration\cplex-4.json
& '.\.venv\Scripts\python.exe' -B diagnostics\solvers\probe.py cpoptimizer 2 diagnostics\runtime-integration\cpoptimizer-4.json
```

CP executable được tìm theo `sys.prefix` của máy chạy, không hard-code ổ D.
Chi tiết các giới hạn bản miễn phí và phạm vi đã probe nằm ở
[diagnostics/solvers/availability.md](diagnostics/solvers/availability.md).
Tóm tắt probe: Gurobi 13.0.3 và CPLEX 22.2.0.0/`cplex` 22.2.0.1 giải 4×4,
9×9; mô hình đầy đủ 16×16 bị giới hạn kích thước trong cả hai. CP Optimizer
22.2.0.0/DOcplex 2.32.264 giải 4×4, 9×9; probe cụ thể 16×16 và 25×25 gặp giới
hạn search space Community `2^1000`. Đây là phạm vi ca đã probe, không khẳng
định mọi Sudoku ở kích thước đó đều bị chặn. CP-SAT đã solve 4×4, 9×9, 16×16,
25×25; HiGHS đã solve 4×4, 9×9, 16×16, 25×25 trong smoke production adapter.
Các probe/smoke không phải benchmark.
Chi tiết tích hợp: [diagnostics/environment-integration.md](diagnostics/environment-integration.md).

Yêu cầu bài nộp gồm chương trình Python, thực nghiệm bảng lớn và đối chứng, báo cáo `cas-sc` (`a4paper,fleqn`), và Data Availability. Hai bản Việt–Anh dùng chung số liệu. Commit công khai `f45d37894cfb19fe3bb890e8f0e06f13b472c2a2` đã được đối chiếu đủ 1.384 blob với snapshot local, gồm source, data, raw results, summary, report và PDF của snapshot đó. Các cập nhật README và final report/provenance hiện hành sẽ đồng bộ sau final QA. Gói bàn giao cần dependency list, dữ liệu/cách lấy, CSV/config, bảng/hình, README, nguồn LaTeX, hai PDF và URL repository. Việc nộp LMS vẫn hoãn.

Nguồn đối chiếu: `D:\KHMT\Tài liệu\Assignment 1 - requirements.pdf` (1 trang)
và `D:\KHMT\Tài liệu\Module 0 - Introduction.pdf` (trang 6: hạn 19/10/2026).
Giờ đóng cổng 23:59 lấy từ xác nhận người dùng, không suy ra từ slide.
Chi tiết môi trường và bằng chứng: [diagnostics/environment.md](diagnostics/environment.md).

## Input JSON và kiểm parser

Với `n` nguyên và `n >= 2`, cạnh bảng là `N = n*n`; `grid` có đúng `N` hàng,
mỗi hàng `N` số nguyên trong `0..N`. `0` là ô trống. Boolean, số thực và chuỗi
không được nhận thay số nguyên. Các trường metadata thêm được bỏ qua. Parser
không yêu cầu uniqueness; clues xung đột nhưng đúng cấu trúc vẫn được nhận để
solver chứng minh UNSAT sau này.

Ví dụ 4×4 dưới đây có 8 clues; chỉ dùng kiểm parser, chưa là một lượt solve:

```json
{
  "n": 2,
  "grid": [
    [1, 0, 0, 4],
    [0, 4, 1, 0],
    [2, 0, 4, 0],
    [0, 3, 0, 1]
  ]
}
```

Chạy nguyên lệnh PowerShell sau từ thư mục dự án; không cần tạo file dữ liệu:

```powershell
@'
{"n":2,"grid":[[1,0,0,4],[0,4,1,0],[2,0,4,0],[0,3,0,1]]}
'@ | & '.\.venv\Scripts\python.exe' -B -X utf8 -c "import sys; from sudoku.model import parse_json; p=parse_json(sys.stdin.read()); print(f'PARSER_OK N={p.N} clues={p.clue_count}')"
```

Kết quả parser đã kiểm: `PARSER_OK N=4 clues=8`. Ví dụ CLI dưới đây dùng trực
tiếp đề 4×4 `data/synthetic/synthetic-N04-p30-s0.json`, cũng có trong
`data/manifest.json`. Nếu lưu JSON riêng, API hiện có là `load_puzzle(path)`;
lỗi file/UTF-8/JSON/shape/domain ném `InvalidInputError`, với `.status ==
SolveStatus.INVALID_INPUT`.

## Chạy CLI cho một đề

Từ thư mục dự án, với `.venv` đã cài theo `requirements.txt`, các lệnh sau chạy
một đề 4×4 bằng ba SAT encoding và năm baseline. CLI in JSON-compatible result
ra stdout, bảng nghiệm/thông tin dễ đọc ra stderr; `--json-output` có thể lưu
bản JSON vào file. Không đặt `--encoding` cho baseline.

```powershell
$puzzle = 'data\synthetic\synthetic-N04-p30-s0.json'
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method sat --encoding pairwise --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method sat --encoding seqcounter --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method sat --encoding bitwise --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method cpsat --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method gurobi --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method cplex_mip --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method cpoptimizer --cutoff 10
& '.\.venv\Scripts\python.exe' -B -m sudoku $puzzle --method highs --cutoff 10
```

`--help` liệt kê method/encoding được parser chấp nhận. Trong CLI một đề,
`--cutoff` dùng giới hạn native/cooperative của adapter và không tự dừng cứng
Windows process tree. Benchmark runner có guard process-tree riêng (Windows Job
Object) cùng guard startup/postprocessing; xem [docs/runner-api.md](docs/runner-api.md).
Benchmark execution vẫn cần qua gate review/pilot/config lock bên dưới.
Trạng thái `LICENSE_LIMIT` (vượt giới hạn miễn phí) khác `TIMEOUT`; không tính
trường hợp đó là đã chạy hết thời gian.

Đã kiểm `--help` và một lần chạy SAT bằng đường dẫn có dấu cách
`diagnostics/cli/puzzle with spaces.json`; kết quả `SAT`, checker hợp lệ. Lệnh
đã kiểm:

```powershell
& '.\.venv\Scripts\python.exe' -B -m sudoku 'diagnostics\cli\puzzle with spaces.json' --method sat --encoding seqcounter --cutoff 5
```

Output và lệnh đầy đủ được lưu tại [diagnostics/readme/cli-smoke.md](diagnostics/readme/cli-smoke.md).

## Kiểm tra dữ liệu, chạy benchmark và phân tích

Các lệnh dưới đây chạy từ thư mục gốc dự án. Trước khi cài lại môi trường,
dùng các lệnh kiểm đóng băng dữ liệu (chỉ so sánh, không ghi hoặc solve):

```powershell
& '.\.venv\Scripts\python.exe' -B '.\scripts\prepare_data.py' --check
& '.\.venv\Scripts\python.exe' -B '.\scripts\verify_public.py' --check
```

`prepare_data.py` không có `--check` sẽ dựng các tệp dữ liệu bị thiếu; chỉ dùng
khi chủ động chuẩn bị lại dữ liệu trong checkout. `verify_public.py` không có
`--check` gọi SAT để kiểm 20 đề public và không phải lệnh kiểm read-only.

Chạy toàn bộ tests bằng pytest; dùng basetemp mới trong workspace để tránh temp
directory hệ thống không ghi được:

```powershell
$testTemp = Join-Path '.tmp' ("pytest-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& '.\.venv\Scripts\python.exe' -B -m pytest -q -p no:cacheprovider --basetemp $testTemp '.\tests'
```

Runner chỉ chuẩn bị kế hoạch theo mặc định. Chọn một output path chưa tồn tại;
lệnh chuẩn bị không gọi solver:

```powershell
$run = 'results\benchmark run new'
& '.\.venv\Scripts\python.exe' -B '.\scripts\run_benchmark.py' --config '.\configs\benchmark.json' --output $run
```

Kiểm tra `run.json` và `schedule.json`, rồi chỉ thêm `--execute` sau khi gate
hard-guard, pilot và khóa cấu hình đã được chấp thuận. Lệnh execute thật sự gọi
solver; có thể giới hạn bằng `--job-ids <file.json>` chứa danh sách job ID thuộc
schedule đã chuẩn bị. Handoff prepare-only đã tạo 906 job, không chạy solver;
đây không phải pilot hoặc benchmark. Mỗi lần chạy/đợt bổ sung cần output path
mới, theo [docs/runner-api.md](docs/runner-api.md) và
[docs/results-schema.md](docs/results-schema.md).

Phân tích chỉ nhận thư mục runner thật. `--output` phải là thư mục mới, riêng
khác thư mục `--run`; analyzer kiểm kết quả, không gọi solver. Thay hai giá trị
đường dẫn mẫu bằng run thật và output duy nhất:

```powershell
$run = 'results\benchmark run id'
$analysis = 'results\analysis pilot new'
& '.\.venv\Scripts\python.exe' -B '.\scripts\analyze_results.py' --run $run --output $analysis --mode pilot
```

Dùng `--mode partial` cho đợt chạy gián đoạn và `--mode final` chỉ khi toàn bộ
schedule được chọn có đủ ba lần lặp. Có thể lặp `--run` cho các đợt disjoint
cùng code, máy, package, dataset, cutoff, seed và watchdog. Analyzer sinh CSV, LaTeX, audit và hình từ run artifacts đã kiểm. Benchmark chính `main-20261016-01` đã chạy đủ 906 lượt và summary ở mode `final` đã được audit. Lệnh `--mode pilot` phía trên chỉ là ví dụ API cho một phân tích pilot mới, không phải lệnh tạo summary final hiện hành.

## Build hai PDF

Toolchain LaTeX portable và cache package/font nằm riêng dưới `report/.tools`.
Đã build sạch hai bản bằng Tectonic 0.17.0, không cần đổi môi trường Python:

```powershell
& '.\report\build.ps1' -Offline
```

Output hiện hành: `report/output/pdf/sudoku-vi.pdf` và
`report/output/pdf/sudoku-en.pdf`, mỗi bản 10 trang. Acceptance record xác nhận
PDF-001/PDF-003 và VI-004/VI-006, EN-001..004 đạt. Snapshot initial commit đã chứa và đối chiếu hash các PDF cùng source/data/raw/summary. README và final report/provenance revisions mới sẽ đồng bộ, xác minh sau final QA; các prototype cũ là lịch sử.
Trên máy chưa có toolchain/cache, chạy bootstrap và một lần build online:

```powershell
& '.\report\bootstrap.ps1'
& '.\report\build.ps1'
```

Bootstrap tải compiler/template miễn phí chính thức trong `report/`; lần build
online tải dependency TeX. Hướng dẫn/font/giấy phép và kiểm PDF:
[report/BUILD.md](report/BUILD.md). Script
`report/export_model_counts.py` chỉ đọc diagnostics để sinh bảng đếm CNF,
không gọi solver hoặc chạy lại benchmark.

## Status contract

Các adapter và CLI đã được tích hợp; bảng trạng thái mô tả contract chung.
`SolveResult.to_dict()` xuất JSON-compatible; giá trị đo còn thiếu là `None`
trong Python / `null` trong JSON, không tự điền bằng 0.

| Status | Ý nghĩa |
|---|---|
| `SAT` | Có nghiệm được checker độc lập chấp nhận; adapter/runner còn phải bảo đảm tìm trong cutoff. Contract từ chối SAT thiếu nghiệm hoặc validation thành công. |
| `UNSAT` | Solver chứng minh không có nghiệm, gồm cả input đúng cấu trúc nhưng clues mâu thuẫn. |
| `TIMEOUT` | Hết ngân sách build + setup/nạp solver + solve; không suy ra UNSAT. |
| `ERROR` | Lỗi chạy/giải mã/checker hoặc nguyên nhân lỗi khác; giữ thông báo và raw status khi có. |
| `INVALID_INPUT` | Lỗi đọc file, UTF-8, JSON, cấu trúc, kiểu hoặc miền input. |
| `UNAVAILABLE` | Thiếu backend/runtime cần thiết. |
| `LICENSE_LIMIT` | Mô hình vượt phạm vi giấy phép được dùng; báo riêng với TIMEOUT. |

Method IDs: `sat`, `cpsat`, `gurobi`, `cplex_mip`, `cpoptimizer`, `highs`.
Chỉ `sat` có tên AMO encoding; baseline không có SAT CNF stats. Raw status gốc
được giữ; trạng thái unknown/interrupted không được chuyển tùy tiện sang UNSAT.
Checker là thành phần riêng, không dùng chính encoder để tự xác nhận nghiệm.
Ranh giới đo của adapter gồm build + setup + solve; imports/đọc input và
validation/I/O ở ngoài phần đo chính. CLI giải từng đề với native/cooperative
cutoff; runner dùng hard Windows process-tree guard khi chạy schedule, còn
`analyze_results.py` sinh bảng/hình từ run artifacts đã kiểm.


## Trạng thái bàn giao

Run `main-20261016-01` có 906 lượt (903 SAT, 3 TIMEOUT, đều là HiGHS).
Summary final được audit; chi tiết scope và giới hạn solver nằm trong
`diagnostics/package/compliance-brief.md`. Repository công khai là
[Ngynkybyrd/2627I_INT3011E](https://github.com/Ngynkybyrd/2627I_INT3011E),
nhánh `main`, có commit khởi tạo `f45d37894cfb19fe3bb890e8f0e06f13b472c2a2`.
Source/data/raw results/summary/report/PDF trong snapshot initial commit đã được
đối chiếu hash với repository. README và final report/provenance revisions mới
chờ đồng bộ sau final QA. Gói bàn giao và việc nộp LMS vẫn hoãn.
