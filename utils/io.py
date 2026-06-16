import json
import re
from pathlib import Path


def parse_summary_groups(summary_path: Path) -> dict:
    """
    ad_hc_mci20_summary.txt에서 피험자별 사전 배정 그룹을 파싱한다.
    반환: {subject_id: group}  예) {"OAS30004": "HC", "OAS30085": "AD"}

    파일 형식:
        - AD | OAS30332 | OAS30332_MR_d0091 | runs=3 | diag_abs_diff=91
    """
    summary_path = Path(summary_path)
    groups: dict[str, str] = {}
    pattern = re.compile(r"^-\s+(AD|HC|MCI)\s+\|\s+(OAS3\w+)")
    with open(summary_path, encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                groups[m.group(2)] = m.group(1)
    return groups


def find_subject_sessions(input_dir: Path) -> list[dict]:
    """
    input/ 하위에서 {subject_id}_MR_{session_day} 폴더를 탐색하고
    task-rest_run-01, run-02 파일 쌍을 반환한다.
    """
    input_dir = Path(input_dir)
    sessions = []

    session_pattern = re.compile(r"^(OAS3\d+)_MR_(d\d+)$")

    for session_dir in sorted(input_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        m = session_pattern.match(session_dir.name)
        if not m:
            continue

        subject_id = m.group(1)
        session_day = m.group(2)

        runs = _find_rest_runs(session_dir, subject_id, session_day)
        if not runs:
            print(f"[WARN] {session_dir.name}: task-rest run-01/02 파일 없음, 건너뜀")
            continue

        sessions.append({
            "subject_id": subject_id,
            "session_day": session_day,
            "session_dir": session_dir,
            "runs": runs,
        })

    return sessions


def _find_rest_runs(session_dir: Path, subject_id: str, session_day: str) -> list[dict]:
    """
    session_dir 내 func* 폴더에서 task-rest_run-01, run-02 파일을 찾아
    run 번호 순으로 정렬해 반환한다. run-01/02만 선택, 초과분 제외.
    """
    run_pattern = re.compile(
        rf"sub-{subject_id}_ses-{session_day}_task-rest_run-(\d{{2}})_bold\.(nii\.gz|json)$"
    )

    found: dict[str, dict] = {}

    for func_dir in sorted(session_dir.iterdir()):
        if not func_dir.is_dir():
            continue
        for f in func_dir.iterdir():
            m = run_pattern.match(f.name)
            if not m:
                continue
            run_num = m.group(1)
            ext = m.group(2)
            if run_num not in found:
                found[run_num] = {}
            if ext == "nii.gz":
                found[run_num]["nii"] = f
            else:
                found[run_num]["json"] = f

    runs = []
    for run_num in ["01", "02"]:
        if run_num not in found:
            continue
        entry = found[run_num]
        if "nii" not in entry or "json" not in entry:
            print(f"[WARN] run-{run_num}: nii.gz 또는 json 누락")
            continue
        runs.append({"run": run_num, "nii": entry["nii"], "json": entry["json"]})

    return runs


def read_sidecar(json_path: Path) -> dict:
    """sidecar JSON을 읽어 dict로 반환한다."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_tr(runs: list[dict]) -> float:
    """
    run 목록의 sidecar JSON에서 RepetitionTime을 읽는다.
    run 간 TR이 다를 경우 경고 후 첫 번째 run 값을 반환한다.
    """
    trs = []
    for run in runs:
        meta = read_sidecar(run["json"])
        tr = meta.get("RepetitionTime")
        if tr is None:
            raise ValueError(f"{run['json']}: RepetitionTime 필드 없음")
        trs.append(float(tr))

    unique = list(set(trs))
    if len(unique) > 1:
        print(f"[WARN] run 간 TR 불일치: {trs} → 첫 번째 값 {trs[0]} 사용")

    return trs[0]


def get_acquisition_meta(runs: list[dict]) -> dict:
    """
    첫 번째 run의 sidecar JSON에서 MagneticFieldStrength, Manufacturer를 읽는다.
    """
    meta = read_sidecar(runs[0]["json"])
    return {
        "MagneticFieldStrength": meta.get("MagneticFieldStrength"),
        "Manufacturer": meta.get("Manufacturer"),
    }
