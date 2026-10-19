# EXP-03 — Đặc tả kiểm thử và cổng QA mở rộng

Ngày 19/10/2026, Asia/Saigon. **Đây là kế hoạch kiểm thử, chưa phải kết quả pass.**
Nguồn phạm vi: SAT-EXPANSION.md và đầu SAT-STATUS.md hiện hành. Chỉ root nghiệm
thu/chỉnh checklist. Chưa viết tests phụ thuộc API mới, chưa chạy suite, solver,
pilot hoặc benchmark trong gói này. Các tên trường dưới đây là khái niệm;
contract versioned được nghiệm thu của 07 mới quyết định tên/API cụ thể.

## 1. Căn cứ code và ranh giới bảo toàn

Đã đọc trực tiếp: docs/runner-api.md, results-schema.md;
src/sudoku/validation.py; các entrypoint và kiểm hash/cleanup trong runner.py,
runner_process.py; generator/fingerprint ở scripts/prepare_data.py; các ca
Windows guard/process cleanup trong tests/test_runner.py.

- Checker hiện có `check_solution(Puzzle, solution) -> ValidationResult` kiểm
  shape, exact-int 1..N, hàng/cột/khối và clues; không dùng SAT encoding.
- `run_job` dùng Job Object trước khi mở gate worker; START/END có deadline,
  startup/postprocessing watchdog riêng; cleanup phải xác nhận hết descendants.
- Schema v1 dùng CSV + file solution, từ chối CSV đã tồn tại khi execute; không
  có transaction SQLite/attempt/resume. Không suy v1 đã đáp ứng yêu cầu mới.
- Giữ nguyên S80/B16/C10, execution/data freeze, 906 raw và analysis cũ.
  Tests mới dùng fixture/thư mục/DB riêng; không sửa schema v1 để nhận dữ liệu
  mới. Hồi quy sau tích hợp phải chứng minh reader v1 và snapshot cũ vẫn nguyên.

## 2. Contract cần 07 chốt trước phần việc phụ thuộc

| ID | Quyết định cần có trong docs/expanded-contract.md | Điều kiện để viết test |
|---|---|---|
| C01 | Version của dataset/run/DB/CSV; API tạo, đọc, resume, export; hành vi với version lạ | Unknown/incompatible version bị từ chối rõ, không tự migrate/ghi lại v1 |
| C02 | 05↔07: canonical bytes dùng dedup và bytes file dùng integrity; ID/hash/witness liên kết, root_id/family/rating/source/license; rounding actual clues | Có fixture hợp lệ và fixture sai, định nghĩa hash tách biệt không phụ thuộc metadata/path |
| C03 | Ma trận preflight theo N, schedule/block/pilot identity và hash; quy tắc root thuộc block | Có danh sách job hợp lệ khóa trước đo; không giả định 330.000 nếu preflight khác |
| C04 | Logical job key, encoding baseline null/empty chuẩn hóa, repetition, experiment namespace; ràng buộc DB unique/FK | Không có key trùng qua encoding thiếu/NULL và không gộp hai experiment |
| C05 | State machine attempt/job: RUNNING/INTERRUPTED/terminal; khi nào ghi RUNNING, kết quả được công nhận, liên kết attempt trước/sau | Crash không biến thành UNSAT/TIMEOUT; một logical job chỉ có một kết quả chính thức |
| C06 | Claim/lock experiment và job; owner token, chống writer cũ, stale recovery, chứng minh worker/process tree cũ đã chết | Hai runner không solve đồng thời; không thu hồi chỉ vì PID không còn/lease hết khi chưa loại PID reuse hoặc process con |
| C07 | Ranh giới transaction result+witness+attempt-final; witness payload ở DB hay artifact ngoài; durability/journal/synchronous/FK settings | SQLite commit không được coi là nguyên tử với file ngoài nếu chưa có protocol và cleanup/reconciliation |
| C08 | Resume fingerprint code/data/config/env/matrix/schedule/schema; fingerprint gồm gì, so package/native runtime ra sao | Mismatch từ chối trước claim/solve; đổi fingerprint cần experiment mới, không override âm thầm |
| C09 | Hành vi stop/recovery khi invalid solution, witnessed UNSAT, cleanup lỗi, disk full/DB busy, user interrupt | Lưu evidence trước khi dừng; không khởi động lượt tiếp theo; có đường điều tra được root nghiệm thu |
| C10 | `--complete-blocks`: thế nào đủ 3 reps/ma trận, terminal status nào cho phép; chọn attempt chính thức; snapshot export lúc đang chạy | TIMEOUT không thành thiếu job; ERROR/LICENSE_LIMIT/UNAVAILABLE bất ngờ không bị loại để tạo block giả đủ |
| C11 | Deadline/walltime/startup/checker/cleanup timestamps và null semantics; mốc ngừng launch 22:30 Asia/Saigon | Không tăng ngân sách solve, không ghi cutoff làm thời gian thật, mốc giờ có thể tiêm clock trong test |
| C12 | Export columns/order/CSV UTF-8, precision/null/status/raw status, solution hashes, provenance, ID sets cho analysis | SQLite→CSV round-trip giữ identity, số liệu và partial; 08/06/10 dùng cùng định nghĩa |

