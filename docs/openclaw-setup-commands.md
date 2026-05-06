# OpenClaw SSH Setup — Commandes complètes

## ⚠️ Contexte avril 2026
Anthropic/OpenAI ont bloqué les outils tiers (OpenClaw, OpenCode, Cline) d'utiliser les abonnements ChatGPT/Claude.
→ OpenClaw nécessite une clé API pay-per-use désormais.
→ Alternative gratuite : Codex CLI (autorisé avec abonnement ChatGPT Plus $20).

Mais si tu veux quand même setup OpenClaw :

---

## 1. Vérifier si OpenClaw est installé

```bash
# En tant que clawops
sudo -u clawops -i
which openclaw
openclaw --version
```

## 2. Installation si absent

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
# ou
npm install -g openclaw
```

## 3. Configuration du provider

```bash
# Lister les providers disponibles
openclaw providers list

# Configurer OpenAI (clé API requise)
openclaw config set model.provider openai
openclaw config set model.name gpt-5.4

# OU modèle local (gratuit)
openclaw config set model.provider ollama
openclaw config set model.name gemma3:27b
```

## 4. Ajouter une clé API

```bash
# OpenAI
openclaw config set auth.openai.api_key sk-xxx

# Anthropic
openclaw config set auth.anthropic.api_key sk-ant-xxx

# La clé est stockée dans ~/.openclaw/config.yaml
```

## 5. Gateway (démarrage)

```bash
# Mode normal
openclaw gateway run

# Mode headless (pas de TUI)
export OPENCLAW_HEADLESS=true
openclaw gateway run

# Ou permanent
openclaw config set gateway.headless true
```

## 6. Mode agent one-shot (sans TUI)

```bash
# Commande unique, retour JSON
openclaw agent --message "Fixe le bug dans backend/orchestrator.py" --json --local

# Avec modèle spécifique
openclaw agent --message "..." --model openai/gpt-5.5 --json
```

## 7. Token/Bearer pour REST API

```bash
openclaw config set gateway.token "mon-secret-token"
# Puis dans les requêtes : Authorization: Bearer mon-secret-token
curl -H "Authorization: Bearer mon-secret-token" http://localhost:18789/api/status
```

## 8. Voir la config actuelle

```bash
cat ~/.openclaw/config.yaml
```

## 9. Config type (exemple)

```yaml
model:
  provider: openai
  name: gpt-5.4

gateway:
  port: 18789
  headless: true
  token: "mon-secret"

auth:
  openai:
    api_key: "sk-..."
```

---

## Alternative : Codex CLI (recommandé)
Utilise ton abonnement ChatGPT Plus $20, sans coût API supplémentaire :
```bash
codex exec --full-auto --skip-git-repo-check
```
