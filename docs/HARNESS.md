# Harness de IA

El harness mantiene la información de Senda correcta y al día. Lee fuentes oficiales y comunitarias de
WoW Forever, compara lo que dicen con las guías de `data/` y propone cambios en un **pull request con un
informe en español**. Nada se publica sin que lo revises y lo fusiones tú.

```
fuentes (sources.toml) ─► watch ─► afirmaciones con cita ─┐
data/guides + QuestieDB ─► audit ─► veredictos por paso ──┼─► propose ─► TOML + informe ─► PR "harness" ─► tú
fuentes ─► tips ─► consejos por raza/clase ───────────────┘        ▲
                                     reglas de confianza (rules.py) ┘
```

## Contenido de `harness/`

| Archivo | Qué hace |
|---|---|
| `sources.toml` | Registro de fuentes: tier, tipo (RSS, HTML, foro Discourse, carpeta local), URL, cadencia, idioma |
| `cli.py` | `python -m harness watch\|audit\|propose\|tips\|daily\|weekly\|sources` |
| `watch.py` | Descarga novedades, detecta cambios (hash) y pide a Claude afirmaciones con cita |
| `audit.py` | Claude revisa cada paso con búsqueda web, lectura web y QuestieDB local (herramienta propia) |
| `tips.py` | Claude investiga trucos de leveo por raza/clase |
| `propose.py` | Confirma la evidencia, aplica las reglas, edita los TOML y escribe el informe. **No usa la API** |
| `rules.py` | Reglas de `verified` / `unverified` / `disputed` (única fuente de verdad) |
| `evidence.py` | Confirmación determinista: la cita está en la página, el id existe en QuestieDB, hay observación |
| `tomledit.py` | Edición mínima por líneas (diff pequeño; conserva comentarios y formato) |
| `llm.py` | Capa sobre el SDK `anthropic`: modelo, presupuesto, caché, dry-run, bucle de herramientas |
| `prompts.py` | Prompts de sistema (los mismos criterios que `claude-code/*.md`) |
| `claude-code/` | Prompts para hacer lo mismo con Claude Code y tu suscripción |
| `state/` | Estado (JSON, se commitea en los PR): qué se ha visto, afirmaciones, veredictos, cola, costes |
| `state/inbox/` | Resultados que deja Claude Code para que `propose` los procese |
| `reports/` | Informes `<fecha>.md` (son también el cuerpo del PR) |
| `inbox/discord/` | Pega aquí exportaciones de Discord (`.json` de DiscordChatExporter, `.txt`, `.md`) |
| `tests/` | Tests sin red ni API: `python -m unittest discover -s harness/tests -t .` |

## Reglas de confianza

Tiers de fuente (los decide el harness **por la URL**, con los prefijos `match` de `sources.toml`; lo que diga
el modelo no cuenta):

| Tier | Ejemplos | ¿Basta para `verified`? |
|---|---|---|
| `official` | Noticias y hotfixes de Blizzard, mensajes azules, notas de desarrollo, Wowhead Blue Tracker | Sí (regla a) |
| `community_curated` | warcraft.wiki.gg, Wowhead Forever, Icy Veins, Warcraft Tavern, Mobalytics, Gamer Guides | Solo junto a QuestieDB (regla c) |
| `community_unverified` | Reddit, hilos de jugadores en los foros, Discord, cualquier URL no registrada | No |

