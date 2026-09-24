"""
Módulo de geração e persistência de embeddings densos semânticos locais.
Utiliza modelos SentenceTransformers compatíveis com português, com inferência em lotes,
normalização L2 e cache persistente em disco (.npy e metadados).
"""
import os
import json
import numpy as np
import pandas as pd
from typing import List, Optional, Tuple
from src.config import EmbeddingsConfig

class LocalEmbeddingManager:
    def __init__(self, cfg: EmbeddingsConfig, cache_dir: str = "data/processed"):
        self.cfg = cfg
        self.cache_dir = cache_dir
        self.model = None
        self._device = None

    def _load_model(self):
        """Carrega preguiçosamente (lazy load) o modelo sentence-transformers."""
        if self.model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            if self.cfg.device == "auto":
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self._device = self.cfg.device

            print(f"Carregando modelo de embeddings '{self.cfg.model_name}' no dispositivo '{self._device}'...")
            try:
                self.model = SentenceTransformer(self.cfg.model_name, device=self._device, local_files_only=True)
            except Exception:
                self.model = SentenceTransformer(self.cfg.model_name, device=self._device)
            print("Modelo de embeddings carregado com sucesso.")

    def _get_cache_path(self, prefix: str) -> Tuple[str, str]:
        npy_path = os.path.join(self.cache_dir, f"{prefix}_embeddings.npy")
        meta_path = os.path.join(self.cache_dir, f"{prefix}_metadata.json")
        return npy_path, meta_path

    def compute_or_load(
        self,
        texts: List[str],
        ids: List[str],
        prefix: str,
        force_recompute: bool = False
    ) -> np.ndarray:
        """
        Calcula embeddings em lote ou carrega do cache se o hash/tamanho bater.
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        npy_path, meta_path = self._get_cache_path(prefix)

        # Checar cache se permitido e não forçado
        if self.cfg.cache_embeddings and not force_recompute:
            if os.path.exists(npy_path) and os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if meta.get("count") == len(texts) and meta.get("model") == self.cfg.model_name:
                        print(f"Carregando {len(texts)} embeddings em cache de: {npy_path}")
                        return np.load(npy_path)
                except Exception as e:
                    print(f"Aviso ao ler cache ({e}). Recalculando embeddings...")

        # Carregar modelo e inferir
        self._load_model()
        print(f"Calculando embeddings para {len(texts)} itens ({prefix})...")
        
        embeddings = self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            show_progress_bar=True,
            normalize_embeddings=self.cfg.normalize_embeddings,
            convert_to_numpy=True
        )

        # Salvar em cache
        if self.cfg.cache_embeddings:
            np.save(npy_path, embeddings)
            metadata = {
                "prefix": prefix,
                "count": len(texts),
                "model": self.cfg.model_name,
                "dimension": int(embeddings.shape[1]),
                "normalized": self.cfg.normalize_embeddings,
                "ids_sample": ids[:10]
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            print(f"Embeddings salvos com sucesso em: {npy_path}")

        return embeddings

    def embed_operations(self, df_ops: pd.DataFrame, force_recompute: bool = False) -> np.ndarray:
        """Gera embeddings para o texto canônico de representação das operações."""
        texts = df_ops["texto_representacao"].fillna("").tolist()
        ids = df_ops["numero_de_ordem"].tolist()
        return self.compute_or_load(texts, ids, prefix="operacoes", force_recompute=force_recompute)

    def embed_cnaes(self, df_cnae: pd.DataFrame, force_recompute: bool = False) -> np.ndarray:
        """Gera embeddings para as descrições oficiais e notas explicativas dos CNAEs."""
        texts = df_cnae["texto_representacao"].fillna("").tolist()
        ids = df_cnae["cnae_codigo"].tolist()
        return self.compute_or_load(texts, ids, prefix="cnaes", force_recompute=force_recompute)

    def embed_ncms(self, df_ncm: pd.DataFrame, force_recompute: bool = False) -> np.ndarray:
        """Gera embeddings para as descrições oficiais dos NCMs."""
        texts = [f"NCM: {row['id_ncm']}. Descrição: {row['nome_ncm_portugues']}" for _, row in df_ncm.iterrows()]
        ids = df_ncm["id_ncm"].tolist()
        return self.compute_or_load(texts, ids, prefix="ncms", force_recompute=force_recompute)
