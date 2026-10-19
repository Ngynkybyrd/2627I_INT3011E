# Báo cáo cuốn chiếu — chỉ dùng dữ liệu đã kiểm chứng (19/10/2026)

Ủy quyền mới nhất: người dùng yêu cầu các chat liên quan chỉnh báo cáo ngay, và CHỈ dùng dữ liệu chắc chắn. Benchmark4worker/1rep đang chạy, tuyệt đối không dừng/sửa source/config/gate/runtime hoặc gọi thêm solver. Không sửa src/, scripts/prepare_expanded_data.py,run_expanded.py,analyze_expanded.py,authorize_expanded_local.py,run_expanded_parallel.py,report/prepare_expanded_report.py,docs/expanded-contract.md,expanded-acceptance.md,expanded-terminal-policy.md hay nguồn freeze cũ. Không chạy fullsuite/benchmark/build nặng song song. Chỉ focusedfake tests; TeXcompile1job BelowNormal khi cần. Không bật automation, push/nộp.

## Dữ liệu được phép

1. Bộ gốc results/raw/main-20261016-01 đãnghiệmthu:906lượt,903SAT+3TIMEOUT,3reps. Kiểm freeze/hash trước dùng. Phạm vi S80/B16/C10 riêng.
2. Bộ mở rộng: main liveDB results/expanded/wave3-20261019-212023-main/experiment.sqlite3. CHỈ lấy repetition1,110.000target,16.000đề(10kN9/5kN16/1kN25),cutoff10s. Manifest gốc330k/3reps giữ nguyên; receipt/session effective1/scope-rep1 mới là phạm vi đang thực hiện.
3. Lấy cố định3batch đầu theo thứ tự dataset-index (quy tắc định trước, không chọn theo hiệu năng). Chỉ xuất khi MỖI job rep1 của cả3batch đã có primary terminal SAT/TIMEOUT,raw/checker/cleanup/schema/hash/identity hợp lệ. Nếu chưa đủ hoặc bất kỳ kiểm tra thất bại: không dùng phần mở rộng, báo blocker; báo cáo vẫn dùng bộ gốc.3batch dựkiến480đề,3300lượt; phải tính từ manifest/DB rồi đối chiếu, không hardcode để bù thiếu.
4. SQLite backup nhất quán vào thưmụcNEW, đóng snapshot rồi kiểm độc lập; không phân tích live tip. Mọi artifact cósha256+receipt. Không dùng RUNNING/INTERRUPTED/reps2,3 hoặc logs/ETA làm sốliệu báo cáo. Không chọn bỏTIMEOUT; timeout làquan sát hợp lệ, không vô nghiệm.
5. Tách profile/session tuần tự và song song.4workersolverthreads1 là resource-contended; không gộp timings thành isolatedbenchmark, không so speedup giữa hai nhóm đề khác nhau. Chỉ paired timing trên đúngIDs chung trong cùngprofile.1rep không có median3lần hayclaimđộ ổnđịnh. Chỉ khẳng định trên tập đãđo;110k/16k làtarget, không nhận tấtcả hoàn tất.

## Phân quyền độc lập

SAT07(gpt-6.1-sol/high): chỉ viết scripts/export_expanded_rolling.py,tests/expanded/test_rolling_export.py và diagnostics/expansion/rolling-export/. Tạo snapshot đãkiểm vào results/rolling-snapshots/rolling-20261019-first3 (NEW). Reader contract ở dưới; gửi HANDOFF ngaykhi cówire/receipt thật. Không đổi fingerprintcore. Một backup+verify nhẹ, không solver.

SAT08(gpt-6.1-sol/medium): chỉ scripts/analyze_rolling_report.py,tests/expanded/test_rolling_analysis.py,diagnostics/expansion/rolling-analysis/ và results/rolling-analysis/rolling-20261019-first3. Đọc contract trước, làm reader/fake tests độc lập; chỉ chạy analysis thật sau root bàn giao snapshot07 PASS. Kết quả CSV/LaTeX/TikZ native córeceipt, tách profiles/coverage/matched IDs, SAT/TIMEOUT/PAR2 khai báo rõ. Không ép fixture vào producer; nếuwirekhác phối hợp root.

