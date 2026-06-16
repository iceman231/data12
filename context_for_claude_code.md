# rsfMRI 파이프라인 재현 - Claude Code 컨텍스트

## 목적
OASIS-3 resting-state fMRI 데이터를 전처리하고, FC matrix 및 그래프 지표를 계산하여 HDF5로 저장하는 파이프라인 코드를 재현한다.

---

## 행동 지침

- **폴더 구조 또는 명시적 지시 없이는 코드를 작성하지 않는다.**
- 파일이 제공되면 구조 파악 후 요약만 제공한다.
- 코드 작성은 사용자가 명시적으로 지시할 때만 시작한다.
- 불필요하게 파일 전체를 읽어 토큰을 낭비하지 않는다.

---

## 환경

- Python (Nilearn, NetworkX, NumPy, SciPy, h5py)
- FSL (MCFLIRT, FLIRT 커맨드라인)
- AAL90 atlas (`nilearn.datasets.fetch_atlas_aal(version="SPM12")`로 자동 취득)
- MNI152_T1_2mm_brain (FSL 기본 포함, `$FSLDIR/data/standard/`)

---

## 입력 폴더 구조

```
input/
│  OASIS3_UDSd1_diagnoses.csv
│  ad_hc_mci20_summary.txt
│  subjects.csv
│
└─{subject_id}_MR_{session_day}/
   └─func{N}/
         sub-{subject_id}_ses-{session_day}_task-rest_run-{01,02}_bold.nii.gz
         sub-{subject_id}_ses-{session_day}_task-rest_run-{01,02}_bold.json
```

- `func{N}` 폴더 번호는 무시, **파일명 기준 `task-rest_run-01`, `task-rest_run-02`** 파일만 선택
- `task-testrest` 등 다른 task 파일은 제외
- 하드코딩 없이 input 하위 폴더를 자동 탐색하는 구조로 작성

**sidecar JSON 활용**
- 각 run의 `.json` sidecar에서 아래 필드를 동적으로 읽어 처리에 반영

| 필드 | 용도 |
|---|---|
| `RepetitionTime` | Bandpass 필터 및 confound 회귀 시 TR로 사용 |
| `MagneticFieldStrength` | QC 메타데이터 기록 |
| `Manufacturer` | QC 메타데이터 기록 |

- TR은 하드코딩하지 않고 run별 JSON에서 읽은 값을 사용
- run 간 TR이 다를 경우 경고 출력 후 첫 번째 run 값 사용

---

## 파이프라인 단계

### 1. 진단 매칭
- `OASIS3_UDSd1_diagnoses.csv`와 MR 세션 날짜(day) 비교
- exact match 우선, 없으면 closest match
- 분류 기준:
  - `NORMCOG=1` → HC
  - `IMPNOMCI=1` → MCI
  - `DEMENTED=1 & (PROBAD or POSSAD)` → AD

### 2. FSL MCFLIRT (Motion Correction)
- run별 개별 실행, 기준 볼륨: 중간 볼륨 (default)
- 출력: motion-corrected `.nii.gz` + `.par` (6 motion parameters)
- FD 계산: `fd_radius=50mm`, `fd_threshold=0.5mm`

### 3. FSL FLIRT (MNI Registration)
- T1w 없음 → BOLD 직접 affine registration
- 기준: `MNI152_T1_2mm_brain`, DOF=12
- 출력: MNI 공간 BOLD `.nii.gz`

### 4. 볼륨 제거 및 연결
- 각 run 앞 **5볼륨 제거** (dummy scan)
- **run-01, run-02 두 개로 고정** (3개 이상인 경우 run-01, run-02만 사용)
- 시간축으로 concatenate
- 기대 shape: `(164 - 5) × 2 = 318` timepoints

> **주의**: run 수를 2개로 고정하는 이유는 피험자 간 timepoints 불균형 방지를 위함.
> timepoints가 피험자마다 다를 경우 FC 계산 자체는 가능하나, 그룹 비교 및 일부 분류 모델에서 불균형이 문제될 수 있음.

