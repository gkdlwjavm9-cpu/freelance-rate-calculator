#!/usr/bin/env bash
# Deploy the freelance rate calculator to GitHub Pages.  bash deploy.sh
# Idempotent: safe to run again after a partial failure.
set -u
OWNER="gkdlwjavm9-cpu"
REPO="freelance-rate-calculator"
BRANCH="main"
URL="https://${OWNER}.github.io/${REPO}/"
cd "$(dirname "$0")" || exit 1

echo "== 1. repository $OWNER/$REPO"
if gh api "repos/$OWNER/$REPO" >/dev/null 2>&1; then
  echo "   already exists"
else
  echo "   creating…"
  if ! gh api -X POST user/repos -f name="$REPO" \
        -f description="Free freelance rate calculator: real hourly rate, day rate and 3-tier project quotes" \
        -F homepage="$URL" -F private=false >/dev/null 2>&1; then
    cat <<EOS
   !! The GitHub connection cannot create repositories (403 Resource not accessible
      by integration). Create it in the browser at https://github.com/new
         name: $REPO   visibility: Public   (no README)
      then run this script again.
EOS
    exit 2
  fi
fi

echo "== 2. commit"
if [ ! -d .git ]; then git init -q -b "$BRANCH" 2>/dev/null || git init -q; fi
git add -A
git -c user.name="$OWNER" -c user.email="${OWNER}@users.noreply.github.com" \
    commit -q -m "Freelance rate & project quote calculator (single file, no dependencies)" \
    || echo "   nothing new to commit"
git branch -M "$BRANCH" 2>/dev/null
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO.git"

echo "== 3. push"
git push -u origin "$BRANCH" || { echo "   !! push failed"; exit 3; }

echo "== 4. GitHub Pages"
if gh api "repos/$OWNER/$REPO/pages" >/dev/null 2>&1; then
  echo "   Pages already enabled"
else
  gh api -X POST "repos/$OWNER/$REPO/pages" \
     -f "source[branch]=$BRANCH" -f "source[path]=/" >/dev/null \
     || echo "   !! enable Pages at https://github.com/$OWNER/$REPO/settings/pages (branch main, / root)"
fi

echo "== 5. waiting for $URL"
for i in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
  if [ "$code" = "200" ]; then echo "   live: $URL"; exit 0; fi
  sleep 15
done
echo "   !! still not live — check https://github.com/$OWNER/$REPO/actions"
exit 4
