"""Validador e Reparador Global de Compliance do Gate 2."""
from pathlib import Path
import pandas as pd

PATH_B2_CSV = Path("gate_2/palpites_base2_top50.csv")
PATH_B2_DET = Path("gate_2/palpites_base2_top50_detalhado.parquet")

PATH_B3_CSV = Path("gate_2/palpites_cnpj_top50_final.csv")
PATH_G1_CSV = Path("gate_1/palpites_cnpj.csv")


def main():
    print("Iniciando auditoria e auto-reparo da Base 2...")

    if not PATH_B2_CSV.exists():
        raise FileNotFoundError(f"Arquivo da Base 2 nao encontrado: {PATH_B2_CSV}")

    df_b2 = pd.read_csv(PATH_B2_CSV, dtype=str)
    
    # Padroniza colunas da Base 2
    cols_map = {}
    for c in df_b2.columns:
        if c.lower() in ["chave_item", "chave", "id"]:
            cols_map[c] = "chave_item"
        elif c.upper() in ["CNPJ", "CNPJ_BASICO", "CNPJ_COMPLETO"]:
            cols_map[c] = "CNPJ"
    df_b2 = df_b2.rename(columns=cols_map)

    if "chave_item" not in df_b2.columns or "CNPJ" not in df_b2.columns:
        raise ValueError(f"Base 2 nao possui as colunas obrigatorias 'chave_item' e 'CNPJ'. Colunas: {list(df_b2.columns)}")

    df_b2["CNPJ"] = df_b2["CNPJ"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14)

    cnpjs_proibidos = set()

    # 1. Carrega Gate 1 (se existir)
    if PATH_G1_CSV.exists():
        df_g1 = pd.read_csv(PATH_G1_CSV, dtype=str)
        col_cnpj = "CNPJ" if "CNPJ" in df_g1.columns else df_g1.columns[1]
        g1_set = set(df_g1[col_cnpj].str.replace(r"\D", "", regex=True).str.zfill(14))
        cnpjs_proibidos.update(g1_set)
        print(f"Gate 1: {len(g1_set)} CNPJs carregados como restritos.")

    # 2. Carrega CNPJs ja identificados na Base 3 para evitar colisao
    if PATH_B3_CSV.exists():
        df_b3 = pd.read_csv(PATH_B3_CSV, dtype=str)
        if "CNPJ" in df_b3.columns:
            b3_cnpjs = df_b3["CNPJ"].str.replace(r"\D", "", regex=True).str.zfill(14).dropna()
            cnpjs_proibidos.update(b3_cnpjs)
            print(f"Base 3: {len(b3_cnpjs)} CNPJs completos identificados como restritos.")
        elif "cnpj_basico" in df_b3.columns:
            b3_basicos = df_b3["cnpj_basico"].str.replace(r"\D", "", regex=True).str.zfill(8).dropna().tolist()
            # Restringe os que comecam com essa raiz
            print(f"Base 3: {len(b3_basicos)} raizes de CNPJ identificadas como restritas.")
            df_b2_raiz = df_b2["CNPJ"].str.slice(0, 8)
            colisoes_raiz = df_b2[df_b2_raiz.isin(b3_basicos)]
            if len(colisoes_raiz) > 0:
                print(f"Aviso: {len(colisoes_raiz)} CNPJs da Base 2 compartilham raiz com Base 3.")

    # 3. Corrige colisoes na Base 2
    b2_conflitos = df_b2["CNPJ"].isin(cnpjs_proibidos)
    n_conflitos = b2_conflitos.sum()

    if n_conflitos > 0:
        print(f"Detectadas {n_conflitos} colisoes exatas de CNPJ na Base 2! Substituindo...")
        df_b2_valido = df_b2[~b2_conflitos]

        if PATH_B2_DET.exists():
            reservas = pd.read_parquet(PATH_B2_DET)
            reservas["CNPJ"] = reservas["cnpj_completo"].astype(str).str.zfill(14)
            if "chave_item_exemplo" in reservas.columns:
                reservas = reservas.rename(columns={"chave_item_exemplo": "chave_item"})

            usados = set(cnpjs_proibidos).union(set(df_b2_valido["CNPJ"]))
            candidatos_novos = reservas[
                (~reservas["CNPJ"].isin(usados)) & 
                (~reservas["chave_item"].isin(df_b2_valido["chave_item"]))
            ][["chave_item", "CNPJ"]].drop_duplicates(subset=["CNPJ"])

            faltam = 50 - len(df_b2_valido)
            reposicao = candidatos_novos.head(faltam)
            df_b2 = pd.concat([df_b2_valido, reposicao], ignore_index=True)
            print(f"Substituicao concluida: {len(reposicao)} novos candidatos adicionados.")
        else:
            df_b2 = df_b2_valido
    else:
        print("Base 2: Zero colisoes diretas de CNPJ encontradas.")

    # Deduplicacao e corte final de seguranca
    df_b2 = df_b2.drop_duplicates(subset=["CNPJ"]).drop_duplicates(subset=["chave_item"]).head(50)

    assert len(df_b2) <= 50, f"Erro: {len(df_b2)} ultrapassou 50 palpites"
    assert (df_b2["CNPJ"].str.len() == 14).all(), "Erro: CNPJ fora de 14 digitos"

    # Salva apenas o arquivo da Base 2
    df_b2.to_csv(PATH_B2_CSV, index=False)

    print("\nAuditoria e Validacao Concluidas com Sucesso:")
    print(f"- Base 2: {len(df_b2)} palpites validados e salvos em {PATH_B2_CSV}")
    print("- Colunas: ['chave_item', 'CNPJ']")
    print("- Verificacao de tamanho de CNPJ (14 digitos estritos): OK")
    print("Arquivo pronto para submissao!")


if __name__ == "__main__":
    main()
