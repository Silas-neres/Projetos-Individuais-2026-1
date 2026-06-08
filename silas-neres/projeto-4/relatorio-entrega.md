# Relatório de Entrega — Projeto Individual 4: Pipeline de UDA para o Setor Habitacional

> **Aluno(a):** Hian Praxedes de Souza Oliveira  
> **Matrícula:** 200019520  
> **Aluno(a):** Silas Neres  
> **Matrícula:** 200043536  

---

## 1. Resumo do Projeto

Este projeto implementa um pipeline de UDA (Unstructured Data Analysis) para extrair dados estruturados a partir de PDFs publicados em páginas de Relações com Investidores de incorporadoras do setor habitacional.

O objetivo da solução é transformar relatórios, boletins e prévias operacionais em dados consultáveis por API, preservando a origem de cada informação extraída. O pipeline coleta PDFs, calcula hash SHA-256 para evitar duplicidade, registra os documentos em um catálogo, extrai o conteúdo com PyMuPDF, utiliza Gemini para interpretação semântica, valida a resposta com Pydantic e salva os dados em PostgreSQL.

O principal resultado obtido foi uma API funcional em FastAPI capaz de expor dados por empresa, ano e trimestre, além de endpoints para consulta do catálogo de PDFs e da linhagem dos dados extraídos.

---

## 2. Problema Escolhido

O problema escolhido foi a análise automatizada de PDFs de Relações com Investidores do setor habitacional.

Empresas como MRV, Direcional, Cury, Tenda, Plano & Plano e Pacaembu publicam prévias operacionais e relatórios em PDF com informações sobre lançamentos, vendas, VGV, estoque, entregas e outros indicadores. Esses documentos são relevantes para relatórios de conjuntura, mas não seguem um formato único e podem variar bastante entre empresas e trimestres.

A automação é relevante porque reduz o esforço manual de coleta e leitura desses PDFs. Além disso, permite transformar dados não estruturados em registros estruturados, rastreáveis e consultáveis, mantendo vínculo com o documento original.

---

## 3. Desenho do Fluxo

O pipeline implementado segue uma estrutura em camadas, com coleta, idempotência, extração semântica, persistência e API.

    Scheduler / Execução manual
    ↓
    Scraper das páginas de RI
    ↓
    Detecção de links de PDFs
    ↓
    Download do PDF
    ↓
    Cálculo do hash SHA-256
    ↓
    PDF já processado?
    ├── true → Retornar ja_processado
    └── false → Registrar no catálogo
              ↓
              Extrair texto do PDF
              ↓
              Detectar tipo de documento
              ├── Boletim de Conjuntura → Extrair variações percentuais
              ├── Prévia Operacional textual → Extrair valores absolutos
              └── PDF visual/slides → Usar extração multimodal
              ↓
              Validar saída com Pydantic
              ↓
              Salvar no PostgreSQL
              ↓
              Disponibilizar via API REST

O fluxo pode ser executado automaticamente pelo scheduler, manualmente por endpoint ou por ingestão direta de uma URL de PDF.

### 3.1 Componentes utilizados

| Componente | Tipo | Função no fluxo |
|----|------|-----------------|
| `scheduler.py` | Agendamento | Executa o pipeline periodicamente usando polling. |
| `src/config.py` | Configuração | Define empresas, URLs de RI e palavras-chave para busca de PDFs. |
| `src/scraper.py` | Coleta | Acessa páginas de RI, detecta links de PDFs, baixa arquivos e calcula hash. |
| `src/pdf_parser.py` | Parsing | Extrai texto dos PDFs com PyMuPDF e oferece suporte a PDFs visuais. |
| `src/pipeline.py` | Orquestração | Controla o fluxo de ingestão, idempotência, extração e persistência. |
| `src/extractor.py` | IA | Usa Gemini para extrair dados com base em prompts semânticos. |
| `src/schemas.py` | Contrato | Define os schemas Pydantic esperados para a resposta da IA. |
| `src/database.py` | Persistência | Define tabelas do catálogo, dados extraídos e linhagem. |
| `src/api.py` | API | Disponibiliza endpoints REST/JSON para ingestão e consulta. |

---

## 4. Papel do Agente de IA

A IA é utilizada como componente de extração semântica. Ela não é usada apenas para resumir texto; sua função é interpretar o conteúdo dos PDFs e retornar dados estruturados de acordo com um contrato definido.

