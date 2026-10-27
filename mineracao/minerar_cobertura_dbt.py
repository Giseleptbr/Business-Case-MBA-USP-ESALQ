#!/usr/bin/env python3
"""
Mineracao de cobertura de testes em projetos dbt publicos no GitHub.

OBJETIVO
  Medir qual PILHA DE CONTROLES os projetos dbt reais efetivamente declaram, para
  ancorar na pratica o resultado experimental de que a pilha padrao (teste de schema +
  testes genericos) nao detecta defeito semantico.

MAPEAMENTO entre teste real de dbt e as camadas do experimento:
  C1  reconciliacao de contagem  <- dbt_utils.equal_rowcount, dbt_utils.fewer_rows_than,
                                    dbt_utils.cardinality_equality, elementary volume_anomalies
  C2  testes genericos           <- unique, not_null, accepted_values, relationships
  C3  schema / contrato          <- config.contract.enforced, constraints, dbt_expectations
                                    expect_table_columns_to_match_*, expect_column_values_to_be_of_type
  C4  reconciliacao de valor     <- audit_helper (compare_relations/compare_queries),
                                    dbt_utils.expression_is_true, dbt_expectations agregados
                                    (expect_column_sum_to_be_between, *_mean_*, *_median_*),
                                    testes singulares com heuristica de reconciliacao

COMO RODAR
  export GITHUB_TOKEN=ghp_...          # token classico com escopo public_repo
  python3 minerar_cobertura_dbt.py --fase frame     # monta o frame amostral
  python3 minerar_cobertura_dbt.py --fase amostra --n 200 --seed 42
  python3 minerar_cobertura_dbt.py --fase coletar   # baixa e parseia a amostra
  python3 minerar_cobertura_dbt.py --fase relatorio

  python3 minerar_cobertura_dbt.py --autoteste      # valida o parser, nao precisa de token

PROTOCOLO (secao de metodos do artigo)
  Frame amostral: repositorios publicos contendo arquivo `dbt_project.yml`, localizados
  pela busca de codigo do GitHub. Como a busca retorna no maximo 1000 resultados por
  consulta, o frame e montado por ESTRATIFICACAO em faixas de tamanho do repositorio
  (parametro `size:` da busca), o que permite ultrapassar esse teto sem amostragem por
  conveniencia. O frame e gravado com carimbo de data e reutilizado, de modo que a
  amostragem seja reproduzivel.

  Criterios de exclusao, aplicados nesta ordem e contabilizados:
    E1 fork                         (nao representa decisao propria de teste)
    E2 arquivado                    (nao reflete pratica corrente)
    E3 sem diretorio de modelos     (nao e projeto dbt utilizavel)
    E4 menos de MIN_MODELOS modelos (projeto de brinquedo ou tutorial)
    E5 heuristica de material didatico no nome ou descricao
  A contagem de exclusoes por criterio entra no relatorio, como exige estudo de mineracao.

  Amostragem: aleatoria simples sem reposicao sobre o frame elegivel, com semente fixa.
"""

import argparse
import io
import json
import os
import random
import re
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("Falta PyYAML. Instale com: pip install pyyaml")

BASE = Path(__file__).resolve().parent / "mineracao_dbt"
BASE.mkdir(exist_ok=True)
FRAME = BASE / "frame.jsonl"
AMOSTRA = BASE / "amostra.json"
RESULT = BASE / "resultado.jsonl"
CACHE = BASE / "cache"
CACHE.mkdir(exist_ok=True)

MIN_MODELOS = 5
API = "https://api.github.com"

PADRAO_DIDATICO = re.compile(
    r"\b(tutorial|course|curso|learn|learning|bootcamp|exercise|exercicio|training|"
    r"demo|sandbox|playground|example|exemplo|test-?repo|my-?first|getting-?started|"
    r"workshop|study|estudo|practice|pratica)\b", re.I)