03 có thể chuẩn bị fixture độc lập về Sudoku trước; tests transaction/resume/
schema phải chờ C01–C12 tương ứng. Runtime matrix từ 04 và dữ liệu từ 05 là
đầu vào kiểm tích hợp, không phải giả định mọi solver/mọi N chạy được.

## 3. Ma trận kiểm dữ liệu và correctness

| ID | Ca kiểm/đối chứng độc lập | Kỳ vọng nghiệm thu |
|---|---|---|
| D01 Schema/input | n>=2 exact int; bool/float/string, thiếu trường, hàng/cột sai, âm/vượt miền, JSON/UTF-8 hỏng, file thiếu; ID/path traversal | INVALID_INPUT hoặc lỗi chuẩn schema; không gọi solver, không ghi accepted observation |
| D02 Witness | Thiếu witness, sai hash/instance/N, wrong shape/domain, lỗi từng hàng/cột/khối, thay clue dù bảng vẫn hợp lệ | Mọi đề admitted có witness checker pass; lỗi không được chữa bằng encoder hoặc đáp án mẫu; witness không truyền làm constraint cho solver |
| D03 Public 9 | Đủ 2.500 mỗi easy/medium/hard/diabolical; commit d8c8ebaee0c08c412cfba96af1923dfa61c83317; source file/URL/license/SHA/rating gốc | Chọn bằng seed trước đo; thiếu nguồn/đủ số sau dedup chưa đạt thì báo thiếu, không tự bổ sung nhóm khác hoặc bịa rating |
| D04 Exact dedup | Cùng n/grid nhưng khác JSON whitespace, metadata, thứ tự key, BOM; duplicate xuyên bốn nguồn, synthetic và bộ cũ | Canonical content hash thống nhất; không đưa rating/root vào fingerprint; bytes hash vẫn phát hiện file đổi. Không gọi exact dedup là loại đẳng cấu |
| D05 Synthetic | 1.000 roots N16, 200 roots N25; mỗi root 5 mật độ 20/30/40/50/60%; kiểm seed/family/root_id/actualclues/witness hash | N16 mỗi mức 1.000, N25 mỗi mức 200; họ cân bằng, mỗi root một họ ổn định; mask là subset của witness và số clues theo rounding C02 |
| D06 Dedup/resampling | Cố ý ép collision và seed trùng; sinh lại theo policy đã chốt; thử cạn candidate | Log rejected/actual seed, root/mask liên quan và lý do; deterministic; không sửa file đã khóa hoặc tự giảm target. Sau sinh lại vẫn đủ 5 mask/root, quota và balance |
| D07 UTF-8/paths | Đường dẫn có dấu cách/tiếng Việt; metadata Unicode; BOM theo contract; CSV quoting, newline, empty field | Import→DB→export giữ bytes/content đúng theo contract; lỗi encoding không âm thầm thay ký tự |
| D08 Freeze/tamper | Thay puzzle, witness, manifest, source, seed, matrix, schedule hoặc config một byte | Hash mismatch bị chặn trước chạy/resume/export accepted; giữ snapshot cũ, không tự cập nhật hash để pass |
| D09 Block balance | 100 blocks, mỗi block 100 N9 (25/nhóm), 50 N16 (10/mức, mỗi họ 5/mức), 10 N25 (2/mức, mỗi họ 1/mức) | 160 IDs/block, không trùng xuyên block; root relationship giữ trong manifest/export. Policy gom/tách roots phải được C03 chốt |
| D10 Counts | Ma trận dự kiến 8 cấu hình N9, 5 N16/25, 3 reps | Theo preflight dự kiến 330.000 jobs và 3.300/block; pilot 8 N9+10 N16+10 N25, 1 rep =164 jobs. Pilot tách main; chưa đủ số không claim đạt target |