- **Modelo/serviço utilizado:** Gemini.
- **Tipo de decisão tomada pela IA:** identificação de período, empresa, métricas operacionais, valores absolutos e variações percentuais.
- **Como a decisão da IA afeta o fluxo:** a IA retorna um JSON estruturado, que é validado pelos schemas Pydantic. Se a resposta estiver dentro do contrato esperado, os dados são persistidos no banco. Quando uma informação não existe no documento, o valor deve ser retornado como `null`.

Exemplo de saída esperada para um boletim:

    {
      "tipo_documento": "boletim_conjuntura",
      "titulo": "Conjuntura do Setor Habitacional",
      "periodo": "3T25",
      "ano": 2025,
      "trimestre": 3,
      "empresas": [
        {
          "empresa": "MRV",
          "lancamentos": {
            "variacao_vs_2t_percentual": -32,
            "variacao_vs_mesmo_tri_ano_anterior_percentual": -19
          },
          "vendas": {
            "variacao_vs_2t_percentual": -12,
            "variacao_vs_mesmo_tri_ano_anterior_percentual": -10
          }
        }
      ]
    }

---

## 5. Lógica de Decisão

O pipeline possui três pontos principais de decisão.

- **Condição 1: PDF já foi processado?**
  - Caminho A → Se o hash SHA-256 já existir no catálogo e estiver marcado como processado, o pipeline retorna `ja_processado`.
  - Caminho B → Se o hash não existir ou ainda não estiver processado, o pipeline segue para extração.

- **Condição 2: Qual é o tipo de documento?**
  - Caminho A → Se for boletim de conjuntura, o pipeline usa o contrato de boletim e extrai variações percentuais.
  - Caminho B → Se for prévia operacional, o pipeline usa o contrato de dados operacionais e extrai valores absolutos.
  - Caminho C → Se for PDF visual ou em slides, o pipeline pode usar extração multimodal.

- **Condição 3: A resposta da IA segue o contrato?**
  - Caminho A → Se a resposta for validada pelo Pydantic, os dados são persistidos.
  - Caminho B → Se a resposta for inválida ou ocorrer erro, o catálogo registra a falha para rastreabilidade.

A decisão mais importante para custo e duplicidade é a primeira, pois evita chamar o LLM quando o PDF já foi processado anteriormente.

---

## 6. Integrações

| Serviço | Finalidade |
|---------|------------|
| Gemini | Extrair dados semânticos dos PDFs e retornar JSON estruturado. |
| PostgreSQL | Persistir catálogo, dados extraídos e linhagem. |
| FastAPI | Disponibilizar endpoints REST/JSON para ingestão e consulta. |
| Portais de RI | Fonte dos PDFs de prévias operacionais e relatórios. |
| Docker Compose | Subir o banco PostgreSQL localmente. |

---

## 7. Persistência e Rastreabilidade

A persistência foi implementada com PostgreSQL. Cada PDF coletado é registrado no catálogo antes do processamento semântico.

O catálogo registra:

- URL do PDF;
- hash SHA-256;
- empresa;
- nome do arquivo;
- status de processamento;
- data de coleta;
- data de processamento;
- erro, quando houver.

A rastreabilidade é mantida associando os dados extraídos ao documento original por meio de campos como:

- `pdf_catalog_id`;
- `url_origem`;
- `hash_pdf`;
- `nome_arquivo`;
- `data_coleta`.

Essa estrutura permite auditar qual PDF originou cada dado retornado pela API.

---

## 8. Tratamento de Erros e Limites

O pipeline implementa tratamento de erros e limites nos principais pontos do fluxo.

- **PDF duplicado:** quando o hash já existe e está processado, o pipeline retorna `ja_processado` e não chama a IA.
- **Falha no download:** se a URL não retornar um PDF válido, o erro é registrado e o documento não é processado.
- **Resposta inválida da IA:** se a resposta não seguir o schema Pydantic, o erro é capturado e registrado.
- **Valores ausentes:** quando um dado não aparece no documento, a IA deve retornar `null`.
- **PDF visual:** quando o documento possui pouco texto útil ou layout de apresentação, o pipeline pode usar extração por imagem.

Limites conhecidos:

- o scraper pode precisar de ajustes se o HTML das páginas de RI mudar muito;
- a extração depende da qualidade do texto extraído do PDF;
- a IA pode errar em documentos ambíguos;
- documentos muito longos podem exigir chunking semântico em uma evolução futura;
- o projeto usa polling periódico, não webhooks, pois nem todos os portais de RI oferecem esse recurso.

