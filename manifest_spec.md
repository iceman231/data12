# manifest.json 구조 명세

파이프라인 실행 완료 후 `output/` 루트에 생성되는 파일.
전체 피험자 목록, 진단 매칭 결과, 파이프라인 메타정보를 담는다.

---

## 최상위 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `pipeline_version` | string | 파이프라인 버전 (예: `"1.0.0"`) |
| `diagnosis_source` | string | 진단 매칭에 사용한 CSV 파일명 |
| `output_layout` | string | 출력 경로 패턴 |
| `group_counts` | object | HC / MCI / AD 각 그룹 피험자 수 |
| `subjects` | array | 피험자별 상세 정보 (아래 참고) |
| `warnings` | array | 파이프라인 경고 목록 |

예시:
```json
{
  "pipeline_version": "1.0.0",
  "diagnosis_source": "OASIS3_UDSd1_diagnoses.csv",
  "output_layout": "output/{HC,MCI,AD}/{subject_id}/{subject_id}.h5",
  "group_counts": {
    "HC": 5,
    "MCI": 5,
    "AD": 5
  },
  "warnings": []
}
```

---

## subjects 배열 (피험자별)

| 필드 | 타입 | 설명 |
|---|---|---|
| `subject_id` | string | 피험자 ID (예: `"OAS30334"`) |
| `group` | string | 진단 그룹 (`HC` / `MCI` / `AD`) |
| `h5_path` | string | HDF5 파일 경로 |
| `n_runs` | int | 실제 사용된 run 수 |
| `total_timepoints_after_drop` | int | dummy 제거 후 총 timepoints |
| `diagnosis` | object | 진단 매칭 상세 (아래 참고) |

---

## diagnosis 객체

| 필드 | 타입 | 설명 |
|---|---|---|
| `subject_id` | string | 피험자 ID |
| `group` | string | 최종 분류 그룹 |
| `mr_day` | int | MR 세션 날짜 (day) |
| `diagnosis_day` | int | 매칭된 진단 날짜 (day) |
| `day_delta` | int | MR 날짜와 진단 날짜의 차이 (일수) |
| `match_type` | string | `"exact"` 또는 `"closest"` |
| `diagnosis_basis` | string | 분류 근거 (예: `"NORMCOG=1"`, `"DEMENTED=1; PROBAD"`) |
| `row` | object | 진단 CSV의 해당 행 전체 |

예시:
```json
{
  "subject_id": "OAS30334",
  "group": "AD",
  "mr_day": 0,
  "diagnosis_day": 0,
  "day_delta": 0,
  "match_type": "exact",
  "diagnosis_basis": "DEMENTED=1; PROBAD",
  "row": {
    "OASISID": "OAS30334",
    "OASIS_session_label": "OAS30334_UDSd1_d0000",
    "days_to_visit": "0000",
    "age at visit": "78.44",
    "NORMCOG": "0",
    "DEMENTED": "1",
    "PROBAD": "1",
    "..."  : "..."
  }
}
```

---

## 비고

- `group`과 `diagnosis.group`이 다를 수 있음
  - 예: OAS30397은 `diagnosis.group = "AD"`이나 `group = "MCI"` 폴더에 저장됨
  - 이는 진단 매칭 결과와 실제 저장 위치가 불일치하는 케이스로 QC 시 주의 필요
- `day_delta`가 클수록 진단 날짜와 MR 날짜 간 간격이 크며 매칭 신뢰도 저하
- `row` 필드는 진단 CSV의 모든 컬럼을 그대로 포함
