# DATA-012 — Giới hạn dữ liệu Sudoku

Ghi nhận ngày 16/10/2026 (Asia/Saigon), trước benchmark. Tài liệu này mô tả
giới hạn của thiết kế và mức bằng chứng hiện có, không công bố kết quả giải.

**Synthetic — thiết kế dự kiến.** Kế hoạch gồm 60 đề ở kích thước 4×4,
9×9, 16×16, 25×25, ba mật độ clue 30/50/70% và năm seed mỗi nhóm. Generator
dự kiến tạo bảng hoàn chỉnh rồi hoán vị giá trị, hàng/band, cột/stack theo
các phép bảo toàn khối trước khi che ô. Các phép này giữ cấu trúc của bảng
gốc và chỉ khám phá họ bảng liên hệ qua các phép biến đổi đã chọn; không
bảo đảm lấy mẫu đều mọi bảng hoàn chỉnh hay mọi puzzle Sudoku. Năm seed
mỗi nhóm cũng không bảo đảm đa dạng cấu trúc. Che ngẫu nhiên các ô không
phải quy trình hiệu chỉnh độ khó hoặc bảo đảm nghiệm duy nhất.
Chưa sinh hay kiểm bộ synthetic; tính hợp lệ và khả năng tái lập còn phải
được xác nhận khi triển khai bằng schema/checker đã thống nhất.

**Public — nguồn và mẫu đã chuẩn bị.** Đã tải một file `hard.txt` từ Sudoku
Exchange Puzzle Bank tại commit cố định và lưu 20 bản ghi mẫu theo seed
20261016 trong `public-selection.csv`. Nguồn này cũng do máy sinh bằng
QQWing, theo README của nhà cung cấp; “public” chỉ có nghĩa nguồn công khai
bên ngoài dự án, không có nghĩa đề do con người biên soạn hoặc phân phối
đại diện mọi Sudoku. Một file, một bucket nguồn và 20 mẫu 9×9 giới hạn khả
năng khái quát, nhất là sang bảng 16×16/25×25. Nhãn `hard` và rating là nhãn
của nguồn, chưa được dự án kiểm chứng bằng hiệu năng solver hoặc người giải.
Loại trùng chuỗi 81 ô không loại được mọi cặp tương đương qua đối xứng.

**Mật độ và kích thước.** Mật độ clue là thuộc tính cấu hình, không phải
thang độ khó: cùng số clue nhưng vị trí và giá trị khác nhau có thể dẫn
đến hành vi solver khác nhau. Ít clue không tự động khó hơn; nhiều clue
cũng không bảo đảm nhanh hơn. Bảng lớn hơn có mô hình lớn hơn trong thiết
kế encoding này nhưng không tự suy ra khó giải hơn. Chỉ kết quả đo theo
protocol mới cho phép mô tả thời gian của các cấu hình trên tập đã chọn;
không diễn giải xu hướng thành quy luật cho mọi Sudoku.

**Tìm một nghiệm và mức xác minh.** Mục tiêu dự án là tìm một nghiệm hợp
lệ, giữ nguyên clues và được checker độc lập chấp nhận. Không yêu cầu
nghiệm solver trùng đáp án generator, không chứng nhận uniqueness hàng
loạt. Synthetic dự kiến có witness là bảng gốc; witness chỉ là bằng chứng
sau khi đã được checker kiểm và phải lưu riêng khỏi input solver. README
nguồn public tuyên bố nghiệm duy nhất, nhưng dự án chưa xác minh SAT hoặc
uniqueness của 20 mẫu: cả hai trường kiểm trong CSV hiện đều là `no`.
Kiểm format, checksum và lấy mẫu tái lập đã làm không thay thế kiểm nghiệm.

**Giới hạn so sánh.** S80/B16/C10 là các tập theo thiết kế đã chốt; hiện mới
có đề xuất thứ tự 20 public và bốn mẫu đầu cho phần public của B16/C10,
chưa khóa bộ JSON/manifest hoàn chỉnh. Đối chứng dùng mẫu nhỏ chỉ cho bằng
chứng bổ sung trên tập giao tương ứng. Không đặt thống kê của các tập khác
nhau cạnh nhau như cùng mẫu hoặc chọn lại đề theo runtime sau khi đo.

Bằng chứng nguồn, quyền dữ liệu, commit/checksum và quy tắc lấy mẫu nằm tại
[data-source.md](data-source.md); bản ghi nguồn tại
[public-selection.csv](public-selection.csv). Chuẩn hóa JSON và kiểm SAT
còn chờ schema chat02, checker chat03 và công cụ tìm nghiệm phù hợp.
