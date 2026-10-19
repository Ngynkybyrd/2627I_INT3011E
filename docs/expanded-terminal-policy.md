# Root policy — terminal execution after code release

Ngày19/10/2026, Asia/Saigon. Quyền mới nhất của user: sau khi mọi nhiệm vụ code/tests/công cụ hoàn tất, được tự mở cửa sổ terminal visible để giải đủ16.000 đề. Phần báo cáo cần dữ liệu hoãn đến có kết quả. Khi terminal đã chạy, ChatGPT kết thúc lượt, không polling, không automation, không tạo agent/task mới để giữ việc. Terminal/Python tự quản tiến độ/checkpoint/log.

## Các điều kiện không được bỏ qua

1. Root phải chạy suite hồi quy/tích hợp trên mã cuối, không fail/skip/xfail giả đạt, kiểm hash32execution/169data v1 và haiPDF19/10; verify_release.py tạo code-release.json chỉ sau khi các kiểm này đạt. Release có source_sha256, regression XML SHA và approved_explicit_terminal_execution=true. Không tự tạo hoặc sửa release để né lỗi.
2. Chỉ root khởi chạy console visible sau release. Wrapper mặc định dryrun; -Execute là thao tác chạy thực. Không API/AI/token trong worker. Benchmark chính vẫn tuần tự1worker, ba repetitions, cutoff10s, đầy đủ matrix đã khóa, không cache CNF/model riêng cho một phương pháp.
3. Terminal có thể tải/stage đề DRAFT rồi thu witness public và finalize cùng IDs. Witness phase dùng cutoff riêng30s và nhãn acquisition, không nhập thời gian đó vào benchmark. Synthetic witness từ bảng gốc đã checker không phải nghiệm benchmark. Collector checkpoint/resume/hash/lock; không chọn lại mẫu hoặc auto retry terminal failure.
4. Root ủy quyền CÓ ĐIỀU KIỆN cho scripts/authorize_expanded_local.py sinh gate receipts sau kiểm máy: dataset thật frozen+witness, code release+source hashes+fullsuite evidence và preflight matrix/native evidence phải đạt trước pilot. accepted_by=root chỉ thể hiện ủy quyền này khi mọi predicate đạt và lưu đủ evidence refs/hashes, không phải cờ bypass.
5. Trước main, auditor phải kiểm pilot THẬT hoàn tất đúng164lượt/theo matrix, cùng mã/môi trường/protocol, input disjoint, checker/identity/cleanup/timing và trạng thái SAT/TIMEOUT hợp lệ; không ERROR/UNSAT/invalid/license. Lưu pilot audit và execution freeze data/config/matrix/schedule/code/env thực tế. Không dùng artificial/replay để mở cổng nghiên cứu.
6. Resume không lặp SAT/TIMEOUT đã commit, không sửa lịch sử. Orphan recovery vẫn cần chứng minh cleanup đúng attempt/process identity; khi không chứng minh được thì terminal dừng và ghi lỗi, không tự nhận cleanup=true hoặc kill theo tên.
7. User đã cho chạy đến hoàn tất kể cả qua ngày, nên mốc session của terminal có thể là UNTIL_COMPLETE (9999-12-31T23:59:59+00:00); đây là operational override được audit, KHÔNG thay cutoff10s hoặc hứa hoàn thành trước hạn nộp23:59 ngày19/10. HaiPDF gốc giữ nguyên làm bản nộp hiện có. Không tự nộp hoặc push.
8. Sau main, terminal export các batch QA-complete, phân tích và tạo gói LaTeX từ receipt hợp lệ. Không tự tuyên bố đủ16.000 nếu thiếu, không nhận partial/pilot/artificial thành kết quả cuối. Kết luận khoa học/hai báo cáo cuối nghiệm thu sau dữ liệu; user đã cho hoãn phần này.

Đây là policy kiểm chứng tự động, không chấp nhận viết accepted=true thiếu evidence. Nếu test/gate/hash/cleanup sai, dừng trước bước solver tiếp theo và giữ lỗi/log/checkpoint để kiểm tra sau; không gọi lại ChatGPT tự động.
