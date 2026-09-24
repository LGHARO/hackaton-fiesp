"""
Gerador de dados de operações de importação sintéticas, realistas e amostradas
para validação, testes e demonstração imediata do pipeline caso a base de operações
ainda não tenha sido fornecida pelo usuário.
"""
import os
import csv
import random
from typing import List, Dict

def generate_sample_operations(
    ncm_csv_path: str = "br_bd_diretorios_mundo_nomenclatura_comum_mercosul.csv",
    output_csv_path: str = "data/raw/operacoes_sample.csv",
    n_samples: int = 500,
    seed: int = 42
) -> str:
    random.seed(seed)
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    # Coletar NCMs disponíveis
    ncms = []
    if os.path.exists(ncm_csv_path):
        with open(ncm_csv_path, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ncm_code = str(row.get("id_ncm", "")).strip().zfill(8)
                ncm_desc = str(row.get("nome_ncm_portugues", "")).strip()
                if len(ncm_code) == 8 and ncm_desc:
                    ncms.append((ncm_code, ncm_desc))

    # Casos realistas em diversos domínios com termos técnicos, marcas anonimizadas, especificações
    templates = [
        # Maquinário e Peças
        ("84818099", "VALVULA DE CONTROLE PNEUMATICA MODELO VCP-40 DN 50 CORPO EM ACO INOX AISI 316 PRESSAO 150 LBS APLICACAO INDUSTRIAL", 14.5, 320.0),
        ("84818099", "VALVULA DE RETENCAO DE FLUXO REF VRET-12 EM BRONZE CONEXAO ROSCADA 1/2 POLEGADA NPT", 1.2, 45.0),
        ("84821010", "ROLAMENTO DE ESFERAS RADIAL DE UMA CARREIRA REF 6205-2RS DIMENSAO 25X52X15 MM FOLGA C3 PARA MOTOR ELETRICO", 0.128, 5.80),
        ("84822010", "ROLAMENTO DE ROLOS CONICOS SERIE METRICA REF 32210 DIMENSAO 50X90X24.75 MM APLICACAO TRANSMISSAO AUTOMOTIVA", 0.65, 18.50),
        ("84137090", "BOMBA CENTRIFUGA MULTIESTAGIO VERTICAL POTENCIA 7.5 HP 220/380V VAZAO 12 M3/H PRESSAO 8.5 BAR ROTOR INOX", 48.0, 1450.0),
        
        # Eletrônicos e Semicondutores
        ("85423190", "CIRCUITO INTEGRADO MICROCONTROLADOR SMD 32 BITS NUCLEO ARM CORTEX-M4 FLASH 512KB ENCAPSULAMENTO LQFP-64", 0.002, 3.45),
        ("85423919", "AMPLIFICADOR OPERACIONAL DE BAIXO RUIDO DUPLO TIPO SOIC-8 ALIMENTACAO 5V A 15V", 0.001, 0.85),
        ("85044021", "FONTE DE ALIMENTACAO CHAVEADA AC/DC ENTRADA 100-240V SAIDA 24VDC 10A 240W MODELO HDR-240-24 TRILHO DIN", 0.75, 42.0),
        ("85365090", "INTERRUPTOR SECCIONADOR ROTATIVO TRIPOLAR 63A 690V FIXACAO FRONTAL IP65 COM MANOPLA TRAVAVEL", 0.35, 28.50),
        
        # Farmacêuticos e Veterinários
        ("30049099", "MEDICAMENTO PARA USO HUMANO A BASE DE CLORIDRATO DE ONDANSETRONA 8MG COMPRIMIDOS CX C/ 30 UNIDADES", 0.08, 12.30),
        ("30022029", "VACINA PARA USO VETERINARIO INATIVADA CONTRA CLOSTRIDIOSE EM FRASCO AMPOLA CONTENDO 50 DOSES 100ML", 0.15, 8.90),
        ("30042099", "ANTIBIOTICO CEFTIOFUR SODICO ESTERIL PO PARA SUSPENSAO INJETAVEL USO VETERINARIO FRASCO 4G", 0.06, 14.20),
        
        # Plásticos e Químicos
        ("39012010", "RESINA POLIETILENO DE ALTA DENSIDADE (PEAD) VIRGEM EM PELETS GRAU SOPRO INDICE FLUIDEZ 0.3 G/10MIN DENSIDADE 0.954", 25000.0, 31250.0),
        ("39233090", "FRASCOS DE POLIETILENO TEREFTALATO (PET) CAPACIDADE 500 ML CRISTAL TRANSPARENTE COM GARGALO 28MM PCO 1881", 1200.0, 4800.0),
        ("38089199", "INSETICIDA AGRICOLA FORMULACAO SUSPENSAO CONCENTRADA A BASE DE TIAMETOXAM 350 G/L GL COM 5 LITROS", 5.6, 85.0),
        ("31021010", "UREIA AGRICOLA FERTILIZANTE GRANULADA COM TEOR MINIMO DE 46% DE NITROGENIO TOTAL EMBALAGEM BIG BAG DE 1000 KG", 50000.0, 22500.0),
        
        # Têxtil e Vestuário
        ("52083200", "TECIDO DE ALGODAO 100% TINTO EM LONA LIGAMENTO TELA LARGURA 1.60 M GRAMATURA 280 G/M2 DESTINADO A CONFECCAO", 450.0, 2350.0),
        ("62034200", "CALCA MASCULINA DE TECIDO PLANO 100% ALGODAO DENIM SARJA 3X1 PESO 12 OZ TAMANHOS DIVERSOS", 85.0, 1150.0),
        
        # Alimentos e Bebidas
        ("22042100", "VINHO FINO TINTO SECO ELABORADO COM UVAS CABERNET SAUVIGNON SAFRA 2022 TEOR ALCOLICO 13.5% VOL GARRAFAS 750ML", 900.0, 3600.0),
        ("09011110", "CAFE CRU EM GRAO NAO DESCAFEINADO TIPO ARABICA SAFRA RECENTE SACAS DE JUTA DE 60 KG", 18000.0, 54000.0),
        ("18063210", "CHOCOLATE EM TABLETES CONTENDO CACAU RECHEADO EM EMBALAGENS DE 100G PARA CONSUMO DIRETO", 350.0, 1850.0),
        
        # Autopeças e Veículos
        ("87082999", "PAINEL LATERAL EXTERNO ESTAMPADO EM CHAPA DE ACO GALVANIZADO PARA CARROCERIA DE VEICULO AUTOMOTOR COD PECA 517823", 12.8, 110.0),
        ("87083090", "PASTILHA DE FREIO A DISCO DIANTEIRO ISENTA DE AMIANTO COMPATIVEL COM PICK-UP REF FP-882 JOGO C/ 4 PECAS", 2.4, 26.50),
        ("87089990", "BARRA ESTABILIZADORA DA SUSPENSAO DIANTEIRA FORJADA EM ACO LIGA DE ALTA RESISTENCIA DIAMETRO 24MM", 6.2, 48.0)
    ]

    paises = ["CHINA", "ESTADOS UNIDOS", "ALEMANHA", "ITALIA", "JAPAO", "ARGENTINA", "COREIA DO SUL", "FRANCA", "INDIA", "MEXICO"]
    meses = [f"2023-{m:02d}" for m in range(1, 13)] + [f"2024-{m:02d}" for m in range(1, 13)]

    records = []
    
    # 1. Gerar operações baseadas nos templates representativos
    op_id = 1000001
    for template_idx, (ncm, desc, peso_base, valor_base) in enumerate(templates):
        # Gerar entre 10 e 25 variações para cada template
        repeat_count = random.randint(12, 22)
        for r in range(repeat_count):
            peso = round(peso_base * random.uniform(0.7, 1.8), 3)
            valor = round(valor_base * random.uniform(0.75, 1.6), 2)
            origem = random.choice(paises)
            mes = random.choice(meses)
            
            # Adicionar pequenas variações técnicas comuns em importação
            variacao = desc
            if random.random() > 0.4:
                variacao += f" LOTE {random.randint(100, 999)}/{random.randint(21, 24)}"
            if random.random() > 0.5:
                variacao += f" EMBALAGEM PADRAO PALETIZADA"
            
            records.append({
                "numero_de_ordem": f"OP-{op_id}",
                "anomes": mes,
                "cod_ncm": ncm,
                "pais_de_origem": origem,
                "descricao_do_produto": variacao,
                "peso_liquido": peso,
                "vmle_dolar": valor
            })
            op_id += 1

    # 2. Se ncms gerais foram carregados, sortear alguns para diversidade
    if ncms and len(records) < n_samples:
        for _ in range(n_samples - len(records)):
            ncm_code, ncm_desc = random.choice(ncms)
            records.append({
                "numero_de_ordem": f"OP-{op_id}",
                "anomes": random.choice(meses),
                "cod_ncm": ncm_code,
                "pais_de_origem": random.choice(paises),
                "descricao_do_produto": f"ITEM IMPORTADO CONFORME ESPECIFICACAO COMERCIAL DO FORNECEDOR RELATIVO A {ncm_desc.upper()}",
                "peso_liquido": round(random.uniform(1.0, 500.0), 3),
                "vmle_dolar": round(random.uniform(50.0, 10000.0), 2)
            })
            op_id += 1

    random.shuffle(records)

    with open(output_csv_path, mode="w", encoding="utf-8", newline="") as f:
        fieldnames = ["numero_de_ordem", "anomes", "cod_ncm", "pais_de_origem", "descricao_do_produto", "peso_liquido", "vmle_dolar"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records[:n_samples])

    print(f"Base de operações gerada com sucesso: {output_csv_path} ({len(records[:n_samples])} registros)")
    return output_csv_path

if __name__ == "__main__":
    generate_sample_operations()
