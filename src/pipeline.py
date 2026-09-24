"""
Pipeline Principal Integrado: Orquestração reproduzível de ponta a ponta.
Executa pré-processamento, baseline TF-IDF, embeddings neurais locais, clustering,
associação CNAE, recuperação de CNPJs e avaliação estatística.
"""
import os
import time
from typing import Tuple, Dict, Any, Optional
import pandas as pd
import numpy as np
from src.config import PipelineConfig
from src.preprocessing import DataPreprocessor
from src.baseline import TFIDFBaseline
from src.embeddings import LocalEmbeddingManager
from src.clustering import OperationsClusterer
from src.association import CNAEAssociator
from src.retrieval import CNPJRetriever
from src.evaluation import PipelineEvaluator

class ImportOpsPipeline:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.cfg = PipelineConfig.from_yaml(config_path)
        self.preprocessor = DataPreprocessor(self.cfg.data, self.cfg.preprocessing)
        self.baseline = TFIDFBaseline(self.cfg.baseline)
        self.embed_manager = LocalEmbeddingManager(self.cfg.embeddings, cache_dir=self.cfg.data.processed_dir)
        self.clusterer = OperationsClusterer(self.cfg.clustering)
        self.associator = CNAEAssociator(self.cfg.association)
        self.retriever = CNPJRetriever(self.cfg.data, self.cfg.retrieval)
        self.evaluator = PipelineEvaluator(self.cfg.data.output_dir)

        # Estados em memória
        self.df_ops = None
        self.df_cnae = None
        self.df_ncm = None
        self.op_embeddings = None
        self.cnae_embeddings = None
        self.cluster_labels = None
        self.centroids = None
        self.cluster_metrics = None
        self.df_associations = None
        self.df_final_results = None

    def step_preprocess(self) -> pd.DataFrame:
        print("\n" + "="*50)
        print("ETAPA 1: Pré-processamento e Validação de Schemas")
        print("="*50)
        self.df_cnae = self.preprocessor.load_cnae_reference()
        self.df_ncm = self.preprocessor.load_ncm_reference()
        self.df_ops = self.preprocessor.process_operations()
        return self.df_ops

    def step_baseline(self) -> pd.DataFrame:
        print("\n" + "="*50)
        print("ETAPA 2: Baseline Interpretável (TF-IDF Palavras + Caracteres)")
        print("="*50)
        if self.df_ops is None or self.df_cnae is None:
            self.step_preprocess()

        self.baseline.fit_cnaes(self.df_cnae)
        df_base_preds = self.baseline.predict_top_k(self.df_ops)

        out_path = os.path.join(self.cfg.data.output_dir, "baseline_cnae_predictions.csv")
        df_base_preds.to_csv(out_path, index=False, encoding="utf-8")
        print(f"Predições do Baseline salvas em: {out_path} ({len(df_base_preds)} linhas)")
        return df_base_preds

    def step_embeddings(self, force: bool = False):
        print("\n" + "="*50)
        print("ETAPA 3: Embeddings Semânticos Densos Locais")
        print("="*50)
        if self.df_ops is None or self.df_cnae is None:
            self.step_preprocess()

        self.op_embeddings = self.embed_manager.embed_operations(self.df_ops, force_recompute=force)
        self.cnae_embeddings = self.embed_manager.embed_cnaes(self.df_cnae, force_recompute=force)
        print(f"Embeddings de operações: shape {self.op_embeddings.shape}")
        print(f"Embeddings de CNAEs: shape {self.cnae_embeddings.shape}")

    def step_clustering(self) -> Tuple[np.ndarray, np.ndarray, dict]:
        print("\n" + "="*50)
        print("ETAPA 4: Agrupamento Não Supervisionado (Clustering)")
        print("="*50)
        if self.op_embeddings is None:
            self.step_embeddings()

        # Busca comparativa do K ideal se K-Means
        if self.cfg.clustering.algorithm in ["kmeans", "minibatch_kmeans"]:
            df_k_search = self.clusterer.search_optimal_k(self.op_embeddings)
            k_search_path = os.path.join(self.cfg.data.output_dir, "k_search_clustering_metrics.csv")
            df_k_search.to_csv(k_search_path, index=False, encoding="utf-8")
            print(f"Busca de K ideal salva em: {k_search_path}")

        # Executar clustering no espaço original
        labels_orig, centroids_orig, metrics_orig = self.clusterer.fit_predict(
            self.op_embeddings,
            use_dim_reduction=False
        )

        # Executar clustering comparativo no espaço reduzido (PCA)
        _, _, metrics_pca = self.clusterer.fit_predict(
            self.op_embeddings,
            use_dim_reduction=True
        )

        print("\nComparativo de Espaço Original vs Reduzido:")
        print(f"  Espaço Original: Silhouette={metrics_orig.get('silhouette')}, Davies-Bouldin={metrics_orig.get('davies_bouldin')}")
        print(f"  Espaço Reduzido (PCA): Silhouette={metrics_pca.get('silhouette')}, Davies-Bouldin={metrics_pca.get('davies_bouldin')}")

        self.cluster_labels = labels_orig
        self.centroids = centroids_orig
        self.cluster_metrics = metrics_orig
        return labels_orig, centroids_orig, metrics_orig

    def step_association(self) -> pd.DataFrame:
        print("\n" + "="*50)
        print("ETAPA 5: Associação Operações/Clusters -> CNAEs Oficiais")
        print("="*50)
        if self.cluster_labels is None:
            self.step_clustering()

        self.df_associations = self.associator.associate(
            df_ops=self.df_ops,
            op_embeddings=self.op_embeddings,
            cluster_labels=self.cluster_labels,
            centroids=self.centroids,
            df_cnae=self.df_cnae,
            cnae_embeddings=self.cnae_embeddings,
            df_ncm=self.df_ncm
        )

        assoc_path = os.path.join(self.cfg.data.output_dir, "associacoes_operacoes_cnae.csv")
        self.df_associations.to_csv(assoc_path, index=False, encoding="utf-8")
        print(f"Associações com CNAEs salvas em: {assoc_path} ({len(self.df_associations)} linhas)")
        return self.df_associations

    def step_retrieval(self) -> pd.DataFrame:
        print("\n" + "="*50)
        print("ETAPA 6: Recuperação de CNPJs na Base Pública")
        print("="*50)
        if self.df_associations is None:
            self.step_association()

        self.df_final_results = self.retriever.retrieve_candidates(self.df_associations)
        
        # Salvar em CSV e Parquet
        csv_path = os.path.join(self.cfg.data.output_dir, "candidatos_cnpjs_finais.csv")
        parquet_path = os.path.join(self.cfg.data.output_dir, "candidatos_cnpjs_finais.parquet")

        self.df_final_results.to_csv(csv_path, index=False, encoding="utf-8")
        self.df_final_results.to_parquet(parquet_path, index=False)
        print(f"Ranking final de candidatos gerado com sucesso!")
        print(f"  CSV: {csv_path}")
        print(f"  Parquet: {parquet_path}")
        print(f"  Total de linhas geradas: {len(self.df_final_results)}")
        return self.df_final_results

    def step_evaluation(self) -> dict:
        print("\n" + "="*50)
        print("ETAPA 7: Avaliação Estatística, Métricas e Amostra de Auditoria")
        print("="*50)
        if self.df_final_results is None:
            self.step_retrieval()

        eval_summary = self.evaluator.evaluate_unsupervised(
            df_ops=self.df_ops,
            cluster_metrics=self.cluster_metrics,
            df_associations=self.df_associations,
            df_cnae=self.df_cnae
        )
        self.evaluator.generate_inspection_sample(
            df_ops=self.df_ops,
            df_final_results=self.df_final_results,
            n_samples=20
        )
        return eval_summary

    def run_all(self, force: bool = False):
        t0 = time.time()
        print("Iniciando Execução Completa do Pipeline...")
        self.step_preprocess()
        self.step_baseline()
        self.step_embeddings(force=force)
        self.step_clustering()
        self.step_association()
        self.step_retrieval()
        self.step_evaluation()
        elapsed = round(time.time() - t0, 2)
        print("\n" + "="*50)
        print(f"Pipeline concluído com sucesso em {elapsed} segundos!")
        print("="*50)
