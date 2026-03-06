#!/usr/bin/env python3
"""
scraper.py — Coleta cotações agrícolas do Notícias Agrícolas
e câmbio do Banco Central do Brasil.
Gera cotacoes.json para ser servido pelo GitHub Pages.
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, date
import time

PRODUTOS = [
    {"id": "soja",      "nome": "Soja",         "emoji": "🫘", "url": "soja",      "cat": "graos"},
    {"id": "milho",     "nome": "Milho",        "emoji": "🌽", "url": "milho",     "cat": "graos"},
    {"id": "trigo",     "nome": "Trigo",        "emoji": "🌾", "url": "trigo",     "cat": "graos"},
    {"id": "arroz",     "nome": "Arroz",        "emoji": "🍚", "url": "arroz",     "cat": "graos"},
    {"id": "algodao",   "nome": "Algodão",      "emoji": "☁️",  "url": "algodao",   "cat": "graos"},
    {"id": "sorgo",     "nome": "Sorgo",        "emoji": "🌿", "url": "sorgo",     "cat": "graos"},
    {"id": "boi",       "nome": "Boi Gordo",    "emoji": "🐂", "url": "boi-gordo", "cat": "proteina"},
    {"id": "frango",    "nome": "Frango",       "emoji": "🐔", "url": "frango",    "cat": "proteina"},
    {"id": "suinos",    "nome": "Suínos",       "emoji": "🐷", "url": "suinos",    "cat": "proteina"},
    {"id": "leite",     "nome": "Leite",        "emoji": "🥛", "url": "leite",     "cat": "proteina"},
    {"id": "cafe",      "nome": "Café",         "emoji": "☕", "url": "cafe",      "cat": "tropicais"},
    {"id": "acucar",    "nome": "Sucroenergético","emoji": "🍬","url": "sucroenergetico","cat": "tropicais"},
    {"id": "laranja",   "nome": "Laranja",      "emoji": "🍊", "url": "laranja",   "cat": "tropicais"},
]

BASE_URL = "https://www.noticiasagricolas.com.br/cotacoes/"
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

def limpar(texto):
    if not texto:
        return None
    return texto.strip().replace("\xa0", " ").replace("\n", " ").strip()

def scrape_produto(produto):
    url = BASE_URL + produto["url"]
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Erro HTTP: {e}")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    indicadores = []
    for bloco in soup.select(".cotacao"):
        titulo_el = bloco.select_one("h2")
        tabela    = bloco.select_one("table.cot-fisicas")
        if not titulo_el or not tabela:
            continue
        titulo = limpar(titulo_el.get_text())
        ths = [limpar(th.get_text()) for th in tabela.select("th")]
        unidade = ths[1] if len(ths) > 1 else "R$"
        for tr in tabela.select("tr"):
            tds = tr.select("td")
            if len(tds) < 2:
                continue
            data_txt  = limpar(tds[0].get_text())
            valor_txt = limpar(tds[1].get_text())
            var_txt   = limpar(tds[2].get_text()) if len(tds) > 2 else None
            if not data_txt or "/" not in data_txt:
                continue
            if "tualizado" in data_txt:
                continue
            indicadores.append({"indicador": titulo, "unidade": unidade,
                                 "data": data_txt, "valor": valor_txt, "variacao": var_txt})
            break
        if len(indicadores) >= 3:
            break
    return indicadores if indicadores else None

def fetch_dolar():
    hoje = date.today()
    data_bcb = hoje.strftime("%m-%d-%Y")
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        f"CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)?"
        f"@moeda='USD'&@dataCotacao='{data_bcb}'"
        "&$top=5&$format=json&$select=cotacaoVenda,dataHoraCotacao"
        "&$orderby=dataHoraCotacao desc"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        valores = resp.json().get("value", [])
        if valores:
            v = valores[0]
            return {"indicador": "USD/BRL — Banco Central", "unidade": "R$",
                    "data": hoje.strftime("%d/%m/%Y"), "valor": str(v["cotacaoVenda"]), "variacao": None}
    except Exception as e:
        print(f"  Erro BCB: {e}")
    return None

def main():
    resultado = {}
    print("=" * 55)
    print("  AgroQuote — Scraper de Cotacoes")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 55)
    for p in PRODUTOS:
        print(f"\n[{p['id'].upper()}] {p['nome']}...")
        indicadores = scrape_produto(p)
        if indicadores:
            resultado[p["id"]] = {"nome": p["nome"], "emoji": p["emoji"], "cat": p["cat"],
                                   "fonte": "Noticias Agricolas / CEPEA", "indicadores": indicadores, "erro": None}
            for ind in indicadores:
                print(f"  OK {ind['indicador']}: {ind['valor']} ({ind['variacao']}) — {ind['data']}")
        else:
            resultado[p["id"]] = {"nome": p["nome"], "emoji": p["emoji"], "cat": p["cat"],
                                   "fonte": "Noticias Agricolas", "indicadores": [], "erro": "Sem dados"}
            print(f"  AVISO: Nenhum indicador encontrado")
        time.sleep(0.8)
    print(f"\n[DOLAR] Dolar (BCB)...")
    dolar = fetch_dolar()
    resultado["dolar"] = {"nome": "Dolar (USD/BRL)", "emoji": "💵", "cat": "cambio",
                           "fonte": "Banco Central do Brasil",
                           "indicadores": [dolar] if dolar else [],
                           "erro": None if dolar else "Cotacao nao disponivel hoje"}
    if dolar:
        print(f"  OK USD/BRL: R$ {dolar['valor']} — {dolar['data']}")
    saida = {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
             "fonte_site": "https://www.noticiasagricolas.com.br/cotacoes/",
             "dados": resultado}
    with open("cotacoes.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    total_ok = sum(1 for v in resultado.values() if v["indicadores"])
    print(f"\n{'=' * 55}")
    print(f"  cotacoes.json salvo — {total_ok}/{len(resultado)} produtos com dados")
    print("=" * 55)

if __name__ == "__main__":
    main()
