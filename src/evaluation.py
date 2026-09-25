"""
Módulo de Avaliação de Desempenho e Qualidade do Pipeline.
Implementa métricas intrínsecas (sem rótulos):
- Qualidade e separabilidade dos clusters
- Coerência setorial NCM-CNAE
- Estabilidade e cobertura
- Amostragem estratificada para inspeção manual
E métricas supervisionadas (quando houver amostra rotulada):
- Recall@K, Precision@K, MRR, acurácia Top-K
- Divisão temporal e por grupos (evitando vazamento de dados / data leakage).
"""
import os
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple

def compute_retrieval_metrics(
    predictions_df: pd.DataFrame,
    ground_truth_df: pd.DataFrame,
    id_col: str = "numero_de_ordem",
    target_col: str = "cnae_candidato",
    true_target_col: str = "cnae_verdadeiro",
    k_list: List[int] = [1, 3, 5, 10]
) -> Dict[str, float]:
    """
    Calcula Recall@K, Precision@K e Mean Reciprocal Rank (MRR)
    para avaliação de recuperação quando houver dados rotulados.
    """
    merged = predictions_df.merge(ground_truth_df[[id_col, true_target_col]], on=id_col, how="inner")
    if merged.empty:
        return {"aviso": "Nenhum par de teste correspondente encontrado na base rotulada."}

    grouped = merged.groupby(id_col)
    n_queries = len(grouped)

    recalls = {k: 0.0 for k in k_list}
    precisions = {k: 0.0 for k in k_list}
    rr_total = 0.0

    for op_id, group in grouped:
        group_sorted = group.sort_values("ranking_cnae")
        true_val = str(group[true_target_col].iloc[0]).strip()
        candidates = [str(c).strip() for c in group_sorted[target_col].tolist()]

        # Reciprocal Rank
        found_rank = None
        for r, cand in enumerate(candidates, start=1):
            if cand == true_val:
                found_rank = r
                break

        if found_rank is not None:
            rr_total += 1.0 / found_rank

        # Top-K
        for k in k_list:
            top_k_cands = candidates[:k]
            if true_val in top_k_cands:
                recalls[k] += 1.0
                precisions[k] += 1.0 / k

    results = {
        "num_avaliados": n_queries,
        "mrr": round(rr_total / n_queries, 4)
    }
    for k in k_list:
        results[f"recall@{k}"] = round(recalls[k] / n_queries, 4)
        results[f"precision@{k}"] = round(precisions[k] / n_queries, 4)

    return results

class PipelineEvaluator:
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def evaluate_unsupervised(
        self,
        df_ops: pd.DataFrame,
        cluster_metrics: Dict[str, Any],
        df_associations: pd.DataFrame,
        df_cnae: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Executa avaliação intrínseca abrangente quando não há rótulos de verdade de campo.
        """
        # 1. Cobertura de CNAEs recuperados
        total_cnaes_ref = len(df_cnae)
        unique_retrieved_cnaes = df_associations["cnae_candidato"].nunique()
        coverage_pct = round((unique_retrieved_cnaes / total_cnaes_ref) * 100.0, 2)

        # 2. Coerência estrutural NCM-CNAE no Top-1
        top1_assoc = df_associations[df_associations["ranking_cnae"] == 1]
        coerencia_taxa = float((top1_assoc["compatibilidade_ncm_cnae"] > 0).mean())

        # 3. Estatísticas dos scores
        scores = top1_assoc["score_cnae_combinado"].values
        score_mean = float(np.mean(scores))
        score_std = float(np.std(scores))
        score_min = float(np.min(scores))
        score_max = float(np.max(scores))

        summary = {
            "clustering": cluster_metrics,
            "cobertura_cnae": {
                "total_cnaes_oficiais": total_cnaes_ref,
                "cnaes_distintos_recuperados": unique_retrieved_cnaes,
                "cobertura_percentual": f"{coverage_pct}%"
            },
            "coerencia_ncm_cnae": {
                "taxa_coerencia_top1": round(coerencia_taxa, 4),
                "descricao": "Fração de operações cujo Top-1 CNAE converge no nível setorial (ISIC) do NCM"
            },
            "distribuicao_scores_top1": {
                "media": round(score_mean, 4),
                "desvio_padrao": round(score_std, 4),
                "minimo": round(score_min, 4),
                "maximo": round(score_max, 4)
            }
        }

        # Salvar relatório em JSON
        report_path = os.path.join(self.output_dir, "relatorio_avaliacao_intrinseca.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"Relatório de avaliação intrínseca salvo em: {report_path}")

        return summary

    def generate_inspection_sample(
        self,
        df_ops: pd.DataFrame,
        df_final_results: pd.DataFrame,
        n_samples: int = 15
    ) -> pd.DataFrame:
        """
        Gera amostra legível para auditoria manual de coerência semântica
        com operação, NCM, descrição do produto, candidatos CNAE e CNPJs associados.
        """
        sample_ops = df_ops["numero_de_ordem"].drop_duplicates().sample(
            min(n_samples, df_ops["numero_de_ordem"].nunique()),
            random_state=42
        )
        sample_results = df_final_results[df_final_results["numero_de_ordem"].isin(sample_ops)].copy()
        
        # Merge com detalhes do produto para visualização amigável
        sample_enriched = sample_results.merge(
            df_ops[["numero_de_ordem", "cod_ncm", "descricao_do_produto", "descricao_ncm"]],
            on="numero_de_ordem",
            how="left"
        )

        out_csv = os.path.join(self.output_dir, "amostra_inspecao_manual.csv")
        sample_enriched.to_csv(out_csv, index=False, encoding="utf-8")
        print(f"Amostra para auditoria manual gerada em: {out_csv} ({len(sample_enriched)} registros)")
        return sample_enriched

    @staticmethod
    def train_test_split_anti_leakage(
        df_ops: pd.DataFrame,
        split_by: str = "anomes",
        test_ratio: float = 0.2
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Separa operações entre treino e teste evitando vazamento de dados (data leakage):
        - Separação Temporal: operações anteriores para treino, posteriores para teste;
        - Separação por Grupo NCM: famílias de produtos mantidas exclusivamente em um dos lados.
        """
        if split_by == "anomes" and "anomes" in df_ops.columns:
            sorted_months = sorted(df_ops["anomes"].dropna().unique())
            split_idx = int(len(sorted_months) * (1.0 - test_ratio))
            train_months = sorted_months[:split_idx]
            test_months = sorted_months[split_idx:]
            train_df = df_ops[df_ops["anomes"].isin(train_months)].copy()
            test_df = df_ops[df_ops["anomes"].isin(test_months)].copy()
            return train_df, test_df
        else:
            # Separação por código NCM (grupos de 4 dígitos do Sistema Harmonizado SH4)
            sh4 = df_ops["cod_ncm"].str[:4].unique()
            np.random.seed(42)
            np.random.shuffle(sh4)
            split_idx = int(len(sh4) * (1.0 - test_ratio))
            train_sh4 = set(sh4[:split_idx])
            train_df = df_ops[df_ops["cod_ncm"].str[:4].isin(train_sh4)].copy()
            test_df = df_ops[~df_ops["cod_ncm"].str[:4].isin(train_sh4)].copy()
            return train_df, test_df
