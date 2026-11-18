#!/usr/bin/env python3
"""
commit-mirror
Espelha a ATIVIDADE (apenas datas/horários) dos seus commits em repositórios
de trabalho para um repositório pessoal, usando commits vazios.
Nenhum código, mensagem, nome de arquivo ou nome de repositório é copiado.

Uso:
    python mirror.py                 # usa config.json ao lado do script
    python mirror.py --dry-run       # mostra o que seria feito, sem commitar
    python mirror.py --push          # commita e faz push
    python mirror.py --config outro.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".idea", ".vscode"}

DEFAULTS = {
    "source_repos": [],
    "source_roots": [],
    "scan_depth": 3,
    "author_emails": [],
    "target_repo": "",
    "target_author_name": "",
    "target_author_email": "",
    "branch": "main",
    "remote_url": "",
    "since": "",
    "include_merges": False,
    "commit_message": "chore: activity sync",
    "push": False,
}


# --------------------------------------------------------------------------- utils

def die(msg: str) -> None:
    print(f"[erro] {msg}", file=sys.stderr)
    sys.exit(1)


def git(args: list[str], cwd: Path, env: dict | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} falhou em {cwd}:\n{result.stderr.strip()}")
    return result.stdout


def to_key(iso_date: str) -> int:
    """Converte uma data ISO 8601 (com fuso) em timestamp UTC, usado para comparar commits."""
    return int(datetime.fromisoformat(iso_date.strip().replace("Z", "+00:00")).timestamp())


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


# --------------------------------------------------------------------------- config

def load_config(path: Path) -> dict:
    if not path.exists():
        die(f"Arquivo de configuração não encontrado: {path}\n"
            f"Copie config.example.json para config.json e preencha.")
    try:
        user_cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"config.json inválido: {e}")

    cfg = {**DEFAULTS, **user_cfg}
    cfg["author_emails"] = [e.strip().lower() for e in cfg["author_emails"] if e.strip()]

    if not cfg["author_emails"]:
        die("Preencha 'author_emails' com o(s) e-mail(s) que você usa nos commits de trabalho.")
    if not cfg["target_repo"]:
        die("Preencha 'target_repo' com o caminho do repositório pessoal de destino.")
    if not cfg["source_repos"] and not cfg["source_roots"]:
        die("Preencha 'source_repos' e/ou 'source_roots' com os repositórios de trabalho.")
    return cfg


# --------------------------------------------------------------------------- source side

def discover_repos(root: Path, max_depth: int) -> list[Path]:
    """Procura pastas que contêm .git dentro de 'root', até 'max_depth' níveis."""
    found: list[Path] = []
    if not root.is_dir():
        print(f"[aviso] pasta não encontrada, ignorando: {root}")
        return found

    def walk(folder: Path, depth: int) -> None:
        if (folder / ".git").exists():
            found.append(folder)
            return
        if depth >= max_depth:
            return
        try:
            for child in folder.iterdir():
                if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith("."):
                    walk(child, depth + 1)
        except PermissionError:
            pass

    walk(root, 0)
    return found


def collect_source_commits(repos: list[Path], emails: set[str], since: str,
                           include_merges: bool) -> tuple[Counter, dict[int, str]]:
    """Retorna ({timestamp_utc: quantidade}, {timestamp_utc: data ISO original com fuso})."""
    seen_hashes: set[str] = set()
    counter: Counter = Counter()
    original: dict[int, str] = {}

    for repo in repos:
        args = ["log", "--all", "--format=%H%x09%ae%x09%aI"]
        if not include_merges:
            args.append("--no-merges")
        if since:
            args.append(f"--since={since}")
        try:
            out = git(args, repo)
        except RuntimeError as e:
            print(f"[aviso] não foi possível ler {repo}: {e}")
            continue

        mine = 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            sha, email, date = parts
            if email.lower() not in emails or sha in seen_hashes:
                continue
            seen_hashes.add(sha)
            key = to_key(date)
            counter[key] += 1
            original.setdefault(key, date.strip())
            mine += 1
        print(f"  {repo}  ->  {mine} commit(s) seus")

    return counter, original


# --------------------------------------------------------------------------- target side

def ensure_target(cfg: dict, target: Path, dry_run: bool) -> None:
    if (target / ".git").exists():
        return
    if dry_run:
        print(f"[dry-run] criaria o repositório de destino em {target}")
        return
    target.mkdir(parents=True, exist_ok=True)
    git(["init", "-q"], target)
    git(["symbolic-ref", "HEAD", f"refs/heads/{cfg['branch']}"], target)
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Activity mirror\n\nRepositório gerado automaticamente pelo commit-mirror.\n",
            encoding="utf-8",
        )
    print(f"Repositório de destino criado em {target}")


def target_identity(cfg: dict, target: Path) -> tuple[str, str]:
    name = cfg["target_author_name"]
    email = cfg["target_author_email"]
    if (target / ".git").exists():
        name = name or git(["config", "user.name"], target, check=False).strip()
        email = email or git(["config", "user.email"], target, check=False).strip()
    if not name or not email:
        die("Defina 'target_author_name' e 'target_author_email' (o e-mail precisa estar "
            "cadastrado na sua conta pessoal do GitHub).")
    return name, email


def collect_target_commits(target: Path) -> Counter:
    counter: Counter = Counter()
    if not (target / ".git").exists():
        return counter
    has_head = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=str(target), capture_output=True
    ).returncode == 0
    if not has_head:
        return counter
    for line in git(["log", "--format=%aI"], target).splitlines():
        if line.strip():
            counter[to_key(line)] += 1
    return counter


def create_commits(target: Path, pending: list[str], name: str, email: str, message: str) -> None:
    base_env = os.environ.copy()
    base_env.update({
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    })

    # Se o repositório ainda não tem nenhum commit, inclui o README no primeiro.
    if (target / "README.md").exists():
        git(["add", "README.md"], target, check=False)

    total = len(pending)
    for i, date in enumerate(pending, start=1):
        env = {**base_env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        git(["commit", "--allow-empty", "--no-verify", "--no-gpg-sign", "-q", "-m", message],
            target, env=env)
        if i % 50 == 0 or i == total:
            print(f"  {i}/{total} commits criados")


def push(cfg: dict, target: Path) -> None:
    remotes = git(["remote"], target).split()
    if "origin" not in remotes:
        if not cfg["remote_url"]:
            die("Não há remote 'origin' no repositório de destino. Defina 'remote_url' no "
                "config.json ou rode: git remote add origin <url>")
        git(["remote", "add", "origin", cfg["remote_url"]], target)
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], target).strip()
    print(f"Fazendo push de '{branch}' para origin...")
    result = subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(target))
    if result.returncode != 0:
        die("O push falhou. Verifique o acesso SSH/HTTPS ao repositório remoto.")


# --------------------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description="Espelha a atividade de commits para um repo pessoal.")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")),
                        help="caminho do config.json (padrão: ao lado do script)")
    parser.add_argument("--dry-run", action="store_true", help="só mostra o que seria feito")
    parser.add_argument("--push", action="store_true", help="faz push ao final")
    parser.add_argument("--since", help="sobrescreve 'since' do config (ex.: 2024-01-01)")
    args = parser.parse_args()

    cfg = load_config(expand(args.config))
    if args.since:
        cfg["since"] = args.since

    # 1. Descobre os repositórios de origem
    repos: list[Path] = [expand(p) for p in cfg["source_repos"]]
    for root in cfg["source_roots"]:
        repos.extend(discover_repos(expand(root), int(cfg["scan_depth"])))
    target = expand(cfg["target_repo"])
    repos = sorted({r for r in repos if r != target})
    if not repos:
        die("Nenhum repositório de origem encontrado.")

    print(f"Lendo {len(repos)} repositório(s) de origem:")
    source, original = collect_source_commits(repos, set(cfg["author_emails"]), cfg["since"], cfg["include_merges"])

    # 2. Compara com o que já existe no destino (torna o script idempotente)
    ensure_target(cfg, target, args.dry_run)
    existing = collect_target_commits(target)
    pending: list[int] = []
    for ts in sorted(source):
        missing = source[ts] - existing.get(ts, 0)
        pending.extend([ts] * max(missing, 0))

    print(f"\nCommits encontrados na origem: {sum(source.values())}")
    print(f"Já espelhados no destino:      {sum(source.values()) - len(pending)}")
    print(f"Novos a criar:                 {len(pending)}")

    if args.dry_run:
        if pending:
            first = datetime.fromtimestamp(pending[0], tz=timezone.utc).date()
            last = datetime.fromtimestamp(pending[-1], tz=timezone.utc).date()
            print(f"[dry-run] criaria {len(pending)} commit(s) entre {first} e {last}")
        return

    # 3. Cria os commits vazios com as mesmas datas
    if pending:
        name, email = target_identity(cfg, target)
        print(f"\nCriando commits como {name} <{email}> em {target}")
        dates = [original[ts] for ts in pending]  # mantém o fuso horário original
        create_commits(target, dates, name, email, cfg["commit_message"])
    else:
        print("Nada novo para espelhar.")

    # 4. Push opcional
    if args.push or cfg["push"]:
        push(cfg, target)

    print("Concluído.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        die(str(e))
    except KeyboardInterrupt:
        die("Interrompido.")
