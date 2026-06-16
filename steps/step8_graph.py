import numpy as np
import networkx as nx


def compute_graph_metrics(fc_result: dict, roi_labels: list[str]) -> dict:
    """
    이진 adjacency matrix로 NetworkX 그래프를 구성하고
    전역/노드별 그래프 지표를 계산한다.

    반환:
        {
            "global_metrics": dict,
            "node_metrics": dict,   # 각 지표: (90,) ndarray
            "edge_list": list[str],
            "node_labels": list[str],
        }
    """
    adjacency = fc_result["adjacency"]  # (90, 90) uint8
    G = nx.from_numpy_array(adjacency)

    global_metrics = _global_metrics(G, fc_result)
    node_metrics = _node_metrics(G)
    edge_list = _build_edge_list(G, roi_labels)

    print(
        f"[GRAPH] nodes={G.number_of_nodes()}, edges={G.number_of_edges()}, "
        f"density={global_metrics['density']:.4f}, "
        f"mean_clustering={global_metrics['mean_clustering']:.4f}"
    )

    return {
        "global_metrics": global_metrics,
        "node_metrics": node_metrics,
        "edge_list": edge_list,
        "node_labels": roi_labels,
    }


def _global_metrics(G: nx.Graph, fc_result: dict) -> dict:
    degrees = [d for _, d in G.degree()]

    return {
        "density":          float(nx.density(G)),
        "mean_degree":      float(np.mean(degrees)) if degrees else 0.0,
        "mean_clustering":  float(nx.average_clustering(G)),
        "transitivity":     float(nx.transitivity(G)),
        "global_efficiency": float(nx.global_efficiency(G)),
        "local_efficiency": float(nx.local_efficiency(G)),
        "n_edges":          fc_result.get("n_edges", G.number_of_edges()),
        "edge_density":     fc_result.get("edge_density", float(nx.density(G))),
    }


def _node_metrics(G: nx.Graph) -> dict:
    n = G.number_of_nodes()

    clustering = nx.clustering(G)
    degree = dict(G.degree())
    degree_centrality = nx.degree_centrality(G)
    betweenness = nx.betweenness_centrality(G, normalized=True)

    try:
        eigenvector = nx.eigenvector_centrality(G, max_iter=1000, tol=1e-6)
    except nx.PowerIterationFailedConvergence:
        print("[WARN] eigenvector_centrality 수렴 실패, 0으로 설정")
        eigenvector = {i: 0.0 for i in G.nodes()}

    def to_array(d: dict) -> np.ndarray:
        return np.array([d.get(i, 0.0) for i in range(n)], dtype=np.float64)

    return {
        "clustering": to_array(clustering),
        "degree": to_array(degree),
        "degree_centrality": to_array(degree_centrality),
        "betweenness_centrality": to_array(betweenness),
        "eigenvector_centrality": to_array(eigenvector),
    }


def _build_edge_list(G: nx.Graph, labels: list[str]) -> list[str]:
    """엣지를 'ROI_A--ROI_B' 문자열 목록으로 반환한다."""
    edges = []
    for u, v in G.edges():
        label_u = labels[u] if u < len(labels) else str(u)
        label_v = labels[v] if v < len(labels) else str(v)
        edges.append(f"{label_u}--{label_v}")
    return edges
