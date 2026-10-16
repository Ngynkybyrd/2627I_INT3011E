# Kết quả thực nghiệm chính — main-20261016-01

Chỉ dùng một CSV chính đã nghiệm thu; không gộp pilot, fixture hay đợt chạy lại.
Đơn vị thời gian là giây. `total = build + setup/nạp solver + solve`; phần setup
đã nằm trong cột build. Import, đọc input, checker và ghi kết quả nằm ngoài phép đo.
Cutoff 10 giây cho tổng, ba lần lặp; không lấy lượt nhanh nhất.

## Phạm vi và số lượt giải được

| Cấu hình | Tập thực chạy | SAT / lượt | Đề đủ ba SAT / đề đã chọn | TIMEOUT |
|---|---|---:|---:|---:|
| Glucose3 pairwise | S80 | 240/240 | 80/80 | 0 |
| Glucose3 sequential counter | S80 | 240/240 | 80/80 | 0 |
| Glucose3 bitwise | S80 | 240/240 | 80/80 | 0 |
| CP-SAT | B16 | 48/48 | 16/16 | 0 |
| HiGHS ILP | B16 | 45/48 | 15/16 | 3 |
| Gurobi MIP | C10 | 30/30 | 10/10 | 0 |
| CPLEX MIP | C10 | 30/30 | 10/10 | 0 |
| CP Optimizer | C10 | 30/30 | 10/10 | 0 |

Nguồn: `coverage.csv`, dòng 2–9 (header là dòng 1), và status counts trong
`summary.csv`; đối chiếu 906 dòng raw. Có 903 SAT đã kiểm nghiệm độc lập; không
có UNSAT, ERROR, INVALID_INPUT, LICENSE_LIMIT hay UNAVAILABLE trong batch này.
Không suy ra solver thương mại đã chạy đủ S80: C10 chỉ gồm 4×4/9×9.

S80 gồm 60 synthetic (4 kích thước × 3 mật độ × 5 seed) và 20 public 9×9.
B16 có 12 synthetic (mỗi kích thước/mật độ một đề) và bốn public; C10 có sáu
synthetic 4×4/9×9 và cùng bốn public. ID chính xác nằm trong
`data/scopes.json` được khóa và `matched-pairs.csv`.

## Encoding, kích thước CNF và chi phí build

Trên synthetic 25×25, 30% clues, năm đề chung mỗi encoding đều có đủ ba SAT:

| Encoding | Median build | Median solve | Median total |
|---|---:|---:|---:|
| pairwise | 0.381882 | 0.022380 | 0.402449 |
| sequential counter | 0.130810 | 0.024383 | 0.159527 |
| bitwise | 0.193860 | 0.015416 | 0.210650 |

Nguồn: `summary.csv` dòng 66, 79, 53; mỗi giá trị là median của median ba lần
lặp theo từng đề. Ba cột được tổng hợp độc lập nên không cộng hai median nhóm
để tái tạo median total. Các nhóm ID là `synthetic-N25-p30-s0` đến `s4`;
`instances.csv` chứa median từng ID, raw CSV chứa từng repetition.

Ở nhóm này build lớn hơn solve đối với cả ba encoding. Sequential có total
thấp nhất trong ba lựa chọn, dù median solve của nó cao hơn bitwise. Kết quả
cho thấy cần tính cả dựng/nạp mô hình khi đánh giá encoding; ít biến hơn hoặc
solve-only nhanh hơn không đảm bảo total thấp hơn.

Ví dụ đếm thực tế trên cùng `synthetic-N25-p30-s0` (188 clues), trước preprocessing:

| Encoding | Biến chính | Biến phụ | Tổng biến | Clauses |
|---|---:|---:|---:|---:|
| pairwise | 15625 | 0 | 15625 | 752688 |
| sequential counter | 15625 | 60000 | 75625 | 180188 |
| bitwise | 15625 | 12500 | 28125 | 315188 |

Nguồn: `cnf.csv` dòng 198, 199, 197; dùng chính ba lượt SAT của ID đó trong raw.
Pairwise không có biến phụ nhưng nhiều clause hơn hai encoder còn lại ở kích
thước này. Sequential nhiều biến phụ hơn bitwise nhưng ít clause hơn.

Thứ tự không cố định trên mọi kích thước: synthetic 4×4, mật độ 30%, median
total pairwise/sequential/bitwise lần lượt 0.001189/0.001520/0.001582;
truy bằng khóa `(configuration, source=synthetic, N=4, density=0.3)` trong
`summary.csv`, ID `synthetic-N04-p30-s0..s4`. Hình runtime giữ riêng cả ba mật
độ và cùng năm ID mỗi điểm; không suy rộng thứ tự này cho mọi n hoặc mọi đề.

## SAT so với CP và ILP trên tập giao

`paper/baseline-matched.csv`/`.tex` dùng pairwise làm mốc hiển thị thống nhất,
không chọn encoding hoặc repetition nhanh nhất cho từng đối thủ. Toàn bộ các
cặp với cả ba encoding vẫn nằm trong `matched-pairs.csv`.

