# Chạy song song bộ mở rộng (ủy quyền người dùng19/10/2026)

Người dùng yêu cầu chuyển sang chạy song song để giảm thời gian thực. Profile mới là `parallel-throughput-v1`,4worker; mỗi solver giữ1thread, cutoff10s,3reps, toàn bộ16.000đề và330.000job không đổi. Một coordinator duy nhất nắm WriterLock/SQLite writer; từng job vẫn được chạy trong tiến trình mới dưới Windows JobObject, checker độc lập và timeout/cleanup cũ. Không mở nhiều runner tuần tự cùng một SQLite.

## Nguồn gốc kết quả

Lượt tuần tự đã được dừng mềm tại ranh giới không còn worker. Giữ1012primary results (1009SAT,3TIMEOUT). Có1attemptINTERRUPTED trước khi được launch, job trảPENDING; không thay thế kết quả terminal nào. ZeroRUNNING vàzeroopen sessions trước tiếp quản. Script dừng và bằng chứng tại diagnostics/expansion/root-wave3/pause-sequential-for-parallel.py và parallel-transition.json.

Các session song song ghi sốworker, profile, hash mã điều phối, rootauthorization và `timing_policy=resource-contended`, `reporting_policy=separate-by-session`. Thời gian tuần tự và song song phải trình bày riêng; không gộp thành so sánh hiệu năng chạy cô lập. TIMEOUT trong profile song song có thể bị ảnh hưởng tranh CPU/RAM. 3reps/10s/quota/schedule gốc vẫn được giữ.

## Vận hành

Terminal: `scripts/start_parallel_expanded_run.ps1 -Execute`. Terminal hiển thị tổngjob, sốactiveworker vàSAT/TIMEOUT mỗi30giây; checkpointSQLite được ghi theo từng kết quả.

Tạm dừng an toàn bằng cách tạo file `diagnostics/expansion/root-wave3/parallel-stop.request`; coordinator ngừng nhậnjob mới và chờ tất cả job đang chạy kết thúc/cleanup rồi mới đóngsession. Trước resume phải kiểm nguyên nhân và xử lý file yêu cầu này. Không kill worker thủ công.

Kiểm thử tích hợp ban đầu giới hạn12job tiếp theo trong schedule, không lựa chọn theo hiệu năng; kết quả giữ nguyên trongmain. Sau khi đạt, session tiếp theo chạy toàn bộjob còn lại với cùng4worker vàreceipt.

Script chạy dài chỉ thu kết quả. Phân tích/báo cáo mới phải đọc sessionprofile và tách nhóm tuần tự/song song trước khi sử dụng số thời gian; không tự dùng pipeline phân tích cũ để xuất kết luận hỗn hợp. Automation10phút giữPAUSED. Không tự nộp bài haypush.
## Điều chỉnh mới nhất: chỉ1lần lặp

Theo yêu cầu tiếp theo của người dùng, chỉ tiếp tục `repetition=1`, mục tiêu110.000job (80.000N9+25.000N16+5.000N25). Frozen manifest gốc3reps/330.000job giữ nguyên để bảo toàn lịch sử. Receipt/session của scope mới ghi `effective_repetitions=1`, `selected_repetitions=[1]`. Chỉ các kết quảrep1 được tính vào mục tiêu và phân tích mới; rep2/3 trướcđó được lưu nhưng không đưa vào bảng chính, không bị xóa hoặc nhận là đãhoàn tất. Khi scope1rep xong, DB gốc vẫnPAUSED vì còn các job2/3 ngoài phạm vi mới; chỉ scope được báoCOMPLETE, không giả nhận330.000job đãxong.

Trước thay đổi này, kiểm thử12lượt song song thật đềuSAT, peak4attempts chồng thời gian,0RUNNING vàsessionđãđóng. Tổng dữ liệu giữ1024primary, trongđó357rep1 được dùng tiếp,324rep2+343rep3 giữ riêng. Quota dữ liệu/cutoff10s/solverthreads1/4worker không đổi. Không còn3reps để ước lượng biến thiên giữa các lần chạy; báo cáo phải ghi hạn chế này.
