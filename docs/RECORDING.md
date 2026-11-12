# Grabador de partidas (esquema 2)

Mide cuánto tarda de verdad cada paso de una guía para compararlo con el tiempo estimado del filtro de eficiencia
(plan 6b). **Apagado por defecto.** Se activa en Opciones («Grabar mis partidas…») o con `/senda grabar on`.

| Comando | Qué hace |
|---|---|
| `/senda grabar on` / `off` | Activa o desactiva la grabación |
| `/senda grabar estado` | Estado, fragmentos guardados y tamaño |
| `/senda grabar rastro on` / `off` | Incluir o no el rastro de posición (por defecto sí, cuando se graba) |
| `/senda grabar limpiar` | Borra lo grabado |

## Qué se guarda y qué no

Se guarda: id de guía y de paso, motivo del cambio de paso (`next`, `skip`, `back`, `pick`, `auto`, `guide`, `login`,
`end`), XP ganada y nivel, combate sí/no, ausente (AFK) sí/no, muertes, misiones aceptadas / entregadas / con los
objetivos completos (solo el id), si vas en un grupo de exactamente dos (sí/no) y, con el rastro activado, mapa y
posición cada ~2 s o 10 yardas. El rastro se detiene solo tras 30 min sin moverte.

**Nunca** se guardan nombres de personaje ni de reino, chat, susurros, nombres de compañeros de grupo ni texto de
misiones. Cada personaje lleva un id aleatorio (no sale de su nombre) que solo une sus sesiones; la herramienta
de ingesta lo sustituye por un hash. Hay una prueba de privacidad en el simulador (`recpriv`) y otra en Python.

## Dónde y cómo

`SendaRecorderDB` (por cuenta, `WTF/Account/<cuenta>/SavedVariables/Senda.lua`):

```lua
chunks = { [seq] = "registro
registro..." }  -- 5 min o 16 KiB por fragmento; el abierto se refresca cada 60 s
seq, install, dropped, maps = ...             -- tope total 4 MiB: se descartan los fragmentos más antiguos
```

Los registros van separados por tabulador; el campo 1 es el tipo y el 2 el tiempo en décimas de segundo desde el
`epoch` de la sesión (que se repite en la cabecera `c` de cada fragmento). Los tipos están descritos en la
cabecera de `addon/Senda/Recorder/Session.lua`. El coste en el juego es una lectura de posición por segundo y unas
pocas comprobaciones; nada se hace en combate que no sea leer.

## De la grabación al informe

1. `python tools/ingest_recording.py <Senda.lua>` separa sesiones, calcula el tiempo activo por paso (el AFK cuenta
   cero, los huecos sin eventos se recortan a 5 min, el tiempo entre sesiones no cuenta), XP/hora, yardas y muertes,
   y escribe `data/recordings/<fecha>-<hash>.json`, anónimo y determinista.
2. `python tools/route_report.py` une las pasadas completas con `data/scores/<guía>.json` (formato en la cabecera
   de la herramienta: paso -> `est_minutes` y XP) y muestra medido, estimado, razón y muestras por paso, los pasos a
   más del doble y la mediana de |medido/estimado - 1| (objetivo del plan: <= 30 %). Con `--check` falla si no se cumple.
3. Los rastros continuos se exportan a `data/recordings/traces/<sesión>.json` para el trabajo de navegación.

Una **pasada** es lo que se tarda en un paso desde que se entra hasta que se sale por `next` o `auto`. Quedan fuera
las que se saltaron (`skip`), las abiertas, las revisitas (Atrás) y las `partial` (no se vio la entrada: primer paso
tras activar la grabación o cambiar de guía).
