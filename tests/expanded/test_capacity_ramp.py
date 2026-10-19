"""Pure policy and selection tests; never execute solvers or inspect host RAM."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2]/"scripts/run_capacity_ramp.py"
SPEC = importlib.util.spec_from_file_location("capacity_ramp_tests", PATH)
ramp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ramp)


def stage(workers, rate, *, cpu=60, ram=16000, throttle=0, cap=None, resource=False):
    return dict(requested_workers=workers, cpu_percent=cpu, min_available_mb=ram,
                resource_stopped=resource, metrics=dict(new_jobs=320, jobs_per_second=rate,
                effective_memory_cap=cap or workers, ram_throttle_count=throttle))


@pytest.mark.parametrize("field", ["driver_sha256", "coordinator_sha256", "scientific_sha256", "allowed_ladder",
                                  "selected_repetitions", "target_jobs", "stage_jobs", "min_available_ram_mb",
                                  "worker_memory_reserve_mb_initial", "accepted_by", "allow_final_run"])
def test_policy_exact_hash_and_subject_binding(tmp_path, monkeypatch, field):
    monkeypatch.setattr(ramp, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="a"*64)
    receipt = ramp.policy_subject(manifest)
    path = tmp_path/"root.json"
    ramp.capacity.write(path, receipt)
    ramp.verify_policy(manifest, path, ramp.capacity.sha(path))
    receipt[field] = "tampered"
    ramp.capacity.write(path, receipt)
    with pytest.raises(ramp.capacity.ExpandedError, match="subject mismatch"):
        ramp.verify_policy(manifest, path, ramp.capacity.sha(path))


def test_policy_receipt_hash_cannot_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ramp, "ROOT", tmp_path)
    manifest = dict(experiment_id="test", scientific_sha256="a"*64)
    path = tmp_path/"root.json"
    ramp.capacity.write(path, ramp.policy_subject(manifest))
    with pytest.raises(ramp.capacity.ExpandedError, match="SHA256 mismatch"):
        ramp.verify_policy(manifest, path, "0"*64)


def test_five_percent_tie_prefers_smaller_workers_and_rolls_back():
    stages = [stage(8, 10), stage(16, 10.4), stage(24, 10.5), stage(32, 8)]
    assert ramp.best_stage(stages)["requested_workers"] == 8
    keep, reason = ramp.next_stage_decision(stages)
    assert not keep and "85 percent" in reason


def test_strong_improvement_selects_best_and_uses_effective_cap():
    stages = [stage(8, 10), stage(16, 12), stage(24, 15, cap=20)]
    assert ramp.best_stage(stages)["metrics"]["effective_memory_cap"] == 20


def test_two_saturated_plateau_stages_stop():
    assert not ramp.next_stage_decision([stage(8, 10), stage(16, 10.2, cpu=90), stage(24, 10.4, cpu=92)])[0]
    assert ramp.next_stage_decision([stage(8, 10), stage(16, 10.2, cpu=60), stage(24, 10.4, cpu=62)])[0]


@pytest.mark.parametrize("cpu,ram,rate,allowed", [(84, 11000, 12, True), (85, 16000, 12, False),
                                                   (60, 10239, 12, False), (60, 16000, 10, False)])
def test_above_forty_requires_spare_resources_and_improving_throughput(cpu, ram, rate, allowed):
    assert ramp.next_stage_decision([stage(32, 10), stage(40, rate, cpu=cpu, ram=ram)])[0] is allowed


@pytest.mark.parametrize("cpu,ram,throttle,reserve", [(84, 12288, 0, 128), (85, 16000, 0, 256),
                                                      (60, 12287, 0, 256), (60, 16000, 1, 256)])
def test_memory_reserve_relaxation_requires_stage_forty_evidence(cpu, ram, throttle, reserve):
    assert ramp.next_reserve([stage(40, 10, cpu=cpu, ram=ram, throttle=throttle)]) == reserve
    assert ramp.next_reserve([stage(32, 10)]) == 256


def test_resource_stop_excluded_from_best_and_stops_ramp():
    safe = stage(8, 10)
    unsafe = stage(16, 20, resource=True)
    assert ramp.best_stage([safe, unsafe]) is safe
    assert not ramp.next_stage_decision([safe, unsafe])[0]


def test_immutable_receipt_is_never_overwritten(tmp_path):
    path = tmp_path/"receipt.json"
    ramp.immutable_json(path, dict(stage=1))
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        ramp.immutable_json(path, dict(stage=2))
    assert path.read_bytes() == before


def test_cpu_percent_accounts_for_kernel_including_idle():
    assert ramp.cpu_percent((100, 1000), (120, 1100)) == 80


def test_stage_uses_shell_free_cli_bound_authorization_and_single_thread_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(ramp, "ROOT", tmp_path)
    monkeypatch.setattr(ramp, "cpu_times", lambda: (0, 0))
    experiment, output = tmp_path/"experiment", tmp_path/"output"
    experiment.mkdir()
    output.mkdir()
    (experiment/"session-manifests").mkdir()
    manifest = dict(experiment_id="test", scientific_sha256="a"*64, config=dict(repetitions=3))
    policy_path = tmp_path/"root.json"
    ramp.capacity.write(policy_path, ramp.policy_subject(manifest))
    ref = ramp.verify_policy(manifest, policy_path, ramp.capacity.sha(policy_path))
    seen = []
    class Child:
        def poll(self):
            return 4
        def wait(self):
            return 4
    def fake_popen(argv, **kwargs):
        assert kwargs["shell"] is False
        assert argv[argv.index("--max-jobs")+1] == "320"
        assert argv[argv.index("--workers")+1] == "40"
        assert argv[argv.index("--repetition")+1] == "1"
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            assert kwargs["env"][key] == "1"
        auth = ramp.capacity.read(argv[argv.index("--authorization")+1])
        assert auth["delegated_root_policy_ref"] == ref
        assert auth["worker_memory_reserve_mb"] == 256
        ramp.capacity.write(experiment/"session-manifests/fake.metrics.json", dict(
            new_jobs=320, jobs_per_second=10, min_available_mb=16000,
            requested_workers=40, effective_memory_cap=40, peak_inflight=40,
            ram_throttle_count=0, statuses=dict(SAT=320)))
        seen.append(argv)
        return Child()
    monkeypatch.setattr(ramp.subprocess, "Popen", fake_popen)
    outcome = ramp.invoke(experiment, output, manifest, ref, 40, 256, stage_jobs=320,
                          stop_file=output/"stage.stop", tag="stage")
    assert len(seen) == 1 and outcome["metrics"]["new_jobs"] == 320
