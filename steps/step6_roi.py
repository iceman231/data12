import ssl
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
import numpy as np
import nibabel as nib
from nilearn.maskers import NiftiLabelsMasker
from pathlib import Path


ATLAS_DIR = Path(__file__).parent.parent / "aal" / "atlas"
ATLAS_NII = ATLAS_DIR / "AAL.nii"
ATLAS_XML = ATLAS_DIR / "AAL.xml"
_AAL_URL = "https://www.gin.cnrs.fr/AAL_files/aal_for_SPM12.tar.gz"

MIN_ROI_VOXELS = 5


def _ensure_atlas():
    """aal/atlas/AAL.nii + AAL.xml이 없으면 SSL 우회로 다운로드한다."""
    if ATLAS_NII.exists() and ATLAS_XML.exists():
        return

    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    tar_path = ATLAS_DIR / "aal_for_SPM12.tar.gz"

    print(f"[ROI] AAL 아틀라스 다운로드 (SSL 검증 비활성화)...")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(_AAL_URL, context=ctx, timeout=180) as resp:
        with open(tar_path, "wb") as fout:
            fout.write(resp.read())

    with tarfile.open(tar_path) as tf:
        tf.extractall(ATLAS_DIR)
    tar_path.unlink(missing_ok=True)

    # tar 내 경로 무관하게 .nii / .xml 파일 찾아 이름 고정
    for src in sorted(ATLAS_DIR.rglob("*.nii")):
        if src != ATLAS_NII:
            src.rename(ATLAS_NII)
            break
    for src in sorted(ATLAS_DIR.rglob("*.xml")):
        if src != ATLAS_XML:
            src.rename(ATLAS_XML)
            break

    if not ATLAS_NII.exists() or not ATLAS_XML.exists():
        raise FileNotFoundError(f"AAL atlas 파일을 {ATLAS_DIR} 에서 찾을 수 없음")
    print(f"[ROI] AAL 아틀라스 준비 완료: {ATLAS_DIR}")


def extract_roi_timeseries(denoise_result: dict, tr: float, concat_result: dict = None) -> dict:
    """
    AAL90 atlas로 ROI별 평균 시계열을 추출한다.

    denoise_result: denoise() 반환값
    tr: RepetitionTime (초)
    """
    from utils.qc import compute_atlas_overlap

    _ensure_atlas()
    atlas_img_full = nib.load(ATLAS_NII)
    roi_labels_full = _load_labels(ATLAS_XML)

    # 소뇌 제외: 앞 90개 ROI만 사용
    roi_labels = roi_labels_full[:90]
    atlas_img = _mask_atlas_to_n(atlas_img_full, n=90)

    masker = NiftiLabelsMasker(
        labels_img=atlas_img,
        standardize=False,
        detrend=False,
        t_r=tr,
        resampling_target="data",
        memory_level=0,
    )

    cleaned_img = nib.load(denoise_result["cleaned_nii"])
    time_series = masker.fit_transform(cleaned_img)  # (T, 90)

    small_roi_count = _check_roi_sizes(atlas_img, cleaned_img)
    # atlas overlap은 denoising 전 concat 이미지 기준으로 계산 (mean 신호가 살아있어야 정확)
    ref_img = nib.load(concat_result["concat_nii"]) if concat_result else cleaned_img
    atlas_overlap = compute_atlas_overlap(ref_img, atlas_img)

    print(
        f"[ROI] time_series shape: {time_series.shape}, "
        f"atlas overlap: {atlas_overlap:.3f}, "
        f"small ROI (<{MIN_ROI_VOXELS} voxel): {small_roi_count}개"
    )

    return {
        "time_series": time_series,
        "roi_labels": roi_labels,
        "atlas_img": atlas_img,
        "small_roi_count": small_roi_count,
        "atlas_overlap": atlas_overlap,
    }


def _mask_atlas_to_n(atlas_img, n: int):
    """atlas에서 라벨 값 기준 상위 n개 ROI만 남기고 나머지를 0으로 마스킹한다."""
    data = atlas_img.get_fdata().copy()
    unique_labels = sorted(np.unique(data[data > 0]))
    keep = set(unique_labels[:n])
    data[~np.isin(data, list(keep))] = 0
    return nib.Nifti1Image(data, atlas_img.affine, atlas_img.header)


def _load_labels(xml_path: Path) -> list[str]:
    """AAL.xml에서 ROI 이름 목록을 파싱한다."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    labels = [el.find("name").text for el in root.iter("label")]
    return labels


def _check_roi_sizes(atlas_img, bold_img) -> int:
    from nilearn import image as nli

    atlas_resampled = nli.resample_to_img(atlas_img, bold_img, interpolation="nearest")
    atlas_data = atlas_resampled.get_fdata()

    unique_labels = np.unique(atlas_data)
    unique_labels = unique_labels[unique_labels > 0]

    small_count = 0
    for label in unique_labels:
        n_voxels = (atlas_data == label).sum()
        if n_voxels < MIN_ROI_VOXELS:
            print(f"[WARN] ROI label {int(label)}: {int(n_voxels)} voxels < {MIN_ROI_VOXELS}")
            small_count += 1

    return small_count
