# rsfMRI 전처리 및 그래프 구성 파이프라인

**데이터셋**: OASIS-3  
**대상**: HC / MCI / AD  
**파이프라인 버전**: 1.0.0

---

## 0. 환경

- Python (Nilearn, NetworkX, NumPy, SciPy, h5py)
- FSL (MCFLIRT, FLIRT)
- AAL90 atlas (`nilearn.datasets.fetch_atlas_aal(version="SPM12")`로 자동 취득)

---

## 1. 입력 데이터

- `sub-{ID}_ses-{day}_task-rest_run-{01,02}_bold.nii.gz`
- 동일 경로의 `.json` sidecar
- `OASIS3_UDSd1_diagnoses.csv`
- `subjects.csv`

---

## 2. 진단 매칭

- MR 세션 날짜(day)와 진단 날짜 비교
- exact match 우선, 없으면 closest match
- 분류 기준:
  - `NORMCOG=1` → HC
  - `IMPNOMCI=1` → MCI
  - `DEMENTED=1 & (PROBAD or POSSAD)` → AD

---

## 3. FSL: Motion Correction (MCFLIRT)

- run별 개별 실행
- 기준 볼륨: 중간 볼륨 (default)
- 출력: motion-corrected `.nii.gz` + `.par` (6 motion parameters)
- FD 계산: `.par`에서 framewise displacement 산출
  - `fd_radius = 50mm`
  - `fd_threshold = 0.5mm`

---

## 4. FSL: MNI Registration (FLIRT)

- T1w 없음 → BOLD를 MNI에 직접 affine registration
- 기준 템플릿: `MNI152_T1_2mm_brain`
- DOF: 12 (affine)
- 출력: MNI 공간 BOLD `.nii.gz`

---

## 5. 볼륨 제거 및 연결

- 각 run 앞 **5볼륨 제거** (dummy scan)
- **run은 01, 02 두 개로 고정** (3개 이상인 경우 run-01, run-02만 사용)
- run 01, 02를 시간축으로 concatenate
- 기대 shape: `(164 - 5) × 2 = 318` timepoints

**run 파일 탐색 방식**
- `func{N}` 폴더 번호는 무시
- 피험자 폴더 하위 전체 func 폴더를 탐색하여 **파일명 기준 `task-rest_run-01`, `task-rest_run-02`** 파일만 선택
- `task-testrest` 등 다른 task 파일은 제외

> **주의**: run 수를 2개로 고정하는 이유는 피험자 간 timepoints 불균형 방지를 위함.  
> timepoints가 피험자마다 다를 경우 FC 계산 자체는 가능하나, 그룹 비교 및 일부 분류 모델에서 불균형이 문제될 수 있음.

---

## 6. Nilearn 신호 처리

| 파라미터 | 값 |
|---|---|
| Smoothing | FWHM = 6mm |
| Bandpass | high_pass = 0.01Hz, low_pass = 0.1Hz |
| TR | 2.2s |
| Confound | PCA 5 components 회귀 |
| Standardize | False |
| Detrend | False |
| GSR | 없음 |

---

## 7. ROI 추출

- AAL90 atlas로 NiftiLabelsMasker 적용
- 각 ROI 내 voxel 평균
- 출력: `(318, 90)` time series
- QC: `min_roi_voxels = 5` 미만 ROI 경고

---

## 8. FC 계산

1. `np.corrcoef(time_series.T)` → Pearson r (90×90) → `raw_fc`
2. `np.arctanh(raw_fc)` → Fisher-z, 대각선 0 → `fisher_z_fc`
3. Proportional thresholding: 상위삼각행렬 기준 **상위 10%** 엣지 유지 → `thresholded_fc`, `adjacency`
   - `threshold_proportion = 0.1`
   - `threshold_use_absolute = False`
   - 음의 상관관계는 제거됨

---

## 9. 그래프 지표 계산 (NetworkX)

- `nx.from_numpy_array(adjacency)` → 이진 무방향 그래프

**전역 지표**

| 지표 | 설명 |
|---|---|
| density | 전체 가능한 엣지 대비 실제 엣지 비율 |
| mean_degree | 평균 연결 수 |
| mean_clustering | 평균 군집 계수 |
| transitivity | 전역 군집 계수 |
| global_efficiency | 전역 효율성 |
| local_efficiency | 지역 효율성 |

**노드별 지표**

| 지표 | 설명 |
|---|---|
| degree | 연결된 엣지 수 |
| clustering | 해당 노드의 군집 계수 |
| degree_centrality | degree 정규화값 |
| betweenness_centrality | 최단경로 매개 중심성 |
| eigenvector_centrality | 고유벡터 중심성 |

---

## 10. 출력 폴더 구조

```
data/
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


## 10. HDF5 저장 구조

```
{subject_id}.h5
├── fc/
│   ├── raw_fc              (90, 90) float32
│   ├── fisher_z_fc         (90, 90) float32
│   └── thresholded_fc      (90, 90) float64
├── graph/
│   ├── adjacency           (90, 90) uint8
│   ├── edge_list           (N,)     object
│   ├── metrics             (1,)     object  # JSON, 전역 지표
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

## 11. QC 기준

| 항목 | 기준 |
|---|---|
| FD > 0.5mm 비율 | 과도한 경우 exclusion 검토 |
| atlas_mask_overlap | 낮을수록 registration 품질 저하 |
| tsnr_after_clean | 음수 또는 극소값이면 신호 소실 의심 |
| small_roi_count | min_roi_voxels 미만 ROI 수 |

---

## 비고

- T1w 해부학 파일 없음 → BOLD 기반 직접 MNI registration (제한사항)
- Slice timing correction 미적용 (원본 데이터에도 미적용)
- Distortion correction 미적용 (원본 데이터에도 미적용)
- run을 01, 02 두 개로 고정한 이유: run 수가 피험자마다 다를 경우 timepoints 불균형이 발생하며, 이는 그룹 비교 및 일부 분류 모델에서 문제가 될 수 있음
