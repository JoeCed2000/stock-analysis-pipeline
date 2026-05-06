# SSH Access — Hermes → OpenClaw (clawops)

## Clé publique à ajouter sur clawops

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEa5Dsf8AZR8mx7JXH75RQeni6JLdcjUBVLoo1ogcD4G hermes-to-clawops
```

## Commande à exécuter en tant que clawops

```bash
# 1. Ajouter la clé
mkdir -p ~/.ssh
echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEa5Dsf8AZR8mx7JXH75RQeni6JLdcjUBVLoo1ogcD4G hermes-to-clawops' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 2. Installer et démarrer le serveur SSH (⚠️ en tant que CED, pas clawops)
sudo apt install openssh-server -y
sudo systemctl enable --now ssh
```

## Test de connexion (depuis l'utilisateur ced)

```bash
ssh -i ~/.ssh/id_ed25519_hermes_clawops clawops@localhost
```

## Une fois connecté, commandes de base OpenClaw

```bash
openclaw --version
openclaw config list   # voir la config actuelle
openclaw providers list
cat ~/.openclaw/config.yaml
```

## Mot de passe clawops — Réinitialiser

```bash
# Depuis l'utilisateur ced (qui a sudo)
sudo passwd clawops
# → Nouveau mot de passe: <taper>
# → Confirmer: <taper>
```

La config que t'avais faite avant — modèle local via Ollama, zéro coût API :

```bash
# 1. Vérifier qu'Ollama tourne
ollama list

# 2. Si Gemma n'est pas encore pullé
ollama pull gemma3:4b

# 3. Configurer OpenClaw pour utiliser Ollama/Gemma
openclaw config set agents.defaults.model.primary ollama/gemma3:4b

# 4. Voir la config résultante
cat ~/.openclaw/config.yaml
# → agents.defaults.model.primary: ollama/gemma3:4b
```
