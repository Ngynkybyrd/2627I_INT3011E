# Build hai báo cáo khoa học Việt/Anh

Hai bản dùng chung công thức, số liệu và nội dung song ngữ; kết quả lấy từ
analysis final đã khóa của main-20261016-01. Chỉ `report/` được thay đổi.
Source/data/results đã công bố tại repo thật, snapshot ban đầu bất biến
f45d37894cfb19fe3bb890e8f0e06f13b472c2a2. Root giữ bước push báo cáo cuối và final QA.
Không chạy solver hoặc thay đổi Python `.venv` của dự án để build report.

## Windows / PowerShell

Từ bất kỳ thư mục nào, dùng đường dẫn có dấu cách trong dấu nháy:

```powershell
& 'D:\KHMT\Project solo\report\bootstrap.ps1'
& 'D:\KHMT\Project solo\report\build.ps1'
```

`bootstrap.ps1` tải Tectonic 0.17.0 x86_64 Windows và template CTAN nếu chưa có.
Không cài hệ thống hoặc yêu cầu quyền administrator. Lần build online đầu cần
mạng để Tectonic tải các package, định dạng XeTeX và font vào `.tools/cache`.
Không đổi PATH hệ thống. Dùng PowerShell 7; nếu chính sách máy chặn script,
có thể chạy riêng phiên `pwsh -NoProfile -ExecutionPolicy Bypass -File <script>`
theo chính sách máy, không cần đổi execution policy lâu dài.

Sau khi cache đủ, build sạch mà không tải mạng:

```powershell
& 'D:\KHMT\Project solo\report\build.ps1' -Offline
```

Mỗi lần build dùng thư mục trung gian mới `build/<timestamp>/vi` và `en`, không
phụ thuộc `.aux`, `.bbl` hoặc `.toc` của lần trước. Tectonic tự chạy XeTeX,
BibTeX và các lượt giải quyết cross-reference. Source không yêu cầu shell escape.
Hai PDF được chép vào:

- `output/pdf/sudoku-vi.pdf`
- `output/pdf/sudoku-en.pdf`

Các file `sudoku-prototype-*` cũ là snapshot lịch sử, không phải output hiện hành.

Log console ở `logs/`; `.log`, `.blg`, `.bbl` và file rule do Tectonic sinh
`dependencies.mk` ở thư mục build tương ứng. Rule này chỉ để tham khảo vì đường
dẫn có dấu cách/outdir của Tectonic không phải Makefile portable. Manifest nguồn
thật ở `logs/source-dependencies.json`; cache package/font được giữ cục bộ.
`logs/latest-build.txt` chỉ cập nhật
sau khi cả hai ngôn ngữ build thành công.

## Cấu trúc và font

- `main-vi.tex`, `main-en.tex`: hai entrypoint `cas-sc` với `a4paper,fleqn`.
- `shared/`: class options, preamble, nội dung và công thức dùng chung; `\lang{Việt}{English}`
  đổi nhãn/văn bản, không tạo hai bộ công thức.
- `tables/final-*.tex`: bảng kết quả chung từ CSV final, giữ scope/matched count.
- `shared/model-and-encoding.tex`: PAPER-001..005, công thức/proof và văn bản
  hai ngôn ngữ dùng chung. `figures/example4.tex` là ví dụ dựng để minh họa;
  không phải output solver hoặc chứng nhận uniqueness.
- `shared/introduction.tex`: VI-001 và PAPER-008, Introduction/Related Work,
  câu hỏi nghiên cứu và phạm vi đóng góp; chưa có kết luận hiệu năng.
- `shared/baseline-models.tex`: PAPER-006, CP AllDifferent/ILP khả thi theo
  handoff builder đã nghiệm thu; không khẳng định adapter solve đã hoàn tất.
- `shared/solver-workflow.tex`: PAPER-007 và VI-002, giả mã và cách gọi các
  adapter đã bàn giao, decoder/checker và ranh giới measurement-end/hard guard.
  Hard guard và hook START/END đã qua pilot rồi dùng trong 906 lượt chính;
  timeout native vẫn là hợp tác.
- `shared/experimental-setup.tex`: VI-003, metadata main/freeze,
  preselection S80/B16/C10, 906 lượt và timing/watchdog, quy tắc aggregate.
- `shared/abstract.tex`, `results.tex`, `conclusion.tex`, `data-availability.tex`:
  phần khoa học cuối dùng cùng numeric macros `result-values.tex` ở cả hai bản.
- `export_final_results.py`: chỉ đọc summary/paper final đã khóa, kiểm hash
  với verification.json, format sáu bảng, macros và copy hai PDF figure vào
  report/. Không tái phân tích raw, không gọi solver. Provenance/hash đầu vào
  ở `logs/final-results-provenance.json`.
- `shared/limitations.tex`: VI-005, bias/uniqueness, matched subsets,
  timeout censoring, giới hạn bản miễn phí và giới hạn khái quát hóa.
