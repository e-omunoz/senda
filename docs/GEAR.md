# Equipo según la build

`addon/Senda/Modules/Gear.lua` valora cada objeto con los pesos de la build de tu clase y de tu tramo de nivel, y lo
aplica en cuatro sitios:

- **Recompensas de misión:** marca «MEJOR» y lo dice en el chat («Recompensa recomendada para tu build: X (+12% para
  tu build)»). Primero lo que puedes ponerte ya; si nada de eso te mejora, lo que pide nivel o aprender el arma (con
  el motivo); si nada te mejora, la recompensa que más vale en el vendedor.
- **Bolsas:** «Ponte X: mejora un 12% para tu build (Pecho, lo llevas en las bolsas)».
- **Descripción de objetos:** una sola línea «Senda: +12% para tu build» (o «no te sirve: tu clase no lo puede
  llevar», «-8% para tu build», «mejora para tu build: no llevas nada ahí», más el motivo si lo hay).
- **Pestaña Equipo:** tu build y tramo de pesos, lo que llevas, mejoras que puedes conseguir ya, **«Mejor pieza conocida
  para tu tramo»** y la lista de «Dónde buscar». El druida tiene un botón para pasar de felino a oso.

El porcentaje es la mejora sobre lo que llevas en esa ranura (para un arma de dos manos, arma + mano izquierda; para
anillos y abalorios, el peor de los dos que llevas).

## Lo que nunca recomienda

- Armadura por encima de la de tu clase (tela para brujo y mago, cuero para druida; malla o placas desde el 40 solo para
  quien las lleva), escudos y reliquias de otra clase, armas que tu clase no aprende y armas en la mano izquierda si tu
  clase no lleva dos armas. Esto sale como «no te sirve» y nunca se propone.
- Un arma que aún no sabes usar (p. ej. el brujo y los bastones antes de Woo Ping) se valora, pero solo se propone si
  no hay nada que puedas ponerte ya, y con el motivo («aprende Bastones con un maestro de armas»). La habilidad se lee
  de las líneas de habilidad del cliente o, si no las da, del hechizo de competencia del arma (Bastones 227, Dagas
  1180…).
- Una mano izquierda mientras llevas un arma de dos manos se compara con esa arma («tendrías que soltar tu arma de dos
  manos»).

## Pesos: `data/knowledge/<clase>/weights.toml`

```toml
id = "warlock-weights"
class = "WARLOCK"
kind = "weights"

[[build]]
key = "affliction"     # GEAR_BUILD_<key> en Core/Locale.lua da el nombre
school = "SHADOW"      # el poder de esa escuela cuenta con SCHOOL_W
default = true         # exactamente una

[[band]]
build = "affliction"
from = 1               # niveles incluidos; por build, los tramos van del 1 al 60 sin huecos ni solapes
to = 29
ref = "Polestar"       # fuente corta que enseña la pestaña
w = { SP = 1.0, SCHOOL_W = 1.0, INT = 0.75, SPI = 0.6, STA = 0.8, MP5 = 1.0, WAND_DPS = 2.0 }
```

Claves (por punto; los porcentajes, por 1 %): `SP` poder con hechizos, `SCHOOL_W` poder de la escuela de la build,
`INT`, `SPI`, `STA`, `STR`, `AGI`, `AP` poder de ataque, `RAP` a distancia, `MP5`, `ARMOR`, `DPS` DPS del arma cuerpo
a cuerpo, `RANGED_DPS` arco/fusil/ballesta, `WAND_DPS` varita, `HIT`/`CRIT` golpe y crítico cuerpo a cuerpo,
`SPELL_HIT`/`SPELL_CRIT` con hechizos, `DEFENSE`, `DODGE`. `tools/validate.py` comprueba las claves, los tramos y la
build por defecto; `tools/build.py` los compila con el resto del conocimiento.

Las clases sin `weights.toml` usan el campo `weights` de alguna página o la tabla de reserva de `Gear.lua`.

### De dónde salen los números

