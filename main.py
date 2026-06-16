import argparse
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

# Windows cp949 환경에서 Unicode 출력 오류 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from utils.io import find_subject_sessions, get_tr, read_sidecar, parse_summary_groups, get_acquisition_meta
from utils.exceptions import InsufficientVolumesError
from steps.step1_diagnosis import match_diagnosis
from steps.step2_mcflirt import run_mcflirt_all
from steps.step3_flirt import run_flirt_all
from steps.step4_concat import concat_runs
from steps.step5_denoise import denoise
from steps.step6_roi import extract_roi_timeseries
from steps.step7_fc import compute_fc
from steps.step8_graph import compute_graph_metrics
from steps.step9_save import save_subject


PIPELINE_VERSION = "1.0.0"
INPUT_DIR = Path("input")
DIAGNOSIS_CSV = INPUT_DIR / "OASIS3_UDSd1_diagnoses.csv"
SUMMARY_TXT = INPUT_DIR / "ad_hc_mci20_summary.txt"


def main():
    parser = argparse.ArgumentParser(description="rsfMRI preprocessing pipeline")
    parser.add_argument("--subject", type=str, default=None,
                        help="단일 피험자 테스트용 ID (예: OAS30227)")
    parser.add_argument("--subjects", type=str, default=None,
                        help="처리할 피험자 목록: 쉼표 구분 (OAS30700_MR_d3380,OAS30717_MR_d2476,...) "
                             "또는 한 줄에 하나씩 적힌 텍스트 파일 경로")
    parser.add_argument("--output", type=str, default="output",
                        help="출력 디렉토리 (기본: output)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    summary_groups = parse_summary_groups(SUMMARY_TXT)
    print(f"[MAIN] summary 그룹 로드: {len(summary_groups)}명")

    sessions = find_subject_sessions(INPUT_DIR)
    if args.subject:
        sessions = [s for s in sessions if s["subject_id"] == args.subject]
        print(f"[MAIN] 필터 (--subject): {args.subject} → {len(sessions)}개 세션")
    elif args.subjects:
        subj_path = Path(args.subjects)
        if subj_path.is_file():
            raw = [l.strip() for l in subj_path.read_text().splitlines() if l.strip()]
        else:
            raw = [s.strip() for s in args.subjects.split(",") if s.strip()]
        filter_set = set(raw)
        sessions = [
            s for s in sessions
            if f"{s['subject_id']}_MR_{s['session_day']}" in filter_set
            or s["subject_id"] in filter_set
        ]
        print(f"[MAIN] 필터 (--subjects): {len(filter_set)}명 지정 → {len(sessions)}개 세션")
    print(f"[MAIN] 총 {len(sessions)}개 세션 처리\n")

    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "diagnosis_source": DIAGNOSIS_CSV.name,
        "output_layout": "output/{HC,MCI,AD}/{subject_id}/{subject_id}.h5",
        "group_counts": {"HC": 0, "MCI": 0, "AD": 0},
        "subjects": [],
        "excluded": [],
        "warnings": [],
    }

    for session in sessions:
        subject_id = session["subject_id"]
        session_day = session["session_day"]
        runs = session["runs"]

        print(f"{'='*60}")
        print(f"[MAIN] {subject_id} / {session_day}")

        try:
            work_dir = output_dir / "tmp" / f"{subject_id}_{session_day}"

            # ── Step 1: 진단 매칭 ─────────────────────────────────
            diagnosis_result = match_diagnosis(subject_id, session_day, DIAGNOSIS_CSV)
            diagnosis_group = diagnosis_result["diagnosis_group"]

            # summary 파일 우선, 없으면 진단 CSV 결과 사용
            group = summary_groups.get(subject_id, diagnosis_group)

            if group != diagnosis_group and diagnosis_group != "UNKNOWN":
                warn_msg = (
                    f"{subject_id}: summary group='{group}' but "
                    f"diagnosis group='{diagnosis_group}' "
                    f"(basis={diagnosis_result['diagnosis_basis']})"
                )
                print(f"[WARN] {warn_msg}")
                manifest["warnings"].append(warn_msg)

            if group == "UNKNOWN":
                print(f"[SKIP] {subject_id}: 진단 그룹 UNKNOWN\n")
                manifest["excluded"].append({
                    "subject_id": subject_id,
                    "session_day": session_day,
                    "reason": "unknown_diagnosis",
                    "detail": diagnosis_result.get("diagnosis_basis", ""),
                })
                continue
            print(f"[STEP1] 진단: {group} (basis: {diagnosis_result['diagnosis_basis']})")

            # ── Step 2: Motion correction ─────────────────────────
            mc_results = run_mcflirt_all(runs, work_dir / "mcflirt")

            # ── Step 3: MNI registration ──────────────────────────
            flirt_results = run_flirt_all(mc_results, work_dir / "flirt")

            # ── Step 4: Dummy 제거 + 연결 ─────────────────────────
            tr = get_tr(runs)
            concat_result = concat_runs(flirt_results, mc_results, work_dir / "concat")

            # ── Step 5: Smoothing + bandpass + PCA confound 회귀 ──
            denoise_result = denoise(concat_result, tr, work_dir / "denoise")

            # ── Step 6: ROI 시계열 추출 ───────────────────────────
            roi_result = extract_roi_timeseries(denoise_result, tr, concat_result)

            # ── Step 7: FC 계산 ───────────────────────────────────
            fc_result = compute_fc(roi_result)

            # ── Step 8: 그래프 지표 ───────────────────────────────
            graph_result = compute_graph_metrics(fc_result, roi_result["roi_labels"])

            # ── Step 9: HDF5 저장 ─────────────────────────────────
            acquisition_meta = get_acquisition_meta(runs)

            h5_path = save_subject(
                subject_id=subject_id,
                diagnosis_group=group,
                diagnosis_result=diagnosis_result,
                fc_result=fc_result,
                graph_result=graph_result,
                roi_result=roi_result,
                concat_result=concat_result,
                denoise_result=denoise_result,
                mc_results=mc_results,
                tr=tr,
                acquisition_meta=acquisition_meta,
                output_root=output_dir,
            )

            manifest["subjects"].append({
                "subject_id": subject_id,
                "group": group,
                "h5_path": str(h5_path),
                "n_runs": len(mc_results),
                "total_timepoints_after_drop": concat_result["n_timepoints"],
                "diagnosis": {
                    k: v for k, v in diagnosis_result.items()
                    if k != "diagnosis_group"
                },
            })
            print(f"[MAIN] {subject_id} 완료\n")

        except InsufficientVolumesError as e:
            print(f"[SKIP] {subject_id}: insufficient_volumes — {e}\n")
            manifest["excluded"].append({
                "subject_id": subject_id,
                "session_day": session_day,
                "reason": "insufficient_volumes",
                "detail": str(e),
            })

        except Exception as e:
            print(f"[ERROR] {subject_id}: {e}")
            traceback.print_exc()
            manifest["excluded"].append({
                "subject_id": subject_id,
                "session_day": session_day,
                "reason": "error",
                "detail": str(e),
            })
            print()

    counts = Counter(s["group"] for s in manifest["subjects"])
    manifest["group_counts"] = {
        "HC": counts.get("HC", 0),
        "MCI": counts.get("MCI", 0),
        "AD": counts.get("AD", 0),
    }

    manifest_path = output_dir / "manifest.json"
    with open(str(manifest_path), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[MAIN] 완료 -> {manifest_path}")
    print(
        f"       처리: {len(manifest['subjects'])}명 "
        f"(HC={manifest['group_counts']['HC']}, "
        f"MCI={manifest['group_counts']['MCI']}, "
        f"AD={manifest['group_counts']['AD']}) | "
        f"제외: {len(manifest['excluded'])}명 | "
        f"경고: {len(manifest['warnings'])}건"
    )


if __name__ == "__main__":
    main()
