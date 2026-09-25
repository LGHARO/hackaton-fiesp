"""
Esquemas de dados tipados para operações, empresas, NCM, CNAE e saídas do pipeline.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class OperacaoImportacao:
    numero_de_ordem: str
    anomes: str
    cod_ncm: str
    pais_de_origem: str
    descricao_do_produto: str
    peso_liquido: float
    vmle_dolar: float
    # Campos derivados
    descricao_ncm: Optional[str] = None
    texto_representacao: Optional[str] = None

@dataclass
class NCMReferencia:
    cod_ncm: str
    descricao_ncm: str

@dataclass
class CNAEReferencia:
    cnae_codigo: str
    cnae_id_numerico: str
    tipo: str
    descricao_cnae: str
    secao: str
    divisao: str
    grupo: str
    atividades: str
    notas_explicativas: str
    texto_representacao: str

@dataclass
class EmpresaCandidata:
    cnpj: str
    razao_social: str
    cnae_2_primaria: str
    sigla_uf: str
    id_municipio_nome: str
    tipo_cnae_empresa: str = "PRIMARIA"  # PRIMARIA ou SECUNDARIA
    situacao_cadastral: str = "ATIVA"

@dataclass
class CandidatoCNAE:
    cnae_codigo: str
    descricao_cnae: str
    ranking_cnae: int
    similaridade_operacao_cnae: float
    similaridade_cluster_cnae: float
    compatibilidade_ncm_cnae: float
    score_cnae: float

@dataclass
class ResultadoAssociacao:
    numero_de_ordem: str
    cluster_id: int
    cnae_candidato: str
    descricao_cnae: str
    ranking_cnae: int
    similaridade_operacao_cnae: float
    similaridade_cluster_cnae: float
    compatibilidade_ncm_cnae: float
    cnpj_candidato: str
    tipo_cnae_empresa: str
    ranking_cnpj: int
    score_total: float
    limitacoes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numero_de_ordem": self.numero_de_ordem,
            "cluster_id": self.cluster_id,
            "cnae_candidato": self.cnae_candidato,
            "descricao_cnae": self.descricao_cnae,
            "ranking_cnae": self.ranking_cnae,
            "similaridade_operacao_cnae": round(self.similaridade_operacao_cnae, 4),
            "similaridade_cluster_cnae": round(self.similaridade_cluster_cnae, 4),
            "compatibilidade_ncm_cnae": round(self.compatibilidade_ncm_cnae, 4),
            "cnpj_candidato": self.cnpj_candidato,
            "tipo_cnae_empresa": self.tipo_cnae_empresa,
            "ranking_cnpj": self.ranking_cnpj,
            "score_total": round(self.score_total, 4),
            "limitacoes": self.limitacoes
        }
