import numpy as np
import nibabel as nib


def compute_fd_from_params(params: np.ndarray, radius: float = 50.0) -> np.ndarray:
    """
    (n_vols, 6) 파라미터 배열에서 FD를 계산한다.
    params: [tx, ty, tz, rx, ry, rz]
    """
    diff = np.diff(params, axis=0)
    diff[:, 3:] *= radius
    fd = np.sum(np.abs(diff), axis=1)
    return np.concatenate([[0.0], fd])


def compute_fd(par_path, radius: float = 50.0) -> np.ndarray:
    """
    MCFLIRT .par 파일에서 FD를 계산한다.
    par: [tx, ty, tz, rx, ry, rz] (translation mm, rotation rad)
    rotation → arc length: angle_rad * radius
    """
    params = np.loadtxt(par_path)
    if params.ndim == 1:
        params = params[np.newaxis, :]

    diff = np.diff(params, axis=0)
    diff[:, 3:] *= radius

    fd = np.sum(np.abs(diff), axis=1)
    fd = np.concatenate([[0.0], fd])
    return fd


def compute_tsnr(img_data: np.ndarray, ref_mean: np.ndarray = None,
                 mask: np.ndarray = None) -> float:
    """
    4D BOLD (x, y, z, t)에서 tSNR을 계산한다.

    mask     : 3D bool — 뇌 영역 마스크. None이면 mean > 0 사용 (부정확).
               step5에서 nilearn compute_brain_mask로 생성해서 넘길 것.
    ref_mean : 분자로 쓸 별도 3D mean. bandpass 후 처럼 신호 mean≈0일 때
               smoothing 전 mean을 넘겨 의미 있는 tSNR을 산출한다.
    공식: median( ref_mean / std )  —  배경·CSF 이상치에 강건한 중앙값 사용.
    """
    actual_mean = ref_mean if ref_mean is not None else img_data.mean(axis=-1)
    std_signal  = img_data.std(axis=-1)

    if mask is None:
        mask = actual_mean > 0

    valid = mask & (std_signal > 0)
    if not valid.any():
        return 0.0

    with np.errstate(divide="ignore", invalid="ignore"):
        tsnr_vals = actual_mean[valid] / (std_signal[valid] + 1e-10)

    return float(np.median(tsnr_vals))


def compute_atlas_overlap(bold_img, atlas_img) -> float:
    """
    BOLD 뇌 마스크와 atlas 마스크의 Dice overlap을 반환한다.
    nilearn compute_brain_mask(Otsu)로 뇌 마스크를 생성한다.
    """
    import nilearn.image as nli
    from nilearn import masking

    brain_mask = masking.compute_brain_mask(bold_img, threshold=0.5)
    bold_mask = brain_mask.get_fdata().astype(bool)

    atlas_resampled = nli.resample_to_img(atlas_img, bold_img, interpolation="nearest")
    atlas_mask = atlas_resampled.get_fdata() > 0

    intersection = np.logical_and(bold_mask, atlas_mask).sum()
    union = bold_mask.sum() + atlas_mask.sum()

    return float(2 * intersection / union) if union > 0 else 0.0


def build_qc_report(
    fd: np.ndarray,
    fd_threshold: float,
    tsnr_before: float,
    tsnr_after: float,
    atlas_overlap: float,
    small_roi_count: int,
    warnings: list[str],
) -> dict:
    """QC 지표를 dict로 집계한다."""
    fd_ratio = float((fd > fd_threshold).sum() / len(fd))
    return {
        "fd_over_threshold_ratio": fd_ratio,
        "fd_threshold_mm": fd_threshold,
        "tsnr_before_clean": tsnr_before,
        "tsnr_after_clean": tsnr_after,
        "atlas_mask_overlap": atlas_overlap,
        "small_roi_count": small_roi_count,
        "warnings": warnings,
    }
