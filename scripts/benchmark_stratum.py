"""Benchmark original pipelines against a local Stratum service."""

import json
import shutil
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import os
import time
from stratum import StratumClient
import filecmp
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "trajectories" / "spaceship_titanic_students"


def save_json(path, data):
    """先写临时文件，再替换，避免留下写到一半的结果。"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare_repeat(folder, manifest):
    """复制原始代码，链接输入数据，隔离两组输出。"""
    files = [
        pipeline["file"]
        for step in manifest["steps"]
        for pipeline in step["pipelines"]
    ]

    for mode in ("baseline", "stratum"):
        workdir = folder / mode
        workdir.mkdir(parents=True, exist_ok=False)

        shutil.copy2(SOURCE / "trajectory.json", workdir / "trajectory.json")

        for filename in files:
            destination = workdir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / filename, destination)

        (workdir / "input").symlink_to(
            (SOURCE / "input").resolve(),
            target_is_directory=True,
        )

    save_json(folder / "timing.json", {
        "status": "prepared",
        "baseline": {},
        "stratum": {},
    })

def run_baseline(folder):
    timing_path = folder / "timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    timing["status"] = "baseline_running"
    save_json(timing_path, timing)

    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_trajectory.py"),
        str(folder / "baseline"),
    ]

    started = None
    try:
        with (
            (folder / "baseline.stdout.log").open("w") as stdout,
            (folder / "baseline.stderr.log").open("w") as stderr,
        ):
            started = perf_counter()
            process = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stdout,
                stderr=stderr,
            )
            elapsed = perf_counter() - started

        timing["baseline"] = {
            "execution_seconds": elapsed,
            "returncode": process.returncode,
            "command": command,
        }
        timing["status"] = (
            "baseline_completed"
            if process.returncode == 0
            else "baseline_failed"
        )
        save_json(timing_path, timing)

    except BaseException as error:
        timing["status"] = "baseline_interrupted_or_error"
        timing["baseline"] = {
            "elapsed_seconds": (
                perf_counter() - started if started is not None else None
            ),
            "error": f"{type(error).__name__}: {error}",
        }
        save_json(timing_path, timing)
        raise

    if process.returncode != 0:
        raise RuntimeError(
            f"基准运行失败，请查看 {folder / 'baseline.stderr.log'}"
        )

    print(f"基准执行完成：{elapsed:.2f} 秒", flush=True)
    print(f"时间已保存：{timing_path}", flush=True)


def run_stratum(folder):
    timing_path = folder / "timing.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    timing["status"] = "stratum_starting"
    record = timing["stratum"] = {}
    save_json(timing_path, timing)

    server_dir = folder / "server"
    if server_dir.exists():
        raise RuntimeError(f"服务目录已存在，请使用新的实验目录：{server_dir}")

    env = os.environ.copy()
    env.pop("STRATUM_URL", None)
    env.pop("STRATUM_TOKEN", None)
    env["STRATUM_SERVER_DIR"] = str(server_dir)

    client = None
    server = None
    succeeded = False

    with (
        (folder / "server.log").open("w") as server_log,
        (folder / "stratum.stdout.log").open("w") as stdout,
        (folder / "stratum.stderr.log").open("w") as stderr,
    ):
        started = perf_counter()
        try:
            server = subprocess.Popen(
                [
                    sys.executable, "-m", "stratum",
                    "--server-dir", str(server_dir), "serve",
                ],
                cwd=ROOT,
                env=env,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )

            # 等待本轮服务生成地址文件，再检查连接。
            deadline = started + 120
            while client is None:
                if server.poll() is not None:
                    raise RuntimeError("服务启动失败，请查看 server.log")
                if perf_counter() >= deadline:
                    raise TimeoutError("等待服务就绪超过 120 秒")

                info_path = server_dir / "server.json"
                if info_path.is_file():
                    try:
                        info = json.loads(info_path.read_text())
                        client = StratumClient(
                            url=info["url"],
                            token=info["token"],
                            timeout=2.0,
                        )
                    except (ConnectionError, json.JSONDecodeError):
                        pass

                if client is None:
                    time.sleep(0.1)

            record["startup_seconds"] = perf_counter() - started
            timing["status"] = "stratum_running"
            save_json(timing_path, timing)

            command = [
                sys.executable,
                str(ROOT / "scripts" / "run_trajectory_stratum.py"),
                str(folder / "stratum"),
            ]
            execution_started = perf_counter()
            process = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
            )
            record["execution_seconds"] = (
                perf_counter() - execution_started
            )
            record["returncode"] = process.returncode
            record["command"] = command
            timing["status"] = "stratum_stopping"
            save_json(timing_path, timing)

            if process.returncode != 0:
                raise RuntimeError(
                    "Stratum Runner 失败，请查看 stratum.stderr.log"
                )
            succeeded = True

        except BaseException as error:
            record["error"] = f"{type(error).__name__}: {error}"
            raise

        finally:
            shutdown_started = perf_counter()
            forced_shutdown = False

            if client is not None:
                try:
                    client.shutdown()
                except Exception as error:
                    record["shutdown_error"] = str(error)
                finally:
                    client.close()

            if server is not None and server.poll() is None:
                if client is None:
                    server.terminate()
                    forced_shutdown = True
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    forced_shutdown = True
                    server.kill()
                    server.wait()

            record["shutdown_seconds"] = (
                perf_counter() - shutdown_started
            )
            record["end_to_end_seconds"] = perf_counter() - started
            record["forced_shutdown"] = forced_shutdown
            timing["status"] = (
                "stratum_completed"
                if succeeded
                and not forced_shutdown
                and "shutdown_error" not in record
                else "failed"
            )
            save_json(timing_path, timing)

    print(
        f"Stratum 执行：{record['execution_seconds']:.2f} 秒；"
        f"端到端：{record['end_to_end_seconds']:.2f} 秒",
        flush=True,
    )


def compare_predictions(folder, manifest):
    differences = []
    checked = 0

    for step in manifest["steps"]:
        for candidate in step["pipelines"]:
            pipeline_id = Path(candidate["file"]).stem

            for filename in (
                "oof_predictions.csv",
                "test_probabilities.csv",
            ):
                relative = Path("results") / pipeline_id / filename
                baseline = folder / "baseline" / relative
                stratum = folder / "stratum" / relative

                if not baseline.is_file() or not stratum.is_file():
                    differences.append({
                        "file": str(relative),
                        "reason": "missing",
                        "baseline_exists": baseline.is_file(),
                        "stratum_exists": stratum.is_file(),
                    })
                    continue

                checked += 1
                if not filecmp.cmp(baseline, stratum, shallow=False):
                    differences.append({
                        "file": str(relative),
                        "reason": "different",
                    })

    passed = checked > 0 and not differences
    report = {
        "passed": passed,
        "comparison": "byte-for-byte",
        "files_compared": checked,
        "differences": differences,
    }
    save_json(folder / "validation.json", report)

    if not passed:
        raise RuntimeError(
            f"预测检查未通过，请查看 {folder / 'validation.json'}"
        )

    print(f"预测检查通过：{checked} 个文件完全一致", flush=True)
    return report


def summarize(session_dir, results):
    baseline_median = median(
        row["baseline_seconds"] for row in results
    )
    execution_median = median(
        row["stratum_execution_seconds"] for row in results
    )
    end_to_end_median = median(
        row["stratum_end_to_end_seconds"] for row in results
    )

    report = {
        "rounds": results,
        "medians": {
            "baseline_seconds": baseline_median,
            "stratum_startup_seconds": median(
                row["stratum_startup_seconds"] for row in results
            ),
            "stratum_execution_seconds": execution_median,
            "stratum_shutdown_seconds": median(
                row["stratum_shutdown_seconds"] for row in results
            ),
            "stratum_end_to_end_seconds": end_to_end_median,
        },
        "speedup_ratio_of_medians": {
            "execution": baseline_median / execution_median,
            "end_to_end": baseline_median / end_to_end_median,
        },
        "end_to_end_time_reduction_percent": (
            1 - end_to_end_median / baseline_median
        ) * 100,
        "all_predictions_identical": all(
            row["predictions_identical"] for row in results
        ),
    }
    save_json(session_dir / "summary.json", report)

    print("\n轮次        基准(s)  Stratum执行(s)  端到端(s)  端到端加速")
    for row in results:
        print(
            f"{row['repeat']}  "
            f"{row['baseline_seconds']:8.2f}  "
            f"{row['stratum_execution_seconds']:14.2f}  "
            f"{row['stratum_end_to_end_seconds']:9.2f}  "
            f"{row['end_to_end_speedup']:9.2f}×"
        )

    print(
        f"\n中位数：基准 {baseline_median:.2f}s，"
        f"Stratum执行 {execution_median:.2f}s，"
        f"端到端 {end_to_end_median:.2f}s"
    )
    print(
        f"中位数之比：执行加速 "
        f"{baseline_median / execution_median:.2f}×，"
        f"端到端加速 {baseline_median / end_to_end_median:.2f}×"
    )
    print(f"汇总已保存：{session_dir / 'summary.json'}")


def main():
    manifest = json.loads(
        (SOURCE / "trajectory.json").read_text(encoding="utf-8")
    )

    for filename in ("train.csv", "test.csv"):
        if not (SOURCE / "input" / filename).is_file():
            raise FileNotFoundError(SOURCE / "input" / filename)

    session_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    session_dir = ROOT / "experiments" / "stratum_imports" / session_name
    session_dir.mkdir(parents=True, exist_ok=False)

    for index in range(1, 4):
        folder = session_dir / f"repeat_{index:02d}"
        prepare_repeat(folder, manifest)

    print(f"实验目录已准备：{session_dir}", flush=True)
    results = []

    for index in range(1, 4):
        folder = session_dir / f"repeat_{index:02d}"
        order = (
            ["baseline", "stratum"]
            if index % 2 == 1
            else ["stratum", "baseline"]
        )

        # 在执行前保存本轮顺序。
        timing_path = folder / "timing.json"
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        timing["order"] = order
        save_json(timing_path, timing)

        print(
            f"\n第 {index}/3 轮，顺序：{' → '.join(order)}",
            flush=True,
        )

        for mode in order:
            if mode == "baseline":
                run_baseline(folder)
            else:
                run_stratum(folder)

        timing = json.loads(timing_path.read_text(encoding="utf-8"))

        # 不接受异常关闭的服务，即使 Runner 已完成。
        if (
            timing["stratum"].get("forced_shutdown")
            or "shutdown_error" in timing["stratum"]
        ):
            raise RuntimeError(f"{folder}: 服务未正常关闭")

        timing["status"] = "validating"
        save_json(timing_path, timing)

        try:
            validation = compare_predictions(folder, manifest)
        except Exception as error:
            timing["status"] = "validation_failed"
            timing["predictions_identical"] = False
            timing["validation_error"] = str(error)
            save_json(timing_path, timing)
            raise

        # 两组完成并通过预测验证后，统一标记本轮完成。
        timing["status"] = "completed"
        timing["predictions_identical"] = validation["passed"]
        save_json(timing_path, timing)

        baseline = timing["baseline"]["execution_seconds"]
        stratum = timing["stratum"]

        results.append({
            "repeat": folder.name,
            "order": order,
            "baseline_seconds": baseline,
            "stratum_startup_seconds": stratum["startup_seconds"],
            "stratum_execution_seconds": stratum["execution_seconds"],
            "stratum_shutdown_seconds": stratum["shutdown_seconds"],
            "stratum_end_to_end_seconds": stratum["end_to_end_seconds"],
            "execution_speedup": baseline / stratum["execution_seconds"],
            "end_to_end_speedup": baseline / stratum["end_to_end_seconds"],
            "predictions_identical": validation["passed"],
        })

        # 每轮通过后立即保存，后续失败也不会丢失已完成数据。
        save_json(session_dir / "completed_rounds.json", results)

    summarize(session_dir, results)


if __name__ == "__main__":
    main()