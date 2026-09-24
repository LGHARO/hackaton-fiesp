"""
Módulo de Baseline: TF-IDF de palavras + TF-IDF de caracteres (char-wb) + similaridade de cosseno.
Fornece um método rápido, reproduzível, leve e altamente interpretável para associar
operações aos CNAEs oficiais sem necessidade de redes neurais.
"""
import os
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from src.config import BaselineConfig

class TFIDFBaseline:
    def __init__(self, cfg: BaselineConfig):
        self.cfg = cfg
        # Vetorizador de palavras (unigramas e bigramas)
        self.word_vec = TfidfVectorizer(
            ngram_range=self.cfg.word_ngram_range,
            max_features=self.cfg.word_max_features,
            sublinear_tf=True,
            strip_accents="unicode",
            lowercase=True
        )
        # Vetorizador de caracteres dentro de limites de palavras (captura raízes, prefixos técnicos e variações morfológicas)
        self.char_vec = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=self.cfg.char_ngram_range,
            max_features=self.cfg.char_max_features,
            sublinear_tf=True,
            strip_accents="unicode",
            lowercase=True
        )
        self.cnae_df: Optional[pd.DataFrame] = None
        self.cnae_word_matrix = None
        self.cnae_char_matrix = None

    def fit_cnaes(self, cnae_df: pd.DataFrame):
        """
        Ajusta os vetorizadores TF-IDF sobre a representação textual oficial dos CNAEs
        (descrição, grupo, divisão, atividades compreendidas e notas explicativas).
        """
        self.cnae_df = cnae_df.reset_index(drop=True)
        cnae_texts = self.cnae_df["texto_representacao"].fillna("").tolist()

        print(f"Treinando TF-IDF de palavras em {len(cnae_texts)} CNAEs...")
        self.cnae_word_matrix = self.word_vec.fit_transform(cnae_texts)

        print(f"Treinando TF-IDF de caracteres em {len(cnae_texts)} CNAEs...")
        self.cnae_char_matrix = self.char_vec.fit_transform(cnae_texts)
        print("Modelos TF-IDF ajustados com sucesso.")

    def predict_top_k(
        self,
        operations_df: pd.DataFrame,
        top_k: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Para cada operação, calcula a similaridade combinada (palavras + caracteres)
        contra todos os CNAEs oficiais e retorna os Top-K candidatos.
        """
        if self.cnae_word_matrix is None or self.cnae_char_matrix is None:
            raise ValueError("O baseline precisa ser ajustado com fit_cnaes() antes de predizer.")

        k = top_k or self.cfg.top_k_cnae
        op_texts = operations_df["texto_representacao"].fillna("").tolist()

        # Vetorizar operações
        op_word_matrix = self.word_vec.transform(op_texts)
        op_char_matrix = self.char_vec.transform(op_texts)

        # Similaridades de cosseno esparsas
        sim_word = cosine_similarity(op_word_matrix, self.cnae_word_matrix)
        sim_char = cosine_similarity(op_char_matrix, self.cnae_char_matrix)

        # Combinação ponderada
        sim_combined = (self.cfg.weight_word * sim_word) + (self.cfg.weight_char * sim_char)

        results = []
        cnae_codes = self.cnae_df["cnae_codigo"].values
        cnae_descs = self.cnae_df["descricao_cnae"].values

        for idx, row in operations_df.iterrows():
            op_scores = sim_combined[idx]
            # Obter os índices dos top-k maiores scores
            top_indices = np.argsort(op_scores)[::-1][:k]

            for rank, cnae_idx in enumerate(top_indices, start=1):
                results.append({
                    "numero_de_ordem": row["numero_de_ordem"],
                    "cod_ncm": row["cod_ncm"],
                    "ranking_cnae": rank,
                    "cnae_candidato": cnae_codes[cnae_idx],
                    "descricao_cnae": cnae_descs[cnae_idx],
                    "score_tfidf_combinado": float(op_scores[cnae_idx]),
                    "score_tfidf_palavras": float(sim_word[idx, cnae_idx]),
                    "score_tfidf_caracteres": float(sim_char[idx, cnae_idx])
                })

        return pd.DataFrame(results)

    def explain_match(self, op_text: str, cnae_idx: int, top_terms: int = 5) -> List[Tuple[str, float]]:
        """
        Interpretabilidade: identifica os termos que mais contribuíram
        para a similaridade entre uma operação e um CNAE específico.
        """
        op_vec = self.word_vec.transform([op_text])
        cnae_vec = self.cnae_word_matrix[cnae_idx]
        
        # Element-wise product of TF-IDF weights
        mult = op_vec.multiply(cnae_vec).toarray()[0]
        nonzero_idx = np.where(mult > 0)[0]
        
        feature_names = np.array(self.word_vec.get_feature_names_out())
        top_sub_idx = nonzero_idx[np.argsort(mult[nonzero_idx])[::-1][:top_terms]]
        
        return [(feature_names[i], float(mult[i])) for i in top_sub_idx]
