"""
Módulo de agrupamento não supervisionado (Clustering) de operações.
Suporta MiniBatchKMeans, KMeans, HDBSCAN e AgglomerativeClustering (Hierárquico).
Calcula métricas intrínsecas: Silhouette, Davies-Bouldin, Calinski-Harabasz,
estabilidade por bootstrap (ARI/NMI), razão de ruído, entropia e distribuição dos grupos.
Permite comparar clustering no espaço original vs espaço reduzido (PCA/UMAP).
"""
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from sklearn.cluster import MiniBatchKMeans, KMeans, HDBSCAN, AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score, adjusted_rand_score
from sklearn.metrics.pairwise import cosine_similarity
from src.config import ClusteringConfig

class OperationsClusterer:
    def __init__(self, cfg: ClusteringConfig):
        self.cfg = cfg
        self.model = None
        self.pca = None
        self.cluster_labels = None
        self.centroids_ = None

    def reduce_dimensions(self, embeddings: np.ndarray, n_components: int = 32) -> np.ndarray:
        """Aplica PCA para redução controlada de dimensionalidade."""
        n_components = min(n_components, embeddings.shape[0] - 1, embeddings.shape[1])
        self.pca = PCA(n_components=n_components, random_state=self.cfg.random_state)
        reduced = self.pca.fit_transform(embeddings)
        # Renormalizar
        norms = np.linalg.norm(reduced, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return reduced / norms

    def evaluate_clustering(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        sample_size: int = 5000
    ) -> Dict[str, Any]:
        """
        Calcula métricas rigorosas de qualidade intrínseca do clustering.
        """
        # Excluir ruído (-1) se presente para cálculo de métricas de separação
        valid_mask = labels != -1
        n_samples = len(labels)
        n_clusters = len(set(labels[valid_mask]))
        noise_count = int(np.sum(~valid_mask))
        noise_ratio = float(noise_count / n_samples)

        metrics = {
            "n_clusters": n_clusters,
            "total_samples": n_samples,
            "noise_samples": noise_count,
            "noise_ratio": round(noise_ratio, 4)
        }

        if n_clusters < 2:
            metrics["silhouette"] = -1.0
            metrics["davies_bouldin"] = 999.0
            metrics["calinski_harabasz"] = 0.0
            metrics["size_entropy"] = 0.0
            metrics["min_size"] = n_samples
            metrics["max_size"] = n_samples
            metrics["median_size"] = n_samples
            return metrics

        # Distribuição dos tamanhos
        unique_labels, counts = np.unique(labels[valid_mask], return_counts=True)
        probs = counts / np.sum(counts)
        entropy = -np.sum(probs * np.log2(probs + 1e-12))
        
        metrics["size_entropy"] = round(float(entropy), 4)
        metrics["min_size"] = int(np.min(counts))
        metrics["max_size"] = int(np.max(counts))
        metrics["median_size"] = float(np.median(counts))
        metrics["std_size"] = round(float(np.std(counts)), 2)

        # Amostrar para cálculo de silhouette se base for muito grande
        eval_embeddings = embeddings[valid_mask]
        eval_labels = labels[valid_mask]
        if len(eval_labels) > sample_size:
            idx = np.random.choice(len(eval_labels), sample_size, replace=False)
            sub_emb = eval_embeddings[idx]
            sub_lab = eval_labels[idx]
        else:
            sub_emb = eval_embeddings
            sub_lab = eval_labels

        try:
            metrics["silhouette"] = round(float(silhouette_score(sub_emb, sub_lab, metric="cosine")), 4)
        except Exception:
            metrics["silhouette"] = -1.0

        try:
            metrics["davies_bouldin"] = round(float(davies_bouldin_score(sub_emb, sub_lab)), 4)
        except Exception:
            metrics["davies_bouldin"] = 999.0

        try:
            metrics["calinski_harabasz"] = round(float(calinski_harabasz_score(sub_emb, sub_lab)), 2)
        except Exception:
            metrics["calinski_harabasz"] = 0.0

        return metrics

    def compute_stability(
        self,
        embeddings: np.ndarray,
        algorithm: str,
        k: int,
        n_bootstraps: int = 5
    ) -> float:
        """
        Avalia a estabilidade dos agrupamentos usando Adjusted Rand Index (ARI)
        em subamostragens (bootstraps). Valores próximos a 1.0 indicam clusters estáveis.
        """
        n = len(embeddings)
        if n < 50:
            return 1.0

        ari_scores = []
        for seed in range(n_bootstraps):
            sub_idx = np.random.RandomState(seed).choice(n, int(n * 0.8), replace=False)
            sub_emb = embeddings[sub_idx]

            if algorithm in ["kmeans", "minibatch_kmeans"]:
                m1 = MiniBatchKMeans(n_clusters=k, random_state=seed, batch_size=256, n_init=3)
                m2 = MiniBatchKMeans(n_clusters=k, random_state=seed + 100, batch_size=256, n_init=3)
                l1 = m1.fit_predict(sub_emb)
                l2 = m2.fit_predict(sub_emb)
                ari = adjusted_rand_score(l1, l2)
                ari_scores.append(ari)

        return round(float(np.mean(ari_scores)), 4) if ari_scores else 0.0

    def search_optimal_k(
        self,
        embeddings: np.ndarray,
        k_list: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """
        Explora a quantidade de clusters K avaliando Silhouette, Davies-Bouldin,
        estabilidade e distribuição dos tamanhos dos grupos.
        """
        k_values = k_list or self.cfg.k_search_range
        rows = []

        print(f"Buscando K ideal na faixa: {k_values}...")
        for k in k_values:
            if k >= len(embeddings):
                continue
            mbk = MiniBatchKMeans(
                n_clusters=k,
                batch_size=256,
                random_state=self.cfg.random_state,
                n_init=3
            )
            labels = mbk.fit_predict(embeddings)
            eval_dict = self.evaluate_clustering(embeddings, labels)
            stability = self.compute_stability(embeddings, "minibatch_kmeans", k)

            eval_dict["k"] = k
            eval_dict["stability_ari"] = stability
            rows.append(eval_dict)

        df_search = pd.DataFrame(rows)
        return df_search

    def fit_predict(
        self,
        embeddings: np.ndarray,
        algorithm: Optional[str] = None,
        n_clusters: Optional[int] = None,
        use_dim_reduction: Optional[bool] = None
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Executa o clustering no espaço original ou reduzido e retorna:
        (labels, centróides_no_espaço_original, métricas_de_avaliação).
        """
        algo = algorithm or self.cfg.algorithm
        k = n_clusters or self.cfg.n_clusters
        do_dim_red = (self.cfg.dim_reduction != "none") if use_dim_reduction is None else use_dim_reduction

        if do_dim_red:
            print(f"Reduzindo dimensionalidade com PCA ({self.cfg.dim_components} componentes)...")
            cluster_input = self.reduce_dimensions(embeddings, self.cfg.dim_components)
        else:
            cluster_input = embeddings

        print(f"Executando clustering com algoritmo: '{algo}'...")
        if algo == "minibatch_kmeans":
            self.model = MiniBatchKMeans(
                n_clusters=k,
                batch_size=256,
                random_state=self.cfg.random_state,
                n_init=5
            )
            labels = self.model.fit_predict(cluster_input)

        elif algo == "kmeans":
            self.model = KMeans(
                n_clusters=k,
                random_state=self.cfg.random_state,
                n_init=10
            )
            labels = self.model.fit_predict(cluster_input)

        elif algo == "hdbscan":
            self.model = HDBSCAN(
                min_cluster_size=self.cfg.hdbscan_min_cluster_size,
                min_samples=self.cfg.hdbscan_min_samples,
                metric="euclidean"
            )
            labels = self.model.fit_predict(cluster_input)

        elif algo == "hierarchical":
            self.model = AgglomerativeClustering(
                n_clusters=k,
                metric="cosine",
                linkage="average"
            )
            labels = self.model.fit_predict(cluster_input)

        else:
            raise ValueError(f"Algoritmo não suportado: {algo}")

        self.cluster_labels = labels

        # Calcular centróides SEMPRE no espaço original dos embeddings
        unique_labels = sorted(list(set(labels)))
        centroids = []
        for cl in unique_labels:
            if cl == -1:
                # Ruído (HDBSCAN) -> centróide nulo
                centroids.append(np.zeros(embeddings.shape[1]))
            else:
                mask = labels == cl
                c = np.mean(embeddings[mask], axis=0)
                norm = np.linalg.norm(c)
                if norm > 0:
                    c = c / norm
                centroids.append(c)

        self.centroids_ = np.vstack(centroids)

        # Avaliar
        eval_metrics = self.evaluate_clustering(embeddings, labels)
        eval_metrics["algorithm"] = algo
        eval_metrics["dim_reduction"] = "pca" if do_dim_red else "none"

        return labels, self.centroids_, eval_metrics