# ----------------------------------------------------------------------------------
# Vocabulario de testes, por camada
# ----------------------------------------------------------------------------------
C2_GENERICOS = {"unique", "not_null", "accepted_values", "relationships"}

C1_CONTAGEM = {
    "dbt_utils.equal_rowcount", "dbt_utils.fewer_rows_than",
    "dbt_utils.cardinality_equality", "equal_rowcount", "fewer_rows_than",
    "elementary.volume_anomalies", "volume_anomalies",
    "dbt_expectations.expect_table_row_count_to_equal_other_table",
    "dbt_expectations.expect_table_row_count_to_be_between",
    "expect_table_row_count_to_equal_other_table",
}

C3_SCHEMA_TESTES = {
    "dbt_expectations.expect_table_columns_to_match_ordered_list",
    "dbt_expectations.expect_table_columns_to_match_set",
    "dbt_expectations.expect_column_values_to_be_of_type",
    "dbt_expectations.expect_column_values_to_be_in_type_list",
    "expect_table_columns_to_match_set",
    "expect_column_values_to_be_of_type",
}

C4_VALOR = {
    "dbt_utils.expression_is_true", "expression_is_true",
    "dbt_utils.equality", "equality",
    "dbt_expectations.expect_column_sum_to_be_between",
    "dbt_expectations.expect_column_mean_to_be_between",
    "dbt_expectations.expect_column_median_to_be_between",
    "dbt_expectations.expect_column_quantile_values_to_be_between",
    "dbt_expectations.expect_column_stdev_to_be_between",
    "expect_column_sum_to_be_between", "expect_column_mean_to_be_between",
    "elementary.column_anomalies", "column_anomalies",
    "elementary.dimension_anomalies", "dimension_anomalies",
}

PACOTES_C1 = {"dbt_utils", "elementary"}
PACOTES_C4 = {"audit_helper", "dbt_expectations", "elementary", "re_data"}

# heuristica para teste singular que faz reconciliacao de valor
PADRAO_RECONC = re.compile(
    r"(compare_relations|compare_queries|compare_column_values|"
    r"\bexcept\b|\bminus\b|reconcil|sum\s*\(|abs\s*\(\s*sum)", re.I)


# ----------------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------------
def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not t:
        sys.exit("Defina GITHUB_TOKEN com um token classico de escopo public_repo.")
    return t


def api(path, params=None, accept="application/vnd.github+json", tentativa=0):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token()}",
        "Accept": accept,
        "User-Agent": "mineracao-cobertura-dbt/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            restante = r.headers.get("X-RateLimit-Remaining")
            if restante is not None and int(restante) <= 2:
                reset = int(r.headers.get("X-RateLimit-Reset", "0"))
                espera = max(reset - int(time.time()) + 3, 3)
                print(f"  [limite de taxa] aguardando {espera}s", file=sys.stderr)
                time.sleep(espera)
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) and tentativa < 5:
            espera = 2 ** tentativa * 15
            print(f"  [HTTP {e.code}] nova tentativa em {espera}s", file=sys.stderr)
            time.sleep(espera)
            return api(path, params, accept, tentativa + 1)
        raise


# ----------------------------------------------------------------------------------
# FASE 1 — frame amostral, estratificado por tamanho
# ----------------------------------------------------------------------------------
FAIXAS = ["<100", "100..300", "300..600", "600..1200", "1200..2500",
          "2500..5000", "5000..12000", "12000..40000", ">40000"]


