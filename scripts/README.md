### Utilitários Python para revisão do texto

Esta pasta reúne os scripts usados para inspecionar a estrutura do livro, resumir os documentos e gerar relatórios de apoio à revisão.

#### `menu.py`

É o ponto de entrada do utilitário de revisão. Ele expõe uma pequena interface de linha de comando com três modos:

`summary`
: mostra um panorama geral do repositório, com quantidade de documentos, número de arquivos de parágrafos e estatísticas sobre `Notes.json`.

`doc <numero>`
: mostra os detalhes de um documento específico, incluindo título, contagem de parágrafos, primeiro e último arquivo, e resumo das notas.

`report -o <arquivo>`
: gera um relatório em markdown com uma tabela consolidada de todos os documentos. O padrão é `review_dashboard.md` na raiz do repositório.

Exemplos de uso a partir da raiz do repositório:

`python scripts/menu.py summary`

`python scripts/menu.py doc 0`

`python scripts/menu.py report -o review_dashboard.md`

#### `repository.py`

Contém a classe `BookRepository`, que concentra a leitura da estrutura do acervo.
Ela localiza as pastas `Doc000` a `Doc196`, lista os arquivos `Par_*.md`, lê os `Notes.json` e monta os resumos usados pelo `menu.py`.

#### `requirements.txt`

Arquivo reservado para dependências do utilitário. Neste momento, o fluxo de revisão não depende de pacotes externos adicionais.

#### `env/`

Ambiente virtual local usado durante desenvolvimento. Não é necessário para entender o fluxo, mas pode ser útil se você quiser isolar a execução do Python.

#### Saída gerada

O comando de relatório cria um arquivo como `review_dashboard.md` na raiz do repositório. Esse arquivo resume o estado geral do texto e ajuda a localizar documentos que merecem atenção.

#### Versão web local

Se preferir revisar no navegador, use a aplicação FastAPI local em `review_web/main.py`.
Ela mostra o texto em inglês do `TR000.json`, o texto atual em português, uma área para a tradução corrigida e um painel de merge/diff visual.

Para executar a interface web a partir da raiz do repositório:

`python -m uvicorn review_web.main:app --reload --port 8000`

As dependências dessa interface estão listadas em `requirements-web.txt`.
