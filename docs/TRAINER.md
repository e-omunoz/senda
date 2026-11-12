# Instructores de clase: qué se entrena y cuándo

Los `[[train]]` de `data/knowledge/{warlock,mage,druid}/spells.toml` (pestaña de hechizos, ventana del
instructor, consejero y tarjeta de nivel) salen de datos de Forever, no de Classic. Ejemplo de por qué: al 20,
Maldición de los Elementos es el 440892 (rangos 1311676/1311677/1311680 al 30, 40 y 50); el 1490 de Classic no
existe en el cliente de Forever, y el addon enseñaba «#1490».

## Fuentes

| Dato | De dónde | Archivo |
|---|---|---|
| Nivel, hechizo, coste, rango, rango anterior, máscara de razas | `addon/Polestar/QoL/ClassSpells.lua` de Polestar (GPL-3.0, commit `19bd636e`), que `forge data classspells` genera de las listas de entrenamiento capturadas del servidor en la base de datos de TrinityCore para Forever (advocaite/TrinityCore, rama `forever`, GPL-2.0; usadas como hechos) y de las tablas `SpellName`, `Spell` y `SkillLineAbility` del cliente | `data/knowledge/trainer/<clase>.json` (las nueve clases) |
| Nombre esES, texto de rango («Rango 4») y nivel de aprendizaje | El cliente de Forever instalado (`E:/World of Warcraft`, producto `wowf`, build 1.60.1.70888): `SpellName.Name_lang`, `Spell.NameSubtext_lang` y `SpellLevels.SpellLevel`, con la caché de hotfixes (`_forever_/Cache/ADB/esES/DBCache.bin`) encima | `data/knowledge/trainer/names.esES.json` (`source = "ingame-client:<build>"`) |
| Qué es opcional, talentos de la build, huecos de la lista | Decisiones de Senda | `data/knowledge/trainer/policy.json` |

Máscara de razas: bit `id de raza - 1` (1 Humano, 2 Orco, 3 Enano, 4 Elfo de la noche, 5 No-muerto, 6 Tauren,
7 Gnomo, 8 Trol); 0 = todas, igual que `raceOk` en `QoL/Spells.lua` de Polestar. Ahora mismo ningún hechizo de
brujo, mago o druida lleva máscara. Rango 0 = el hechizo no tiene rango.

## Regenerar

```sh
# 1. Listas del instructor (con un clon de Polestar; el commit sale de `git rev-parse HEAD`)
python tools/gen_trainer.py --polestar RUTA/polestar

# 2. Nombres esES y niveles del cliente (WoWDBDefs: solo las definiciones de columnas, ver docs/NAV.md)
cd nav && cargo build --release -p senda-spellnames
target/release/senda-spellnames --wow "E:/World of Warcraft" --product wowf --defs RUTA/WoWDBDefs \
    --trainer ../data/knowledge/trainer --ids ids-extra.txt --out ../data/knowledge/trainer/names.esES.json
#    --trainer lee `spell` y `prev` de cada <clase>.json; --ids (opcional, repetible) añade los números de un
#    archivo de texto: los hechizos que no vende el instructor (inicio, misión, talentos, barras y macros, los
#    `extra` de policy.json). Los que no estén en el cliente salen en `missing`.

# 3. Los [[train]] de los spells.toml
cd .. && python tools/gen_trainer.py --rewrite
python tools/validate.py && python tools/build.py
```

`--check` en los pasos 1 y 3 solo dice si algo cambiaría (sale con 1).

## Cómo se reescribe un spells.toml

- Solo se tocan los `[[train]]` **generados**: los que llevan `sources = ["trainer:polestar-<commit>", ...]`. Van
  tras el preámbulo, ordenados por nivel. El resto del archivo (`[[alias]]`, `[[check]]`, `[ids]`, comentarios) no
  cambia.
- Los `[[train]]` **a mano** (sin esa fuente) se conservan y sus hechizos no se repiten en los generados:
  hechizos de inicio, invocaciones y formas de misión (`quest = true`), habilidades de demonio (`pet = true`),
  talentos (`talent = true`) y lo que no vende el instructor de clase (teletransportes y portales del mago,
  libros, Regalo de lo salvaje). Llevan el nivel del cliente y `status = "unverified"` cuando el coste o el sitio
  no están confirmados.
- Se filtra por la raza del personaje de cada guía: brujo gnomo, mago humano, druida elfo de la noche.
- Un `[[train]]` por nivel con todo lo que la build necesita: hechizos nuevos y subidas de rango. `names` en
  esES con el rango del cliente («Corrupción (rango 4)»; el rango 1 sin sufijo); `cost` = suma en cobre.
