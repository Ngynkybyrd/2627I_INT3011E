# Chạy thực nghiệm mở rộng trên máy local

Tài liệu này chỉ mô tả pipeline schema v2. Nó không nhập, gộp hay sửa run cũ
`S80/B16/C10` và 906 kết quả. Contract chính thức vẫn là
[expanded-contract.md](expanded-contract.md); giao diện owner hiện tại được
chuyển tiếp nguyên trạng, không tạo gate thay SAT03/05/07/08/09 hoặc root.

## Trạng thái tích hợp

- `scripts/run_expanded.py` có `prepare`, `pilot`, `run`, `status`, `resume`,
  `export`; `src/sudoku/expanded_runner.py` sở hữu validator, SQLite, locks,
  gates và worker. CLI không tự chấp thuận gate.
- `scripts/analyze_expanded.py` nhận immutable schema-2 export; nó không solve.
- `scripts/prepare_expanded_data.py` hiện có `stage-inputs` với `--output` cho
  main/pilot DRAFT datasets; top-level help khẳng định không giải witness hoặc
  freeze. `-StageInputs` chỉ gọi command này rồi xác minh cả hai dataset bằng
  `verify-inputs` (`PASS_INPUTS_ONLY`, `solver_calls=0`, `frozen=false`).
  `generate` tìm witness public bằng SAT nên
  không được dùng làm fallback.
- Report preparer hiện có ở `report/prepare_expanded_report.py`, nhận
  `--analysis`, `--output`, `--analysis-receipt`, và `--receipt-sha256`.
  Pipeline dùng `analysis-hashes.json` sau analysis, tự tính SHA-256 và chuyển
  cho preparer. Receipt bảo toàn artifact; nó không thay gate hoặc điều kiện
  `report_ready`.
- `prepare`, worker, export, analysis và report tích hợp thật vẫn cần các cổng
  owner/root đang chờ trong `docs/expanded-acceptance.md`. `--help`, doctor và
  dry-run không thay thế gate nghiệm thu.

## Lệnh local

Chạy ở PowerShell từ project root. Không truyền action thì chỉ chạy doctor đọc
config, module, cache/dataset path, disk còn trống và cấu hình matrix; không cài
package, gọi network, đọc secret value, ghi dataset, hay gọi solver.

```powershell
& '.\scripts\local_expanded_pipeline.ps1'
& '.\scripts\local_expanded_pipeline.ps1' -DryRun -StageInputs
& '.\scripts\local_expanded_pipeline.ps1' -DryRun -Prepare -Phase main
```

Khi command SAT05 đã có và help/receipt chứng minh không solve, action riêng
`-StageInputs` lưu nguồn/puzzle draft dưới `data/expanded-inputs/draft-*`, ngoài
`data/expanded/<dataset_id>` đóng băng. Nó phải trả DRAFT, `solver_calls=0`,
`frozen=false`; không có witness admission và không được đưa cho runner.
Không chạy `prepare_expanded_data.py generate` từ wrapper staging vì bước đó
solve witness public. Dataset được witness/validate/freeze là bước khác, theo
SAT05 và cổng root.

Prepare chỉ kiểm dataset/config/matrix rồi tạo experiment mới, chưa chạy worker:

```powershell
& '.\scripts\local_expanded_pipeline.ps1' -Prepare -Phase main `
  -Dataset '.\data\expanded\expanded-20261019-v2' `
  -Experiment '.\results\expanded\main-20261019-a' `
  -Config '.\configs\expanded\main.json' `
  -Matrix '.\configs\expanded\matrix.json'
```

Tên experiment/output không được ghi đè; dùng thư mục mới cho lần prepare/export/
analysis khác. Doctor/preflight đòi matrix 8 cấu hình N9, 5 cấu hình N16, 5 cấu
hình N25, cutoff 10 giây, 3 rep main/1 rep pilot, tất cả thread=1; phạm vi dự
kiến là 330.000 lượt main và 164 lượt pilot. Matrix lệch thì dừng, không tự
chuẩn hóa hoặc bỏ solver.

## Worker, checkpoint và status

Chỉ các lệnh dưới đây mới yêu cầu execute rõ ràng, và root gates trong manifest
phải được chấp thuận trước khi runner khởi tạo worker:

```powershell
& '.\scripts\local_expanded_pipeline.ps1' -Pilot -Experiment '.\results\expanded\pilot-a'
& '.\scripts\local_expanded_pipeline.ps1' -Run -Experiment '.\results\expanded\main-a'
& '.\scripts\local_expanded_pipeline.ps1' -Status -Experiment '.\results\expanded\main-a'
& '.\scripts\local_expanded_pipeline.ps1' -Resume -Experiment '.\results\expanded\main-a' `
  -Reason 'operator-provided recovery reason'
