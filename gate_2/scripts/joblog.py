"""Log de progresso dos jobs do gate_2 em SQLite.

Os pipelines aqui rodam por horas em background, e ate agora a unica forma
de acompanhar era contar arquivos no disco ou ler stdout com buffer (que so
aparece no fim ou quando da erro). Isso registra cada iteracao (bloco de
clusterizacao, grupo do score final, etc) numa tabela sqlite -- da pra
consultar progresso, duracao por item e falhas a qualquer momento, de
qualquer processo (inclusive enquanto o job ta rodando).

Uso:
    from joblog import log_iteracao

    for item in itens:
        with log_iteracao("nome_do_job", str(item)) as it:
            ... trabalho ...
            it["n_linhas"] = 123  # opcional, aparece na coluna n_linhas

Consulta rapida (outro terminal, job rodando ou nao):
    sqlite3 gate_2/dados/processado/jobs.sqlite "select job, status, count(*), avg(duracao_s) from iteracoes group by 1,2"
"""
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path("gate_2/dados/processado/jobs.sqlite")


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")  # varios workers escrevendo ao mesmo tempo
    con.execute(
        """
        create table if not exists iteracoes (
            id integer primary key autoincrement,
            job text not null,
            item text not null,
            status text not null,
            started_at text not null,
            finished_at text not null,
            duracao_s real not null,
            n_linhas integer,
            detalhe text
        )
        """
    )
    return con


@contextmanager
def log_iteracao(job: str, item: str):
    item = str(item)  # coluna item e NOT NULL -- nunca deixa passar None
    info: dict = {"n_linhas": None, "detalhe": None}
    t0 = time.time()
    inicio = _agora()
    try:
        yield info
    except Exception as e:
        _registrar(job, item, "erro", inicio, _agora(), time.time() - t0, info, detalhe=str(e))
        raise
    else:
        _registrar(job, item, "ok", inicio, _agora(), time.time() - t0, info)


def _registrar(job, item, status, inicio, fim, duracao_s, info, detalhe=None) -> None:
    con = _connect()
    con.execute(
        "insert into iteracoes "
        "(job, item, status, started_at, finished_at, duracao_s, n_linhas, detalhe) "
        "values (?, ?, ?, ?, ?, ?, ?, ?)",
        (job, item, status, inicio, fim, duracao_s, info.get("n_linhas"), detalhe or info.get("detalhe")),
    )
    con.commit()
    con.close()