Uniqueness public giữ nhãn attribution từ nguồn khác với bằng chứng tự chứng
minh. Synthetic luôn `unverified`; không lấy witness làm chứng nhận unique.
Tests số lượng dùng manifest/fixture nhỏ trước; chỉ quét dataset đầy đủ sau
khi 05 bàn giao, không sinh 16.000 đề để kiểm một API.

### Whole-cycle trade (D11)

Với một bảng hoàn chỉnh đã checker pass, chọn hai hàng A,B khác nhau **cùng
band**. Định nghĩa permutation p trên giá trị bằng `p(A[c]) = B[c]`. Chọn
**trọn một chu trình** của p; tập cột S có A[c] thuộc chu trình đó. Tráo A[c]
và B[c] tại tất cả c thuộc S, rồi kiểm lại độc lập bảng hoàn chỉnh và masks.

Kiểm độc lập: p là bijection; chu trình không lặp/đứt và đóng về điểm đầu;
tập cột đúng preimage của chu trình; ngoài hai hàng/cột S không đổi; mỗi cột
giữ multiset; mỗi hàng vẫn chứa 1..N; blocks giữ hợp lệ vì hai hàng cùng band.
Tráo cùng S lần thứ hai khôi phục bảng gốc. Fixture có chu trình dài hơn 2
được chọn cố định; tráo strict nonempty proper subset phải bị kiểm hàng hoặc
checker loại. Fixture hai hàng khác band có thể tạo block lỗi dùng làm ca âm
cụ thể, không khẳng định mọi trade khác band đều sai. Chu trình phủ mọi cột
có thể tương đương đổi hai hàng: vẫn hợp lệ, không chứng minh đề không đẳng
cấu hoặc họ mới có độ khó cao hơn. Metadata phải ghi nguồn/gốc/trade/seed thực
dùng theo C02; không tự suy cân bằng họ từ hash nghiệm.

### K01 correctness suite (độc lập dữ liệu benchmark)

Tái dùng oracle backtracking 4×4 không import encoder; full, single-hole,
blank/multiple, sparse/multiple, conflict hàng/cột/khối, UNSAT không trùng clue
trực tiếp. Giữ semantics: cấu trúc clue hợp lệ nhưng mâu thuẫn là UNSAT,
không INVALID_INPUT; nhiều nghiệm chỉ cần một nghiệm hợp lệ.

Đối chiếu cả ba SAT encoding và backend trong ma trận khả dụng trên cùng
fixture nhỏ. Mỗi SAT phải qua checker. Giữ kiểm AMO/EXO input 3/4/5 với aux
tự do, aux không đè primary/nhóm khác, mapping bốn cỡ, decoder chỉ primary.
Smoke N16/N25 theo runtime đã xác nhận; ưu tiên tái dùng evidence có hash còn
khớp, chỉ solve bổ sung phần tích hợp thiếu. LICENSE_LIMIT/UNAVAILABLE có lý
do không phải pass đồng thuận; không lặp probe giới hạn lớn đã biết.

## 4. SQLite, attempt, locking và resume

Các ca dưới đây tiêm lỗi bằng process fixture/điểm ngắt được contract cho
phép; không kill runner thật hoặc ghi vào DB nghiên cứu để thử crash.

