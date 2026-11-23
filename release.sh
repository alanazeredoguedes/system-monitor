#!/bin/bash
# Cria uma versão: roda os testes, cria a tag vX.Y.Z e envia a tag ao GitHub.
# O GitHub Actions então compila Linux e Windows e publica a Release com os executáveis.
# Uso: ./release.sh 1.0.1
# Pede confirmação antes de criar a tag e antes de enviar.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="${1:-}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Uso: ./release.sh X.Y.Z  (ex.: 1.0.1)"; exit 1; }
TAG="v$VERSION"

[[ "$(git branch --show-current)" == "main" ]] || { echo "Troque para a branch main antes."; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Há alterações sem commit. Faça o commit antes."; git status --short; exit 1; }
git rev-parse "$TAG" >/dev/null 2>&1 && { echo "A tag $TAG já existe."; exit 1; }

echo "Rodando testes..."
PY=.venv/bin/python; [[ -x "$PY" ]] || PY=python3
QT_QPA_PLATFORM=offscreen "$PY" -m pytest -q

echo
echo "Última versão: $(git describe --tags --abbrev=0 2>/dev/null || echo 'nenhuma')"
echo "Commits desde então:"
git log --oneline "$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)"..HEAD | head -20
echo
read -r -p "Criar a tag $TAG neste commit? [s/N] " ok
[[ "$ok" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
git tag -a "$TAG" -m "Versão $VERSION"

read -r -p "Enviar main e $TAG para o GitHub (dispara o build da Release)? [s/N] " ok
if [[ "$ok" =~ ^[sS]$ ]]; then
  git push origin main "$TAG"
  echo "Enviado. Acompanhe em: $(git remote get-url origin | sed 's/\.git$//')/actions"
else
  echo "Tag criada só localmente. Para enviar depois: git push origin main $TAG"
fi
