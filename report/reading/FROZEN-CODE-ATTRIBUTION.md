# REF-002/003 — code/runtime đã freeze

Ngày 16/10/2026. Phạm vi là report citation/attribution gắn với
`results/raw/main-20261016-01/{run.json,execution-freeze.json}`, không phải
audit pháp lý hay tuyên bố lịch sử tác quyền đã được chứng minh tuyệt đối.
`verify-frozen-references.py` chỉ đọc, kiểm 32 hash frozen, requirements và
installed distribution metadata; không import/gọi solver. Kết quả/hash binary
được lưu `../logs/frozen-reference-verification.json`.

## Mã và tài liệu tương ứng

| Mã thực dùng | Nguồn/citation | Cách dùng và attribution |
|---|---|---|
| `src/sudoku/model.py`, `sat.py` | Lynce–Ouaknine 2006; Sinz 2005; `pysat2018`, `pysat-card` | Ô–giá trị, bốn họ EXO; pairwise được dựng bằng combinations; seqcounter/bitwise gọi `CardEnc.atmost(bound=1, top_id=..., encoding=EncType...)`. Không chép encoder C++ vào src. Không đồng nhất bitwise AMO với binary counter Sinz. |
| `src/sudoku/sat.py` | `glucose2009`, `minisat2004`, PySAT | Gọi `pysat.solvers.Glucose3`, không đổi solver giữa ba encoding. Installed wrapper gọi đây là Glucose 3; không có native version API trong evidence, không suy version từ python-sat. |
| `src/sudoku/baselines/cp.py`, `adapters.py` | `cp-sat-doc`, `cplex-cp-doc` | Gọi OR-Tools CpModel/CpSolver và DOcplex.CP CpoModel/CpoSolver. DOcplex private preload `_init_model_in_solver()` được gọi, không sao chép thân hàm; cần kiểm khi nâng interface. |
| `src/sudoku/baselines/ilp.py`, `adapters.py` | `gurobi-manual`, `cplex-python-api`, `highs-python`, `highs2018` | Dựng CSR bằng NumPy/SciPy; truyền cùng ILP sang gurobipy, cplex trực tiếp, highspy. Không dùng DOcplex.MP hay scipy.optimize.milp làm baseline chính. Bài HiGHS dual simplex không được dùng mô tả toàn bộ MIP. |
| `scripts/prepare_data.py`, `prepare_public.py`, `verify_public.py`; `data/source/` | `sudoku-exchange-data` | 20 public lấy hard.txt tại commit d8c8ebaee0c08c412cfba96af1923dfa61c83317; LICENSE/README giữ nguyên ở data/source. Dữ liệu được tái dùng; generator QQWing và bộ phân loại Sukaku Explainer không được sao chép vào code dự án. Uniqueness chưa kiểm. |
| Parser/decoder/checker/runner/CLI và scripts frozen còn lại | Contract nội bộ; Python standard library và dependencies gọi qua API | Kiểm imports, headers, cấu trúc source frozen và handoff liên quan: không nhận diện block source bên thứ ba được chép/adapt kèm nguồn ngoài. Đây là kết luận inspection, không phải lời chứng tác giả về nguồn gốc mọi dòng. Không phát sinh yêu cầu vendor toàn dependency chỉ vì gọi API. |

## Phiên bản đã đối chiếu

| Thành phần | Distribution/interface | Native runtime/evidence |
|---|---|---|
| PySAT / Glucose3 | python-sat 1.9.dev16 | Glucose3 wrapper; native patch/build version không xác lập |
| CP-SAT | ortools 9.15.6755 | OR-Tools packaged CP-SAT; không đặt version độc lập |
| Gurobi | gurobipy 13.0.3 | 13.0.3 trong environment evidence của run.json |
| CPLEX MIP | cplex distribution 22.2.0.1 | 22.2.0.0; installed cplex.__version__ cũng 22.2.0.0 |
| CP Optimizer | docplex 2.32.264 | executable 22.2.0.0; không gọi đây là DOcplex 22.2 |
| HiGHS | highspy 1.15.1 | 1.15.1; không suy HiGHS nhúng SciPy |
| ILP matrix | numpy 2.5.4; scipy 1.18.1 | Chỉ dùng sparse matrix trong adapter chính |

Manual CPLEX Python API official hiện có banner 22.1.2; được cite cho giao diện,
không giả là manual 22.2.0 hay chứng nhận binary đã chạy. DOcplex docs V2.32 khớp
dòng interface 2.32.264. Living docs dùng n.d.; ngày truy cập không thành năm xuất
bản. DOI/năm paper giữ metadata đã kiểm trong reading-notes.md.

## Bản sao thực có và notices

- `reading/evidence/bitwise.hh`, `seqcounter.hh`: bản upstream đọc ở commit
  218c1c163f837c6512d8970e4bdf49ae02cee779. Giữ header credit card/BOLT và
  `PySAT-LICENSE.txt` MIT; không phải source compiler đang được dự án build.
  `PySAT-installed-LICENSE.txt` và `PySAT-installed-METADATA.txt` giữ notice và
  metadata nguyên byte của distribution cài thực. Hash card.py/solvers.py,
  pycard/pysolvers binary được lưu riêng. Không có wheel-to-source build
  provenance; snapshot upstream chưa được coi là binary match. Formula/count
  evidence là kiểm semantics/count, không chứng minh byte identity.
- Sudoku Exchange: bản sao dataset dùng public-domain dedication nguyên bản
  trong `data/source/sudoku-exchange-LICENSE.txt`; không mở rộng sang tool sinh
  hoặc mọi code trên GitHub. Không tạo lại/đổi license dữ liệu.
- Template cas-sc/font/compiler: SOURCES.md, vendor manifest/LPPL/GUST và
  `.tools/tectonic/LICENSE` giữ notice đã sao chép. Không sửa class vendor.
- Không sao chép OR-Tools/Gurobi/CPLEX/HiGHS example source vào report hoặc
  vendor dependency source vào src trong inspection này. Runtime được cài và
  gọi API; gói nộp chưa bao gồm môi trường/native binary. Nếu sau này phân phối
  binary/dependency source, phải giữ notices/điều khoản gói thực phân phối;
  MIT của PySAT wrapper không áp chung bundled engines, IBM hay Gurobi.

## Trạng thái còn chờ

Repository đích đã được người dùng cung cấp:
https://github.com/Ngynkybyrd/2627I_INT3011E . Nội dung hiện ở gói cục bộ,
chưa đồng bộ/publish; chưa xác nhận code/results khả dụng online. REF
citation/attribution không hoàn tất VI-007/DEL-007/PDF-002. Không tự chọn
license cho toàn repository, công bố/nộp hoặc đưa runtime thương mại vào gói.
Findings đã khóa và Results/VI-004/VI-006/EN đã tích hợp; xem scientific report
acceptance và repository-destination evidence hiện hành trong logs/.