def montar_frame():
    vistos, total = {}, 0
    for faixa in FAIXAS:
        q = f"filename:dbt_project.yml size:{faixa}"
        print(f"[frame] faixa size:{faixa}")
        for pagina in range(1, 11):              # 10 x 100 = teto de 1000 por consulta
            try:
                d = api("/search/code", {"q": q, "per_page": 100, "page": pagina})
            except urllib.error.HTTPError as e:
                print(f"  parou na pagina {pagina}: HTTP {e.code}", file=sys.stderr)
                break
            itens = d.get("items", [])
            if not itens:
                break
            for it in itens:
                r = it["repository"]
                if r["full_name"] in vistos:
                    continue
                vistos[r["full_name"]] = {
                    "full_name": r["full_name"],
                    "caminho_projeto": it["path"],
                    "fork": r.get("fork"),
                    "faixa": faixa,
                }
                total += 1
            print(f"  pagina {pagina}: {len(itens)} itens, frame com {total}")
            time.sleep(6)                        # busca de codigo: 10 req/min
            if len(itens) < 100:
                break
    with FRAME.open("w") as f:
        f.write(json.dumps({"_meta": {"gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                time.gmtime()),
                                      "consulta": "filename:dbt_project.yml",
                                      "estratos": FAIXAS,
                                      "total": total}}) + "\n")
        for v in vistos.values():
            f.write(json.dumps(v) + "\n")
    print(f"[frame] {total} repositorios distintos -> {FRAME}")


