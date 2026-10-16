# DATA-005 — Nguồn public 9×9 và chuẩn bị DATA-006

Ngày chuẩn bị: 16/10/2026 (Asia/Saigon). Chỉ chuẩn bị nguồn và đề xuất mẫu;
chưa chuẩn hóa input JSON, kiểm SAT/uniqueness, sinh synthetic hoặc benchmark.

## Nguồn được chọn

- Nhà cung cấp: Sudoku Exchange Puzzle Bank, tài khoản GitHub `grantm`.
- Repository: https://github.com/grantm/sudoku-exchange-puzzle-bank
- Commit cố định: `d8c8ebaee0c08c412cfba96af1923dfa61c83317`.
- Chính xác một file puzzle được chọn: `hard.txt`.
- URL cố định: https://raw.githubusercontent.com/grantm/sudoku-exchange-puzzle-bank/d8c8ebaee0c08c412cfba96af1923dfa61c83317/hard.txt
- Bản tải nguyên byte: `data/source/sudoku-exchange-hard.txt`.
- Kích thước: 32.159.200 byte; 321.592 dòng; 321.592 chuỗi puzzle khác nhau.
- SHA-256: `abcff1512411e601abd5e861c60add5be5d877739b6faa249ee86960f5ad85e9`.
- Git blob SHA-1: `fa8ee5ead4ab7be4e8c1b9af91d859384d5d4cfb`;
  đã đối chiếu với GitHub Contents API tại đúng commit.
- Metadata API: https://api.github.com/repos/grantm/sudoku-exchange-puzzle-bank/contents/hard.txt?ref=d8c8ebaee0c08c412cfba96af1923dfa61c83317

## Quyền đối với dữ liệu

README của nguồn nói rõ **data set** được đưa vào public domain; LICENSE.txt
cho phép sao chép, sửa, dùng và phân phối dữ liệu, cả dạng gốc và chuyển đổi,
cho mục đích thương mại hoặc phi thương mại. Đây là tuyên bố trực tiếp đối với
dataset, không suy từ giấy phép phần mềm generator hoặc code solver.
Giữ bản LICENSE và attribution nguồn khi bàn giao; không có yêu cầu xin phép
riêng trong điều kiện nguồn đã đọc. Dữ liệu được cung cấp không bảo hành.

- LICENSE cố định: https://github.com/grantm/sudoku-exchange-puzzle-bank/blob/d8c8ebaee0c08c412cfba96af1923dfa61c83317/LICENSE.txt
- Bản lưu: `data/source/sudoku-exchange-LICENSE.txt`.
- SHA-256 LICENSE: `0f3ab60214dbfacca972a724efd3b0b3248b65b02d9874e95ed3f412f232c385`.
- README cố định: https://github.com/grantm/sudoku-exchange-puzzle-bank/blob/d8c8ebaee0c08c412cfba96af1923dfa61c83317/README.md
- Bản lưu: `data/source/sudoku-exchange-README.md`.
- SHA-256 README: `494477eae319136793973e81d74ace35dcea91e3dbb40de1f53bc4a9ef03117e`.

Nguồn tham khảo cũ `rkkautsar/sudoku-solver` công bố MIT cho project, nhưng
README dẫn bộ 17-clue từ một nguồn bên ngoài (Code Golf). Chưa xác định được
chuỗi quyền riêng cho file dữ liệu ngoài đó; vì vậy không dùng file từ repo
cũ và không diễn giải MIT của solver thành quyền đối với dữ liệu bên ngoài.
Nguồn thay thế này có tuyên bố quyền dataset trực tiếp và đủ số đề; chỉ chọn
một file thay thế, giữ nguyên tổng 20 public theo chỉ dẫn cho phép tìm nguồn khác.

## Format và mức kiểm đã làm

Mỗi dòng ASCII/LF có ba trường phân cách bằng whitespace: ID nguồn 12 ký tự
hex, chuỗi 81 chữ số `0..9` theo hàng, rating một chữ số thập phân. `0` là ô
trống; chuyển đổi sau sẽ dùng `n=3`, `N=9`. Mỗi record gốc dài 100 byte.
Script đã kiểm hình thức tất cả dòng và loại trùng theo **chuỗi puzzle**,
không theo source ID: 0 bản trùng. Không chuẩn hóa theo đối xứng Sudoku.