### 5. Nilearn 신호 처리
| 파라미터 | 값 |
|---|---|
| Smoothing | FWHM = 6mm |
| Bandpass | high_pass=0.01Hz, low_pass=0.1Hz |
| TR | sidecar JSON의 `RepetitionTime` 필드에서 run별로 동적으로 읽음 |
| Confound | PCA 5 components 회귀 |
| Standardize | False |
| Detrend | False |
| GSR | 없음 |

### 6. ROI 추출
- AAL90 atlas NiftiLabelsMasker 적용
- 각 ROI 내 voxel 평균
- 출력: `(318, 90)` time series
- `min_roi_voxels=5` 미만 ROI 경고

### 7. FC 계산
1. `np.corrcoef(time_series.T)` → Pearson r → `raw_fc` (90×90)
2. `np.arctanh(raw_fc)` → Fisher-z, 대각선=0 → `fisher_z_fc`
3. Proportional thresholding: 상위삼각행렬 상위 10% 유지
   - `threshold_proportion=0.1`, `threshold_use_absolute=False`
   - 음의 상관관계 제거됨
   - 출력: `thresholded_fc`, `adjacency` (0/1)

### 8. 그래프 지표 (NetworkX)
- `nx.from_numpy_array(adjacency)` → 이진 무방향 그래프
- **전역**: density, mean_degree, mean_clustering, transitivity, global_efficiency, local_efficiency
- **노드별**: clustering, degree, degree_centrality, betweenness_centrality, eigenvector_centrality

---

## 출력 폴더 구조

```
output/
│  manifest.json
│
├─AD
│  └─{subject_id}/
│         {subject_id}.h5
│
├─HC
│  └─{subject_id}/
│         {subject_id}.h5
│
└─MCI
   └─{subject_id}/
          {subject_id}.h5
```

- 진단 그룹(AD / HC / MCI)별 폴더로 분류
- 각 피험자마다 `{subject_id}` 이름의 하위 폴더 생성
- 그 안에 `{subject_id}.h5` 단일 파일 저장
- 루트에 전체 피험자 목록 및 요약 정보를 담은 `manifest.json` 생성

---

## HDF5 저장 구조

```
{subject_id}.h5
├── fc/
│   ├── raw_fc              (90, 90) float32
│   ├── fisher_z_fc         (90, 90) float32
│   └── thresholded_fc      (90, 90) float64
├── graph/
│   ├── adjacency           (90, 90) uint8
│   ├── edge_list           (N,)     object
│   ├── metrics             (1,)     object  # JSON
│   ├── node_labels         (90,)    object
│   └── node_metrics/
│       ├── clustering              (90,) float64
│       ├── degree                  (90,) float64
│       ├── degree_centrality       (90,) float64
│       ├── betweenness_centrality  (90,) float64
│       └── eigenvector_centrality  (90,) float64
├── roi_time_series/
│   └── data                (318, 90) float32
├── metadata/
│   ├── acquisition_metadata
│   ├── demographics
│   ├── diagnosis
│   ├── preprocessing_config
│   ├── qc_notes
│   ├── run_concatenation
│   ├── selected_runs
│   ├── subject
│   └── warnings
└── qc/
    ├── atlas_mask_overlap      scalar  float64
    ├── fd_over_0_5_ratio       scalar  float64
    ├── motion_fd               (318,)  float64
    ├── report                  (1,)    object  # JSON
    └── tsnr                    (2,)    float64  # [before, after]
```

---

## QC 기준
| 항목 | 기준 |
|---|---|
| FD > 0.5mm 비율 | 과도 시 exclusion 검토 |
| atlas_mask_overlap | 낮을수록 registration 품질 저하 |
| tsnr_after_clean | 음수 또는 극소값이면 신호 소실 의심 |
| small_roi_count | min_roi_voxels 미만 ROI 수 |

---

## 비고
- T1w 없음 → BOLD 기반 직접 MNI registration (제한사항)
- Slice timing correction 미적용 (원본 데이터에도 미적용)
- Distortion correction 미적용 (원본 데이터에도 미적용)