- `export_model_counts.py`: đọc diagnostics/model/results.json đã nghiệm thu,
  kiểm số học rồi sinh `tables/cnf-counts.tex` dùng chung. Chạy bằng Python
  standard library; không giải đề hoặc sửa diagnostics. Log nguồn/hash tại
  `logs/paper-counts-verification.json`.
- `figures/block-layout.tex`: hình vector kiểm dàn trang do report tạo; không phải
  hình kết quả hoặc ví dụ solver từ nhóm phân tích.
- `references.bib`: bibliography chung. BibTeX style chính thức nằm trong vendor.
- `vendor/els-cas-templates/`: toàn bộ bundle cas-sc 2.4 nguyên bản, gồm class,
  style, bibliography style, template, tài liệu và manifest.

Tectonic dựa trên XeTeX; `fontspec` dùng TeX Gyre Termes/Heros dạng OTF từ
TeX bundle, có glyph tiếng Việt. Không phụ thuộc font cài thêm trên Windows.
Font monospace là Latin Modern Mono OTF `lmmono8-regular.otf` đã nằm trong cache,
dùng cho tên API/đường dẫn trong phần toán.
`shared/class-options.tex` dùng hook LaTeX để tắt STIX 8-bit tùy chọn của class;
math dùng `unicode-math` và `texgyretermes-math.otf`, tránh sai ký hiệu khi ghép
fontspec với STIX cũ. `FONTCONFIG_FILE` cũng được đặt riêng trong process build,
không đổi cấu hình hệ thống. Class cas-sc 2.4 đặt stock 192×262 mm;
`\geometry{a4paper}` trong preamble chuyển PDF sang A4 thật 210×297 mm trong khi
giữ class gốc nguyên vẹn. Các công thức vẫn căn trái theo `fleqn`.

Abstract của cas-sc được ghi verbatim ra `.abs`. Dùng `\begin{abstract}[]` rồi
`\input{shared/abstract}` để optional-argument parser không làm mất
macro đầu dòng. Hai nhánh ngôn ngữ được kiểm trong PDF. Các float dùng `pos=H`
với package `float`; tùy chọn `hypertexnames=false` tránh anchor trùng. Footer
được đặt trong preamble với tên tác giả/lớp để không hiện dòng bài mẫu gửi Elsevier;
không điền ORCID hoặc tên giảng viên giả.

## Kiểm PDF

`verify_pdf.py` cần Python với `pypdf` và `pypdfium2`, chỉ dùng để kiểm và render;
đây không phải dependency build LaTeX. Trong môi trường Codex hiện tại:

```powershell
& 'C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'D:\KHMT\Project solo\report\verify_pdf.py'
```

Script kiểm A4, thông tin sinh viên, không còn nhãn prototype/pre-main, metrics
sáu chữ số thập phân từ bảng, coverage count, glyph thiếu,
cross-reference/citation thiếu và overfull box trong log cuối; render toàn bộ
trang vào `output/preview/`. Đọc ảnh thủ công để kiểm chồng chữ/cắt hình và dấu.
Kết quả kiểm máy lưu tại `logs/verification.json`.

## Trạng thái khoa học và phần còn thiếu

Đợt chính đủ 906 lượt: 903 SAT và 3 TIMEOUT của một ID HiGHS. Results,
Abstract và Conclusion đã viết theo findings/CSV final; không tái dùng pilot.
Phần toán PAPER-001..005 đã đối chiếu model/CNF contract v1; bảng count từ
diagnostics vẫn được ghi rõ là kiểm cấu trúc, tách khỏi count thực main.
Giảng viên đã được người dùng xác nhận: TS. Tô Vân Khánh;
nguồn thông tin hiện hành là docs/submission-info.md.
Repo công bố là https://github.com/Ngynkybyrd/2627I_INT3011E ; snapshot ban đầu
f45d37894cfb19fe3bb890e8f0e06f13b472c2a2 chứa source/data/results đã được root
kiểm toàn bộ 1.384 blob GitHub với bản cục bộ. Data Availability dùng link repo
và link commit này. Báo cáo hoàn thiện sau snapshot, root sẽ push sau final QA.
Không tự nộp bài. Xem `logs/PUBLISHED-AVAILABILITY-HANDOFF.md` cho trạng thái
hiện hành; `SETUP-LIMITATIONS-ACCEPTANCE.md` là snapshot trước main.

Không dùng compiler standalone của app cho project nhiều file này. Có thể mở
source trong editor bất kỳ; chỉ lệnh build thành công mới chứng minh đã biên dịch.

## Nguồn và phân phối

Xem `SOURCES.md`. Giữ vendor/manifest/attribution khi chia sẻ nguồn. `.tools` chứa
compiler/cache lớn, `build` chứa trung gian và `output/preview` chứa ảnh kiểm;
có thể loại chúng khỏi gói nộp sau khi đã bảo toàn nguồn, hai PDF, build instruction
và bằng chứng cần thiết. Muốn build offline phải giữ cache và compiler hiện có.