README cho biết dữ liệu được tạo bằng QQWing và tuyên bố nghiệm duy nhất;
đây chỉ là **tuyên bố của nguồn**, chưa được dự án xác minh. Các trường
`sat_checked` và `uniqueness_checked` trong CSV đều là `no`. Rating và tên
file `hard` là nhãn nguồn, không phải đánh giá độ khó được dự án kiểm chứng.
Public ở đây có nghĩa dữ liệu công khai từ bên ngoài dự án; bản thân nguồn
cũng là dữ liệu do máy sinh. Một bucket duy nhất và 20 mẫu không đại diện mọi Sudoku.

## Quy tắc mẫu độc lập, trước kết quả

`diagnostics/select_public_source.py` chỉ dùng Python standard library.
Quét dòng theo thứ tự file, giữ lần xuất hiện đầu của mỗi chuỗi puzzle rồi
dùng `random.Random(20261016).sample(records, 20)`; giữ **thứ tự sample trả về**.
Runtime đã dùng: Python 3.13.5. Lưu kết quả để không phụ thuộc việc lấy mẫu
lại bằng phiên bản Python khác. Không chọn theo rating, SAT hay runtime.

CSV đề xuất: `diagnostics/public-selection.csv` (chưa là manifest dataset cuối).
SHA-256 CSV: `13f6ff47669498070f53a1404ed1f0492b2d740a461401b3605b9d1bd988c96a`.
ID đề xuất gắn số dòng nguồn 1-based, không phải thứ hạng tốc độ:

| Thứ tự mẫu | ID đề xuất | B16/C10 đề xuất |
|---:|---|---|
| 1 | public-se-hard-L069940 | Có |
| 2 | public-se-hard-L293964 | Có |
| 3 | public-se-hard-L269904 | Có |
| 4 | public-se-hard-L215069 | Có |
| 5 | public-se-hard-L287183 | |
| 6 | public-se-hard-L155430 | |
| 7 | public-se-hard-L232809 | |
| 8 | public-se-hard-L091326 | |
| 9 | public-se-hard-L051662 | |
| 10 | public-se-hard-L307500 | |
| 11 | public-se-hard-L275967 | |
| 12 | public-se-hard-L120921 | |
| 13 | public-se-hard-L277959 | |
| 14 | public-se-hard-L141105 | |
| 15 | public-se-hard-L027825 | |
| 16 | public-se-hard-L087170 | |
| 17 | public-se-hard-L032223 | |
| 18 | public-se-hard-L001693 | |
| 19 | public-se-hard-L315444 | |
| 20 | public-se-hard-L247515 | |

Bốn dòng đầu dùng chung cho phần public của B16 và C10 theo TODO; chưa khóa
toàn bộ S80/B16/C10 vì phần synthetic/JSON/checker còn phụ thuộc các chat khác.
CSV giữ source ID, số dòng, puzzle nguyên bản, clue count, seed, hash chuỗi
81 ký tự ASCII không newline và nhãn mức kiểm để phần chuẩn hóa truy vết.

## Tái lập và bằng chứng

Chạy từ `D:\KHMT\Project solo` (output phải chưa tồn tại để tránh ghi đè):

```powershell
& '.\.venv\Scripts\python.exe' '.\diagnostics\select_public_source.py' '.\data\source\sudoku-exchange-hard.txt' --output '.\diagnostics\public-selection-recheck.csv'
Get-FileHash -Algorithm SHA256 '.\diagnostics\public-selection-recheck.csv'
```

Đã sinh lại trong bộ nhớ và so từng byte với CSV lưu: PASS; đủ 20 puzzle
khác nhau, đúng 4 đề xuất B16/C10: PASS; Git blob hash và số byte khớp API:
PASS. Không cài package hoặc thay đổi môi trường.

## Bàn giao / phần còn chờ

- DATA-005: đủ bằng chứng chọn nguồn/file/commit/format/checksum/quyền dữ liệu.
- DATA-006: mới chuẩn bị nguồn, loại trùng và đề xuất mẫu; **chưa hoàn thành**
  vì chưa chuyển JSON theo schema chat02.
- DATA-007: **chưa thực hiện**; cần công cụ tìm ít nhất một nghiệm và checker
  độc lập chat03; không coi tuyên bố uniqueness của nguồn là checker pass.
- DATA-008 và DATA-011: **chưa hoàn thành**; CSV nguồn không thay manifest
  dataset80 hoặc danh sách S80/B16/C10 cuối.
- Không viết model/solver, sinh synthetic, sửa TODO/STATUS hoặc chạy benchmark.