SAT09(gpt-6.1-sol/medium): chỉ report/rolling-20261019/. Tạo hai bản LaTeXVI/EN từ templateCAS/STIX hiện hành, bám mẫu gốc. Cập nhật phương pháp,nguồn/quota,family/mask,1rep/4worker/110ktarget,timeouts,limitations/DataAvailability repo thật, ghi scope1rep riêng và giữ kết quả gốc3rep riêng. Chưa có receipt08 thì dùng kết quả gốc; không điền sốmởrộng tựước lượng. Sau08PASS ghép sốhình/bảng đãkiểm rồi build haiPDFnháp riêng1joblầnlượt, kiểm font/caption/footnote/layout. Không ghi đèhaiPDFgốc17:34 hoặc toolsreportpinned. Không kếtluận toàn16k khi chỉ3batch.

SAT10(gpt-6-luna/medium): chỉ docs/rolling-report-handoff.md và diagnostics/expansion/rolling-package/. Chuẩn bị hướng dẫn ngắn phạm vi mới1rep/4workers/110k,paths/nguồngốc/v1+snapshot, phân biệt dữliệuđãkiểm với target. Chỉ điền hashes/PDFpaths khi filethật có; không tạozipfinal/nghiệmthu toànbộ. Không sửa mainREADME/pipelinepinned. Rà bàn giao đợt này khi đầu ra09 có.

Chỉroot sửa SAT-STATUS/SAT-THREADS/checklist. Cácchat chỉ gọi subagent khi cóviệc độc lập cần thiết, không kích hoạt cả4agent, không đọc lại toànhistory/PDF, báo cáo ngắn paths+hash+checks+blocker.

## Wire tối thiểu SAT07→SAT08

snapshot.json: schema_version=1,kind=VERIFIED_ROLLING_SNAPSHOT,full_experiment_complete=false,source_experiment_id,source_scientific_sha256,created_utc,selected_repetitions=[1],effective_repetitions=1,original_repetitions=3,target_jobs=110000,target_instances=16000,selected_batch_ids thứtự3batch,expected_jobs/observed_jobs,selected_instances,qa_passed=true vàevidence/hashes. Expected=observed3300,instances480 nếu đúng cấu hình. Filessha256 cho results.csv,instances.jsonl,snapshot.sqlite3,source-manifest.json,source-index.json,profiles.json (snapshot.json tựkhônghashchínhnó). Giữ manifest/index nguồn nguyênbyte.

results.csv: CSV_FIELDS coreexpandedexport cộng session_id,profile,workers,timing_policy. Only primaryrepetition1, SAT/TIMEOUT, selected3batch. profiles.json ánhxạsession với source sessionmanifest/hash,profile,workers=1cho originalsequential hoặc4cho parallel; cần phảnánh đúngmetadata thật. instances.jsonl chỉ480đề selected. Bảngđầu ra08 phải ghi selector3batch cốđịnh vàcoverage, nhận VERIFIED_SUBSET chứ không fullreport-ready. Không dùng analyzer cũ vốnstrict3reps/completeblocks330k.
### Delta capacity theo yêu cầu mới

Người dùng cho phép tăng nấc vượt40 nếu còn tài nguyên, giảm nấc nếu quá tải. Root đang chuẩn bị profilecapacity và sẽghi riêng từngsession/tài nguyên/worker. Không đổi selectorb001–b003 hoặc nguồn báo cáo theo hiệu năng. Tập snapshotbáocáo này phải dùng đúng profiles đãtồn tại trong3batch, không gán worker tươnglai cho dữliệu đãđo. Quy tắc1rep/110ktarget và không dùngchưakiểm giữ nguyên.
