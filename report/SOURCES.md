# Nguồn toolchain và template

Ngày tải/kiểm: 16/10/2026. Không dùng nguồn bài mẫu làm nội dung khoa học.

| Thành phần | Nguồn chính thức | Điều kiện/ghi chú |
|---|---|---|
| Elsevier CAS bundle 2.4 (2024-05-04) | https://ctan.org/pkg/els-cas-templates | LPPL; giữ nguyên class/style và toàn bộ manifest/bundle |
| Archive template | https://tug.ctan.org/macros/latex/contrib/els-cas-templates.zip | Bản archive tải được lưu ở vendor/ |
| Tectonic 0.17.0 Windows x86_64 | https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.17.0 | MIT cho dự án Tectonic; các thư viện tích hợp theo giấy phép riêng của upstream |
| Compiler archive | https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip | Compiler portable; không cài hệ thống |
| Tectonic installation | https://tectonic-typesetting.github.io/book/latest/installation/ | Hướng dẫn upstream |
| TeX/font dependencies | Bundle mặc định Tectonic được tải theo nhu cầu | Cache cục bộ `.tools/cache`, danh sách file thực dùng ở build/*/*/dependencies.mk |
| TeX Gyre font project | https://www.gust.org.pl/projects/e-foundry/tex-gyre | Font OTF từ TeX bundle; GUST Font License; không sao chép font thương mại từ Windows |

`vendor/els-cas-templates/README`, `manifest.txt` và header class chứa thông tin
bản quyền/LPPL. Bản văn LPPL 1.3c được lưu tại `vendor/LPPL-1.3c.txt`.
`.tools/tectonic/LICENSE` chứa MIT notice của Tectonic. Việc dùng binary không có
nghĩa mọi thư viện/font trong TeX bundle đều có cùng giấy phép MIT.
`vendor/GUST-FONT-LICENSE.txt` giữ bản văn giấy phép font từ thư mục doc/tex-gyre
của CTAN.
Không thay đổi file class/style của Elsevier. Thay đổi cho A4 và font được đặt
trong source riêng ở shared/preamble.tex.

`logs/download-sha256.json` ghi checksum archive/compiler và ba file template
được dùng trực tiếp. Thông tin release GitHub tải tại `.tools/release.json`.
Bibliography chung còn chứa nguồn mô hình/solver/dataset; audit REF-002/003 của
frozen code/runtime nằm tại `reading/FROZEN-CODE-ATTRIBUTION.md` và
`logs/REF-FROZEN-ACCEPTANCE.md`. URL repo dự án chưa được cung cấp.
