# Projeto Individual 4 — Pipeline de UDA para o Setor Habitacional

## Identificação

- **Aluno:** Hian Praxedes de Souza Oliveira - 200019520
- **Aluno:** Silas Neres - 200043536
- **Projeto:** Projeto Individual 4 — Pipeline de UDA (Unstructured Data Analysis)
- **Tema:** Extração semântica de dados de PDFs de Relações com Investidores do setor habitacional

## Descrição

Este projeto implementa um pipeline de UDA para coletar, processar e disponibilizar dados de relatórios e prévias operacionais em PDF publicados por incorporadoras brasileiras em seus portais de Relações com Investidores.

A solução monitora fontes de RI, identifica links de PDFs relevantes, calcula uma assinatura única do documento com SHA-256, evita reprocessamento de arquivos já catalogados, extrai informações com apoio de LLM e disponibiliza os dados estruturados por meio de uma API REST.

O projeto utiliza uma abordagem semântica para lidar com a variação de layouts dos PDFs. Em vez de depender de coordenadas fixas, expressões regulares rígidas ou posições específicas de tabelas, o pipeline envia o conteúdo extraído para um modelo de IA com contrato de saída estruturado.

## Problema abordado

Relatórios operacionais e financeiros de incorporadoras costumam ser publicados em PDFs com formatos variados, como tabelas, apresentações, releases e boletins consolidados.

Esses documentos contêm dados importantes para análise do setor habitacional, mas as informações estão em formato não estruturado. Isso dificulta a geração de séries históricas, consultas por empresa, comparação entre trimestres e alimentação de relatórios de conjuntura.

O problema abordado pelo projeto é transformar esses documentos não estruturados em dados estruturados, rastreáveis e consultáveis, evitando duplicidade e preservando a origem de cada informação extraída.

## Objetivo

Criar um pipeline automatizado capaz de:

- monitorar páginas de RI/Central de Resultados das incorporadoras;
- detectar novos PDFs publicados;
- baixar ou receber PDFs para processamento;
- calcular hash SHA-256 para evitar duplicidade;
- registrar cada documento em um catálogo de dados;
- extrair dados operacionais e percentuais com apoio de LLM;
- validar a resposta da IA com schemas Pydantic;
- persistir os dados estruturados em banco relacional;
- preservar a linhagem dos dados extraídos;
- disponibilizar consultas por API REST/JSON;
- permitir filtros por empresa, ano e trimestre.

## Solução final

A solução final escolhida foi uma **implementação nativa em Python com FastAPI, PostgreSQL, PyMuPDF, Gemini e Pydantic**.

O fluxo final é:

    Scheduler / Execução manual
    ↓
    Scraper das páginas de RI
    ↓
    Detecção de links de PDFs relevantes
    ↓
    Download do PDF
    ↓
    Cálculo do hash SHA-256
    ↓
    PDF já existe no catálogo?
    ├── true → Ignorar documento e retornar ja_processado
    └── false → Registrar no catálogo
              ↓
              Parsing do PDF com PyMuPDF
              ↓
              Detecção do tipo de documento
              ├── Boletim de Conjuntura → Extração semântica de variações percentuais
              ├── Prévia Operacional textual → Extração semântica de valores absolutos
              └── PDF visual/slides → Extração multimodal com imagens
              ↓
              Validação por contrato Pydantic
              ↓
              Persistência no PostgreSQL
              ↓
              API REST para consulta dos dados

A arquitetura atende às três camadas obrigatórias do desafio:

1. **Camada de Extração de Dados:** scraper, download, parsing com PyMuPDF e fallback visual para PDFs em formato de apresentação.
2. **Contrato Semântico dos Dados:** prompts e schemas Pydantic para forçar saída estruturada, tratar ausências como `null` e evitar alucinações.
3. **Catálogo de Dados e Linhagem:** tabelas que registram URL, hash, empresa, nome do arquivo, status de processamento e vínculo entre cada dado extraído e seu PDF de origem.

## Tecnologias utilizadas