# ----------------------------------------------------------------------------------
# FASE 2 — amostra aleatoria com criterios de exclusao
# ----------------------------------------------------------------------------------
def sortear(n, seed):
    linhas = [json.loads(l) for l in FRAME.open() if l.strip()]
    meta = linhas[0]["_meta"] if "_meta" in linhas[0] else {}
    cands = [l for l in linhas if "full_name" in l]
    random.Random(seed).shuffle(cands)

    exclusoes = Counter()
    elegiveis = []
    for c in cands:
        if len(elegiveis) >= n:
            break
        try:
            r = api(f"/repos/{c['full_name']}")
        except urllib.error.HTTPError:
            exclusoes["erro_api"] += 1
            continue
        if r.get("fork"):
            exclusoes["E1_fork"] += 1;        continue
        if r.get("archived"):
            exclusoes["E2_arquivado"] += 1;   continue
        texto = f"{r.get('name','')} {r.get('description') or ''}"
        if PADRAO_DIDATICO.search(texto):
            exclusoes["E5_didatico"] += 1;    continue
        c.update({"default_branch": r["default_branch"],
                  "stars": r["stargazers_count"],
                  "pushed_at": r["pushed_at"],
                  "size_kb": r["size"],
                  "description": r.get("description")})
        elegiveis.append(c)
        print(f"  [{len(elegiveis)}/{n}] {c['full_name']}")

    AMOSTRA.write_text(json.dumps({
        "_meta": {"seed": seed, "n_alvo": n, "frame": meta,
                  "exclusoes_fase2": dict(exclusoes),
                  "sorteado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "repos": elegiveis}, indent=2))
    print(f"[amostra] {len(elegiveis)} elegiveis; exclusoes {dict(exclusoes)} -> {AMOSTRA}")


# ----------------------------------------------------------------------------------
# PARSER
# ----------------------------------------------------------------------------------
def _nomes_de_testes(bloco):
    """Extrai nomes de teste de uma lista `tests:` / `data_tests:` do dbt."""
    saida = []
    if not isinstance(bloco, list):
        return saida
    for t in bloco:
        if isinstance(t, str):
            saida.append(t)
        elif isinstance(t, dict):
            for k in t:
                saida.append(k)
    return saida


def parsear_yaml_dbt(texto):
    """Conta testes declarados em um arquivo YAML de schema do dbt."""
    out = Counter()
    modelos, modelos_com_teste = 0, 0
    contratos = 0
    try:
        doc = yaml.safe_load(texto)
    except Exception:
        out["_yaml_invalido"] += 1
        return out, modelos, modelos_com_teste, contratos
    if not isinstance(doc, dict):
        return out, modelos, modelos_com_teste, contratos

    def processa_no(no):
        nonlocal contratos
        nomes = []
        for chave in ("tests", "data_tests"):
            nomes += _nomes_de_testes(no.get(chave))
        for col in no.get("columns") or []:
            if isinstance(col, dict):
                for chave in ("tests", "data_tests"):
                    nomes += _nomes_de_testes(col.get(chave))
        cfg = no.get("config") or {}
        if isinstance(cfg, dict):
            ct = cfg.get("contract") or {}
            if isinstance(ct, dict) and ct.get("enforced"):
                contratos += 1
        if no.get("constraints"):
            contratos += 1
        for col in no.get("columns") or []:
            if isinstance(col, dict) and col.get("constraints"):
                contratos += 1
        return nomes

    for ch in ("models", "seeds", "snapshots"):
        for no in doc.get(ch) or []:
            if not isinstance(no, dict):
                continue
            if ch == "models":
                modelos += 1
            nomes = processa_no(no)
            if nomes:
                if ch == "models":
                    modelos_com_teste += 1
                out.update(nomes)

    for src in doc.get("sources") or []:
        if not isinstance(src, dict):
            continue
        if src.get("freshness"):
            out["_source_freshness"] += 1
        for tb in src.get("tables") or []:
            if isinstance(tb, dict):
                if tb.get("freshness"):
                    out["_source_freshness"] += 1
                out.update(processa_no(tb))

    if doc.get("unit_tests"):
        out["_unit_tests"] += len(doc["unit_tests"])

    return out, modelos, modelos_com_teste, contratos


def classificar(testes, pacotes, n_singular, n_reconc_singular, contratos):
    """Determina quais camadas de controle o projeto possui."""
    nomes = set(testes)
    tem = {
        "C1_contagem": bool(nomes & C1_CONTAGEM),
        "C2_genericos": bool(nomes & C2_GENERICOS),
        "C3_schema": bool(contratos or (nomes & C3_SCHEMA_TESTES)),
        "C4_valor": bool((nomes & C4_VALOR) or n_reconc_singular > 0
                         or "audit_helper" in pacotes),
    }
    if tem["C4_valor"]:
        pilha = "D_completa_com_valor"
    elif tem["C1_contagem"]:
        pilha = "C_dbt_mais_contagem"
    elif tem["C2_genericos"]:
        pilha = "B_padrao_dbt"
    elif tem["C3_schema"]:
        pilha = "A_so_schema"
    else:
        pilha = "Z_sem_controle"
    return tem, pilha


def analisar_tarball(blob, caminho_projeto):
    raiz_proj = str(Path(caminho_projeto).parent)
    testes = Counter()
    modelos = modelos_com_teste = contratos = 0
    n_singular = n_reconc = 0
    pacotes = set()
    arquivos_yaml = 0

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or m.size > 4_000_000:
                continue
            partes = m.name.split("/", 1)
            rel = partes[1] if len(partes) > 1 else ""
            if raiz_proj not in (".", "") and not rel.startswith(raiz_proj + "/"):
                continue
            sub = rel[len(raiz_proj) + 1:] if raiz_proj not in (".", "") else rel

            if sub.endswith((".yml", ".yaml")):
                nome = Path(sub).name
                try:
                    txt = tf.extractfile(m).read().decode("utf-8", "replace")
                except Exception:
                    continue
                if nome in ("packages.yml", "dependencies.yml"):
                    try:
                        d = yaml.safe_load(txt) or {}
                        for p in d.get("packages") or []:
                            if isinstance(p, dict):
                                alvo = p.get("package") or p.get("git") or ""
                                for conhecido in (PACOTES_C1 | PACOTES_C4 | {"dbt_utils"}):
                                    if conhecido in str(alvo):
                                        pacotes.add(conhecido)
                    except Exception:
                        pass
                    continue
                if nome == "dbt_project.yml":
                    continue
                if sub.startswith(("models/", "seeds/", "snapshots/")) or "/models/" in sub:
                    arquivos_yaml += 1
                    t, nm, nmt, ct = parsear_yaml_dbt(txt)
                    testes.update(t); modelos += nm
                    modelos_com_teste += nmt; contratos += ct

            elif sub.endswith(".sql"):
                if sub.startswith("tests/") or "/tests/" in sub:
                    n_singular += 1
                    try:
                        txt = tf.extractfile(m).read().decode("utf-8", "replace")
                        if PADRAO_RECONC.search(txt):
                            n_reconc += 1
                    except Exception:
                        pass
                elif sub.startswith("models/") or "/models/" in sub:
                    modelos = modelos  # contagem de modelos vem do YAML e do disco
    return dict(testes=testes, modelos=modelos, modelos_com_teste=modelos_com_teste,
                contratos=contratos, n_singular=n_singular, n_reconc=n_reconc,
                pacotes=pacotes, arquivos_yaml=arquivos_yaml)


def contar_modelos_sql(blob, caminho_projeto):
    raiz = str(Path(caminho_projeto).parent)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or not m.name.endswith(".sql"):
                continue
            partes = m.name.split("/", 1)
            rel = partes[1] if len(partes) > 1 else ""
            if raiz not in (".", "") and not rel.startswith(raiz + "/"):
                continue
            sub = rel[len(raiz) + 1:] if raiz not in (".", "") else rel
            if sub.startswith("models/") or "/models/" in sub:
                n += 1
    return n


# ----------------------------------------------------------------------------------
# FASE 3 — coleta
# ----------------------------------------------------------------------------------
def baixar_tarball(full_name, branch):
    destino = CACHE / (full_name.replace("/", "__") + ".tar.gz")
    if destino.exists():
        return destino.read_bytes()
    url = f"{API}/repos/{full_name}/tarball/{branch}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token()}",
        "User-Agent": "mineracao-cobertura-dbt/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        blob = r.read()
    destino.write_bytes(blob)
    return blob


def coletar():
    am = json.loads(AMOSTRA.read_text())
    exclusoes = Counter()
    with RESULT.open("w") as fout:
        fout.write(json.dumps({"_meta": am["_meta"]}) + "\n")
        for i, r in enumerate(am["repos"], 1):
            fn = r["full_name"]
            try:
                blob = baixar_tarball(fn, r["default_branch"])
                a = analisar_tarball(blob, r["caminho_projeto"])
                n_sql = contar_modelos_sql(blob, r["caminho_projeto"])
            except Exception as e:
                print(f"  [{i}] {fn}: FALHOU {type(e).__name__}", file=sys.stderr)
                exclusoes["erro_download"] += 1
                continue

            n_modelos = max(a["modelos"], n_sql)
            if n_sql == 0:
                exclusoes["E3_sem_modelos"] += 1
                print(f"  [{i}] {fn}: sem diretorio de modelos, excluido")
                continue
            if n_modelos < MIN_MODELOS:
                exclusoes["E4_poucos_modelos"] += 1
                print(f"  [{i}] {fn}: {n_modelos} modelos, abaixo do minimo, excluido")
                continue

            tem, pilha = classificar(a["testes"], a["pacotes"], a["n_singular"],
                                     a["n_reconc"], a["contratos"])
            genericos = {k: a["testes"].get(k, 0) for k in sorted(C2_GENERICOS)}
            reg = {
                "full_name": fn, "stars": r.get("stars"), "pushed_at": r.get("pushed_at"),
                "n_modelos_sql": n_sql, "n_modelos_yaml": a["modelos"],
                "n_modelos_com_teste": a["modelos_com_teste"],
                "cobertura_modelos": round(a["modelos_com_teste"] / n_sql, 4) if n_sql else 0,
                "n_testes_total": int(sum(v for k, v in a["testes"].items()
                                          if not k.startswith("_"))),
                "genericos": genericos,
                "n_contratos": a["contratos"],
                "n_singular": a["n_singular"], "n_singular_reconc": a["n_reconc"],
                "source_freshness": int(a["testes"].get("_source_freshness", 0)),
                "unit_tests": int(a["testes"].get("_unit_tests", 0)),
                "pacotes": sorted(a["pacotes"]),
                "camadas": tem, "pilha": pilha,
                "top_testes": dict(Counter({k: v for k, v in a["testes"].items()
                                            if not k.startswith("_")}).most_common(12)),
            }
            fout.write(json.dumps(reg) + "\n")
            print(f"  [{i}] {fn}: {n_sql} modelos, cobertura "
                  f"{reg['cobertura_modelos']:.0%}, pilha {pilha}")
    print(f"[coleta] exclusoes fase 3: {dict(exclusoes)} -> {RESULT}")


# ----------------------------------------------------------------------------------
# FASE 4 — relatorio
# ----------------------------------------------------------------------------------
def relatorio():
    linhas = [json.loads(l) for l in RESULT.open() if l.strip()]
    meta = linhas[0].get("_meta", {})
    regs = [l for l in linhas if "full_name" in l]
    if not regs:
        sys.exit("Sem registros. Rode a fase coletar primeiro.")
    n = len(regs)
    print("=" * 96)
    print(f"COBERTURA DE TESTES EM PROJETOS dbt PUBLICOS  —  n = {n}")
    print(f"frame: {meta.get('frame', {}).get('total', '?')} repos | "
          f"semente: {meta.get('seed')} | sorteio: {meta.get('sorteado_em')}")
    print("=" * 96)

    print("\nDISTRIBUICAO POR PILHA DE CONTROLES")
    c = Counter(r["pilha"] for r in regs)
    for p in ["Z_sem_controle", "A_so_schema", "B_padrao_dbt",
              "C_dbt_mais_contagem", "D_completa_com_valor"]:
        print(f"  {p:24s} {c.get(p,0):4d}  {c.get(p,0)/n:6.1%}")

    print("\nPRESENCA DE CADA CAMADA (nao exclusiva)")
    for k in ["C1_contagem", "C2_genericos", "C3_schema", "C4_valor"]:
        q = sum(1 for r in regs if r["camadas"][k])
        print(f"  {k:14s} {q:4d}  {q/n:6.1%}")

    print("\nCOBERTURA DE MODELOS POR TESTE (fracao dos modelos com ao menos um teste)")
    cob = sorted(r["cobertura_modelos"] for r in regs)
    def pct(p):
        return cob[min(int(p * len(cob)), len(cob) - 1)]
    print(f"  mediana {pct(0.5):.1%} | p25 {pct(0.25):.1%} | p75 {pct(0.75):.1%}")
    print(f"  projetos com ZERO testes declarados: "
          f"{sum(1 for r in regs if r['n_testes_total'] == 0)} "
          f"({sum(1 for r in regs if r['n_testes_total'] == 0)/n:.1%})")

    print("\nTESTES GENERICOS MAIS DECLARADOS")
    tot = Counter()
    for r in regs:
        tot.update(r["genericos"])
        tot.update({k: v for k, v in r["top_testes"].items() if k not in r["genericos"]})
    for k, v in tot.most_common(15):
        print(f"  {k:52s} {v:7d}")

    print("\nPACOTES DE TESTE EM USO")
    pk = Counter()
    for r in regs:
        pk.update(r["pacotes"])
    for k, v in pk.most_common():
        print(f"  {k:20s} {v:4d}  {v/n:6.1%}")

    print("\n" + "=" * 96)
    cego = sum(1 for r in regs if not r["camadas"]["C1_contagem"]
               and not r["camadas"]["C4_valor"])
    print(f"RESULTADO PARA O ARTIGO: {cego} de {n} projetos ({cego/n:.1%}) declaram "
          f"APENAS controles\nque o experimento mostrou detectarem ZERO de nove defeitos "
          f"semanticos.")
    print("=" * 96)


# ----------------------------------------------------------------------------------
# AUTOTESTE do parser, com gabarito conhecido
# ----------------------------------------------------------------------------------
FIXTURES = [
    # (yaml, modelos, modelos_com_teste, testes esperados, contratos)
    ("""
version: 2
models:
  - name: customers
    columns:
      - name: customer_id
        tests:
          - unique
          - not_null
  - name: orders
    tests:
      - dbt_utils.equal_rowcount:
          compare_model: ref('stg_orders')
    columns:
      - name: status
        tests:
          - accepted_values:
              values: ['placed', 'shipped']
""", 2, 2, {"unique": 1, "not_null": 1, "dbt_utils.equal_rowcount": 1,
            "accepted_values": 1}, 0),
    # dbt 1.8+: data_tests, contrato e constraints
    ("""
version: 2
models:
  - name: fct_revenue
    config:
      contract:
        enforced: true
    data_tests:
      - dbt_expectations.expect_column_sum_to_be_between:
          column_name: revenue
          min_value: 0
    columns:
      - name: revenue
        constraints:
          - type: not_null
        data_tests:
          - not_null
""", 1, 1, {"dbt_expectations.expect_column_sum_to_be_between": 1, "not_null": 1}, 2),
    # modelo sem nenhum teste
    ("""
version: 2
models:
  - name: dim_date
    description: calendario
""", 1, 0, {}, 0),
    # sources com freshness e testes
    ("""
version: 2
sources:
  - name: raw
    freshness:
      warn_after: {count: 12, period: hour}
    tables:
      - name: orders
        tests:
          - unique
""", 0, 0, {"unique": 1, "_source_freshness": 1}, 0),
]


def autoteste():
    ok = True
    for i, (txt, em, emt, esperado, ect) in enumerate(FIXTURES, 1):
        t, m, mt, ct = parsear_yaml_dbt(txt)
        reais = {k: v for k, v in t.items() if not k.startswith("_") or k in esperado}
        problemas = []
        if m != em:   problemas.append(f"modelos {m} != {em}")
        if mt != emt: problemas.append(f"modelos_com_teste {mt} != {emt}")
        if ct != ect: problemas.append(f"contratos {ct} != {ect}")
        if reais != esperado:
            problemas.append(f"testes {dict(reais)} != {esperado}")
        print(("  OK   " if not problemas else "  FALHA") + f" fixture {i}"
              + ("" if not problemas else "  " + "; ".join(problemas)))
        ok &= not problemas

    casos = [
        ({"unique": 1, "not_null": 3}, set(), 0, 0, 0, "B_padrao_dbt"),
        ({}, set(), 0, 0, 2, "A_so_schema"),
        ({}, set(), 0, 0, 0, "Z_sem_controle"),
        ({"unique": 1, "dbt_utils.equal_rowcount": 1}, {"dbt_utils"}, 0, 0, 0,
         "C_dbt_mais_contagem"),
        ({"unique": 1}, {"audit_helper"}, 2, 0, 0, "D_completa_com_valor"),
        ({"unique": 1}, set(), 3, 1, 0, "D_completa_com_valor"),
    ]
    for i, (t, p, ns, nr, ct, esperada) in enumerate(casos, 1):
        _, pilha = classificar(Counter(t), p, ns, nr, ct)
        bom = pilha == esperada
        print(("  OK   " if bom else "  FALHA") + f" classificacao {i}: {pilha}"
              + ("" if bom else f" != {esperada}"))
        ok &= bom

    print("\nAUTOTESTE " + ("PASSOU" if ok else "FALHOU"))
    return 0 if ok else 1


# ----------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fase", choices=["frame", "amostra", "coletar", "relatorio"])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--autoteste", action="store_true")
    a = ap.parse_args()
    if a.autoteste:
        sys.exit(autoteste())
    if a.fase == "frame":
        montar_frame()
    elif a.fase == "amostra":
        sortear(a.n, a.seed)
    elif a.fase == "coletar":
        coletar()
    elif a.fase == "relatorio":
        relatorio()
    else:
        ap.print_help()


if __name__ == "__main__":
    import urllib.parse  # usado em api()
    main()
