"""
Gerenciamento de configurações e hiperparâmetros do pipeline.
"""
import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class DataConfig:
    operations_file: str = "data/raw/operacoes_sample.csv"
    companies_file: str = "dados_tabela_exportacoes_importacoes.csv"
    ncm_file: str = "br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv"
    cnae_file: str = "data/reference/cnae_referencia.csv"
    processed_dir: str = "data/processed"
    output_dir: str = "outputs"

@dataclass
class PreprocessingConfig:
    sample_size: Optional[int] = None
    text_template: str = "NCM: {cod_ncm}. Descrição oficial do NCM: {descricao_ncm}. Produto: {descricao_do_produto}."
    fill_missing_str: str = "NÃO INFORMADO"

@dataclass
class BaselineConfig:
    top_k_cnae: int = 5
    word_ngram_range: tuple = (1, 2)
    char_ngram_range: tuple = (3, 5)
    word_max_features: int = 25000
    char_max_features: int = 35000
    weight_word: float = 0.5
    weight_char: float = 0.5

@dataclass
class EmbeddingsConfig:
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    batch_size: int = 64
    normalize_embeddings: bool = True
    device: str = "auto"
    cache_embeddings: bool = True

@dataclass
class ClusteringConfig:
    algorithm: str = "minibatch_kmeans"
    n_clusters: int = 20
    k_search_range: List[int] = field(default_factory=lambda: [5, 10, 15, 20, 30, 40])
    hdbscan_min_cluster_size: int = 15
    hdbscan_min_samples: int = 5
    random_state: int = 42
    dim_reduction: str = "none"
    dim_components: int = 32

@dataclass
class AssociationConfig:
    top_k_cnae: int = 5
    weight_op_sim: float = 0.55
    weight_cluster_sim: float = 0.35
    weight_ncm_compat: float = 0.10

@dataclass
class RetrievalConfig:
    top_k_cnpjs: int = 10
    prioritize_active: bool = True
    primary_cnae_score: float = 1.0
    secondary_cnae_score: float = 0.8
    max_candidates_per_op: int = 25

@dataclass
class PipelineConfig:
    data: DataConfig = field(default_factory=DataConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    association: AssociationConfig = field(default_factory=AssociationConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "PipelineConfig":
        if not os.path.exists(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        cfg = cls()
        if "data" in raw:
            for k, v in raw["data"].items():
                if hasattr(cfg.data, k):
                    setattr(cfg.data, k, v)
        if "preprocessing" in raw:
            for k, v in raw["preprocessing"].items():
                if hasattr(cfg.preprocessing, k):
                    setattr(cfg.preprocessing, k, v)
        if "baseline" in raw:
            for k, v in raw["baseline"].items():
                if k.endswith("_ngram_range") and isinstance(v, list):
                    v = tuple(v)
                if hasattr(cfg.baseline, k):
                    setattr(cfg.baseline, k, v)
        if "embeddings" in raw:
            for k, v in raw["embeddings"].items():
                if hasattr(cfg.embeddings, k):
                    setattr(cfg.embeddings, k, v)
        if "clustering" in raw:
            for k, v in raw["clustering"].items():
                if hasattr(cfg.clustering, k):
                    setattr(cfg.clustering, k, v)
        if "association" in raw:
            for k, v in raw["association"].items():
                if hasattr(cfg.association, k):
                    setattr(cfg.association, k, v)
        if "retrieval" in raw:
            for k, v in raw["retrieval"].items():
                if hasattr(cfg.retrieval, k):
                    setattr(cfg.retrieval, k, v)
        return cfg