- Python
- FastAPI
- Uvicorn
- PostgreSQL
- Docker Compose
- SQLAlchemy
- APScheduler
- PyMuPDF
- BeautifulSoup
- Requests
- Gemini
- Pydantic
- JSON
- Git
- GitHub

## Integrações

O projeto possui integração com três tipos principais de fonte ou serviço externo.

### Portais de RI das empresas

As fontes de dados são páginas de Relações com Investidores e Centrais de Resultados das incorporadoras.

A lista de empresas e páginas monitoradas é configurada em:

    src/config.py

Exemplos de empresas consideradas no escopo:

- MRV
- Direcional
- Cury
- Tenda
- Plano & Plano
- Pacaembu

### Gemini

O Gemini é usado como motor de extração semântica.

A IA recebe o texto ou as imagens do PDF e retorna uma resposta estruturada conforme os schemas definidos no projeto.

As principais regras passadas à IA são:

- não inventar valores;
- retornar `null` quando a informação não estiver no documento;
- extrair somente valores absolutos em prévias operacionais;
- não confundir percentuais de variação com valores absolutos;
- capturar todas as empresas e métricas presentes no boletim;
- responder em JSON validável pelo schema.

### PostgreSQL

O PostgreSQL é usado como camada de persistência.

O banco armazena:

- catálogo dos PDFs processados;
- hash SHA-256 dos documentos;
- dados operacionais por empresa, ano e trimestre;
- boletins de conjuntura;
- totais e variações por empresa;
- linhagem dos dados extraídos.

## Estrutura do projeto

    projeto-4/
    ├── .env.example
    ├── .gitignore
    ├── docker-compose.yml
    ├── exemplo_Boletim_Conjuntura_2025_3T.pdf
    ├── main.py
    ├── README.md
    ├── requirements.txt
    ├── scheduler.py
    ├── docs/
    │   └── evidence/
    └── src/
        ├── __init__.py
        ├── api.py
        ├── config.py
        ├── database.py
        ├── extractor.py
        ├── pdf_parser.py
        ├── pipeline.py
        ├── schemas.py
        └── scraper.py

## Soluções avaliadas

### Solution A — Processamento manual de PDF único

A primeira alternativa seria processar apenas um PDF específico informado manualmente no código.

Essa solução é simples, mas não atende bem ao enunciado, pois não observa fontes continuamente, não detecta novos documentos e não demonstra robustez contra diferentes empresas e layouts.

### Solution B — Extração baseada em regras fixas

A segunda alternativa seria usar regras tradicionais, como expressões regulares, coordenadas fixas ou posições específicas em tabelas.

Essa abordagem pode funcionar para um PDF específico, mas é frágil quando os relatórios mudam de layout, quando os dados aparecem em slides ou quando as empresas reorganizam a apresentação das informações.

### Solution C — Pipeline UDA com catálogo, IA e API

A terceira alternativa combina scraper, catálogo de dados, idempotência por hash, parsing de PDF, extração semântica com LLM, contrato Pydantic, banco relacional e API REST.

Essa foi a solução escolhida por ser mais aderente ao desafio, pois permite lidar com documentos de layouts diferentes e preserva rastreabilidade dos dados extraídos.

## Como testar o projeto

Para testar o projeto, é necessário configurar as variáveis de ambiente, subir o banco de dados e executar a API.

### 1. Configurar variáveis de ambiente

Copiar o arquivo de exemplo:

    cp .env.example .env

No Windows PowerShell:

    Copy-Item .env.example .env

Editar o arquivo `.env` e preencher a chave do Gemini:

    GEMINI_API_KEY=sua_chave_aqui
    DATABASE_URL=postgresql://uda_user:uda_password@localhost:5433/uda_pipeline
    POLLING_INTERVAL_HOURS=24

Observação: a chave da API não deve ser versionada no repositório.

### 2. Subir o banco PostgreSQL

Executar:

    docker compose up -d

Verificar se o container está rodando:

    docker compose ps

### 3. Instalar dependências

Executar:

    pip install -r requirements.txt

### 4. Rodar a aplicação

Executar:

    python main.py

A aplicação sobe a API FastAPI e inicia o scheduler de polling em background.

A API fica disponível em:

    http://localhost:8000

