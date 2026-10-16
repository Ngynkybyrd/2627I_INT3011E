# RUN-010 / main launch handoff — 16/10/2026

RUN-010 đạt: analyze_results.py --mode pilot xác nhận 55 dòng, 54 SAT/1 TIMEOUT,
54 nghiệm hợp lệ, không thiếu job. CNF counts/formula pass; median3rep và
matched-speed trống. Đã xem 4 PNG và bảng CSV/LaTeX; nhãn PILOT rõ, hình runtime
chỉ là placeholder. Output: `diagnostics/runner/pilot-analysis-01/`.
Raw pilot/selection giữ nguyên, không tái sử dụng trong main.

Suite mới: **653 passed**, 136 cảnh báo JUnit formatting; XML
`diagnostics/runner/full-suite-main-01.xml`. Dataset hash giữ nguyên.
Freeze: `results/raw/main-20261016-01/execution-freeze.json`, gồm source,
CLI/analysis/API/config/dependencies cùng hash suite/run/schedule. 906 job:
720 S80 + 96 B16 + 90 C10; 10s, 3rep, seed20261016.

Gate workload: snapshot cuối các chat liên quan idle; không thấy tiến trình
Python/solver/TeX trước launch. Root xác nhận SAT09 build xong, SAT10 chỉ nhẹ.

**Main RUNNING**, bắt đầu **19:35:37 giờ Việt Nam**. Supervisor PID **19484**,
launcher PID42272, shell session68083 chờ giữ lifetime; cửa sổ Hidden.
Snapshot xác nhận 37 dòng đã ghi. Không polling theo puzzle.

Trong thư mục main: `supervisor-status.json`, `stdout.log`, `stderr.log`,
`results.csv` (progress), `launcher.json`, `supervisor-launch.lock`.
Root đọc status/CSV mỗi10phút; không khởi động lại nếu FAILED hoặc mất process.
Khóa launch ngăn trùng, lỗi UNSAT/cleanup dừng batch và giữ raw.

Lần Start-Process đầu kết thúc trước khi tạo lock/status/CSV: không job nào
chạy; giữ `launch01-*`. Lần sau thêm shell WaitForExit và đã xác nhận RUNNING.

RUN-012 **chưa hoàn tất**; chờ đủ906 và nghiệm thu. Không sửa implementation
trong khi đo. Không có blocker đang biết.
