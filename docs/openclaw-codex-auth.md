# OpenClaw + Codex (ChatGPT Plus) — Commandes d'activation

## Authentification Codex (obligatoire, interactif)

Ouvre un terminal et connecte-toi en tant que clawops :
```bash
su - clawops
```
(entre le mot de passe clawops)

Puis lance l'authentification Codex :
```bash
export PATH="$HOME/.openclaw/bin:$PATH"
openclaw models auth login --provider codex
```

C'est interactif — ça va ouvrir un navigateur pour te connecter avec ton compte ChatGPT Plus.

Une fois authentifié, on pourra utiliser les modèles GPT via ton abonnement.

## Vérifier que c'est bon

```bash
openclaw models list | grep -i codex
openclaw models status
```

## Passer Codex en modèle par défaut

```bash
openclaw models set codex/gpt-5.5    # ou codex/gpt-5
```
