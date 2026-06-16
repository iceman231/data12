import nibabel as nib
import numpy as np
from pathlib import Path

from utils.exceptions import InsufficientVolumesError

DUMMY_VOLS = 5
EXPECTED_TIMEPOINTS = 318  # (164 - 5) * 2


def concat_runs(flirt_results: list[dict], mc_results: list[dict], out_dir: Path) -> dict:
    """
    run-01, run-02의 MNI BOLD에서 앞 5볼륨을 제거하고 시간축으로 연결한다.

    flirt_results: run_flirt_all() 반환값 (run-01, run-02 순서)
    mc_results: run_mcflirt_all() 반환값 (FD 연결에 사용)
    out_dir: 출력 디렉토리

    반환:
        {
            "concat_nii": Path,
            "n_timepoints": int,
            "fd_concat": np.ndarray,
            "run_info": list[dict],
        }
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    volumes = []
    fd_parts = []
    run_info = []

    # run-01, run-02 고정 (최대 2개)
    for flirt_r, mc_r in zip(flirt_results[:2], mc_results[:2]):
        img = nib.load(flirt_r["mni_nii"])
        data = img.get_fdata(dtype=np.float32)

        if data.ndim != 4:
            raise ValueError(f"4D 볼륨 아님: {flirt_r['mni_nii']}")

        n_orig = data.shape[-1]
        if n_orig <= DUMMY_VOLS:
            print(
                f"[CONCAT] run-{flirt_r['run']}: 볼륨 수 {n_orig} ≤ DUMMY_VOLS({DUMMY_VOLS}), 스킵"
            )
            continue
        data_trimmed = data[..., DUMMY_VOLS:]
        n_trimmed = data_trimmed.shape[-1]

        print(
            f"[CONCAT] run-{flirt_r['run']}: {n_orig} vol → {DUMMY_VOLS}개 제거 → {n_trimmed} vol"
        )

        volumes.append(data_trimmed)

        fd = mc_r["fd"]
        fd_parts.append(fd[DUMMY_VOLS:])

        run_info.append({
            "run": flirt_r["run"],
            "original_vols": n_orig,
            "trimmed_vols": n_trimmed,
        })

        affine = img.affine
        header = img.header

    if not volumes:
        raise InsufficientVolumesError("유효한 run이 없습니다 (모든 run이 볼륨 부족으로 스킵됨)")

    concat_data = np.concatenate(volumes, axis=-1)
    fd_concat = np.concatenate(fd_parts)

    n_total = concat_data.shape[-1]
    if n_total != EXPECTED_TIMEPOINTS:
        print(
            f"[WARN] concatenated timepoints = {n_total}, "
            f"예상 {EXPECTED_TIMEPOINTS}"
        )

    out_nii = out_dir / "bold_mni_concat.nii.gz"
    out_img = nib.Nifti1Image(concat_data, affine, header)
    nib.save(out_img, str(out_nii))

    print(f"[CONCAT] 완료: {n_total} timepoints → {out_nii}")

    return {
        "concat_nii": out_nii,
        "n_timepoints": n_total,
        "fd_concat": fd_concat,
        "run_info": run_info,
    }