| ID | Vị trí/sự kiện | Bất biến phải giữ |
|---|---|---|
| T01 | Hai connection claim cùng job/experiment cùng lúc | Một owner có quyền chạy; runner còn lại từ chối/đợi theo C06, không launch solver thứ hai; baseline encoding NULL không né unique key |
| T02 | Crash trước claim hoặc sau commit RUNNING, trước launch | Chưa có accepted result; RUNNING tồn tại được nhận diện interrupted sau recovery an toàn; job chưa launch không thành TIMEOUT |
| T03 | Crash trong build/solve; parent chết khi còn worker/con solver | OS containment dọn process tree; trước resume phải chứng minh cleanup; giữ attempt INTERRUPTED với thời gian chỉ biết thực, không đoán solver status |
| T04 | Solve xong nhưng chưa validate/chưa transaction | Không publish SAT/witness chưa kiểm; nếu mất kết quả, attempt sau có thể solve lại nhưng lịch sử cũ còn; không claim solve exactly-once |
| T05 | Lỗi giữa insert witness/result/finalize attempt, trước COMMIT | Rollback toàn bộ accepted publication: không row SAT thiếu witness, không witness trỏ sai job, không terminal job thiếu final attempt |
| T06 | Crash sau COMMIT nhưng trước ACK/export/tiến độ | Resume nhận kết quả đã commit, không solve/insert lại; export tái tạo từ DB, không tin CSV tiến độ cũ |
| T07 | Witness là file ngoài SQLite (nếu C07 chọn) | Tiêm crash trước/giữa/sau file publish và DB commit; accepted result không có dangling path/hash; orphan được nhận diện, không nhập thành nghiệm. Transaction DB đơn thuần chưa đủ |
| T08 | Retry resume sau interrupt, gọi resume lặp | Attempt number/ID tăng và liên kết audit; attempt cũ append-only, tối đa một observation chính thức/logical job; không ghi đè kết quả terminal |
| T09 | TIMEOUT/ERROR đã commit | Không tự retry để chọn lần nhanh/SAT; TIMEOUT vẫn là observation; ERROR giữ evidence theo stop policy, không biến thành interrupted để tự retry |
| T10 | Stale lock/owner cũ quay lại sau recovery, PID reuse, runner thứ hai mở DB | Fencing/ownership theo C06 từ chối late writes/launch; không dùng chỉ PID/mtime làm bằng chứng cleanup; xác nhận một worker đo tại mọi thời điểm |
| T11 | Mismatch code/data/config/env/matrix/schedule/schema khi resume | Từ chối trước launch/claim/publication; old attempts/DB không đổi; experiment mới có namespace riêng nếu root cho thay đổi |
| T12 | DB busy, disk full, permissions, interruption trong COMMIT | Không báo checkpoint thành công khi chưa durable; dừng launch, giữ DB nhất quán và evidence; lần recovery kiểm lại integrity/FK theo cấu hình thực dùng |
| T13 | Reader/export đồng thời commit, export bị ngắt rồi làm lại | Một snapshot nhất quán, không lẫn row/witness nửa commit; complete-blocks xét cùng snapshot; export mới không ghi đè raw DB hoặc snapshot cũ |

Chạy kiểm integrity DB và foreign-key theo policy C07 sau các ca crash; không
gọi `integrity_check` là chứng minh không mất điện vật lý. Test kill process
chỉ xác minh fault model đã mô tả với settings SQLite thực dùng.

## 5. Cổng timeout, fairness và dừng an toàn

| ID | Ca kiểm | Kỳ vọng |
|---|---|---|
| G01 | Build chiếm gần/hết budget, native solve chậm hoặc trả SAT muộn | 10 giây gồm build/setup/solve; solve chỉ nhận phần còn lại, không được cấp thêm 10 giây; late/no END là TIMEOUT, không nhận SAT muộn |
| G02 | Import/read startup chậm, checker/decode/cleanup chậm sau END đúng hạn | Startup và postprocessing có watchdog riêng; không tăng ngân sách đo; checker/cleanup ngoài build+solve, walltime vẫn ghi riêng |
| G03 | END sát deadline, notification đến trễ, result đến trước END hoặc không có END | Giữ recheck shared state hiện hành; không nhận kết quả chỉ vì pipe đến; unknown component là null, không bịa 0/cutoff |
| G04 | Worker hang, child hang, worker hoàn tất để orphan, fail AssignProcess/cleanup | Job Object được gán trước gate; terminate/wait đến zero descendants trước lượt mới. Cleanup failure là ERROR và dừng batch, không giả TIMEOUT/skip |
| G05 | Parent bị kill/user interrupt lúc worker đang chạy | Process tree không sống tiếp cạnh tranh lần resume; attempt lifecycle theo T03, không claim checkpoint thành công khi chưa commit |
| G06 | Result SAT sai clue/domain/khối, decode fail hoặc witnessed SAT bị UNSAT | Lưu raw/evidence và dừng trước launch kế; không admit thành công, không thay witness/dataset hoặc retry tự động để che sai |
| G07 | Một thread/worker theo backend; model/solver mới mỗi job; measurement hook | Configuration/runtime readback theo 04; không model cache riêng một phương pháp; SQLite/checker/export không nằm trong thời gian solver, có walltime riêng |
| G08 | Tới mốc 22:30 Asia/Saigon, job đã chạy, rồi resume sau cutoff launch | Không mở lượt mới sau mốc đã chốt; xử lý lượt đang chạy theo deadline cũ và checkpoint. Policy override/chạy tiếp sau hạn phải tường minh, không lách qua resume |

