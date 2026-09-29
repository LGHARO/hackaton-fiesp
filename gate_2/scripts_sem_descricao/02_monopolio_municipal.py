"""Passo 2 (Base 2): Monopolio Municipal e Cruzamento com RFB."""
from pathlib import Path
import pandas as pd

OUT_DIR = Path("gate_2/dados/processado_sem_desc")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    est = pd.read_parquet(
        "shared/dados/processado/estabelecimentos_candidatos.parquet",
        columns=[
            "cnpj_basico",
            "nome_fantasia",
            "cnae_principal",
            "uf",
            "municipio",
        ],
    )
    emp = pd.read_parquet(
        "shared/dados/processado/empresas_candidatas.parquet",
        columns=["cnpj_basico", "razao_social"],
    )

    # Padronizacao do codigo TOM do municipio (4 digitos com zeros a esquerda)
    est["municipio"] = est["municipio"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)

    # Formata CNPJ completo usando a raiz e matriz padrao
    est["cnpj_completo"] = est["cnpj_basico"].astype(str).str.zfill(8) + "000100"

    empresas = est.merge(emp, on="cnpj_basico", how="inner")
    del est, emp

    # Monopolio absoluto no municipio: municipios com exatamente 1 empresa candidata
    contagem_mun = (
        empresas.groupby("municipio")["cnpj_basico"]
        .nunique()
        .reset_index(name="qtd_raizes_no_mun")
    )
    
    empresas = empresas.merge(contagem_mun, on="municipio", how="left")

    saida = OUT_DIR / "empresas_candidatas_tratadas.parquet"
    empresas.to_parquet(saida, index=False)
    print(f"Total de estabelecimentos validos: {len(empresas)}")
    print(f"Municipios com empresa unica (monopolio estrito): {(contagem_mun['qtd_raizes_no_mun'] == 1).sum()}")


if __name__ == "__main__":
    main()