| Build | Tramo | Fuente |
|---|---|---|
| Brujo Aflicción | 1-29 | Pesos de subida de Polestar (`addon/Polestar/Gear/Weights.lua`, GPL-3.0, commit `19bd636e`), hechos con las fórmulas de Classic |
| | 30-39 | Igual, con la varita a 0.6: **criterio** de Senda a partir de Warcraft Tavern («el DPS de varita importa hasta el 30») |
| | 40-59 | 50 % Polestar + 50 % wowsims Classic (`ui/warlock/sim.ts`, MIT, commit `7779ebbf`); la mezcla es **criterio** (el método de Polestar) |
| | 60 | 25 % Polestar + 75 % wowsims (igual que el tramo de nivel 60 de Polestar) |
| Mago Escarcha | 1-39 | Polestar (divididos entre 1.1 para que el poder con hechizos valga 1) |
| | 40-59 / 60 | 50/50 y 25/75 con wowsims Classic (`ui/mage/sim.ts`) |
| Druida felino | 1-39 | Polestar |
| | 40-59 / 60 | 50/50 y 25/75 con wowsims Classic (`ui/feral_druid/sim.ts`, dividido entre la Fuerza) |
| Druida oso | 1-60 | wowsims Classic (`ui/feral_tank_druid/sim.ts`, dividido entre la Agilidad). Es una simulación de nivel 60: usarla en todos los tramos es **criterio** |

**DPS del arma del druida.** En Forever las formas pegan con el daño del arma (Warcraft Tavern y Method, citados en
`druid-gear`), así que el DPS del arma cuenta: 14 × el peso del poder de ataque (14 de poder de ataque = 1 de DPS en
Classic; la misma regla que Polestar en `Gear.WeightsFor`). wowsims Classic no lo cuenta porque allí las formas ignoran
el arma. Si se comprueba en el juego que Forever no lo hace así, basta con poner `DPS = 0` en `druid/weights.toml`.

wowsims simula banda a nivel 60 y no cuenta el tiempo muerto ni la supervivencia (Espíritu y Aguante salen a 0): por eso
pesa poco antes del 40 y nada antes.

## Mejor pieza conocida: `data/knowledge/<clase>/bis-forever.toml`

Lo genera `tools/gen_bis.py` (no se edita a mano):

```
python tools/gen_bis.py --polestar RUTA/polestar           # escribe los tres archivos
python tools/gen_bis.py --polestar RUTA/polestar --check   # sale con 1 si cambiaría algo
```

Objetos y de dónde salen: **ForeverLevelingBiS v0.12.0-beta** de Thunder (MIT, datos del 13-oct-2026), tal como lo
redistribuye Polestar en `addon/Polestar_ItemDB/Forever.lua` (aviso MIT en su `LICENSE-DATA.txt`). La herramienta se
niega si ese archivo no dice que su versión es MIT: las versiones nuevas de ForeverLevelingBiS en CurseForge
(https://www.curseforge.com/wow/addons/forever-leveling-bis, v1.2.7-forever) son «All Rights Reserved» y no se usan.

La elección es de Senda, no una lista «BiS» publicada por nadie: para cada build y tramo de 10 niveles, por ranura, el
objeto que más puntúa con los pesos del final del tramo entre los que la clase puede llevar, que se consigue en el tramo
(nivel requerido; si no tiene, el nivel de la misión) y que la Alianza consigue: misiones de la Alianza o de ambos
bandos (con la raza si la misión es solo de una), botín con al menos un 5 % de probabilidad (**criterio**) o recetas de
las profesiones del plan de la clase (Sastrería y Encantamiento para brujo y mago). Armas: el arma de dos manos si
puntúa al menos lo que la mejor de una mano más la mejor mano izquierda; si no, las dos.

```toml
[[bis]]
from = 21
to = 30
build = "affliction"
slot = 16            # ranura de Senda: 1 cabeza … 16 arma, 17 mano izquierda, 18 a distancia o reliquia
id = 6691
npc = 4422           # botín: pnj (0 = suelto), zone = id de área del cliente (C_Map.GetAreaInfo), pct
zone = 491
pct = 33.5
# o quest = N (misión), o craft = hechizo, prof = "tailoring", skill = 70; race = "Human" si solo esa raza
```

## Simulador

Escenarios `gear-reward`, `gear-usable`, `gear-tip`, `gear-band`, `gear-skill`, `gear-druid` y `gear-en` en
`tests/wowsim/run.js` (objetos de prueba 90001-90009 en `tests/wowsim/mock/api.lua`).