`verified` exige, como dice [ARCHITECTURE.md](ARCHITECTURE.md#harness-de-verificación):
(a) una fuente oficial, o (b) una observación en partida, o (c) QuestieDB local + otra fuente independiente
oficial o curada. Y además, **solo cuenta la evidencia que el harness ha confirmado él mismo**:

- **Web**: `propose` descarga la URL y busca la cita literal (normalizando espacios, comillas y mayúsculas). Si no
  está, la evidencia no cuenta. Así se neutralizan citas o URL inventadas.
- **QuestieDB**: la referencia `questie:quest/179` se consulta de verdad con `tools/lookup.py`.
- **Observación**: la referencia `obs:accept/179` tiene que existir en `data/observations/`.

Otras reglas:

- Fuentes fiables (oficial, curada, QuestieDB u observación) que se contradicen → `disputed`, con ambas en
  `sources`. Una contradicción solo de Reddit/Discord se anota en el informe, pero no abre disputa.
- Un paso `verified` nunca se rebaja en silencio: si llega evidencia en contra, pasa a `disputed`.
- Un cambio de valor (PNJ, coordenadas, texto...) solo se aplica si hay al menos una evidencia confirmada; entra
  como `unverified` salvo que se cumpla la regla.
- Nunca se cambian `id`, ni se reescriben pasos enteros: ediciones mínimas por línea. Los consejos nuevos se
  añaden a `tip` (sin pisar el del autor).
- Los consejos de `tips` van a `data/knowledge/<clase>/harness-tips.toml` como página `unverified`; los que
  solo tienen fuentes sin verificar llevan el prefijo «(Sin verificar, fuente comunitaria)».
- Si `tools/verify.py` informa `conflict` en un paso, la evidencia de QuestieDB a favor de ese paso no cuenta.
- QuestieDB es «all rights reserved»: solo verifica. Nunca se copian sus coordenadas ni textos a `data/`; unas
  coordenadas nuevas exigen una web citada u observaciones en partida.
- `tomledit` se niega a escribir `status = "verified"` sin evidencia que cumpla la regla (lo comprueban los tests).

> **QuestieDB en CI.** QuestieDB tiene licencia «all rights reserved» y no se commitea, así que en GitHub Actions
> `tools/lookup.py` no tiene datos: allí la regla (c) no se puede cumplir y solo verifican (a) y (b). Para usar la
> regla (c), ejecuta la auditoría en local (API o Claude Code) con QuestieDB instalada.

## Pipelines

```bash
python -m harness sources                         # lista el registro
python -m harness watch   [--source ID] [--force] # novedades -> harness/state/claims.json
python -m harness audit   --guide gnome-warlock [--section 01-coldridge] [--limit 2]
python -m harness tips    [--guide human-mage] [--limit 1]
python -m harness propose [--dry-run] [--offline] [--open-pr]
python -m harness daily   # watch + propose     (CI, cada día)
python -m harness weekly  # audit + tips + propose (CI, los lunes)
```

Opciones comunes: `--dry-run` (imprime los prompts y la estimación; no llama a la API ni escribe estado),
`--limit N`, `--guide ID`, `--budget-usd X`, `--model ID`, `--no-cache`, `--json`.

- **watch** respeta la cadencia de cada fuente, descarga solo los enlaces nuevos y detecta cambios por hash.
  Los mensajes de los foros de Blizzard se leen por la API JSON de Discourse y solo los de empleados de Blizzard
  cuentan como oficiales. Cada afirmación lleva categoría, resumen en español, cita literal, URL, fecha, tier e
  ids. Las que mencionan misiones/PNJ/objetos de una guía ponen esos pasos en la cola de auditoría
  (`state/audit_queue.json`), que `audit` revisa primero.
- **audit** envía a Claude cada sección (en trozos de 25 pasos) con la salida de `tools/verify.py` si existe y
  las afirmaciones recientes relacionadas. Claude tiene `web_search`, `web_fetch` (limitados a los dominios de
  `sources.toml`), `questie_lookup` (llama a `tools/lookup.py`), `observations_lookup` y termina con
  `submit_verdicts` (esquema estricto): veredicto `ok | incorrect | outdated | uncertain`, estado propuesto,
  cambios mínimos y evidencia.
- **tips** busca 3-8 trucos nuevos por raza/clase de las guías existentes, con citas.
- **propose** es el único que escribe en `data/`. Confirma la evidencia, decide el estado, aplica ediciones,
  escribe `harness/reports/<fecha>.md` y, con `--open-pr`, ejecuta `tools/validate.py` y `tools/build.py` y abre
  el PR (o actualiza el PR del harness que siga abierto). Si la validación falla, no abre PR.

## Modelo y API

- Modelo por defecto: **`claude-opus-5-5`** (el más capaz de la familia Opus). Cámbialo con
  `SENDA_HARNESS_MODEL` o `--model`.
- Esfuerzo: `SENDA_HARNESS_EFFORT_EXTRACT` (medium), `SENDA_HARNESS_EFFORT_AUDIT` (high),
  `SENDA_HARNESS_EFFORT_TIPS` (high). El pensamiento adaptativo va siempre activo en este modelo.
- Salida estructurada (`output_config.format`) en `watch`; herramienta final con `strict: true` en `audit`/`tips`.
- Respaldo ante rechazos del servidor activado (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`);
  desactívalo con `SENDA_HARNESS_FALLBACK=""`.
- Otras variables: `SENDA_HARNESS_WEB_SEARCHES` (8 por sección), `SENDA_HARNESS_WEB_FETCHES` (6),
  `SENDA_HARNESS_RESTRICT_DOMAINS` (1 = solo dominios del registro), `SENDA_HARNESS_MAX_TURNS` (12),
  `SENDA_HARNESS_STEPS_PER_CALL` (25), `SENDA_HARNESS_MAX_TOKENS` (16000).

## Costes

El harness estima el coste antes de cada llamada y lleva la cuenta real con el `usage` de la API
(entrada, caché, salida y búsquedas web). Si la siguiente llamada superaría `--budget-usd`, para y lo dice.
Cada ejecución queda en `harness/state/costs.json` y en el informe.

Órdenes de magnitud con `claude-opus-5-5` (4 USD / 20 USD por millón de tokens de entrada / salida; búsqueda web
≈ 0,01 USD). Son estimaciones; mira `costs.json` para los reales:

| Tarea | Coste típico |
|---|---|
| `watch`, por elemento nuevo | 0,02-0,10 USD (más si es un parche largo) |
| `daily` (≈ 5-15 elementos) | 0,20-1 USD |
| `audit`, por sección de 25 pasos | 0,30-1,50 USD (depende de las búsquedas) |
| `tips`, por raza/clase | 0,30-1 USD |
| `weekly` (2 guías completas) | 5-25 USD → usa `--limit` y `--budget-usd` |

Para gastar menos:

- `--limit` y `--budget-usd` (CI usa 5 USD por defecto). La auditoría prioriza la cola y lo menos revisado, así
  que con `--limit 3` cada semana se recorre toda la guía poco a poco.
- Caché de prompts: el prompt de sistema es estable y el historial del bucle de herramientas se cachea.
- Caché local de respuestas (`.cache/harness/responses`): la misma extracción no se paga dos veces.
- `--dry-run` para ver prompts y estimación antes de gastar.
- `--model claude-sonnet-5-5` para tareas rutinarias (más barato; decisión tuya).
- El camino de Claude Code no gasta API: usa tu suscripción.

## Dos formas de ejecutarlo

### 1. GitHub Actions (API key)

`.github/workflows/harness.yml` ejecuta `daily` cada día y `weekly` los lunes, y se puede lanzar a mano
(*Actions → Harness IA → Run workflow*) eligiendo tarea, guía, límite, presupuesto, modelo y dry-run.

Configuración (una vez):

1. Crea una API key en <https://platform.claude.com/> (*API keys*). Pon un límite de gasto mensual en la consola.
2. En GitHub: *Settings → Secrets and variables → Actions → New repository secret*, nombre
   **`ANTHROPIC_API_KEY`**, valor la clave. (Con la CLI: `gh secret set ANTHROPIC_API_KEY`.)
3. *Settings → Actions → General → Workflow permissions*: marca **«Allow GitHub Actions to create and approve
   pull requests»**.
4. Opcional: los PR creados con el token por defecto no disparan la CI normal. Si quieres que la disparen, crea un
   PAT *fine-grained* con permisos *Contents* y *Pull requests* de lectura/escritura sobre el repo y guárdalo como
   secreto **`HARNESS_PR_TOKEN`**.

El workflow instala `harness/requirements.txt`, pasa los tests del harness, continúa el PR del harness que siga
abierto (para no repetir trabajo ni abrir uno por día), ejecuta la tarea, valida y compila, y abre o actualiza el
PR con la etiqueta `harness`. **Nunca empuja a `main` ni fusiona.**

En local con API key: `pip install -r harness/requirements.txt`, exporta `ANTHROPIC_API_KEY` (o usa
`ant auth login`) y ejecuta los mismos comandos. Sin `--open-pr` solo cambia archivos en tu copia.

### 2. Claude Code (tu suscripción, sin API key)

Los prompts de `harness/claude-code/` hacen el mismo trabajo con las herramientas de Claude Code y dejan el
resultado en `harness/state/inbox/`. Después, `propose` (que no usa la API) confirma la evidencia y aplica las
mismas reglas: lo que diga Claude Code no se aplica sin pasar por `rules.py`.

```bash
# Git Bash / Linux / macOS
harness/claude-code/run.sh audit gnome-warlock 01-coldridge
harness/claude-code/run.sh watch 7
harness/claude-code/run.sh tips Gnome WARLOCK

python -m harness propose --dry-run   # mira el diff
python -m harness propose             # aplica y escribe el informe; revisa con git diff y haz commit tú
```

`run.sh` quita el encabezado del prompt, sustituye los argumentos y llama a
`claude -p "<prompt>" --allowedTools "<las del encabezado>" --permission-mode acceptEdits`. En PowerShell, sin
Bash, abre `claude` en la raíz del repo y pega el contenido de `harness/claude-code/audit.md` seguido de los
argumentos. También puedes copiar los tres `.md` a `.claude/commands/` para tenerlos como `/audit`, `/watch` y
`/tips` dentro de Claude Code (usan `$ARGUMENTS`).

En local tienes QuestieDB, así que este camino sí puede cumplir la regla (c).

## Cómo revisar un PR del harness

1. **Lee el informe** (cuerpo del PR). Empieza por «Requiere tu atención»: disputas nuevas y cambios que el
   harness no aplicó por falta de evidencia.
2. **Mira la evidencia de cada cambio**: ✔ = confirmada por el harness, ✘ = no cuenta. Abre al menos las URL de
   lo que pase a `verified` o cambie un valor (PNJ, coordenadas, misión). Comprueba que la cita habla de
   **Forever** y no de Classic Era o Retail.
3. **Revisa el diff de `data/`**: deben ser cambios de una o pocas líneas. Desconfía de textos reescritos.
4. **Disputas**: decide tú. Edita el TOML en la rama del PR (deja el estado que corresponda y las fuentes) o
   anótalo para comprobarlo en partida; las observaciones del addon resuelven muchas.
5. **Consejos** (`harness-tips.toml`): borra los que no aporten o no sean de Forever; reescribe si hace falta.
6. Si algo está mal, edítalo en la rama o descártalo con un commit; si todo el PR sobra, ciérralo. Los elementos
   ya vistos no se vuelven a procesar (están en `harness/state/`) salvo que cambien.
7. Comprueba que la CI está en verde (`validate.py` y `build.py` ya pasaron antes de abrir el PR) y **fusiona tú**.

Señales de alarma: un `verified` cuya única evidencia es una wiki; una cita que no aparece al abrir la página
(la página cambió); coordenadas copiadas de Classic; muchos cambios de texto en un mismo PR.

## Mantenimiento

- **Añadir una fuente**: un bloque `[[source]]` en `sources.toml` con `tier`, `kind`, `url`, `match` y
  `cadence`. Las marcadas `check = true` son URL que conviene confirmar (el informe avisa si fallan). En
  noviembre de 2026, Mobalytics y Reddit rechazan a clientes automáticos (403/429): Mobalytics queda solo para
  clasificar URL y Reddit se intenta y, si falla, solo se anota.
- **Cambiar criterios**: `harness/prompts.py` y, en paralelo, `harness/claude-code/*.md`.
- **Cambiar reglas**: `harness/rules.py` + `harness/tests/test_rules.py` + este documento + ARCHITECTURE.md.
- **Probar**: `python -m unittest discover -s harness/tests -t .` y
  `python -m harness audit --dry-run --guide <id> --limit 1`. Con `SENDA_HARNESS_DATA=<carpeta>` puedes apuntar
  el harness a datos de prueba.
