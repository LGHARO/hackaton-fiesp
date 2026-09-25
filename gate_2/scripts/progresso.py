"""Progresso do clustering: % concluido (arquivos no disco, reflete o total
real desde o inicio) + ETA (duracao media dos blocos logados em
gate_2/dados/processado/jobs.sqlite nesta sessao -- ver joblog.py).
"""
import sqlite3
from pathlib import Path

TOTAL_BLOCOS = 5756
OUT_DIR = Path("gate_2/dados/processado/cluster_parts")
DB_PATH = Path("gate_2/dados/processado/jobs.sqlite")


def main() -> None:
    feitos = len(list(OUT_DIR.glob("ncm_*.parquet")))
    restantes = TOTAL_BLOCOS - feitos
    pct = 100 * feitos / TOTAL_BLOCOS

    n_sessao = media = None
    if DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        n_sessao, media = con.execute(
            "select count(*), avg(duracao_s) from iteracoes "
            "where job='cluster_texto' and status='ok'"
        ).fetchone()

    eta_min = (restantes * media / 60) if media else None

    print(f"{'concluidos':>10} {'total':>7} {'%':>7} {'restantes':>10} "
          f"{'dur.media(s)':>13} {'ETA (min)':>10}")
    print(
        f"{feitos:>10} {TOTAL_BLOCOS:>7} {pct:>6.1f}% {restantes:>10} "
        f"{(media or 0):>13.2f} {(eta_min if eta_min is not None else float('nan')):>10.0f}"
    )
    if n_sessao:
        print(f"({n_sessao} blocos logados nesta sessao pra calcular a media)")


if __name__ == "__main__":
    main()
