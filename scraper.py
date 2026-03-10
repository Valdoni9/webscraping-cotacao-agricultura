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

PRODUTOS_CONFIG = {
    'soja':            ('soja',            'Sorriso/MT',  'R$/Sc 60kg'),
    'milho':           ('milho',           'Sorriso/MT',  'R$/Sc 60kg'),
    'algodao':         ('algodao',         'Sorriso/MT',  'R$/@ 15kg'),
    'trigo':           ('trigo',           None,          ''),
    'arroz':           ('arroz',           'Sorriso/MT',  'R$/Sc 50kg'),
    'sorgo':           ('sorgo',           None,          ''),
    'boi':             ('boi-gordo',       'MT Norte',    'R$/@'),
    'frango':          ('frango',          None,          ''),
    'suinos':          ('suinos',          None,          ''),
    'leite':           ('leite',           None,          ''),
    'cafe':            ('cafe',            None,          ''),
    'sucroenergetico': ('sucroenergetico', None,          ''),
    'laranja':         ('laranja',         None,          ''),
}

# Fallback Agrolink: média mensal estadual MT, quando praça não tem cotação no dia
AGROLINK_FALLBACKS = {
    'milho': {
        'url':       'https://www.agrolink.com.br/cotacoes/historico/mt/milho-seco-sc-60kg',
        'unidade':   'R$/Sc 60kg',
        'indicador': 'MT Estadual/Agrolink (média mensal)',
    },
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
            if not valor or valor.lower() in ('s/ cotacao', 's/ cotação', 's/ cotaÃ§Ã£o', '-', ''):
                print(f'    {local}: sem cotação hoje')
                return None
            return {
                'indicador': local,
                'valor':     valor,
                'variacao':  var,
                'unidade':   unidade_override,
                'data':      datetime.now().strftime('%d/%m/%Y'),
            }
    return None

def extrair_agrolink(prod_id):
    """Busca média mensal estadual MT no Agrolink como fallback."""
    cfg = AGROLINK_FALLBACKS.get(prod_id)
    if not cfg:
        return None
    print(f'    → Agrolink fallback: {cfg["url"]}')
    soup = get_page(cfg['url'])
    if not soup:
        return None
    rows = soup.find_all('tr')
    for row in rows:
        tds = row.find_all('td')
        if len(tds) >= 2:
            mes_ano  = tds[0].get_text(strip=True)   # ex: "3/2026"
            estadual = tds[1].get_text(strip=True)   # ex: "46,1321"
            if '/' in mes_ano and ',' in estadual and any(c.isdigit() for c in estadual):
                print(f'    Agrolink [{mes_ano}] MT estadual: {estadual}')
                return {
                    'indicador': f'{cfg["indicador"]} ({mes_ano})',
                    'valor':     estadual,
                    'variacao':  '',
                    'unidade':   cfg['unidade'],
                    'data':      datetime.now().strftime('%d/%m/%Y'),
                    'fonte':     'agrolink',
                }
    print(f'    Agrolink: nenhum dado encontrado')
    return None

def extrair_primeiro_indicador(soup):
    tabelas = soup.find_all('table')
    for tabela in tabelas:
        headers = tabela.find_all('th')
        rows    = tabela.find_all('tr')
        if not headers or len(rows) < 2:
            continue
        col_names = [h.get_text(strip=True) for h in headers]
        idx_val = next((i for i, h in enumerate(col_names) if any(k in h.lower() for k in ('valor', 'r$', 'fechamento', 'preco', 'preço'))), 1)
        idx_var = next((i for i, h in enumerate(col_names) if 'varia' in h.lower()), min(2, len(col_names)-1))
        idx_dat = next((i for i, h in enumerate(col_names) if any(k in h.lower() for k in ('data', 'mes', 'contrato', 'praca'))), 0)
        bloco  = tabela.find_parent(['div', 'section'])
        titulo = ''
        if bloco:
            h = bloco.find(['h2', 'h3', 'h4'])
            if h:
                titulo = h.get_text(strip=True)
        unidade_el = next((h for h in headers if any(k in h.get_text().lower() for k in ('r$', 'valor', 'preco'))), None)
        unidade    = unidade_el.get_text(strip=True) if unidade_el else ''
        for row in rows[1:]:
            tds = row.find_all('td')
            if not tds or len(tds) < 2:
                continue
            try:
                val = tds[min(idx_val, len(tds)-1)].get_text(strip=True)
                var = tds[min(idx_var, len(tds)-1)].get_text(strip=True) if len(tds) > idx_var else ''
                dat = tds[min(idx_dat, len(tds)-1)].get_text(strip=True) if len(tds) > idx_dat else ''
                if val and val not in ('-', 's/ cotacao', 's/ cotação', '') and any(c.isdigit() for c in val):
                    return [{'indicador': titulo or dat or 'Indicador Principal',
                             'valor': val, 'variacao': var, 'unidade': unidade, 'data': dat}]
            except Exception:
                continue
    return []

def scrape_produto(prod_id, slug, termo, unidade_override):
    url = f'{BASE_URL}/{slug}'
    print(f'  [{prod_id}] {url}')
    soup = get_page(url)
    if not soup:
        return {'indicadores': []}
    if termo:
        ind = extrair_por_termo(soup, termo, unidade_override)
        if ind:
            print(f'    {ind["indicador"]}: {ind["valor"]} ({ind["variacao"]})')
            return {'indicadores': [ind]}
        # Sem cotação na praça → tenta Agrolink
        agl = extrair_agrolink(prod_id)
        if agl:
            return {'indicadores': [agl]}
        print(f'    usando primeiro indicador da página')
    inds = extrair_primeiro_indicador(soup)
    if inds:
        print(f'    fallback: {inds[0]["valor"]}')
    return {'indicadores': inds}

def scrape_cambio():
    """Busca PTAX do BCB. Tenta hoje; se ainda nao publicado, usa ultimo dia util."""
    try:
        from datetime import timedelta
        hoje = datetime.now()
        for i in range(6):
            dt = hoje - timedelta(days=i)
            if dt.weekday() >= 5:  # pula fim de semana
                continue
            data_str = dt.strftime('%m-%d-%Y')
            url = (
                f'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/'
                f'CotacaoDolarDia(dataCotacao=@dataCotacao)'
                f'?@dataCotacao=%27{data_str}%27&$format=json'
            )
            r     = requests.get(url, timeout=10)
            dados = r.json()
            if dados.get('value'):
                valor    = dados['value'][0]['cotacaoVenda']
                data_ref = dt.strftime('%d/%m/%Y')
                sufixo   = '' if dt.date() == hoje.date() else f' ({data_ref})'
                print(f'  Cambio: R$ {valor:.4f}{sufixo}')
                return {
                    'indicadores': [{
                        'indicador': f'Dolar (venda){sufixo}',
                        'valor':     f'{valor:.4f}',
                        'variacao':  '',
                        'unidade':   'BRL/USD',
                        'data':      data_ref,
                    }]
                }
        print('  Cambio: sem dados BCB')
        return {'indicadores': []}
    except Exception as e:
        print(f'  Cambio erro: {e}')
        return {'indicadores': []}

def main():
    print('=== Scraper AgroQuote - Sorriso/MT ===')
    resultado = {
        'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'dados': {},
    }
    for prod_id, (slug, termo, unidade) in PRODUTOS_CONFIG.items():
        resultado['dados'][prod_id] = scrape_produto(prod_id, slug, termo, unidade)
        time.sleep(0.8)
    resultado['dados']['cambio'] = scrape_cambio()
    with open('cotacoes.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f'cotacoes.json salvo - {datetime.now().strftime("%d/%m/%Y %H:%M")}')

if __name__ == '__main__':
    main()
