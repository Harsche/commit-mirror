# commit-mirror

Espelha a **atividade** dos seus commits em repositórios de trabalho (ou de qualquer outra conta) para um repositório pessoal no GitHub, para que ela apareça no seu gráfico de contribuições.

Só a **data e a hora** de cada commit são copiadas. Nada de código, mensagens, nomes de arquivos ou nomes de repositórios sai dos repositórios de origem: cada commit espelhado é um commit vazio com a mensagem genérica que você definir.

## Como funciona

1. Lê os repositórios de origem que você indicar (ou procura todos dentro de uma pasta).
2. Filtra os commits cujo autor tem um dos e-mails configurados, em todas as branches, ignorando merges.
3. Compara com o que já existe no repositório de destino e cria só os commits que faltam, com o mesmo horário e fuso dos originais, assinados com a sua identidade pessoal.
4. Opcionalmente, faz push.

O script é **idempotente**: pode rodar quantas vezes quiser, ele nunca duplica commits.

## Requisitos

- [Git](https://git-scm.com/)
- [Python](https://www.python.org/) 3.8 ou mais recente (sem dependências externas)
- Acesso de push (SSH ou HTTPS) ao seu repositório pessoal

## Instalação

```bash
git clone git@github.com:<seu-usuario>/commit-mirror.git
cd commit-mirror
cp config.example.json config.json      # Windows: copy config.example.json config.json
```

Edite o `config.json` (ele está no `.gitignore` e nunca é commitado).

## Configuração

| Campo | Descrição |
|---|---|
| `source_roots` | Pastas onde ficam os repositórios de origem. Todos os repositórios dentro delas são encontrados automaticamente. |
| `source_repos` | Caminhos de repositórios específicos (alternativa ou complemento a `source_roots`). |
| `scan_depth` | Quantos níveis de subpastas procurar dentro de `source_roots`. Padrão: `3`. |
| `author_emails` | E-mail(s) que você usa nos commits de origem. Só esses commits são espelhados. |
| `target_repo` | Caminho local do repositório de destino. Se não existir, é criado. |
| `target_author_name` / `target_author_email` | Sua identidade pessoal. **O e-mail precisa estar cadastrado e verificado na sua conta do GitHub**, senão os commits não contam. |
| `branch` | Branch usada ao criar o repositório de destino. Padrão: `main`. |
| `remote_url` | URL do repositório pessoal no GitHub, usada no push se o destino ainda não tiver `origin`. |
| `since` | Espelha só commits a partir desta data (ex.: `"2024-01-01"`). Vazio = todo o histórico. |
| `include_merges` | Se `true`, também conta commits de merge. Padrão: `false`. |
| `commit_message` | Mensagem dos commits espelhados. Padrão: `"chore: activity sync"`. |
| `push` | Se `true`, faz push sempre, sem precisar de `--push`. |

Em caminhos do Windows, use `/` ou `\\` no JSON (ex.: `"C:/Repositories/trabalho"`).

## Uso

```bash
python mirror.py --dry-run     # simula: mostra quantos commits seriam criados
python mirror.py               # cria os commits localmente
python mirror.py --push        # cria e faz push
python mirror.py --since 2025-01-01
python mirror.py --config caminho/para/outro.json
```

No Windows, use `py` no lugar de `python` se for o seu caso, ou o atalho `.\run.ps1` (e `.\run.ps1 -DryRun`).

Antes do primeiro push, crie o repositório de destino no GitHub **vazio** (sem README, sem licença).

## Configurando o GitHub

- **Repositório privado (recomendado):** para que as contribuições apareçam no perfil, ative *Settings → Public profile → Include private contributions on my profile*. Elas aparecem no gráfico sem revelar o repositório.
- **Branch padrão:** o GitHub só conta commits na branch padrão do repositório.
- **Não use um fork** como destino; commits em forks não contam.
- O gráfico pode levar alguns minutos para atualizar depois do push.

## Rodando automaticamente

**Windows (Agendador de Tarefas)**, todo dia às 19h:

```powershell
schtasks /Create /TN "commit-mirror" /SC DAILY /ST 19:00 `
  /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Repositories\commit-mirror\run.ps1"
```

Para remover: `schtasks /Delete /TN "commit-mirror" /F`

**Linux / macOS (cron)**, todo dia às 19h:

```bash
0 19 * * * cd /caminho/para/commit-mirror && python3 mirror.py --push >> mirror.log 2>&1
```

O push agendado precisa funcionar sem senha (chave SSH sem passphrase, ou com ssh-agent ativo).

## Usando mais de uma conta do GitHub com SSH

Se a chave SSH padrão da máquina é a do trabalho, crie um alias para a conta pessoal em `~/.ssh/config` (no Windows: `C:\Users\<voce>\.ssh\config`):

```
Host github-pessoal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_pessoal
    IdentitiesOnly yes
```

E use o alias na URL: `git@github-pessoal:<seu-usuario>/activity-mirror.git`.
Para testar: `ssh -T git@github-pessoal` deve responder com o seu usuário pessoal.

## Perguntas frequentes

**Reescrevi a história no repo de origem (rebase/squash). E agora?**
Commits novos com horários novos serão espelhados; os antigos continuam no destino. Para recomeçar do zero, apague o repositório de destino (local e no GitHub) e rode de novo.

**Dois commits no mesmo segundo viram um só?**
Não. O script conta quantos commits existem em cada horário e cria a mesma quantidade.

**Como desfazer tudo?**
Apague o repositório de destino no GitHub. Nenhum outro lugar é alterado.

## Aviso

O script não copia conteúdo, mas mesmo os horários dos commits revelam algo sobre o seu trabalho. Confira se isso está de acordo com a política da sua empresa.
