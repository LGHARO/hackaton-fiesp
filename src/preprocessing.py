"""
Módulo de pré-processamento de dados de operações, NCMs e CNAEs.
Validação de schemas, tratamento de valores ausentes, normalização de textos
e geração da representação canônica textual.
"""
import os
import re
import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict
from src.config import PreprocessingConfig, DataConfig

def clean_technical_text(text: str) -> str:
    """
    Normaliza textos preservando termos técnicos, modelos, materiais,
    dimensões, códigos de peças e unidades de medida.
    """
    if pd.isna(text) or not str(text).strip():
        return "NÃO INFORMADO"
    
    text = str(text)
    # Substituir quebras de linha e tabs por espaço
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # Uniformizar separadores mantendo hífens, barras e pontos em códigos técnicos (ex: 6205-2RS, 1/2", 10.5MM)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().upper()

def format_ncm_code(code: any) -> str:
    """Padroniza código NCM para 8 dígitos numéricos com zero à esquerda se necessário."""
    if pd.isna(code):
        return "00000000"
    digits = re.sub(r'\D', '', str(code))
    return digits.zfill(8)

def format_cnae_code(code: any) -> str:
    """Padroniza código CNAE de classe para o formato oficial XX.XX-X."""
    if pd.isna(code):
        return ""
    digits = re.sub(r'\D', '', str(code))
    if len(digits) >= 5:
        d5 = digits[:5]
        return f"{d5[:2]}.{d5[2:4]}-{d5[4]}"
    return str(code).strip()

class DataPreprocessor:
    def __init__(self, data_cfg: DataConfig, prep_cfg: PreprocessingConfig):
        self.data_cfg = data_cfg
        self.prep_cfg = prep_cfg

    def load_ncm_reference(self) -> pd.DataFrame:
        """Carrega e padroniza tabela oficial de NCMs."""
        ncm_path = self.data_cfg.ncm_file
        if not os.path.exists(ncm_path):
            raise FileNotFoundError(f"Arquivo NCM não encontrado: {ncm_path}")

        df_ncm = pd.read_csv(
            ncm_path,
            dtype=str,
            usecols=lambda col: col in ["id_ncm", "nome_ncm_portugues", "id_sh6", "nome_unidade"]
        )
        df_ncm["id_ncm"] = df_ncm["id_ncm"].apply(format_ncm_code)
        df_ncm["nome_ncm_portugues"] = df_ncm["nome_ncm_portugues"].fillna("DESCRIÇÃO NÃO DISPONÍVEL").str.strip()
        # Deduplicar por id_ncm
        df_ncm = df_ncm.drop_duplicates(subset=["id_ncm"]).reset_index(drop=True)
        return df_ncm

    def load_cnae_reference(self) -> pd.DataFrame:
        """Carrega tabela de referência de CNAEs."""
        cnae_path = self.data_cfg.cnae_file
        if not os.path.exists(cnae_path):
            raise FileNotFoundError(f"Arquivo CNAE de referência não encontrado: {cnae_path}")

        df_cnae = pd.read_csv(cnae_path, dtype=str)
        df_cnae["cnae_codigo"] = df_cnae["cnae_codigo"].apply(format_cnae_code)
        return df_cnae

    def process_operations(self) -> pd.DataFrame:
        """
        Carrega, valida, une com NCM e constrói a representação canônica
        das operações de importação.
        """
        ops_path = self.data_cfg.operations_file
        if not os.path.exists(ops_path):
            raise FileNotFoundError(f"Arquivo de operações não encontrado: {ops_path}")

        if ops_path.endswith(".parquet") or ops_path.endswith(".pq"):
            df_ops = pd.read_parquet(ops_path)
        else:
            df_ops = pd.read_csv(ops_path, dtype={"numero_de_ordem": str, "cod_ncm": str, "anomes": str})
        
        # Validar colunas obrigatórias
        required = ["numero_de_ordem", "anomes", "cod_ncm", "pais_de_origem", "descricao_do_produto", "peso_liquido", "vmle_dolar"]
        for col in required:
            if col not in df_ops.columns:
                raise ValueError(f"Coluna obrigatória ausente na base de operações: {col}")

        # Limitar amostra se especificado no config
        if self.prep_cfg.sample_size and len(df_ops) > self.prep_cfg.sample_size:
            df_ops = df_ops.sample(n=self.prep_cfg.sample_size, random_state=42).reset_index(drop=True)

        # Tratar tipos e valores ausentes
        df_ops["numero_de_ordem"] = df_ops["numero_de_ordem"].fillna("OP_DESCONHECIDA").astype(str).str.strip()
        df_ops["cod_ncm"] = df_ops["cod_ncm"].apply(format_ncm_code)
        df_ops["descricao_do_produto"] = df_ops["descricao_do_produto"].apply(clean_technical_text)
        df_ops["pais_de_origem"] = df_ops["pais_de_origem"].fillna("NÃO INFORMADO").astype(str).str.strip().str.upper()
        df_ops["anomes"] = df_ops["anomes"].fillna("NÃO INFORMADO").astype(str).str.strip()
        
        # Numéricos
        df_ops["peso_liquido"] = pd.to_numeric(df_ops["peso_liquido"], errors="coerce").fillna(0.0)
        df_ops["vmle_dolar"] = pd.to_numeric(df_ops["vmle_dolar"], errors="coerce").fillna(0.0)

        # Merge com tabela oficial NCM
        df_ncm = self.load_ncm_reference()
        df_merged = df_ops.merge(
            df_ncm[["id_ncm", "nome_ncm_portugues"]],
            left_on="cod_ncm",
            right_on="id_ncm",
            how="left"
        )
        df_merged["descricao_ncm"] = df_merged["nome_ncm_portugues"].fillna("SEM DESCRIÇÃO OFICIAL NCM")
        df_merged = df_merged.drop(columns=["id_ncm", "nome_ncm_portugues"], errors="ignore")

        # Construir representação canônica
        # Template: NCM: {cod_ncm}. Descrição oficial do NCM: {descricao_ncm}. Produto: {descricao_do_produto}.
        def build_repr(row):
            return self.prep_cfg.text_template.format(
                cod_ncm=row["cod_ncm"],
                descricao_ncm=row["descricao_ncm"],
                descricao_do_produto=row["descricao_do_produto"]
            )

        df_merged["texto_representacao"] = df_merged.apply(build_repr, axis=1)

        # Salvar em Parquet para alta performance
        os.makedirs(self.data_cfg.processed_dir, exist_ok=True)
        out_parquet = os.path.join(self.data_cfg.processed_dir, "operacoes_processadas.parquet")
        df_merged.to_parquet(out_parquet, index=False)
        print(f"Operações pré-processadas e salvas em: {out_parquet} ({len(df_merged)} linhas)")

        return df_merged

if __name__ == "__main__":
    from src.config import PipelineConfig
    cfg = PipelineConfig()
    prep = DataPreprocessor(cfg.data, cfg.preprocessing)
    prep.process_operations()
