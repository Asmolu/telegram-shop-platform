# GitHub Setup

## Option A — GitHub website + terminal

1. Create a new repository on GitHub.
2. Do not initialize it with README, `.gitignore`, or license if you are pushing this prepared local project.
3. Copy the repository URL.
4. Run commands from the project root.

HTTPS example:

```bash
git init
git add .
git commit -m "Initialize Telegram Shop Platform"
git branch -M main
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

SSH example:

```bash
git init
git add .
git commit -m "Initialize Telegram Shop Platform"
git branch -M main
git remote add origin git@github.com:OWNER/REPOSITORY.git
git push -u origin main
```

Replace:

```text
OWNER      -> your GitHub username or organization
REPOSITORY -> repository name, for example telegram-shop-platform
```

## Option B — GitHub CLI

Install and authenticate GitHub CLI first:

```bash
gh auth login
```

Then from project root:

```bash
git init
git add .
git commit -m "Initialize Telegram Shop Platform"
git branch -M main
gh repo create telegram-shop-platform --private --source=. --remote=origin --push
```

For a public repository, replace `--private` with `--public`.

## After first push

Check:

```bash
git status
git remote -v
git log --oneline -5
```

Then open the repository on GitHub and check the Actions tab.
