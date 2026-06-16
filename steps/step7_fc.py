import numpy as np


THRESHOLD_PROPORTION = 0.1
THRESHOLD_USE_ABSOLUTE = False


def compute_fc(roi_result: dict) -> dict:
    """
    ROI 시계열에서 FC matrix를 계산한다.

    처리 순서:
      1. np.corrcoef(time_series.T) → raw_fc (90×90), Pearson r
      2. np.arctanh(raw_fc) → fisher_z_fc, 대각선=0
      3. proportional thresholding (양의 FC 상위 10%) → thresholded_fc, adjacency

    반환:
        {
            "raw_fc":         np.ndarray (90, 90) float32
            "fisher_z_fc":    np.ndarray (90, 90) float32
            "thresholded_fc": np.ndarray (90, 90) float64
            "adjacency":      np.ndarray (90, 90) uint8
            "n_edges":        int
            "edge_density":   float
        }
    """
    time_series = roi_result["time_series"]  # (T, 90)

    if time_series.ndim != 2:
        raise ValueError(f"time_series는 2D (T, ROI)여야 함, 현재 shape: {time_series.shape}")

    n_roi = time_series.shape[1]

    # raw_fc: NaN/Inf 방어 처리
    raw_fc = np.corrcoef(time_series.T)
    raw_fc = np.nan_to_num(raw_fc, nan=0.0, posinf=0.0, neginf=0.0)

    # fisher_z: r=±1 클리핑 후 arctanh, 대각선=0
    clipped    = np.clip(raw_fc, -0.999999, 0.999999)
    fisher_z   = np.arctanh(clipped)
    np.fill_diagonal(fisher_z, 0.0)

    thresholded_fc, adjacency = _proportional_threshold(
        raw_fc, THRESHOLD_PROPORTION, use_absolute=THRESHOLD_USE_ABSOLUTE
    )

    n_edges       = int(adjacency.sum() // 2)
    possible_edges = n_roi * (n_roi - 1) // 2
    edge_density  = n_edges / possible_edges if possible_edges > 0 else 0.0

    print(
        f"[FC] raw_fc range: [{raw_fc.min():.3f}, {raw_fc.max():.3f}], "
        f"edges after thresholding: {n_edges}, density: {edge_density:.4f}"
    )

    return {
        "raw_fc":         raw_fc.astype(np.float32),
        "fisher_z_fc":    fisher_z.astype(np.float32),
        "thresholded_fc": thresholded_fc.astype(np.float64),
        "adjacency":      adjacency.astype(np.uint8),
        "n_edges":        n_edges,
        "edge_density":   edge_density,
    }


def _proportional_threshold(raw_fc: np.ndarray, proportion: float, use_absolute: bool) -> tuple:
    """
    상위삼각행렬(대각선 제외)에서 상위 proportion 비율의 연결만 유지한다.

    use_absolute=False (기본): 양의 FC만 대상으로 상위 proportion% 선택
    use_absolute=True:         절댓값 기준 상위 proportion% 선택

    반환: (thresholded_fc, adjacency), 각 (90,90), 대칭, 대각선=0
    """
    n  = raw_fc.shape[0]
    fc = raw_fc.copy()
    np.fill_diagonal(fc, 0.0)

    fc_for_ranking = np.where(fc > 0, fc, 0.0) if not use_absolute else np.abs(fc)

    iu         = np.triu_indices(n, k=1)
    upper_vals = fc_for_ranking[iu]

    n_keep = max(1, int(np.floor(len(upper_vals) * proportion)))

    nonzero_vals = upper_vals[upper_vals > 0]
    if len(nonzero_vals) == 0:
        return np.zeros((n, n), dtype=np.float64), np.zeros((n, n), dtype=np.uint8)

    n_keep      = min(n_keep, len(nonzero_vals))
    sorted_vals = np.sort(nonzero_vals)[::-1]
    cutoff      = sorted_vals[n_keep - 1]

    mask_upper = np.triu(fc_for_ranking >= cutoff, k=1)
    mask       = mask_upper | mask_upper.T

    adjacency = mask.astype(np.uint8)
    np.fill_diagonal(adjacency, 0)

    thresholded_fc = np.where(mask, fc, 0.0)
    np.fill_diagonal(thresholded_fc, 0.0)

    return thresholded_fc, adjacency
