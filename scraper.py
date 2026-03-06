"""
Scraper de cotações agropecuárias – Sorriso/MT
Fonte: Bolsa Brasileira de Mercadorias (BBM) – mercado físico disponível
Câmbio: API BCB (Banco Central do Brasil)
"""

import json, re, time, datetime, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# ─── Câmbio USD/BRL via BCB ────────────────────────────────────────────────
def fetch_cambio():
    try:
        url = (
            "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
            "CotacaoDolarDia(dataCotacao=@dataCotacao)"
            "?@dataCotacao='%s'&$top=1&$format=json&$select=cotacaoVenda"
            % datetime.date.today().strftime("%m-%d-%Y")
        )
        r = requests.get(url, headers=HEADERS, timeout=10)
        val = r.json()["value"]
        if val:
            return round(val[0]["cotacaoVenda"], 4)
    except Exception:
        pass
    try:
        ontem = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%m-%d-%Y")
        url2 = (
            "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
            "CotacaoDolarDia(dataCotacao=@dataCotacao)"
            "?@dataCotacao='%s'&$top=1&$format=json&$select=cotacaoVenda" % ontem
        )
        r2 = requests.get(url2, headers=HEADERS, timeout=10)
        val2 = r2.json()["value"]
        if val2:
            return round(val2[0]["cotacaoVenda"], 4)
    except Exception:
        pass
    return None

def parse_brl(s):
    s = re.sub(r"[R$\\s]", "", s).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

# ─── Scraping BBM Bolsa (Sorriso/MT) ───────────────────────────────────────
def scrape_bbm():
    url = "https://www.bbmbolsa.com.br/cotacoes-agricolas/"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text

    def find_sorriso(produto_keyword, unidade, nome):
        idx_prod = html.lower().find(("<h4>" + produto_keyword.lower() + "</h4>"))
        if idx_prod == -1:
            idx_prod = html.lower().find(produto_keyword.lower() + "</h4>")
        if idx_prod == -1:
            return None
        chunk = html[idx_prod:idx_prod+8000]
        idx_s = chunk.find("Sorriso")
        if idx_s == -1:
            return None
        snippet = chunk[idx_s:idx_s+500]
        clean = re.sub(r"<[^>]+>", " ", snippet)
        clean = re.sub(r"\\s+", " ", clean).strip()
        m = re.search(
            r"Sorriso[^\\d]*R\\$\\s*([\\d\\.,]+)\\s+([-\\d,]+%)\\s+([-\\d,]+%)",
            clean
        )
        if m:
            return {
                "produto": nome,
                "valor": "R$ " + m.group(1),
                "variacao": m.group(2),
                "unidade": unidade,
                "praca": "Sorriso/MT",
                "fonte": "BBM Bolsa",
            }
        return None

    resultados = {}
    soja = find_sorriso("Soja", "R$/60kg", "Soja")
    if soja:
        resultados["soja"] = soja
    milho = find_sorriso("Milho", "R$/60kg", "Milho")
    if milho:
        resultados["milho"] = milho
    return resultados

# ─── Cotações CEPEA/ESALQ via Notícias Agrícolas ───────────────────────────
CEPEA_URLS = {
    "boi-gordo":       ("https://www.noticiasagricolas.com.br/cotacoes/boi-gordo", "R$/arroba", "Boi Gordo"),
    "cafe":            ("https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-esalq-bmf", "R$/saca", "Café"),
    "algodao":         ("https://www.noticiasagricolas.com.br/cotacoes/algodao/algodao-esalq", "R$/arroba", "Algodão"),
    "trigo":           ("https://www.noticiasagricolas.com.br/cotacoes/trigo/trigo-parana", "R$/sc", "Trigo"),
    "arroz":           ("https://www.noticiasagricolas.com.br/cotacoes/arroz/arroz-esalq", "R$/sc", "Arroz"),
    "frango":          ("https://www.noticiasagricolas.com.br/cotacoes/frango/frango-embrapa", "R$/kg", "Frango"),
    "suinos":          ("https://www.noticiasagricolas.com.br/cotacoes/suinos/suinos-cepea-esalq", "R$/kg", "Suínos"),
    "leite":           ("https://www.noticiasagricolas.com.br/cotacoes/leite/leite-cepea", "R$/litro", "Leite"),
    "sorgo":           ("https://www.noticiasagricolas.com.br/cotacoes/milho/sorgo-cepea-esalq", "R$/sc", "Sorgo"),
    "sucroenergetico": ("https://www.noticiasagricolas.com.br/cotacoes/cana-de-acucar/acucar-cristal-esalq", "R$/sc", "Açúcar"),
    "laranja":         ("https://www.noticiasagricolas.com.br/cotacoes/laranja/laranja-esalq", "R$/cx", "Laranja"),
}

def scrape_cepea(pid, url, unidade, nome):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tabela = soup.find("table", class_="cot-fisio") or soup.find("table")
        if tabela is None:
            return None
        linhas = tabela.find_all("tr")
        for linha in linhas[1:3]:
            cols = [td.get_text(strip=True) for td in linha.find_all(["td", "th"])]
            if len(cols) >= 2:
                valor = cols[1] if len(cols) > 1 else cols[0]
                variacao = cols[2] if len(cols) > 2 else "–"
                if valor and valor not in ["-", "–", ""]:
                    return {
                        "produto": nome,
                        "valor": valor,
                        "variacao": variacao,
                        "unidade": unidade,
                        "praca": "CEPEA/ESALQ",
                        "fonte": "Notícias Agrícolas",
                    }
    except Exception as e:
        print(f"  ERRO {pid}: {e}")
    return None

# ─── MAIN ──────────────────────────────────────────────────────────────────
def main():
    dados = {}
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    print("=== Scraper AgroQuote – Sorriso/MT ===")

    print("\n[1] Câmbio USD/BRL...")
    cambio = fetch_cambio()
    print(f"    USD/BRL = {cambio}")

    print("\n[2] BBM Bolsa – Sorriso/MT...")
    try:
        bbm = scrape_bbm()
        for pid, item in bbm.items():
            dados[pid] = item
            print(f"    {pid}: {item['valor']} ({item['variacao']})")
    except Exception as e:
        print(f"    ERRO BBM: {e}")

    print("\n[3] CEPEA/Notícias Agrícolas...")
    for pid, (url, unidade, nome) in CEPEA_URLS.items():
        print(f"    {pid}...", end=" ", flush=True)
        result = scrape_cepea(pid, url, unidade, nome)
        if result:
            dados[pid] = result
            print(f"{result['valor']} ({result['variacao']})")
        else:
            print("sem dados")
        time.sleep(0.5)

    saida = {
        "gerado_em": agora,
        "cambio_usd_brl": cambio,
        "praca_principal": "Sorriso/MT",
        "dados": dados,
    }
    with open("cotacoes.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(f"\n✅ cotacoes.json gerado com {len(dados)} produtos.")

if __name__ == "__main__":
    main()
