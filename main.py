"""
Interface de Linha de Comando (CLI) para execução modular do pipeline de importações -> CNAE -> CNPJs.
"""
import argparse
import sys
import os

from src.pipeline import ImportOpsPipeline
from src.sample_data import generate_sample_operations

def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Local de ML: Associação de Operações de Importação a CNAEs e Recuperação de CNPJs."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Caminho para o arquivo YAML de configurações."
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="all",
        choices=["all", "preprocess", "baseline", "embeddings", "cluster", "associate", "retrieve", "evaluate", "sample"],
        help="Etapa a ser executada."
    )
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        help="Força o recálculo dos embeddings sem ler o cache em disco."
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="Quantidade de operações a gerar no modo 'sample'."
    )

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Caminho direto para o arquivo de operações (Parquet ou CSV). Sobrescreve o config.yaml."
    )

    args = parser.parse_args()

    if args.mode == "sample":
        print(f"Gerando nova base de operações sintéticas com {args.sample_size} registros...")
        generate_sample_operations(n_samples=args.sample_size)
        return

    pipeline = ImportOpsPipeline(config_path=args.config)

    if args.input:
        if not os.path.exists(args.input):
            print(f"ERRO: Arquivo de entrada não encontrado: {args.input}")
            sys.exit(1)
        print(f"Usando arquivo de operações customizado: {args.input}")
        pipeline.cfg.data.operations_file = args.input
        pipeline.preprocessor.data_cfg.operations_file = args.input

    if args.mode == "preprocess":
        pipeline.step_preprocess()
    elif args.mode == "baseline":
        pipeline.step_baseline()
    elif args.mode == "embeddings":
        pipeline.step_embeddings(force=args.force_recompute)
    elif args.mode == "cluster":
        pipeline.step_clustering()
    elif args.mode == "associate":
        pipeline.step_association()
    elif args.mode == "retrieve":
        pipeline.step_retrieval()
    elif args.mode == "evaluate":
        pipeline.step_evaluation()
    elif args.mode == "all":
        pipeline.run_all(force=args.force_recompute)

if __name__ == "__main__":
    main()
