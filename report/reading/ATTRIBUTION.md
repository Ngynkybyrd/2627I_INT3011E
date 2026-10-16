# Attribution đã xác minh và phần chưa khóa

Ngày kiểm 16/10/2026. Đây là ledger nguồn cho report/, không phải tuyên bố mọi
dependency/code của repository đã được audit.

| Thành phần | Đã làm / tài liệu phải giữ | Chưa được suy ra |
|---|---|---|
| cas-sc / TeX Gyre / Tectonic | SOURCES.md và vendor/ giữ bundle/manifest, LPPL, GUST license; compiler MIT notice ở .tools/tectonic/LICENSE. Không sửa vendor class. | Giấy phép compiler không áp chung mọi dependency trong TeX bundle. |
| Snapshot PySAT cardenc | evidence/bitwise.hh, seqcounter.hh giữ header nguyên bản; evidence/PySAT-LICENSE.txt giữ MIT notice; commit/URL trong bibliography và reading notes. | Không khẳng định code dự án đã chép các file này; đây chỉ là bản đọc nguồn upstream. Header BOLT được giữ, không bỏ credit hay suy author `aign` thành metadata cá nhân chưa xác minh. |
| Sudoku Exchange | Citation đúng file/commit. Bản LICENSE/README nguồn được nhóm data lưu ở data/source; diagnostics/data-source.md giữ hash/provenance. | Không coi dedication dữ liệu là giấy phép của QQWing/Sukaku Explainer, hoặc coi nhãn uniqueness là xác minh độc lập. |
| OR-Tools examples | Trang Google Developers ghi nội dung CC BY 4.0, code samples Apache 2.0; source LICENSE OR-Tools chính thức là Apache 2.0. | Nếu sao chép/adapt code, chủ code cần ghi file/commit, giữ notice thực áp dụng. Chưa có audit reuse cuối. |
| Glucose/MiniSat | Có nguồn citation tác giả và MiniSat theo yêu cầu upstream Glucose. | Không tuyên bố license của tất cả native engines từ MIT của Python wrapper; cần notice của bản solver thực đóng gói nếu phân phối binary/source. |
| HiGHS | Repo/README chính thức nêu MIT; đã thêm citation bài được upstream khuyến nghị và Python docs. | Bài dual simplex không mô tả toàn bộ MIP. Kiểm native notices theo gói phân phối thực tế. |
| Gurobi/CPLEX examples/runtime | Chỉ chuẩn bị citation tài liệu chính thức, không chép source ví dụ vào report. | `free/Community` không có nghĩa mã nguồn/license được phép phân phối lại. Cần giữ điều kiện package/runtime thực dùng và code-reuse ledger cuối từ chủ adapter. |
| Paper khoa học | BibTeX/ghi chú diễn giải ngắn kèm URL/DOI; không sao chép nội dung bài mẫu hoặc phân phối bản PDF toàn văn của nhà xuất bản. | Có quyền đọc không đồng nghĩa quyền tái sử dụng hình/bảng nguyên bản. |

Các dòng inventory trên ghi phạm vi gói đọc ban đầu. Delta audit code/runtime
đã freeze được ghi tại `FROZEN-CODE-ATTRIBUTION.md`, cùng hash bằng chứng và
phân biệt API call với source copy; trạng thái hiện hành ở
`../logs/REF-FROZEN-ACCEPTANCE.md`. Không tự đặt URL repo dự án, không tự công bố
mã hay gói runtime. File `references-check.tex`
chỉ kiểm mọi entry BibTeX, không phải danh mục tất cả nguồn bắt buộc xuất hiện
trong bài cuối; khi viết, chỉ cite nguồn thực sự dùng cho nhận định tương ứng.