---

## 9. Diferenciais implementados

- [x] Catálogo de documentos processados
- [x] Idempotência com hash SHA-256
- [x] Contrato semântico com Pydantic
- [x] Extração com LLM
- [x] API REST/JSON
- [x] Linhagem dos dados extraídos
- [x] Suporte a diferentes tipos de PDF
- [ ] Uso de embeddings / busca semântica
- [ ] Webhook nativo dos portais de RI

Observação: o projeto utiliza polling para monitoramento das fontes e um contrato semântico para reduzir alucinações e padronizar a estrutura da resposta da IA.

---

## 10. Limitações e Riscos

As principais limitações e riscos identificados foram:

- a IA pode interpretar incorretamente documentos com layout muito ambíguo;
- alguns PDFs podem não possuir texto selecionável suficiente;
- portais de RI podem mudar URLs, HTML ou estrutura de links;
- documentos longos podem ter custo maior de processamento;
- links de RI podem redirecionar para serviços externos sem extensão `.pdf`;
- valores percentuais podem ser confundidos com absolutos se o prompt e o schema não forem bem definidos;
- a solução depende de conexão com Gemini;
- a chave de API deve ser configurada localmente e não pode ser versionada;
- a validação humana ainda é recomendada para resultados críticos.

A solução reduz esses riscos com hash SHA-256, catálogo de documentos, validação Pydantic, prompts restritivos, registro de erros e preservação da linhagem.

---

## 11. Como executar

Instruções para rodar o projeto localmente:

    # 1. Copiar as variáveis de ambiente
    cp .env.example .env

    # 2. Editar o .env e configurar a chave do Gemini
    GEMINI_API_KEY=sua_chave_aqui
    DATABASE_URL=postgresql://uda_user:uda_password@localhost:5433/uda_pipeline
    POLLING_INTERVAL_HOURS=24

    # 3. Subir o PostgreSQL
    docker compose up -d

    # 4. Instalar dependências
    pip install -r requirements.txt

    # 5. Rodar a aplicação
    python main.py

A API ficará disponível em:

    http://localhost:8000

A documentação Swagger ficará disponível em:

    http://localhost:8000/docs

### Executar o pipeline completo

    curl -X POST http://localhost:8000/api/pipeline/run

### Ingerir um PDF específico

    curl -X POST http://localhost:8000/api/ingest \
      -H "Content-Type: application/json" \
      -d '{"empresa":"MRV","url":"URL_DO_PDF"}'

### Consultar dados por empresa e período

    curl "http://localhost:8000/api/conjuntura?empresa=MRV&ano=2025&trimestre=3"

### Consultar boletim

    curl "http://localhost:8000/api/boletim?ano=2025&trimestre=3"

### Consultar catálogo

    curl "http://localhost:8000/api/catalogo"

### Consultar linhagem

    curl "http://localhost:8000/api/linhagem"

Resultado esperado da consulta de catálogo:

    {
      "empresa": "MRV",
      "url": "URL_DO_PDF",
      "hash_sha256": "...",
      "processado": true
    }

---

## 12. Referências

1. Documentação oficial do FastAPI.
2. Documentação oficial do PostgreSQL.
3. Documentação oficial do SQLAlchemy.
4. Documentação oficial do PyMuPDF.
5. Documentação oficial do APScheduler.
6. Documentação oficial do Pydantic.
7. Documentação oficial do Gemini / Google AI Studio.
8. Enunciado do Projeto Individual 4.
9. PDF de exemplo: Boletim de Conjuntura 2025 — 3º trimestre.
10. Portais de Relações com Investidores das empresas analisadas.

---

## 13. Checklist de entrega

- [x] Código do pipeline incluído
- [x] API FastAPI implementada
- [x] Banco PostgreSQL configurado via Docker Compose
- [x] Scraper de páginas de RI incluído
- [x] Cálculo de hash SHA-256 implementado
- [x] Catálogo de PDFs implementado
- [x] Extração semântica com LLM implementada
- [x] Contrato Pydantic implementado
- [x] Endpoints de consulta implementados
- [x] Linhagem dos dados registrada
- [x] README preenchido
- [x] Relatório de entrega preenchido
- [x] Evidências previstas em `docs/evidence/`
- [x] Pull Request aberto
