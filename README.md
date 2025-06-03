# Sistema de Campanha de E-mails – Python Norte 2025

Este repositório contém um sistema completo para gerenciamento e disparo de e-mails de comunicação com palestrantes e instrutores(as) da conferência **Python Norte 2025**.

## Visão Geral

O sistema automatiza o fluxo de trabalho a partir da planilha de submissões do Google Sheets, realizando as seguintes etapas:

1. Download da planilha em formato CSV.
2. Parseamento e validação dos dados de palestrantes/instrutores.
3. Geração de e-mails personalizados a partir de um template.
4. Envio dos e-mails via SMTP.
5. Registro dos temas já processados para evitar envios duplicados.
6. Exibição de estatísticas da campanha.

## Estrutura de Diretórios Gerados

```
📂 data/
   └── campaign_history.json        # Base de dados local
📂 logs/
   └── campaign.log                 # Arquivo de logs da aplicação
📂 speakers/
   └── speakers_<timestamp>.csv     # Arquivos CSV baixados da planilha
```

## Pré-requisitos

* Python 3.10 ou superior
* Uma conta de e-mail (Gmail recomendado) com senha de aplicativo habilitada.
* Variáveis de ambiente configuradas (ver abaixo).

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:

```env
# SMTP
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
GMAIL_EMAIL=seu-email@gmail.com
GMAIL_APP_PASSWORD=sua-senha-de-aplicativo
SENDER_NAME=Equipe Organizadora Python Norte 2025

# Planilha
SHEET_URL=https://docs.google.com/spreadsheets/d/ID_DA_PLANILHA/edit?usp=sharing
```

## Execução

```bash
python main.py
```

Ao iniciar, será exibido um menu com as opções de:

1. Enviar e-mails (produção) – realiza o envio real.
2. Modo de teste (simulação) – executa todas as etapas sem disparar e-mails.
3. Ver estatísticas – mostra um resumo dos temas já processados.

## Personalização do Template

O conteúdo do e-mail encontra-se em `EmailTemplate.TEMPLATE`, dentro do arquivo `main.py`.

## Contribuição

Sinta-se livre para abrir issues ou enviar pull requests com melhorias, correções ou novas funcionalidades.

## Licença

Este projeto está licenciado sob a **MIT License** – veja o arquivo [LICENSE](LICENSE) para detalhes.