import pandas as pd
from pathlib import Path


# MCI 서브타입 컬럼 (IMPNOMCI 없어도 서브타입 플래그로 MCI 분류 가능)
_MCI_SUBTYPE_FLAGS = [
    "MCIAMEM", "MCIAPLUS", "MCIAPLAN", "MCIAPATT", "MCIAPEX",
    "MCIAPVIS", "MCINON1", "MCINON2",
]


def match_diagnosis(subject_id: str, session_day: str, csv_path: Path) -> dict:
    """
    OASIS3_UDSd1_diagnoses.csv에서 피험자+세션 날짜를 매칭하여
    진단 그룹(HC / MCI / AD)과 세부 정보를 반환한다.

    반환 dict 키:
        subject_id, group, diagnosis_group (alias),
        mr_day, diagnosis_day, day_delta, match_type,
        diagnosis_basis, row
    """
    csv_path = Path(csv_path)
    # dtype=str + fillna("")로 읽어 NaN 처리를 안전하게 수행
    df = pd.read_csv(csv_path, dtype=str).fillna("")

    mr_day = int(session_day.lstrip("d"))

    subj_df = df[df["OASISID"] == subject_id].copy()
    if subj_df.empty:
        return _unknown(subject_id, session_day, mr_day, "CSV에 피험자 없음")

    subj_df["_day_int"] = pd.to_numeric(subj_df["days_to_visit"], errors="coerce").fillna(-1).astype(int)
    subj_df = subj_df.sort_values("_day_int")

    exact = subj_df[subj_df["_day_int"] == mr_day]
    if not exact.empty:
        row = exact.iloc[0]
        match_type = "exact"
    else:
        idx = (subj_df["_day_int"] - mr_day).abs().idxmin()
        row = subj_df.loc[idx]
        match_type = "closest"
        closest_day = int(row["_day_int"])
        print(
            f"[INFO] {subject_id} {session_day}: exact match 없음 → "
            f"closest day {closest_day} (차이 {abs(closest_day - mr_day)}일)"
        )

    diagnosis_day = int(row["_day_int"])
    day_delta = abs(mr_day - diagnosis_day)
    group, basis = _classify(row)

    # row 전체를 string dict로 보존 (_day_int 임시 컬럼 제외)
    row_dict = row.drop(labels=["_day_int"]).to_dict()

    return {
        "subject_id": subject_id,
        "group": group,
        "diagnosis_group": group,   # main.py 호환 alias
        "mr_day": mr_day,
        "diagnosis_day": diagnosis_day,
        "day_delta": day_delta,
        "match_type": match_type,
        "diagnosis_basis": basis,
        "row": row_dict,
    }


def _classify(row) -> tuple[str, str]:
    """
    진단 분류 우선순위:
      1. NORMCOG=1                            → HC
      2. IMPNOMCI=1                           → MCI  (PROBAD보다 서브타입 MCI 우선)
      3. DEMENTED=1 & (PROBAD=1 | POSSAD=1)  → AD
      4. MCI 서브타입 플래그 존재             → MCI
      5. 해당 없음                            → UNKNOWN
    """
    def flag(col):
        try:
            return int(float(row.get(col, 0))) == 1
        except (ValueError, TypeError):
            return False

    if flag("NORMCOG"):
        return "HC", "NORMCOG=1"

    if flag("IMPNOMCI"):
        return "MCI", "IMPNOMCI"

    if flag("DEMENTED") and (flag("PROBAD") or flag("POSSAD")):
        ad_flags = [f for f in ("PROBAD", "POSSAD") if flag(f)]
        return "AD", f"DEMENTED=1; {', '.join(ad_flags)}"

    active_subtypes = [f for f in _MCI_SUBTYPE_FLAGS if flag(f)]
    if active_subtypes:
        return "MCI", ",".join(active_subtypes)

    return "UNKNOWN", ""


def _unknown(subject_id: str, session_day: str, mr_day: int, reason: str) -> dict:
    print(f"[WARN] {subject_id} {session_day}: {reason}")
    return {
        "subject_id": subject_id,
        "group": "UNKNOWN",
        "diagnosis_group": "UNKNOWN",
        "mr_day": mr_day,
        "diagnosis_day": None,
        "day_delta": None,
        "match_type": None,
        "diagnosis_basis": "",
        "row": {},
    }
