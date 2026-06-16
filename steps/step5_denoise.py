import nibabel as nib
import numpy as np
from nilearn import image as nli
from nilearn.signal import clean
from pathlib import Path


FWHM = 6.0
HIGH_PASS = 0.01
LOW_PASS = 0.1
N_PCA_COMPONENTS = 5


def denoise(concat_result: dict, tr: float, out_dir: Path) -> dict:
    """
    Nilearn을 사용해 smoothing, bandpass filtering, PCA confound 회귀를 적용한다.

    concat_result: concat_runs() 반환값
    tr: sidecar JSON에서 읽은 RepetitionTime (초)
    out_dir: 출력 디렉토리

    반환:
        {
            "cleaned_nii": Path,
            "tsnr_before": float,
            "tsnr_after": float,
        }
    """
    from utils.qc import compute_tsnr
    from nilearn.masking import compute_brain_mask

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img = nib.load(concat_result["concat_nii"])
    data_before = img.get_fdata(dtype=np.float32)

    # 뇌 마스크 (Otsu, threshold=0.5) — 배경·CSF 이상치 제외
    brain_mask_img = compute_brain_mask(img, threshold=0.5)
    brain_mask = brain_mask_img.get_fdata().astype(bool)  # (x,y,z)

    tsnr_before = compute_tsnr(data_before, mask=brain_mask)

    # Spatial smoothing
    print(f"[DENOISE] Smoothing FWHM={FWHM}mm")
    smoothed_img = nli.smooth_img(img, fwhm=FWHM)

    # Extract signals: (T, V)
    smoothed_data = smoothed_img.get_fdata(dtype=np.float32)
    T = smoothed_data.shape[-1]
    signals = smoothed_data.reshape(-1, T).T  # (T, V)

    # PCA confounds
    confounds = _pca_confounds(signals, n_components=N_PCA_COMPONENTS)

    # Bandpass + confound regression
    print(f"[DENOISE] Bandpass {HIGH_PASS}-{LOW_PASS} Hz, TR={tr}s, PCA {N_PCA_COMPONENTS}개 회귀")
    cleaned_signals = clean(
        signals,
        confounds=confounds,
        t_r=tr,
        high_pass=HIGH_PASS,
        low_pass=LOW_PASS,
        standardize=None,
        detrend=False,
    )

    cleaned_data = cleaned_signals.T.reshape(smoothed_data.shape)

    # tSNR after: smoothing 전 mean을 분자로, cleaned std를 분모로 사용
    # bandpass 후 mean≈0이므로 smoothed mean(bandpass 전)을 기준 신호로 유지
    tsnr_after = compute_tsnr(
        cleaned_data,
        ref_mean=smoothed_data.mean(axis=-1),
        mask=brain_mask,
    )

    out_nii = out_dir / "bold_mni_cleaned.nii.gz"
    out_img = nib.Nifti1Image(cleaned_data, img.affine, img.header)
    nib.save(out_img, str(out_nii))

    print(f"[DENOISE] tSNR (brain mask, median): {tsnr_before:.1f} → {tsnr_after:.1f}")

    return {
        "cleaned_nii": out_nii,
        "tsnr_before": tsnr_before,
        "tsnr_after": tsnr_after,
    }


def _pca_confounds(signals: np.ndarray, n_components: int) -> np.ndarray:
    """
    신호에서 PCA로 주성분을 추출해 confound matrix로 반환한다.
    signals: (T, V)
    반환: (T, n_components)
    """
    from sklearn.decomposition import PCA

    pca = PCA(n_components=n_components)
    confounds = pca.fit_transform(signals)
    return confounds
