import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

BASE_URL = 'https://www.noticiasagricolas.com.br/cotacoes'

# Configuracao por produto:
# (slug, termo_busca, unidade_override)
# termo_busca: None = pega primeiro indicador da pagina
#              string = procura linha contendo esse texto na tabela de precos fisicos
PRODUTOS_CONFIG = {
    'soja':    ('soja',           'Sorriso/MT',   'R$/Sc 60kg'),
    'milho':   ('milho',          'Sorriso/MT',   'R$/Sc 60kg'),
    'algodao': ('algodao',        'Sorriso/MT',   'R$/@ 15kg'),
    'trigo':   ('trigo',          None,           ''),
    'arroz':   ('arroz',          'Sorriso/MT',   'R$/Sc 50kg'),
    'sorgo':   ('sorgo',          None,           ''),
    'boi':     ('boi-gordo',      'MT Norte',     'R$/@'),
    'frango':  ('frango',         None,           ''),
    'suinos':  ('suinos',         None,           ''),
    'leite':   ('leite',          None,           ''),
    'cafe':    ('cafe',           None,           ''),
    'sucroenergetico': ('sucroenergetico', None, ''),
    'laranja': ('laranja',        None,           ''),
}

def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f'  ERRO ao buscar {url}: {e}')
        return None

def extrair_por_termo(soup, termo, unidade_override=''):
    rows = soup.find_all('tr')
    for row in rows:
        tds = row.find_all('td')
        if len(tds) >= 2 and termo.lower() in tds[0].get_text(strip=True).lower():
            local = tds[0].get_text(strip=True)
            valor = tds[1].get_text(strip=True)
            var   = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            if not valor or valor.lower() in ('s/ cotacao', 's/ cotaÃ§Ã£o', '-', ''):
                print(f'    {local}: sem cotacao hoje - usando fallback')
                return None
            return {
                'indicador': local,
                'valor':     valor,
                'variacao':  var,
                'unidade':   unidade_override,
                'data':      datetime.now().strftime('%d/%m/%Y'),
            }
    return None

def extrair_primeiro_indicador(soup):
    tabelas = soup.find_all('table')
    for tabela in tabelas:
        headers = tabela.find_all('th')
        rows    = tabela.find_all('tr')
        if not headers or len(rows) < 2:
            continue
        col_names = [h.get_text(strip=True) for h in headers]
        idx_val = next((i for i, h in enumerate(col_names)
                        if any(k in h.lower() for k in ('valor', 'r$', 'fechamento', 'preco', 'preÃ§o'))), 1)
        idx_var = next((i for i, h in enumerate(col_names)
                        if 'varia' in h.lower()), min(2, len(col_names)-1))
        idx_dat = next((i for i, h in enumerate(col_names)
                        if any(k in h.lower() for k in ('data', 'mes', 'contrato', 'praca'))), 0)
        bloco = tabela.find_parent(['div', 'section'])
        titulo = ''
        if bloco:
            h = bloco.find(['h2', 'h3', 'h4'])
            if h: titulo = h.get_text(strip=True)
        unidade_el = next((h for h in headers if any(k in h.get_text().lower()
                            for k in ('r$', 'valor', 'preco'))), None)
        unidade = unidade_el.get_text(strip=True) if unidade_el else ''
        for row in rows[1:]:
            tds = row.find_all('td')
            if not tds or len(tds) < 2: continue
            try:
                val = tds[min(idx_val, len(tds)-1)].get_text(strip=True)
                var = tds[min(idx_var, len(tds)-1)].get_text(strip=True) if len(tds) > idx_var else ''
                dat = tds[min(idx_dat, len(tds)-1)].get_text(strip=True) if len(tds) > idx_dat else ''
                if val and val not in ('-', 's!/ cotacao', 's! cotaÃ§Ã£o', '') and any(c.isdigit() for c in val):
                    return [{'indicador': titulo or dat or 'Indicador Principal',
                             'valor': val, 'variacao': var, 'unidade': unidade, 'data': dat}]
            except Exception: continue
    return []

def scrape_produto(prod_id, slug, termo, unidade_override):
    url = f'{BASE_URL}/{slug}'
    print(f'  [{prod_id}] {url}')
    soup = get_page(url)
    if not soup: return {'indicadores': []}
    if termo:
        ind = extrair_por_termo(soup, termo, unidade_override)
        if ind:
            print(f'    {ind["indicador"]}: {ind["valor"]} ({ind["variacao"]})')
            return {'indicadores': [ind]}
        print(f'    "termo" sem cotacao - usando fallback')
    inds = extrair_primeiro_indicador(soup)
    if inds: print(f'    fallback: {inds[0]["valor"]}')
    return {'indicadores': inds}

def scrape_cambio():
    try:
        data_str = datetime.now().strftime('%m-%d-%Y')
        url = (f'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/'
               f'CotacaoDolarDia(dataCotacao=@dataCotacao)'
               f'?@dataCotacao=%27{data_str}%27&$format=json')
        r = requests.get(url, timeout=10)
        dados = r.json()
        valor = dados['value'][0]['cotacaoVenda'] if dados.get('value') else None
        return {'indicadores': [{'indicador': 'Dolar (venda)', 'valor': f'{valor:.4f}' if valor else '-', 'variacao': '', 'unidade': 'BRL/USD', 'data': datetime.now().strftime('%d/%m/%Y')}]}
    except Exception as e:
        print(f'  Cambio erro: {e}')
        return {'indicadores': []}

def main():
    print('=== Scraper AgroQuote - Sorriso/MT ===')
    resultado = {'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'), 'dados': {}}
    for prod_id, (slug, termo, unidade) in PRODUTOS_CONFIG.items():
        resultado['dados'][prod_id] = scrape_produto(prod_id, slug, termo, unidade)
        time.sleep(0.8)
    resultado['dados']['cambio'] = scrape_cambio()
    with open('cotacoes.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f'cotacoes.json salvo - {datetime.now().strftime("%d/%m/%Y %H:%M")}')

if __name__ == '__main__':
    main()
