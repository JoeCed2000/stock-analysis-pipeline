# Ruflo vs Hermes — Orchestration Comparison (2026-05-04)

Analyse comparative de [Ruflo](https://github.com/ruvnet/ruflo) (37.8K★) — framework d'orchestration d'agents pour Claude Code — vs notre setup Hermes + Codex.

Ruflo v3.6.12, TypeScript, Node 20+, licence MIT. Hermes v2026.4.30, Python, DeepSeek V4 Pro.

## Architecture Philosophy

| Axe | Ruflo | Hermes |
|-----|-------|--------|
| **Rôle** | Toolkit d'orchestration (à installer) | Agent autonome (runtime complet) |
| **Modèle cible** | Claude Code uniquement | Model-agnostic (DeepSeek, OpenAI, NVIDIA...) |
| **Langage** | TypeScript / Node 20+ | Python |
| **Split Orchestrator/Worker** | "Claude-flow = LEDGER, Codex = EXECUTOR" | "Hermes orchestre, Codex exécute" |
| **Agents** | Conceptuels (spawnés avec noms) | Process réels isolés (delegate_task) |

## Feature Matrix

| Feature | Ruflo | Hermes | Δ |
|---------|-------|--------|---|
| **Swarm topologies** | Hierarchical, Mesh, V3 queen-led (15 agents) | Ad-hoc, skill-driven | Ruflo a des topologies explicites |
| **Agent types** | coordinator, coder, tester, reviewer, architect, researcher, sec-architect, perf-engineer | Rôles HERMES.md (architecte, codeur, reviewer, testeur) | Ruflo a plus de rôles spécialisés |
| **Memory** | key-value vector (AgentDB + HNSW) | Facts structurés (add/replace/remove) + L0-L4 compilé | Ruflo = vectoriel, Hermes = hiérarchique |
| **HNSW search** | ✅ 150x-12,500x plus rapide | ❌ session_search est linéaire | **Pertinent à implanter** |
| **Event sourcing** | ✅ Audit trail complet | ⚠️ L4 archive post-hoc | **Pertinent à implanter** |
| **Plugin architecture** | ✅ Microkernel | ⚠️ Système de skills (plus léger) | Ruflo plus modulaire |
| **Guidance engine** | ✅ compile/enforce/prove/evolve rules | ❌ Pas d'équivalent | "Prove" → validation déterministe |
| **Performance benchmarks** | ✅ HNSW 150x, Flash Attention 2.49-7.47x, Int8 quantization | ❌ Pas de benchmarks | Ruflo mesure tout |
| **MCP** | ✅ MCP-first API | ✅ MCP natif | Équivalent |
| **Sécurité** | Zod validation, CVE remediation, path traversal, SQL injection prevention | AGENTS.md règles + .env obligatoire | Ruflo plus systématique |
| **CLI scope** | 26 commandes / 140+ subcommands | Config-driven, cron jobs | Ruflo plus riche |
| **Skills catalogués** | ❌ Pas d'équivalent | ✅ 100+ skills catégorisés avec triggers | Hermes unique |
| **TTS / voix** | ❌ | ✅ Réponses vocales, podcast | Hermes unique |
| **Multi-plateforme** | ❌ Claude Code seulement | ✅ Telegram, Discord, SMS | Hermes unique |
| **Cron jobs** | ❌ | ✅ Planification native | Hermes unique |
| **Wiki LLM** | ❌ | ✅ Base markdown inter-liée | Hermes unique |
| **Coût** | Gratuit (OSS) | Gratuit + tokens LLM | Équivalent OSS |

## Ce qui est implantable maintenant

### Priorité HAUTE
1. **HNSW vector search** — remplacer session_search linéaire → 150x+ plus rapide. Pertinent pour toutes les recherches cross-session.
2. **Event sourcing** — tracer les actions en temps réel (au lieu du L4 post-hoc). Feed le dashboard Agent Quality Monitor.

### Priorité MOYENNE
3. **Topologie explicite** pour nos batchs delegate_task (hierarchical/mesh). Formaliser le passage ad-hoc → structuré.
4. **Guidance engine "prove"** — validation déterministe post-agent (cf. Resonant OS Oracle/Logician). On a `deterministic-validator` mais pas de boucle prove.

### Non applicable
- Flash Attention (on n'embarque pas le modèle)
- Int8 quantization (sauf si on fait du local LLM)
- 140+ subcommands CLI (overkill pour nous)

## Verdict

Ruflo = meilleur **framework** (structure, benchmarks, sécurité).  
Hermes = meilleur **agent** (autonomie, multi-plateforme, voix, mémoire compilée).

Les deux sont complémentaires — on peut prendre les patterns de Ruflo (HNSW, event sourcing, topologies) et les intégrer dans Hermes sans changer de runtime.
