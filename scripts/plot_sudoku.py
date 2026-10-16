"""RES-008: illustrate a checked synthetic witness without invoking a solver."""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sudoku.model import load_puzzle
from sudoku.validation import check_solution


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw_board(puzzle, grid, instance_id, destination, solution=False):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig = plt.figure(figsize=(5.2, 6.3), facecolor="white")
    ax = fig.add_axes((0.12, 0.23, 0.76, 0.63))
    ax.set(xlim=(-0.03, 4.03), ylim=(4.03, -0.03), aspect="equal")
    ax.axis("off")
    for r in range(4):
        for c in range(4):
            clue = puzzle.grid[r][c] != 0
            if solution and not clue:
                ax.add_patch(Rectangle((c, r), 1, 1, facecolor="#eef4f9", edgecolor="none"))
            if grid[r][c]:
                ax.text(c + 0.5, r + 0.5, str(grid[r][c]), ha="center", va="center",
                        fontsize=29, fontweight="bold" if clue else "normal",
                        color="#17212b" if clue else "#24587a")
    for k in range(5):
        width = 2.4 if k % puzzle.n == 0 else 0.7
        ax.plot([k, k], [0, 4], color="#17212b", linewidth=width, solid_capstyle="butt")
        ax.plot([0, 4], [k, k], color="#17212b", linewidth=width, solid_capstyle="butt")
    fig.text(0.5, 0.94, "Sudoku 4×4 — " + ("Valid witness" if solution else "Puzzle"),
             ha="center", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.885, instance_id, ha="center", fontsize=11)
    legend = ("Bold: original clues  •  Blue: witness values" if solution
              else f"{puzzle.clue_count} clues ({100 * puzzle.clue_count / puzzle.N**2:g}%)"
              "  •  Empty cells are blank")
    fig.text(0.5, 0.17, legend, ha="center", fontsize=10)
    fig.text(0.5, 0.115, "Source: synthetic dataset / generator witness", ha="center", fontsize=10)
    fig.text(0.5, 0.075, "Witness checked independently; no solver or benchmark result.",
             ha="center", fontsize=8.5)
    fig.text(0.5, 0.04, "Uniqueness has not been verified.", ha="center", fontsize=9)
    outputs = []
    for suffix in (".png", ".pdf", ".svg"):
        path = destination.with_suffix(suffix)
        fig.savefig(path, dpi=300, facecolor="white",
                    metadata={"Creator": "RES-008 plot_sudoku.py"})
        outputs.append(path)
    plt.close(fig)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", default="synthetic-N04-p50-s0")
    args = parser.parse_args()
    manifest_path = ROOT / "data/manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8-sig"))["records"]
    matches = [record for record in records if record["instance_id"] == args.instance_id]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching manifest record")
    record = matches[0]
    if record["source"] != "synthetic" or record["N"] != 4:
        raise ValueError("This illustration requires a synthetic 4x4 instance")
    puzzle_path = ROOT / record["file"]
    witness_path = ROOT / record["witness_file"]
    for path, expected in ((puzzle_path, record["sha256"]),
                           (witness_path, record["witness_sha256"])):
        if digest(path) != expected:
            raise ValueError(f"Manifest checksum mismatch: {path.name}")
    puzzle = load_puzzle(puzzle_path)
    witness = json.loads(witness_path.read_text(encoding="utf-8-sig"))
    if puzzle.N != 4 or witness["n"] != puzzle.n or puzzle.clue_count != record["clue_count"]:
        raise ValueError("Puzzle/witness metadata mismatch")
    validation = check_solution(puzzle, witness["solution"])
    if not validation.valid:
        raise ValueError(f"Independent checker rejected witness: {validation.message}")
    figures = ROOT / "results/figures"
    evidence_dir = ROOT / "diagnostics/illustration"
    figures.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(evidence_dir / "mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    outputs = draw_board(puzzle, puzzle.grid, args.instance_id, figures / "sudoku-4x4-puzzle")
    outputs += draw_board(puzzle, witness["solution"], args.instance_id,
                          figures / "sudoku-4x4-solution", solution=True)
    evidence = {
        "task": "RES-008", "instance_id": args.instance_id,
        "purpose": "Generator witness illustration, not a solver or benchmark result",
        "uniqueness": "unverified", "validation": asdict(validation),
        "clue_count": puzzle.clue_count, "n": puzzle.n, "N": puzzle.N,
        "inputs": [{"file": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                   for path in (manifest_path, puzzle_path, witness_path)],
        "outputs": [{"file": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                    for path in outputs],
        "matplotlib_version": matplotlib.__version__, "python_version": sys.version,
        "command": '.\\.venv\\Scripts\\python.exe -B scripts/plot_sudoku.py',
    }
    (evidence_dir / "validation.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RES-008: checker PASS; {args.instance_id}; {len(outputs)} figures exported")


if __name__ == "__main__":
    main()
