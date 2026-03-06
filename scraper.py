import json, re, time, datetime, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

def fetch_cambio():
    for delta in [0, 1, 2, 3]:
        try:
            d = (datetime.date.today() - datetime.timedelta(days=delta)).strftime("%m-%d-%Y")
            url = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                   "CotacaoDolarDia(dataCotacao=@dataCotacao)"
                   "?@dataCotacao='" + d + "'&$top=1&$format=json&$select=cotacaoVenda")
            r = requests.get(url, headers=HEADERS, timeout=10)
            val = r.json()["value"]
            if val:
                return round(val[0]["cotacaoVenda"], 4)
        except Exception:
            pass
    return None

def scrape_bbm():
    url = "https://www.bbmbolsa.com.br/cotacoes-agricolas/"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    html = r.text
    resultados = {}
    mapa = [
        ("soja",  "Soja",  "R$/60kg"),
        ("milho", "Milho", "R$/60kg"),
    ]
    for pid, nome, unidade in mapa:
        tag = "<h4>" + nome + "</h4>"
        idx = html.lower().find(tag.lower())
        if idx == -1:
            continue
        chunk = html[idx:idx+8000]
        idx_s = chunk.find("Sorriso")
        if idx_s == -1:
            continue
        snippet = chunk[idx_s:idx_s+500]
        clean = re.sub(r"<[^>]+>", " ", snippet)
        clean = re.sub(r"\s+", " ", clean).strip()
        m = re.search(r"Sorriso[\D]+R\$\s*([\d\.,]+)\s+([-\d,]+%)\s+([-\d,]+%)", clean)
        if m:
            resultados[pid] = {
                "produto": nome,
                "valor": "R$ " + m.group(1),
                "variacao": m.group(2),
                "unidade": unidade,
                "praca": "Sorriso/MT",
                "fonte": "BBM Bolsa",
            }
    return resultados

CEPEA_URLS = {
    "boi-gordo":       ("https://www.noticiasagricolas.com.br/cotacoes/boi-gordo", "R$/arroba", "Boi Gordo"),
    "cafe":            ("https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-esalq-bmf", "R$/saca", "Cafe"),
    "algodao":         ("https://www.noticiasagricolas.com.br/cotacoes/algodao/algodao-esalq", "R$/arroba", "Algodao"),
    "trigo":           ("https://www.noticiasagricolas.com.br/cotacoes/trigo/trigo-parana", "R$/sc", "Trigo"),
    "arroz":           ("https://www.noticiasagricolas.com.br/cotacoes/arroz/arroz-esalq", "R$/sc", "Arroz"),
    "frango":          ("https://www.noticiasagricolas.com.br/cotacoes/frango/frango-embrapa", "R$/kg", "Frango"),
    "suinos":          ("https://www.noticiasagricolas.com.br/cotacoes/suinos/suinos-cepea-esalq", "R$/kg", "Suinos"),
    "leite":           ("https://www.noticiasagricolas.com.br/cotacoes/leite/leite-cepea", "R$/litro", "Leite"),
    "sorgo":           ("https://www.noticiasagricolas.com.br/cotacoes/milho/sorgo-cepea-esalq", "R$/sc", "Sorgo"),
    "sucroenergetico": ("https://www.noticiasagricolas.com.br/cotacoes/cana-de-acucar/acucar-cristal-esalq", "R$/sc", "Acucar"),
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
        for linha in tabela.find_all("tr")[1:3]:
            cols = [td.get_text(strip=True) for td in linha.find_all(["td", "th"])]
            if len(cols) >= 2 and cols[1] not in ["-", ""]:
                return {
                    "produto": nome,
                    "valor": cols[1],
                    "variacao": cols[2] if len(cols) > 2 else "-",
                    "unidade": unidade,
                    "praca": "CEPEA/ESALQ",
                    "fonte": "Noticias Agricolas",
                }
    except Exception as e:
        print("  ERRO " + pid + ": " + str(e))
    return None

def main():
    dados = {}
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    print("=== AgroQuote Sorriso/MT ===")

    cambio = fetch_cambio()
    print("USD/BRL = " + str(cambio))

    try:
        bbm = scrape_bbm()
        for pid, item in bbm.items():
            dados[pid] = item
            print(pid + ": " + item["valor"])
    except Exception as e:
        print("ERRO BBM: " + str(e))

    for pid, (url, unidade, nome) in CEPEA_URLS.items():
        result = scrape_cepea(pid, url, unidade, nome)
        if result:
            dados[pid] = result
            print(pid + ": " + result["valor"])
        time.sleep(0.5)

    saida = {
        "gerado_em": agora,
        "cambio_usd_brl": cambio,
        "praca_principal": "Sorriso/MT",
        "dados": dados,
    }
    with open("cotacoes.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print("OK: " + str(len(dados)) + " produtos")

if __name__ == "__main__":
    main()