Trên đề B16 `synthetic-N25-p30-s0`, CP-SAT median total 0.230552 còn pairwise
0.394866; cả hai đủ ba SAT (một ID, không phải năm ID S80).
Trên `synthetic-N25-p50-s0` tương ứng là 0.055806 và 0.382179; trên
`synthetic-N25-p70-s0` là 0.012724 và 0.383525.
Nguồn: `matched-pairs.csv` dòng 134–136, kèm `instance_ids` và
`matched_count=1`. Không thay các giá trị pairwise này bằng median S80 ở bảng trên.

Trên cùng bốn public 9×9 trong C10, median total của CPLEX MIP là 0.004748,
Gurobi 0.008019, CP Optimizer 0.030911, còn pairwise 0.006534. CPLEX MIP thấp
hơn pairwise ở thống kê này; Gurobi và CP Optimizer cao hơn. Đây là quan sát
trên bốn đề chung, không phải kết luận SAT hoặc ILP/CP luôn thắng.
Nguồn: `matched-pairs.csv` dòng 43, 171, 85. ID:
`public-se-hard-L069940`, `L293964`, `L269904`, `L215069` (đều có prefix
`public-se-hard-` trong CSV). Ratio theo cặp nếu cần phải dùng cột
`median_paired_a_over_b`, không lấy tỷ số hai median nhóm thay thế.

## Timeout và PAR-2

Cả ba timeout thuộc `synthetic-N25-p30-s0__highs__none__r1/r2/r3`.
HiGHS không có median SAT cho ID này; cặp HiGHS với SAT/CP-SAT trên B16 chỉ
còn 15 ID đủ ba SAT ở cả hai bên. Các cặp với backend thương mại giới hạn C10
vẫn có 10 ID. So hai SAT encoding có 80 ID chung. Những số này phải công bố
cùng solved count toàn tập, không chỉ đưa runtime của phần đã giải được.

Mỗi timeout nhận PAR-2 = 20.000000, tổng penalty ba lượt là 60.000000;
`summary.csv` dòng 40 ghi mean PAR-2=20.000000 cho đúng nhóm HiGHS N25/30%
với ba lượt đủ điều kiện. Không dùng các observed total hơi quá cutoff làm
penalty. `r3` thiếu cả ba thành phần timing trong raw và vẫn để trống; `r1/r2`
có observed total khoảng 10 giây nhưng trạng thái vẫn TIMEOUT.
Truy từng `job_id` qua `run-par2.csv` và `paper/raw-row-index.csv` để tới dòng
raw gốc. Không có status loại trừ PAR-2 trong batch này; quy tắc vẫn loại
ERROR/INVALID_INPUT/LICENSE_LIMIT/UNAVAILABLE nếu xuất hiện.

## Giới hạn và sử dụng trong BTL

- Synthetic từ cùng generator/hoán vị có bias; tăng kích thước hoặc giảm clues
  không tự chứng minh tăng độ khó. Unique chưa được xác minh.
- B16 mỗi synthetic stratum chỉ có một ID; C10 chỉ có kích thước nhỏ, bốn đề
  public chung không đại diện mọi Sudoku public. Không gọi 80 đề là đã thử mọi solver.
- Một máy, một cấu hình thư viện, ba repetitions và cutoff hữu hạn; chênh lệch
  millisecond ở bảng nhỏ dễ chịu ảnh hưởng overhead. Không có kiểm định thống kê
  hoặc tuyên bố vượt trội phổ quát. RAM/search counters không được đo.
- Các lớp mô hình CP/ILP khác SAT và dùng engine khác nhau; số biến/clause CNF
  không phải chỉ số trực tiếp so kích thước mô hình native CP/MIP.

Chọn hai nhóm hình cho bài: `paper/figure-cnf-size.pdf` (hai panel variables/
clauses, mật độ cố định 50% được ghi rõ) và `paper/figure-runtime.pdf` (ba
panel mật độ, ba encoding trên cùng ID synthetic). Public và baseline trình
bày bằng bảng có matched count: `paper/baseline-matched.tex` (nên chia theo
scope/source khi dàn trang), `paper/coverage.tex`; bảng đầy đủ ở CSV.
Không đưa cả 28 hình cặp vào PDF. `total-time.pdf` gốc chỉ là trang chỉ dẫn
tới hình matched, không dùng làm hình kết quả. Cactus không cần vì timeout
tập trung ở một ID đã được thể hiện bằng count/PAR-2.

## Truy vết và kiểm toàn vẹn

`verification.json`: tái tính 301 nhóm median hợp lệ, 252 dòng thống kê cặp,
906 penalty theo lượt; checksum 903 nghiệm khớp bằng chứng nghiệm thu của root.
`paper/raw-row-index.csv` ánh xạ tất cả job ID sang số dòng raw (header=1).
`audit.json` ghi hash từng file nguồn/đầu ra, schema, config và môi trường.
Raw SHA-256 trước và sau đều:
`aac4cde1fed90857ea81a1575e326049be71a528f27a6a744435b94c42dfdda7`.
Analysis implementation đã khóa không thay đổi; không gọi solver hay chạy lại benchmark.
