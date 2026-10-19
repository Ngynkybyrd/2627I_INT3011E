# Dữ liệu và giới hạn — đoạn dùng cho báo cáo

Bộ dữ liệu mở rộng đã khóa gồm 16.000 đề: 10.000 đề công khai 9×9,
5.000 đề synthetic 16×16 và 1.000 đề synthetic 25×25. Bốn file easy.txt,
medium.txt, hard.txt và diabolical.txt của Sudoku Exchange Puzzle Bank tại
commit `d8c8ebaee0c08c412cfba96af1923dfa61c83317` đóng góp mỗi file 2.500 đề.
Nguồn sử dụng QQWing để sinh đề, Sukaku Explainer để gán rating và công bố
dataset thuộc public domain; bản LICENSE cho phép sử dụng, sửa và phân phối.
Nhãn nhóm và rating gốc được giữ nguyên, không phải thang độ khó do dự án
hiệu chỉnh theo các solver thực nghiệm. Khoảng số clue quan sát tương ứng
bốn nhóm là 22–41, 22–36, 23–36 và 23–37; rating lần lượt nằm trong
1,2–1,2; 1,5–2,3; 2,5–4,7 và 5,0–9,1. Public cũng là dữ liệu do máy sinh.

Phần synthetic sử dụng hai bảng nghiệm nguồn đã có, một cho mỗi kích thước.
Từ đó tạo 1.000 root 16×16 và 200 root 25×25 khác nhau theo nội dung chính
xác. Ở mỗi kích thước, một nửa root thuộc họ permutation và một nửa thuộc
họ row_cycle; mỗi root cung cấp năm mask ở mật độ yêu cầu 20%, 30%, 40%,
50%, 60%. Cả 1.200 root khác bảng nguồn tương ứng; mọi root bắt đầu bằng
hoán vị hợp lệ. Trong 600 root row_cycle, một phép tráo trọn proper cycle
giữa hai hàng cùng band được áp dụng thêm: N16 có 248 chu trình dài 2 và
252 chu trình dài 4, N25 có 100 chu trình dài 5. Đây là số biến đổi ghi nhận,
không phải số lớp đẳng cấu đã được chứng minh khác nhau.

Mỗi mức mật độ có 1.000 đề N16 hoặc 200 đề N25, cân bằng hai họ. Làm tròn
`floor(p*N*N/100+0.5)` cho số clue thực N16 là 51, 77, 102, 128, 154 và
N25 là 125, 188, 250, 313, 375. Vì vậy mật độ thực có thể lệch nhẹ khỏi
mức yêu cầu. Năm mask cùng root không phải năm mẫu độc lập; ngay các root
cũng được xây từ chỉ hai bảng nguồn nên không được mặc định độc lập hoàn
toàn. Loại trùng chính xác xác nhận 16.000 input và 1.200 root riêng biệt,
không trùng S80 hoặc pilot về input; kết quả này không chứng minh lấy mẫu
đều, không đẳng cấu hoặc tính đại diện cho mọi Sudoku. Root_id cần được
giữ khi phân tầng, ghép mẫu hoặc đánh giá bất định.

Frozen metadata ghi 16.000 witness đã được kiểm: 6.000 witness generator
và 10.000 witness thu bằng production solver. Acquisition public dùng
ngân sách riêng 30 giây, khác cutoff benchmark 10 giây; thời gian và nghiệm
acquisition không thay kết quả benchmark. Không chạy kiểm uniqueness trong
gói provenance này: 10.000 public mang nhãn source_claimed có citation,
6.000 synthetic mang nhãn unverified; không có chứng nhận uniqueness độc
lập của dự án. Có witness hợp lệ chỉ chứng minh tồn tại nghiệm, không có
nghĩa mọi cấu hình benchmark đều giải thành công.

Không suy ít clue hoặc kích thước lớn hơn luôn khó hơn. Phân bố vị trí/giá
trị clue, họ biến đổi, nguồn sinh và solver đều có thể ảnh hưởng kết quả.
So N9 công khai với N16/N25 synthetic đồng thời thay nguồn và cấu trúc dữ
liệu, nên không cô lập ảnh hưởng kích thước hay chứng minh độ phức tạp thuần.
Số liệu composition và hash được kiểm từ frozen index/manifest/roots và
nguồn đã pin, lưu trong counts.json; không lấy thêm đề hoặc chạy solver mới.

Nguồn trích: https://github.com/grantm/sudoku-exchange-puzzle-bank/tree/d8c8ebaee0c08c412cfba96af1923dfa61c83317
