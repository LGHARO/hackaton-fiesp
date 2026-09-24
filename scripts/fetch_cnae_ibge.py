"""
Script para baixar a estrutura oficial completa do CNAE 2.0 / 2.3 diretamente da API pública do IBGE (CONCLA)
e gerar a base de referência canônica com descrições, hierarquia (seção, divisão, grupo), atividades e notas explicativas.
"""
import urllib.request
import json
import csv
import os
import re
from typing import Dict, List, Any

def format_classe_id(cid: str) -> str:
    # 01113 -> 01.11-3
    cid = re.sub(r'\D', '', str(cid)).zfill(5)
    return f"{cid[:2]}.{cid[2:4]}-{cid[4]}"

def clean_text(t: str) -> str:
    if not t:
        return ""
    # remove excessive newlines and whitespace
    t = re.sub(r'[\r\n\t]+', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def fetch_cnae_reference(output_csv: str = "data/reference/cnae_referencia.csv"):
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    
    print("Baixando classes CNAE do IBGE...")
    req_classes = urllib.request.Request(
        "https://servicodados.ibge.gov.br/api/v2/cnae/classes",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req_classes, timeout=30) as resp:
        classes_data = json.loads(resp.read().decode('utf-8'))
        
    print(f"Total de classes recebidas: {len(classes_data)}")

    print("Baixando subclasses CNAE do IBGE...")
    req_sub = urllib.request.Request(
        "https://servicodados.ibge.gov.br/api/v2/cnae/subclasses",
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req_sub, timeout=30) as resp:
        subclasses_data = json.loads(resp.read().decode('utf-8'))
        
    print(f"Total de subclasses recebidas: {len(subclasses_data)}")

    # Indexar atividades e notas por classe
    classe_atividades: Dict[str, List[str]] = {}
    classe_notas: Dict[str, List[str]] = {}

    for sub in subclasses_data:
        classe_info = sub.get("classe", {})
        cid = classe_info.get("id")
        if not cid:
            continue
        c_fmt = format_classe_id(cid)
        
        atividades = sub.get("atividades", [])
        if atividades:
            classe_atividades.setdefault(c_fmt, []).extend(atividades)
            
        notas = sub.get("observacoes", [])
        if notas:
            classe_notas.setdefault(c_fmt, []).extend(notas)

    records = []
    
    # Processar classes (que batem diretamente com o formato da base de empresas: XX.XX-X)
    for c in classes_data:
        cid_raw = c.get("id", "")
        cid_fmt = format_classe_id(cid_raw)
        desc = clean_text(c.get("descricao", ""))
        
        grupo_info = c.get("grupo", {})
        div_info = grupo_info.get("divisao", {})
        sec_info = div_info.get("secao", {})
        
        grupo_desc = clean_text(f"{grupo_info.get('id', '')} - {grupo_info.get('descricao', '')}")
        div_desc = clean_text(f"{div_info.get('id', '')} - {div_info.get('descricao', '')}")
        sec_desc = clean_text(f"{sec_info.get('id', '')} - {sec_info.get('descricao', '')}")
        
        # Coletar notas explicativas da classe e subclasses associadas
        obs = c.get("observacoes", [])
        obs_extra = classe_notas.get(cid_fmt, [])
        all_obs = [clean_text(o) for o in (obs + obs_extra) if clean_text(o)]
        # deduplicar notas preservando ordem
        dedup_obs = list(dict.fromkeys(all_obs))
        notas_txt = " | ".join(dedup_obs[:5]) # top notas mais relevantes
        
        atvs = [clean_text(a) for a in classe_atividades.get(cid_fmt, []) if clean_text(a)]
        dedup_atvs = list(dict.fromkeys(atvs))
        atividades_txt = "; ".join(dedup_atvs[:15]) # principais atividades
        
        # Montar texto completo para representação semântica rica
        texto_completo_parts = [
            f"CNAE: {cid_fmt}",
            f"Atividade: {desc}",
            f"Seção: {sec_desc}",
            f"Divisão: {div_desc}",
            f"Grupo: {grupo_desc}",
        ]
        if atividades_txt:
            texto_completo_parts.append(f"Atividades compreendidas: {atividades_txt}")
        if notas_txt:
            texto_completo_parts.append(f"Notas explicativas: {notas_txt}")
            
        texto_completo = ". ".join(texto_completo_parts) + "."

        records.append({
            "cnae_codigo": cid_fmt,
            "cnae_id_numerico": cid_raw,
            "tipo": "classe",
            "descricao_cnae": desc,
            "secao": sec_desc,
            "divisao": div_desc,
            "grupo": grupo_desc,
            "atividades": atividades_txt,
            "notas_explicativas": notas_txt,
            "texto_representacao": texto_completo
        })

    # Gravar CSV
    fieldnames = [
        "cnae_codigo", "cnae_id_numerico", "tipo", "descricao_cnae",
        "secao", "divisao", "grupo", "atividades", "notas_explicativas", "texto_representacao"
    ]
    with open(output_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Base de referência CNAE gravada com sucesso em: {output_csv} ({len(records)} registros)")

if __name__ == "__main__":
    fetch_cnae_reference()