```

`-Pilot`, `-Run`, `-Resume` không có cờ bypass. Runner kiểm tra gate subject,
hash, cleanup/fingerprint và lock; thiếu/sai gate thì không launch. Default
`StopStartingAt` là `2026-10-19T22:30:00+07:00`; có thể truyền mốc session khác
được audit. Hard timeout và process-tree cleanup nằm ở runner. Timeout/Error
là terminal observations, không tự retry để chọn số thuận lợi. Chỉ Resume explicit
mới xử lý job PENDING/INTERRUPTED đủ điều kiện; giữ toàn bộ attempt history.

`-Status` gọi snapshot read-only: số job/trạng thái, block execution/QA-complete,
active attempt, elapsed wall, disk DB/WAL/log, recent-rate ETA và coverage của ETA.
ETA null/partial thì nói rõ, không hứa deadline. `-Run` và main `-Resume` sau
khi tiến trình đã dừng sẽ tự export `--complete-blocks` nếu có QA-complete block,
rồi gọi analyzer. Không có block thì giữ raw/checkpoint, không tạo báo cáo giả.
Analysis incomplete/pilot/artificial giữ nhãn tương ứng; report preparer chỉ chạy
khi summary nói `report_ready=true`, `phase=main`, `artificial=false`.

Mỗi action ghi log vào `diagnostics/expansion/package/local-pipeline/` và giữ một
OS-exclusive local action lock; không xoá lock theo tuổi hoặc chạy generation,
prepare, benchmark cùng lúc. Trước worker, wrapper kiểm reserve từ config (mặc
định 1 GiB); runner kiểm lại trước claim. Không lưu CNF từng lượt.

Prepare và worker cùng đặt `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`,
`MKL_NUM_THREADS`, `NUMEXPR_NUM_THREADS` thành `1` **chỉ trong tiến trình con**,
rồi khôi phục environment của PowerShell. Như vậy fingerprint lúc prepare trùng
môi trường run/resume; kiểm mismatch của runner vẫn bật. Tất cả Python command
dùng environment đã cài sẵn, không tự cài package. Không chạy tiến trình AI theo
đề và không dùng automation.

## Export, phân tích, report

Post-run dùng thư mục mới:

```powershell
& '.\scripts\local_expanded_pipeline.ps1' -Export `
  -Experiment '.\results\expanded\main-a' `
  -ExportDirectory '.\results\expanded-exports\main-a-complete'
& '.\scripts\local_expanded_pipeline.ps1' -Analyze `
  -ExportDirectory '.\results\expanded-exports\main-a-complete' `
  -AnalysisOutput '.\results\expanded-analysis\main-a-complete'
```

Wrapper luôn thêm `--complete-blocks`; export là consistent SQLite snapshot, raw
database không đổi. Analyzer đọc export đó, không solve. Report preparation yêu
cầu receipt SAT08 và hash được tính từ receipt. Final handoff cần audit source hashes,
export hashes, strata/pairing/root clusters, song ngữ và QA riêng; không sửa report
v1 hoặc các PDF cũ trong pipeline này.

## Full-run launcher

`scripts/start_full_expanded_run.ps1` mặc định chỉ in kế hoạch và trạng thái các
điều kiện release/owner API. Khi root đã phát hành
`diagnostics/expansion/root-wave3/code-release.json` với
`approved_explicit_terminal_execution=true`, hash nguồn khớp và các CLI05/07
đã hiện diện, một lệnh chạy tuần tự DRAFT → witness/freeze → pilot → pilot audit
→ main → export/analyze/report:

```powershell
pwsh -NoExit -File .\scripts\start_full_expanded_run.ps1 -Execute
```

Launcher khóa toàn bộ flow, giữ thread variables ở `1`, ghi audit/checkpoint và
dùng mốc session `9999-12-31T23:59:59+00:00`; cutoff benchmark vẫn 10 giây, ba
repetitions và matrix một worker. Windows sleep bị ngăn trong vòng đời launcher
process và được khôi phục khi process thoát; nên cắm nguồn. Launcher dừng nếu
release/hash/API/gate/audit/cleanup sai. Nó không tự ghi gate acceptance hoặc
đoán cách dọn orphan.

Tiếp tục full workflow dùng đúng `full-run-checkpoint.json`, draft/evidence,
dataset và experiment paths đã ghi; witness CLI nhận lại cùng evidence namespace
để nhận durable SAT checkpoint, còn timeout đã terminal không được chạy lại:

```powershell
pwsh -NoExit -File .\scripts\start_full_expanded_run.ps1 -Execute -Resume `
  -Reason 'operator-provided recovery reason'
```

Nếu tiếp tục trực tiếp một runner experiment, truyền thêm
`-Experiment '.\results\expanded\<experiment>'`. Resume giữ attempt đã commit
và cần cleanup proof đúng orphan từ runner/root; launcher không kill tiến trình
theo tên hoặc đánh dấu cleanup thay owner.
Không chạy lại SAT/TIMEOUT đã terminal. Việc hoàn tất 16.000 puzzles có thể vượt
qua hạn 23:59 ngày 19/10; báo cáo mở rộng chờ kết quả và hai PDF cũ tiếp tục là
bản nộp hiện có.
