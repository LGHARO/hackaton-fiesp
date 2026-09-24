"""
Testes unitários e de integração para validar a integridade dos módulos do pipeline.
"""
import unittest
import numpy as np
import pandas as pd
from src.preprocessing import clean_technical_text, format_ncm_code, format_cnae_code
from src.config import BaselineConfig, ClusteringConfig, AssociationConfig
from src.baseline import TFIDFBaseline
from src.clustering import OperationsClusterer
from src.association import CNAEAssociator

class TestImportPipeline(unittest.TestCase):

    def test_text_cleaning_and_formatting(self):
        # Preservação de termos técnicos, modelos, dimensões
        raw = "Válvula de esfera DN50 2'' Inox 316 / Ref: 6205-2RS \n 120V "
        cleaned = clean_technical_text(raw)
        self.assertIn("DN50", cleaned)
        self.assertIn("INOX 316", cleaned)
        self.assertIn("6205-2RS", cleaned)
        self.assertIn("120V", cleaned)

        # NCM code padding
        self.assertEqual(format_ncm_code("1021090"), "01021090")
        self.assertEqual(format_ncm_code(84818099), "84818099")

        # CNAE code formatting
        self.assertEqual(format_cnae_code("46494"), "46.49-4")
        self.assertEqual(format_cnae_code("46.49-4"), "46.49-4")

    def test_baseline_tfidf(self):
        cfg = BaselineConfig(top_k_cnae=2)
        baseline = TFIDFBaseline(cfg)

        df_cnae = pd.DataFrame([
            {"cnae_codigo": "46.63-0", "descricao_cnae": "Comércio de máquinas industriais", "texto_representacao": "CNAE: 46.63-0. Máquinas e equipamentos industriais válvulas bombas."},
            {"cnae_codigo": "01.11-3", "descricao_cnae": "Cultivo de cereais", "texto_representacao": "CNAE: 01.11-3. Agricultura sementes arroz milho grãos."}
        ])
        baseline.fit_cnaes(df_cnae)

        df_ops = pd.DataFrame([
            {
                "numero_de_ordem": "OP-1",
                "cod_ncm": "84818099",
                "texto_representacao": "NCM: 84818099. Descrição oficial: Válvulas. Produto: Válvula industrial para máquinas."
            }
        ])

        preds = baseline.predict_top_k(df_ops, top_k=1)
        self.assertEqual(len(preds), 1)
        # O top-1 deve ser máquinas industriais (46.63-0)
        self.assertEqual(preds.iloc[0]["cnae_candidato"], "46.63-0")
        self.assertGreater(preds.iloc[0]["score_tfidf_combinado"], 0.0)

    def test_clustering_metrics(self):
        cfg = ClusteringConfig(n_clusters=2, random_state=42)
        clusterer = OperationsClusterer(cfg)

        # Dados sintéticos com 2 grupos bem separados
        g1 = np.random.randn(20, 16) + 5.0
        g2 = np.random.randn(20, 16) - 5.0
        embeddings = np.vstack([g1, g2])
        # L2 norm
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        labels, centroids, metrics = clusterer.fit_predict(embeddings, algorithm="kmeans", n_clusters=2)
        self.assertEqual(len(labels), 40)
        self.assertEqual(len(centroids), 2)
        self.assertGreater(metrics["silhouette"], 0.5)
        self.assertIn("davies_bouldin", metrics)
        self.assertIn("size_entropy", metrics)

    def test_association_score_transparency(self):
        cfg = AssociationConfig(top_k_cnae=1, weight_op_sim=0.6, weight_cluster_sim=0.4, weight_ncm_compat=0.0)
        associator = CNAEAssociator(cfg)

        df_ops = pd.DataFrame([{"numero_de_ordem": "OP-99", "cod_ncm": "84818099"}])
        op_emb = np.array([[1.0, 0.0]])
        cluster_labels = np.array([0])
        centroids = np.array([[1.0, 0.0]])

        df_cnae = pd.DataFrame([{
            "cnae_codigo": "46.63-0",
            "descricao_cnae": "Comércio de máquinas",
            "cnae_id_numerico": "46630"
        }])
        cnae_emb = np.array([[1.0, 0.0]])

        df_res = associator.associate(df_ops, op_emb, cluster_labels, centroids, df_cnae, cnae_emb)
        self.assertEqual(len(df_res), 1)
        row = df_res.iloc[0]
        # Verificar que os scores estão separados
        self.assertAlmostEqual(row["similaridade_operacao_cnae"], 1.0)
        self.assertAlmostEqual(row["similaridade_cluster_cnae"], 1.0)
        self.assertAlmostEqual(row["score_cnae_combinado"], 1.0)

if __name__ == "__main__":
    unittest.main()
