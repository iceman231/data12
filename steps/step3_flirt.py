"""
BOLD -> MNI152 affine registration via FSL FLIRT.
1단계: mean BOLD -> MNI (flirt -dof 12) → transform matrix 산출
2단계: 4D BOLD 전체에 transform 적용 (flirt -applyxfm)
MNI 템플릿: $FSLDIR/data/standard/MNI152_T1_2mm_brain.nii.gz
"""

import os
import subprocess
from pathlib import Path


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


def _get_mni_template(fsldir: str) -> str:
    template = os.path.join(fsldir, "data", "standard", "MNI152_T1_2mm_brain.nii.gz")
    if not os.path.exists(template):
        raise FileNotFoundError(
            f"MNI 템플릿을 찾을 수 없습니다: {template}\n"
            f"FSLDIR={fsldir} 가 올바른지 확인하세요."
        )
    return template


def run_flirt(mc_result: dict, out_dir: Path) -> dict:
    """
    motion-corrected BOLD를 MNI152 2mm 공간으로 affine registration한다.

    mc_result: run_mcflirt() 반환값
    반환:
        {
            "run": str,
            "mni_nii": Path,
        }
    """
    fsldir   = _check_fsldir()
    mni_tmpl = _get_mni_template(fsldir)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_num  = mc_result["run"]
    in_nii   = mc_result["mc_nii"]
    out_nii  = out_dir / f"run-{run_num}_bold_mni.nii.gz"
    mat_file = out_dir / f"run-{run_num}_bold2mni.mat"
    mean_nii = out_dir / f"run-{run_num}_bold_mean.nii.gz"

    if out_nii.exists():
        print(f"[FLIRT] run-{run_num}: 캐시 사용 (이미 완료)")
        return {"run": run_num, "mni_nii": out_nii}

    env = _fsl_env(fsldir)

    def _run(cmd, label):
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.stdout:
            print(result.stdout.strip())
        if result.returncode != 0:
            raise RuntimeError(
                f"{label} 실패 (run-{run_num}):\n"
                f"CMD: {' '.join(cmd)}\n"
                f"STDERR: {result.stderr}"
            )

    # 1. mean BOLD 생성
    print(f"[FLIRT] run-{run_num}: mean BOLD 생성 (fslmaths -Tmean)")
    _run(["fslmaths", str(in_nii), "-Tmean", str(mean_nii)], "fslmaths")

    # 2. mean BOLD → MNI (transform matrix 추출)
    mean_mni = out_dir / f"run-{run_num}_mean_mni.nii.gz"
    print(f"[FLIRT] run-{run_num}: mean BOLD -> MNI152 등록 (dof=12)")
    _run([
        "flirt",
        "-in",   str(mean_nii),
        "-ref",  mni_tmpl,
        "-out",  str(mean_mni),
        "-omat", str(mat_file),
        "-dof",  "12",
    ], "flirt 등록")

    # 3. 4D BOLD 전체에 transform 적용
    print(f"[FLIRT] run-{run_num}: 4D BOLD MNI 공간 변환 중 (applyxfm)")
    _run([
        "flirt",
        "-in",       str(in_nii),
        "-ref",      mni_tmpl,
        "-out",      str(out_nii),
        "-init",     str(mat_file),
        "-applyxfm",
    ], "flirt applyxfm")

    print(f"[FLIRT] run-{run_num}: 완료 -> {out_nii}")
    return {"run": run_num, "mni_nii": out_nii}


def run_flirt_all(mc_results: list[dict], out_dir: Path) -> list[dict]:
    results = []
    for mc_result in mc_results:
        results.append(run_flirt(mc_result, out_dir))
    return results
