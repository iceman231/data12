"""
Motion correction via FSL MCFLIRT.
subprocess로 mcflirt 명령어를 직접 호출한다.
"""

import os
import subprocess
import numpy as np
from pathlib import Path

from utils.qc import compute_fd


FD_RADIUS    = 50.0
FD_THRESHOLD = 0.5


def _check_fsldir() -> str:
    fsldir = os.environ.get("FSLDIR")
    if not fsldir:
        raise EnvironmentError(
            "FSLDIR 환경변수가 설정되지 않았습니다.\n"
            "FSL 설치 경로를 확인 후 다음 명령으로 설정하세요:\n"
            "  export FSLDIR=/home/<username>/fsl\n"
            "  source $FSLDIR/etc/fslconf/fsl.sh\n"
            "  export PATH=$FSLDIR/bin:$PATH"
        )
    return fsldir


def _fsl_env(fsldir: str) -> dict:
    """FSL 명령어 실행용 환경변수 dict를 반환한다.
    conda 기반 설치($FSLDIR/share/fsl/bin)와 표준 설치($FSLDIR/bin) 모두 지원.
    """
    env = os.environ.copy()
    env["FSLDIR"] = fsldir
    env.setdefault("FSLOUTPUTTYPE", "NIFTI_GZ")

    fsl_bin_candidates = [
        os.path.join(fsldir, "bin"),
        os.path.join(fsldir, "share", "fsl", "bin"),
    ]
    extra = [p for p in fsl_bin_candidates if os.path.isdir(p)]
    if extra:
        env["PATH"] = ":".join(extra) + ":" + env.get("PATH", "")

    return env


def run_mcflirt(run: dict, out_dir: Path, n_workers: int = None) -> dict:
    """
    FSL mcflirt으로 motion correction을 수행한다.

    run: {"run": "01", "nii": Path, "json": Path}

    반환:
        {
            "run": str,
            "mc_nii": Path,    # motion-corrected NIfTI
            "par": Path,       # [tx, ty, tz, rx, ry, rz] 형식 .par
            "fd": np.ndarray,  # framewise displacement
            "fd_ratio": float,
        }
    """
    fsldir = _check_fsldir()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_num     = run["run"]
    in_nii      = run["nii"]
    out_base    = out_dir / f"run-{run_num}_bold_mcf"
    mc_nii_path = out_dir / f"run-{run_num}_bold_mcf.nii.gz"
    par_path    = out_dir / f"run-{run_num}_bold_mcf.par"

    if mc_nii_path.exists() and par_path.exists():
        print(f"[MCFLIRT] run-{run_num}: 캐시 사용 (이미 완료)")
        fd       = compute_fd(par_path, radius=FD_RADIUS)
        fd_ratio = float((fd > FD_THRESHOLD).sum() / len(fd))
        return {"run": run_num, "mc_nii": mc_nii_path, "par": par_path,
                "fd": fd, "fd_ratio": fd_ratio}

    env = _fsl_env(fsldir)

    cmd = [
        "mcflirt",
        "-in",  str(in_nii),
        "-out", str(out_base),
        "-plots",
    ]
    print(f"[MCFLIRT] run-{run_num}: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"mcflirt 실패 (run-{run_num}):\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )

    # FSL par 형식: [rx, ry, rz, tx, ty, tz]
    # compute_fd 기대 형식: [tx, ty, tz, rx, ry, rz] (columns 3-5에 radius 곱함)
    fsl_params = np.loadtxt(str(par_path))
    if fsl_params.ndim == 1:
        fsl_params = fsl_params[np.newaxis, :]
    reordered = fsl_params[:, [3, 4, 5, 0, 1, 2]]
    np.savetxt(str(par_path), reordered, fmt="%.6f")

    fd       = compute_fd(par_path, radius=FD_RADIUS)
    fd_ratio = float((fd > FD_THRESHOLD).sum() / len(fd))
    print(f"[MCFLIRT] run-{run_num}: FD>{FD_THRESHOLD}mm 비율={fd_ratio:.3f} ({int(fd_ratio * len(fd))}/{len(fd)} vols)")

    return {
        "run":      run_num,
        "mc_nii":   mc_nii_path,
        "par":      par_path,
        "fd":       fd,
        "fd_ratio": fd_ratio,
    }


def run_mcflirt_all(runs: list[dict], out_dir: Path, n_workers: int = None) -> list[dict]:
    results = []
    for run in runs:
        results.append(run_mcflirt(run, out_dir, n_workers=n_workers))
    return results
