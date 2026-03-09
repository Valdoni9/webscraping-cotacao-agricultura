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

# Mapeamento: id_produto -> (slug_url, termo_busca_regiao)
# termo_busca_regiao: texto que identifica a linha de Sorriso/MT na tabela fÃ­sica
# Se None, pega o primeiro indicador disponÃ­vel (produtos sem dado regional de Sorriso)
PRODUTOS_CONFIG = {
    'soja':    ('soja',           'Sorriso/MT'),
    'milho':   ('milho',          'Sorriso/MT'),
    'algodao': ('algodao',        'Sorriso/MT'),
    'trigo':   ('trigo',          'Sorriso/MT'),
    'arroz':   ('arroz',          'Sorriso/MT'),
    'sorgo':   ('sorgo',          'Sorriso/MT'),
    'boi':     ('boi-gordo',      'Sorriso/MT'),
    'frango':  ('frango',         None),          # sem dado regional Sorriso
    'suinos':  ('suinos',         None),
    'leite':   ('leite',          'Sorriso/MT'),
    'cafe':    ('cafe',           None),
    'sucroenergetico': ('sucroenergetico', None),
    'laranja': ('laranja',        None),
}

def get_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f'  ERRO ao buscar {url}: {e}')
        return None

def extrair_sorriso(soup, termo):
    """
    Procura a linha com 'termo' nas tabelas de mercado fÃ­sico.
    Retorna dict com valor, variacao, indicador, unidade, data.
    """
    rows = soup.find_all('tr')
    for row in rows:
        tds = row.find_all('td')
        if len(tds) >= 2 and termo.lower() in tds[0].get_text(strip=True).lower():
            local = tds[0].get_text(strip=True)
            valor = tds[1].get_text(strip=True)
            var   = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            # Ignora linhas sem cotaÃ§Ã£o
            if not valor or valor.lower() in ('s/ cotaÃ§Ã£o', '-', ''):
                continue
            return {
                'indicador': local,
                'valor':     valor,
                'variacao':  var,
                'unidade':   'R$/Saca 60 kg',
                'data':      datetime.now().strftime('%d/%m/%Y'),
            }
    return None

def extrair_primeiro_indicador(soup):
    """Fallback: pega o primeiro bloco de cotaÃ§Ã£o (indicador principal)."""
    indicadores = []

    # Tenta tabelas com th/td (padrÃ£o do site)
    tabelas = soup.find_all('table')
    for tabela in tabelas:
        headers = tabela.find_all('th')
        rows    = tabela.find_all('tr')
        if not headers or not rows:
            continue
        col_names = [h.get_text(strip=True) for h in headers]

        # Determina Ã­ndices
        idx_val = next((i for i, h in enumerate(col_names) if 'valor' in h.lower() or 'r$' in h.lower() or 'fechamento' in h.lower()), 1)
        idx_var = next((i for i, h in enumerate(col_names) if 'varia' in h.lower()), 2)
        idx_dat = next((i for i, h in enumerate(col_names) if 'data' in h.lower() or 'mÃªs' in h.lower() or 'mes' in h.lower()), 0)

        # Tenta pegar o tÃ­tulo do bloco
        bloco = tabela.find_parent(['div', 'section'])
        titulo = ''
        if bloco:
            h = bloco.find(['h2', 'h3', 'h4'])
            if h:
                titulo = h.get_text(strip=True)
            subtitulo_el = bloco.find(class_=lambda c: c and ('fonte' in c or 'subtitle' in c or 'sub' in c))
            subtitulo = subtitulo_el.get_text(strip=True) if subtitulo_el else ''
        else:
            titulo = ''
            subtitulo = ''

        for row in rows[1:]:  # pula cabeÃ§alho
            tds = row.find_all('td')
            if not tds or len(tds) < 2:
                continue
            try:
                val = tds[idx_val].get_text(strip=True)
                var = tds[idx_var].get_text(strip=True) if len(tds) > idx_var else ''
                dat = tds[idx_dat].get_text(strip=True) if len(tds) > idx_dat else ''
                unidade_el = tabela.find('th', string=lambda s: s and ('valor' in s.lower() or 'r$' in s.lower()))
                unidade = unidade_el.get_text(strip=True) if unidade_el else ''

                if val and val not in ('-', 's/ cotaÃ§Ã£o'):
                    indicadores.append({
                        'indicador': titulo or 'Indicador Principal',
                        'valor':     val,
                        'variacao':  var,
                        'unidade':   unidade,
                        'data':      dat,
                    })
                    break  # sÃ³ o primeiro
            except Exception:
                continue
        if indicadores:
            break

    return indicadores

def scrape_produto(prod_id, slug, termo_sorriso):
    url = f'{BASE_URL}/{slug}'
    print(f'  [{prod_id}] {url}')
    soup = get_page(url)
    if not soup:
        return {'indicadores': []}

    resultado = {'indicadores': []}

    if termo_sorriso:
        ind = extrair_sorriso(soup, termo_sorriso)
        if ind:
            resultado['indicadores'] = [ind]
            print(f'    â Sorriso/MT: {ind["valor"]} ({ind["variacao"]})')
        else:
            print(f'    â  Sorriso/MT nÃ£o encontrado, usando fallback')
            resultado['indicadores'] = extrair_primeiro_indicador(soup)
    else:
        resultado['indicadores'] = extrair_primeiro_indicador(soup)
        if resultado['indicadores']:
            print(f'    â Fallback: {resultado["indicadores"][0]["valor"]}')

    return resultado

def scrape_cambio():
    try:
        url = 'https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao=%27{data}%27&$format=json'.format(
            data=datetime.now().strftime('%m-%d-%Y')
        )
        r = requests.get(url, timeout=10)
        dados = r.json()
        valor = dados['value'][0]['cotacaoVenda'] if dados.get('value') else None
        return {'indicadores': [{'indicador': 'DÃ³lar (venda)', 'valor': f'{valor:.4f}' if valor else 'â', 'variacao': '', 'unidade': 'BRL/USD', 'data': datetime.now().strftime('%d/%m/%Y')}]}
    except Exception as e:
        print(f'  CÃ¢mbio erro: {e}')
        return {'indicadores': []}

def main():
    print('=== Scraper AgroQuote â Sorriso/MT ===')
    resultado = {'gerado_em': datetime.now().strftime('%d/%m/%Y %H:%M'), 'dados': {}}

    for prod_id, (slug, termo) in PRODUTOS_CONFIG.items():
        resultado['dados'][prod_id] = scrape_produto(prod_id, slug, termo)
        time.sleep(0.8)

    resultado['dados']['cambio'] = scrape_cambio()

    with open('cotacoes.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f'\nâ cotacoes.json salvo â {datetime.now().strftime("%d/%m/%Y %H:%M")}')

if __name__ == '__main__':
    main()
