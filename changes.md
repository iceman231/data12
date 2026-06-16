# 파이프라인 주요 변경 사항

## Step 2 — Motion Correction (FSL MCFLIRT → dipy)
- FSL 미지원(Windows) → dipy `RigidTransform3D`로 대체
- 각 볼륨을 중간 볼륨 기준으로 registration, translation+rotation 파라미터 추출
- `compute_fd_from_params()`로 FD 계산 (radius=50mm, threshold=0.5mm)
- 제한: FSL 대비 속도 느림, 정확도 다소 낮음

## Step 3 — MNI Registration (FSL FLIRT → dipy)
- FSL 미지원(Windows) → dipy `AffineTransform3D`로 대체
- 평균 볼륨으로 registration 계산 후 4D 전체에 적용
- 기준 템플릿: `load_mni152_template(resolution=2)`

## Step 6 — AAL Atlas 로드 방식
- `fetch_atlas_aal()` SSL 오류 → 로컬 파일 직접 로드 (`aal/atlas/AAL.nii`, `AAL.xml`)
- SPM12/SPM8 모두 AAL116(소뇌 포함)임을 확인 → 앞 90개 ROI만 필터링 (`_mask_atlas_to_n()`)

## utils/qc.py — tSNR 계산
- bandpass 후 mean≈0 → 기존 `mean/std` 방식으로 tSNR≈0 왜곡
- `cleaned=True` 플래그 추가: cleaned 데이터는 `1/std` 방식으로 계산

## utils/qc.py — atlas overlap 계산
- cleaned 이미지 기준 → concat 이미지(denoising 전) 기준으로 변경
- BOLD 마스크: `bold > 0` → `nilearn compute_brain_mask(threshold=0.5)` (Otsu)
- 결과: 0.16 → 0.84

## Step 9 — acquisition_metadata
- `MagneticFieldStrength`, `Manufacturer` 필드 추가 (sidecar JSON에서 읽어 저장)

## Step 1 — CSV NaN 처리
- 진단 필드 NaN값으로 `int()` 변환 시 ValueError 발생
- `_int()` 헬퍼 함수 추가로 NaN 안전 처리