Không chạy sinh dữ liệu, build PDF, solver nặng hoặc nhiều runner cạnh tranh
trong pilot/main. 03 chỉ điều khiển tests correctness được giao; **07 là chat
duy nhất điều khiển benchmark**. Native time limit không thay hard guard.

## 6. Export, thống kê và điều kiện mở cổng

E01: fixture hai block với missing rep, interrupted attempt, all-SAT,
mixed SAT/TIMEOUT, terminal ERROR và witness lỗi. `--complete-blocks` chỉ lấy
block đủ **toàn ma trận hợp lệ × ba reps** trong snapshot, checker/hashes đạt;
pilot một rep không bao giờ được nhận thành main block. TIMEOUT vẫn đủ một
observation, khác thiếu attempt. Unexpected license/runtime/error không bị
âm thầm bỏ khỏi ma trận để block thành đủ; xử lý theo C09/C10 trước export QA.

E02: CSV xuất giữ logical key/attempt chính thức, null/timing/status/raw status,
solution hash và manifest joins. Đếm SQLite→CSV bằng key sets và hash/provenance,
không chỉ tổng số dòng. Export lại cùng snapshot deterministic theo C12;
partial vẫn lưu trong DB, có báo cáo riêng và không trộn kết luận main.

E03 (bàn giao 08): cùng IDs cho paired comparisons; runtime thành công dùng
median ba SAT cho từng đề, mixed status báo riêng. p90/p95 trên medians từng
đề, cần chốt interpolation/mẫu số; PAR-2 theo từng lượt TIMEOUT=20 với cutoff
10, loại lỗi/license/unavailable khỏi penalty và công bố coverage. Không tính
reps hay năm masks/root thành mẫu độc lập; cluster uncertainty theo root_id,
giữ quan hệ root kể cả tách block. Không suy độ phức tạp thuần từ nguồn khác N.

| Cổng | Đầu vào | Bằng chứng đạt trước bước tiếp |
|---|---|---|
| QA-A Contract | C01–C12, model review 02, matrix/fairness 04, inventory 01 | Root nghiệm thu contract; chưa code theo API tạm hoặc tự mở task kế |
| QA-B Data/correctness | 05 dataset+witness, freeze mới và unit/integration fixtures | D01–D11/K01 correctness đạt; không bất đồng nghiệm, không unknown license giả timeout |
| QA-C Persistence/guard | 07 runner/SQLite, 06 API CLI ổn định | T01–T13/G01–G08/E01–E02 đạt; suite hồi quy v1 hiện hành pass; không sửa frozen v1 để tests pass |
| QA-D Pilot | QA-A/B/C và gate workload độc quyền | Pilot riêng 28 đề/164 lượt dự kiến theo matrix; checker/cleanup/timing/CSV khớp; walltime thật mới cho ETA, không claim 330k sẽ đủ hôm nay |
| QA-E Main/report | Freeze code/data/config/env/matrix/schedule sau pilot | Chỉ 07 chạy main; block đủ và QA mới vào report trước hạn23:59; phần chưa đủ giữ checkpoint, không nhận đủ16.000 |

## 7. Bằng chứng và bàn giao

Khi được giao triển khai tiếp, lưu command, Python/package/version, JUnit/log,
seed fixture/fault point, danh sách test pass/fail/skip có lý do; hash source/
DB/export/artifact liên quan; chỉ rõ host Windows và ca cleanup thực chạy.
Không coi mock status là bằng chứng hard kill; không claim suite cũ vừa chạy
lại nếu chỉ đọc log cũ. Snapshot thời gian/ID/attempt trước và sau crash phải
đủ để truy nguyên, không log credentials hoặc lưu CNF từng job.

03 bàn giao evidence và issue file+repro qua root cho 07 (cổng chạy chính),
05 (data/witness/trade), 04 (adapter/fairness) và 10 (tái lập/gói). 08 nhận
fixture/key sets/status definitions sau contract; 09 chỉ nhận block đã QA
qua 08. Không sửa module chủ khác để tests pass, không tự tick checklist.

**Trạng thái EXP-03:** đã đặc tả; chưa có test mới hoặc execution evidence.
API/schema/attempt/lock từ 07 và contract05↔07 được root nghiệm thu là đầu vào
thực sự còn thiếu cho bước triển khai tests phụ thuộc, không phải blocker
để hoàn tất tài liệu kế hoạch này.