- Cada hechizo opcional va en su propio `[[train]]` con `optional = true` y una nota de una línea. El addon no
  los cuenta como pendientes (`Knowledge.TrainNow`).
- Cadenas de rangos: se agrupan por su raíz, el rango más bajo al que se llega siguiendo `prev` (aunque ese rango
  no lo venda el instructor). Las decisiones de `policy.json` se escriben con esa raíz.
- Talentos (`talents` en `policy.json`: raíz → nivel en que la build coge el talento): si la build no lo coge
  (0), sus rangos son opcionales («solo con el talento ...»). Si lo coge más tarde de lo que el instructor
  vende el rango 2, ese rango pasa al nivel del talento, con una nota.
- Huecos (`extra`): hechizos del instructor que faltan en la lista capturada. Hoy son los niveles 8 a 14 del
  druida, que la lista de TrinityCore no trae: van con el nivel de `SpellLevels` del cliente, sin coste y
  `status = "unverified"`.

## Política de opcionales

Opcional = la build no lo usa en su rotación, macros ni barras, así que no cuenta como pendiente. Regla de
comprobación: un hechizo que usen `bars.toml`, `macros.toml` o `rotation.toml` de la clase es obligatorio.

**Brujo (Aflicción con Abisario; daño de Sombras).** Opcionales: Maldición de debilidad, Maldición de temeridad,
Dolor abrasador, Lluvia de Fuego, Maldición de los Elementos («solo en grupo con un mago de Fuego o Escarcha, en
élites; Agonía es tu maldición»), Drenar maná, Captar demonios, Detectar invisibilidad, Crear piedra de fuego y
pirorroca, Subyugar demonio, Piroinferno, Crear piedra de hechizos, Fuego de alma, Custodia de las Sombras,
Terror de fatalidad, Ritual de condena y Fuerza inmortal (todos sus rangos), y los rangos de talentos que la build
no coge (Quemadura de las Sombras, Conflagrar, Incinerar). Todo lo demás es obligatorio: los rangos de
Corrupción, Agonía, Inmolar, Descarga de las Sombras, Drenar vida, Drenar alma, Cauce de salud, Piel y Armadura
demoníaca, Miedo, Aullido de terror, Espiral mortal, piedras de salud y de alma, Ritual de invocación, Ojo de
Kilrogg, Desterrar, Maldición de la lengua y Succionar vida (talento al 36). Excepción a la regla de las barras:
la casilla S4 lleva Maldición de los Elementos, pero es opcional por decisión expresa (la barra solo la coloca si
la conoces).

**Mago (Escarcha).** Opcionales: Empapar magia, Amplificar magia, Custodia de Fuego y de Escarcha, Portal: Forjaz
y Portal: Darnassus, Teletransporte a: Dalaran (id desconocido), las variantes de Polimorfia (vaca, cerdo,
tortuga), Resplandor Arcano y los rangos de talentos que la build no coge (Piroexplosión, Ola explosiva,
Explosión Arcana). Obligatorios: teletransportes, gemas de maná, Escudo de maná, Deshacer maldición inferior,
todos los rangos de daño (incluidos Bola de Fuego, Misiles Arcanos, Chamuscar y Descarga de Pirofrío), Lanza de
hielo (talento al 22) y Barrera de hielo (talento al 40). Portal: Ventormenta es obligatorio porque está en las
barras.

**Druida (feral: gato, oso para élites).** Opcionales: Calmar animal, Tranquilidad, Huracán y los rangos de
talentos que la build no coge (Enjambre de insectos, Crecimiento salvaje). Por la regla de las barras son
obligatorios Hibernar, Espinas, Enredaderas (Raíces enredadoras), Cólera, Fuegolunar y Fuego estelar con todos sus
rangos (las barras ponen siempre el rango más alto que conoces). También Marca y Regalo de lo salvaje, los rangos
de sanación, las formas y todo lo de gato y oso. Mordisco primigenio: talento al 41, así que su rango 2 (36 en el
instructor) se pide al 41.

## Pendiente

- Druida 8-14: la lista capturada de TrinityCore no los trae; nivel del cliente y coste sin confirmar.
- Regalo de lo salvaje (21849/21850) no sale en la lista del instructor de druida: comprobar dónde se aprende.
- Brujo al 16: el jugador vio Fuerza inmortal por 16 platas; la lista da 12 platas (1200 de cobre).
- Teletransportes y portales del mago: nivel del cliente; coste y quién los enseña sin confirmar.