A documentação Swagger fica disponível em:

    http://localhost:8000/docs

### 5. Disparar o pipeline completo

Para executar a varredura das fontes de RI configuradas:

    curl -X POST http://localhost:8000/api/pipeline/run

Esse endpoint aciona o pipeline em background.

O fluxo busca PDFs nas páginas configuradas, calcula hash, ignora documentos já processados e processa apenas arquivos novos.

### 6. Ingerir um PDF manualmente pela API

Também é possível enviar diretamente uma URL de PDF para o pipeline.

Exemplo:

    curl -X POST http://localhost:8000/api/ingest ^
      -H "Content-Type: application/json" ^
      -d "{\"empresa\":\"MRV\",\"url\":\"https://api.mziq.com/mzfilemanager/v2/d/4b56353d-d5d9-435f-bf63-dcbf0a6c25d5/9d9c8de1-c30a-0260-a69f-5c1c06219644?origin=2\"}"

No Linux/macOS:

    curl -X POST http://localhost:8000/api/ingest \
      -H "Content-Type: application/json" \
      -d '{"empresa":"MRV","url":"https://api.mziq.com/mzfilemanager/v2/d/4b56353d-d5d9-435f-bf63-dcbf0a6c25d5/9d9c8de1-c30a-0260-a69f-5c1c06219644?origin=2"}'

### 7. Testar o PDF de exemplo local

O repositório contém o arquivo:

    exemplo_Boletim_Conjuntura_2025_3T.pdf

Esse PDF pode ser usado como evidência de validação do boletim de conjuntura.

Se a versão do pipeline estiver com suporte a `arquivo_local:`, o teste pode ser executado com:

    python -c "from src.database import init_db; from src.pipeline import process_pdf; init_db(); print(process_pdf('arquivo_local:exemplo_Boletim_Conjuntura_2025_3T.pdf', 'Boletim Conjuntura', 'exemplo_Boletim_Conjuntura_2025_3T.pdf'))"

Resultado esperado na primeira execução:

    status: sucesso
    tipo: boletim_conjuntura
    ano: 2025
    trimestre: 3

Resultado esperado na segunda execução:

    status: ja_processado

Esse segundo resultado comprova a idempotência por hash.

### 8. Consultar boletim de conjuntura

Após processar o PDF do boletim, consultar:

    curl "http://localhost:8000/api/boletim?ano=2025&trimestre=3"

Resultado esperado:

- documento do 3º trimestre de 2025;
- totais de lançamentos e vendas;
- dados por empresa;
- variações percentuais;
- hash do PDF original.

### 9. Consultar dados por empresa e período

Endpoint principal do desafio:

    curl "http://localhost:8000/api/conjuntura?empresa=MRV&ano=2025&trimestre=3"

Resultado esperado:

- empresa filtrada;
- ano filtrado;
- trimestre filtrado;
- dados extraídos;
- fonte do dado;
- URL de origem;
- hash do PDF.

### 10. Consultar catálogo de PDFs

Para visualizar os documentos coletados e processados:

    curl "http://localhost:8000/api/catalogo"

Resultado esperado:

- empresa;
- nome do arquivo;
- URL;
- hash SHA-256;
- status de processamento;
- data de coleta;
- data de processamento;
- erro, caso exista.

### 11. Consultar linhagem dos dados

Para verificar a origem dos registros extraídos:

    curl "http://localhost:8000/api/linhagem"

Resultado esperado:

- tipo do documento;
- empresa;
- ano;
- trimestre;
- URL de origem;
- hash do PDF;
- nome do arquivo;
- data de coleta.

## Casos de teste

Os casos de teste considerados para validação do projeto são:

### Caso 1 — Ingestão de boletim de conjuntura

Entrada:

    exemplo_Boletim_Conjuntura_2025_3T.pdf

Resultado esperado:

- identificação do documento como boletim de conjuntura;
- extração do ano 2025;
- extração do trimestre 3;
- extração das empresas do boletim;
- extração das métricas de lançamentos e vendas;
- valores ausentes retornados como `null`.

### Caso 2 — Idempotência por hash

Entrada:

    mesmo PDF processado duas vezes

