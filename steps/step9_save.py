import h5py
import json
import numpy as np
import pandas as pd
from pathlib import Path


def save_subject(
    subject_id: str,
    diagnosis_group: str,
    diagnosis_result: dict,
    fc_result: dict,
    graph_result: dict,
    roi_result: dict,
    concat_result: dict,
    denoise_result: dict,
    mc_results: list[dict],
    tr: float,
    acquisition_meta: dict,
    output_root: Path,
) -> Path:
    """
    피험자 데이터를 HDF5로 저장한다.

    반환: 저장된 .h5 파일 경로
    """
    output_root = Path(output_root)
    subject_dir = output_root / diagnosis_group / subject_id
    subject_dir.mkdir(parents=True, exist_ok=True)

    h5_path = subject_dir / f"{subject_id}.h5"

    demographics = _extract_demographics(diagnosis_result)

    with h5py.File(h5_path, "w") as f:
        _save_fc(f, fc_result)
        _save_graph(f, fc_result, graph_result)
        _save_roi(f, roi_result)
        _save_metadata(f, subject_id, diagnosis_result, concat_result, mc_results, tr, acquisition_meta, demographics)
        _save_qc(f, concat_result, denoise_result, roi_result, mc_results)

    print(f"[SAVE] {h5_path}")
    return h5_path


def _extract_demographics(diagnosis_result: dict) -> dict:
    """
    step1 diagnosis_result["row"] (진단 CSV 해당 행)에서
    인구통계 관련 필드를 추출한다.
    subjects.csv 없이 진단 CSV만으로 채울 수 있는 필드.
    """
    row = diagnosis_result.get("row", {})
    return {
        "OASISID":       row.get("OASISID", diagnosis_result.get("subject_id", "")),
        "age_at_visit":  row.get("age at visit", ""),
        "days_to_visit": row.get("days_to_visit", ""),
        "WHODIDDX":      row.get("WHODIDDX", ""),
    }


def _save_fc(f: h5py.File, fc_result: dict):
    grp = f.create_group("fc")
    grp.create_dataset("raw_fc",         data=fc_result["raw_fc"].astype(np.float32))
    grp.create_dataset("fisher_z_fc",    data=fc_result["fisher_z_fc"].astype(np.float32))
    grp.create_dataset("thresholded_fc", data=fc_result["thresholded_fc"].astype(np.float64))


def _save_graph(f: h5py.File, fc_result: dict, graph_result: dict):
    grp = f.create_group("graph")
    grp.create_dataset("adjacency", data=fc_result["adjacency"].astype(np.uint8))

    edge_list = graph_result["edge_list"]
    dt = h5py.special_dtype(vlen=str)
    edge_ds = grp.create_dataset("edge_list", shape=(len(edge_list),), dtype=dt)
    for i, e in enumerate(edge_list):
        edge_ds[i] = e

    metrics_json = json.dumps(graph_result["global_metrics"])
    metrics_ds = grp.create_dataset("metrics", shape=(1,), dtype=dt)
    metrics_ds[0] = metrics_json

    node_labels = graph_result["node_labels"]
    label_ds = grp.create_dataset("node_labels", shape=(len(node_labels),), dtype=dt)
    for i, lbl in enumerate(node_labels):
        label_ds[i] = lbl

    nm_grp = grp.create_group("node_metrics")
    for key, arr in graph_result["node_metrics"].items():
        nm_grp.create_dataset(key, data=arr.astype(np.float64))


def _save_roi(f: h5py.File, roi_result: dict):
    grp = f.create_group("roi_time_series")
    grp.create_dataset("data", data=roi_result["time_series"].astype(np.float32))


def _save_metadata(
    f: h5py.File,
    subject_id: str,
    diagnosis_result: dict,
    concat_result: dict,
    mc_results: list[dict],
    tr: float,
    acquisition_meta: dict,
    demographics: dict,
):
    grp = f.create_group("metadata")
    dt = h5py.special_dtype(vlen=str)

    def _json_ds(name: str, obj):
        ds = grp.create_dataset(name, shape=(1,), dtype=dt)
        ds[0] = json.dumps(obj, default=str, ensure_ascii=False)

    _json_ds("subject", {"subject_id": subject_id})
    _json_ds("diagnosis", diagnosis_result)
    _json_ds("demographics", demographics)

    _json_ds("preprocessing_config", {
        "registered_to_mni": True,
        "registration_tool": "FSL FLIRT 6.0.7.22",
        "mni_template": "$FSLDIR/data/standard/MNI152_T1_2mm_brain.nii.gz",
        "dof": 12,
        "motion_corrected": True,
        "motion_tool": "FSL MCFLIRT 6.0.7.22",
        "dummy_vols_removed": 5,
        "smoothing_fwhm_mm": 6,
        "bandpass_high_pass_hz": 0.01,
        "bandpass_low_pass_hz": 0.1,
        "confound_pca_components": 5,
        "standardize": False,
        "detrend": False,
        "gsr": False,
        "fd_radius_mm": 50,
        "fd_threshold_mm": 0.5,
        "threshold_proportion": 0.1,
        "atlas": "AAL90 (SPM12)",
        "tr": tr,
    })

    run_info = concat_result.get("run_info", [])
    _json_ds("run_concatenation", {"run_info": run_info, "total_timepoints": concat_result["n_timepoints"]})

    selected_runs = [r["run"] for r in mc_results[:2]]
    _json_ds("selected_runs", {"runs": selected_runs})

    _json_ds("acquisition_metadata", {
        "tr": tr,
        "MagneticFieldStrength": acquisition_meta.get("MagneticFieldStrength"),
        "Manufacturer": acquisition_meta.get("Manufacturer"),
    })

    _json_ds("qc_notes", {
        "atlas_overlap_pass_threshold": 0.85,
        "atlas_overlap_warn_threshold": 0.80,
        "atlas_overlap_criteria": (
            ">=0.85: PASS, 0.80~0.85: WARNING, <0.80: FAIL"
        ),
    })
    _json_ds("warnings", [])


def _save_qc(
    f: h5py.File,
    concat_result: dict,
    denoise_result: dict,
    roi_result: dict,
    mc_results: list[dict],
):
    grp = f.create_group("qc")
    dt = h5py.special_dtype(vlen=str)

    fd = concat_result["fd_concat"]
    fd_ratio = float((fd > 0.5).sum() / len(fd))

    grp.create_dataset("motion_fd", data=fd.astype(np.float64))
    grp.create_dataset("fd_over_0_5_ratio", data=fd_ratio)
    grp.create_dataset("atlas_mask_overlap", data=roi_result["atlas_overlap"])
    grp.create_dataset(
        "tsnr",
        data=np.array([denoise_result["tsnr_before"], denoise_result["tsnr_after"]], dtype=np.float64)
    )

    report = {
        "fd_over_0_5_ratio": fd_ratio,
        "tsnr_before": denoise_result["tsnr_before"],
        "tsnr_after": denoise_result["tsnr_after"],
        "atlas_mask_overlap": roi_result["atlas_overlap"],
        "small_roi_count": roi_result["small_roi_count"],
    }
    report_ds = grp.create_dataset("report", shape=(1,), dtype=dt)
    report_ds[0] = json.dumps(report)