Resultado esperado:

- primeira execução processa e salva os dados;
- segunda execução retorna `ja_processado`;
- o LLM não é chamado novamente para o mesmo hash.

### Caso 3 — Ingestão de prévia operacional

Entrada:

    PDF de prévia operacional de uma incorporadora

Resultado esperado:

- identificação como prévia operacional;
- extração de ano e trimestre;
- extração de valores absolutos quando disponíveis;
- percentuais não são confundidos com valores absolutos;
- valores ausentes retornam `null`.

### Caso 4 — Consulta pela API

Entrada:

    GET /api/conjuntura?empresa=MRV&ano=2025&trimestre=3

Resultado esperado:

- retorno em JSON;
- filtro por empresa;
- filtro por ano;
- filtro por trimestre;
- dados acompanhados de URL e hash de origem.

### Caso 5 — Catálogo e linhagem

Entrada:

    GET /api/catalogo
    GET /api/linhagem

Resultado esperado:

- listagem de PDFs processados;
- identificação de hash;
- status de processamento;
- associação dos dados extraídos ao PDF original.

## Evidências

As evidências de funcionamento devem ser armazenadas em:

    docs/evidence/

Evidências principais esperadas:

- código com empresas e URLs de RI configuradas;
- função de scraping buscando links nas páginas de RI;
- função de download do PDF e cálculo de SHA-256;
- verificação de idempotência antes da chamada ao LLM;
- schemas Pydantic usados como contrato semântico;
- prompts com regras para não inventar valores;
- tabelas/modelos de catálogo e linhagem;
- API rodando no navegador ou terminal;
- Swagger com endpoints disponíveis;
- primeira ingestão de PDF com `status: sucesso`;
- segunda ingestão do mesmo PDF com `status: ja_processado`;
- consulta `/api/boletim`;
- consulta `/api/conjuntura`;
- consulta `/api/catalogo`;
- consulta `/api/linhagem`.

## Decisão arquitetural

A decisão arquitetural principal foi utilizar uma solução nativa em Python com LLM e contrato semântico, em vez de extratores rígidos baseados em layout.

A estratégia de parsing adotada foi:

- **Full-Scan textual:** extrair o texto completo do PDF com PyMuPDF e enviar ao LLM quando o documento possuir texto selecionável.
- **Fallback visual:** converter páginas em imagens e usar extração multimodal quando o PDF tiver características de apresentação ou pouco texto útil.

Essa decisão foi tomada porque os relatórios de RI podem variar bastante entre empresas. O uso de IA com contrato estruturado torna o pipeline mais resiliente a mudanças de layout, enquanto o catálogo por hash evita reprocessamento desnecessário.

## Limitações

- A solução depende da disponibilidade das páginas de RI das empresas.
- Mudanças profundas no HTML das páginas podem exigir ajuste no scraper.
- A extração semântica depende da disponibilidade e qualidade da resposta do Gemini.
- PDFs com muitas páginas podem ser truncados para controle de custo e latência.
- O fallback visual possui limite de páginas para evitar sobrecarga no modelo.
- A API não possui interface gráfica própria.
- A solução não substitui validação humana em casos ambíguos.
- O projeto usa polling periódico, não webhooks, pois nem todos os portais de RI oferecem RSS ou webhook.

## Segurança e credenciais

As credenciais não são versionadas no repositório.

O arquivo `.env` deve conter a chave do Gemini e a string de conexão do banco local.

O repositório versiona apenas:

    .env.example

O arquivo real com credenciais deve permanecer fora do Git.

Também é importante não expor:

- `GEMINI_API_KEY`;
- senhas de banco;
- tokens de serviços externos;
- arquivos temporários com credenciais.

## Resultado

O projeto demonstra um pipeline de UDA para o setor habitacional capaz de coletar PDFs de RI, identificar duplicidade por hash, extrair dados com IA, validar a saída com Pydantic, salvar os registros em banco relacional e disponibilizar consultas estruturadas via API REST.

A solução permite alimentar análises de conjuntura por empresa, ano e trimestre, mantendo rastreabilidade entre cada dado estruturado e o PDF original de onde ele foi extraído.
