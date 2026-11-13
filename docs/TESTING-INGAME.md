# Prueba en el juego de Senda 0.7.0

Lista corta para probar la versión en el cliente real de WoW: Forever. Sobre todo con el **brujo gnomo**; el **mago
humano** y el **druida elfo de la noche** solo donde se indica. Cada punto dice qué hacer y qué deberías ver. Si algo
no sale así, apúntalo con `/senda informe` (abajo).

Antes de empezar:
- Instala el zip completo: cinco carpetas en `Interface/AddOns` (`Senda`, `Senda_Lookup`, `Senda_Nav`, `Senda_Nav_EK`,
  `Senda_Nav_Kalimdor`). En la lista de addons, Senda_Lookup y Senda_Nav salen como «cargar bajo demanda»: es normal.
- Entra con el brujo. No debería salir ningún error de Lua (si usas BugSack o `/console scriptErrors 1`, mejor).

## 1. HUD y guía

| Qué haces | Qué deberías ver |
|---|---|
| Entras con el brujo | El HUD con el paso actual de su guía, sin elegir nada. |
| Pasas el ratón por el texto del paso | La descripción dice **por qué** toca («+591 XP · ~5 min · desbloquea...»). |
| Opciones > HUD > «Mostrar por qué bajo el paso» | Apagada por defecto. Al activarla sale una línea tenue bajo el texto, sin pisar el consejo ni los objetivos. |
| Clic derecho en un paso de misión | Menú «Saltar esta misión» / «Dejar para después». |
| Juegas un rato normal | Los pasos de coger, entregar y matar avanzan solos. Nunca hay dos líneas extra a la vez debajo del paso. |

## 2. Flecha y ruta a pie

| Qué haces | Qué deberías ver |
|---|---|
| Sigues un paso con destino en tu continente | Delante de la distancia, **«Ruta a pie»** en verde; la flecha gira suave y sigue el camino (no corta por montañas). |
| Miras el minimapa | Una **línea verde** con el camino. Gira bien con el minimapa giratorio. Se apaga en Opciones > Flecha > «Dibujar la ruta en el minimapa». |
| Montas en un grifo, entras en combate o en una cueva sin datos | **«Línea recta»** en gris y debajo el motivo (volando, en combate, sin caminos...). Al bajar del grifo vuelve sola a «Ruta a pie». |
| Te sales del camino a propósito | En unos segundos recalcula desde donde estás. |
| Opciones > Flecha > «Seguir caminos reales» apagada | Siempre línea recta, sin la línea del minimapa. |

## 3. Cambio de continente, tranvía y barco

| Qué haces | Qué deberías ver |
|---|---|
| Coges el **Tranvía subterráneo** (Forjaz - Ventormenta) | La flecha dice «Tranvía: súbete y baja en Ventormenta» (o Forjaz). Al salir del tranvía, la ruta a pie vuelve **enseguida**, sin esperar. |
| Coges un barco a Kalimdor (Menethil - Theramore o Auberdine) | Al llegar, la flecha vuelve a «Ruta a pie» sin `/reload` y sin tirones largos. |
| Vuelves al otro continente | Igual: sin `/reload`, sin errores. |

## 4. Viaje (camino más rápido)

| Qué haces | Qué deberías ver |
|---|---|
| Un paso lejos (otro continente o más de 800 m) | Una línea en el HUD: «Camino más rápido: vuela a X (3 min) » barco a Y » a pie». La flecha apunta al primer embarque. |
| Hablas con el maestro de vuelo | El nodo al que hay que volar marcado en su mapa. Senda **no** vuela por ti. |
| `/senda viaje recalcular` | Recalcula y vuelve a enseñar la línea. |
| **Mago:** con Teletransporte aprendido y su runa | El viaje lo propone si es más rápido. |
| **Druida:** con Teletransporte: Claro de la Luna | Igual. |

## 5. Aparte (para después, reserva de XP, desvío)

| Qué haces | Qué deberías ver |
|---|---|
| Clic derecho en un paso > «Dejar para después» (p. ej. la cadena del súcubo) | La misión y las que dependen de ella pasan a la pestaña «Aparte»; la guía sigue sin ellas. |
| Vuelves cerca de lo aparcado | Una línea «Pendiente aquí: X · Retomar». |
| Te falta nivel para el siguiente paso | «Te faltan N XP...: estas misiones te los dan en ~M min». |
| Coges una misión de la reserva | El HUD y la flecha siguen el desvío; al acabar vuelves a la ruta donde la dejaste. Sobrevive a `/reload`. |

## 6. Raros

| Qué haces | Qué deberías ver |
|---|---|
| Pasas cerca de un raro de tu nivel | Línea «Raro cerca: nombre (nivel A-B) · Señalar». Clic en Señalar: la flecha va al raro. |
| Entras en combate con el aviso puesto | El aviso espera y vuelve al salir si sigue vivo. Nada en mazmorras. |
| `/senda raros` | Opciones de raros (solo ±3 niveles, sonido). |

## 7. Equipo

| Qué haces | Qué deberías ver |
|---|---|
| Entregas una misión con recompensa a elegir | La recomendada para Aflicción (brujo) / Escarcha (mago) / felino (druida). |
| Te cae una mejora en las bolsas | «Ponte X: mejora un N% para tu build». |
| Pasas el ratón por un objeto | Una línea «Senda: +N% para tu build» solo si te mejora. |
| **Druida:** `/senda equipo oso` y luego `/senda equipo felino` | La pestaña Equipo cambia de pesos; nunca propone placas ni mallas. |

## 8. Mazmorras

| Qué haces | Qué deberías ver |
|---|---|
| Pestaña «Mazmorras» (o `/senda mazmorra`) | Las mazmorras de la Alianza por nivel (no sale Sima Ígnea). En verde las de tu nivel; «»» la que manda tu guía. |
| Abres Minas de la Muerte | Niveles, entrada en Páramos de Poniente, jefes, misiones (las de tu guía primero) y botín que mejora tu build. Brujo: tela con intelecto/poder con hechizos/sombras; mago: tela con escarcha; druida: cuero con agilidad (y su lista de oso). |
| «Flecha a la entrada» / «Flecha a la piedra» | La flecha va ahí; «Quitar la flecha» la quita. **Comprueba en el mapa que la entrada y la piedra están donde dicen** (al menos Minas de la Muerte, Mazmorras de Ventormenta y Gnomeregan). |
| Entras en la instancia | La flecha a la mazmorra se quita sola. |
| Un paso de mazmorra de la guía (p. ej. Minas de la Muerte) | El texto del paso termina en «Ver en Mazmorras »»; clic izquierdo en el paso abre su ficha. Sin línea nueva en el HUD. |

## 9. Buscador de objetos

| Qué haces | Qué deberías ver |
|---|---|
| Pasas el ratón por un objeto de misión de la guía (fuera de combate) | Una sola línea «Senda: lo sueltan X y Y en Dun Morogh» (o «lo vende...», «recompensa de...», «para...»). La primera vez puede tardar un instante: se carga Senda_Lookup. |
| Lo mismo en combate, sin haber mirado nada antes | Sin línea (no carga nada en combate); sale después. |
| `/senda objeto <nombre>` (o un enlace o un número) | De dónde sale: botín con zona y probabilidad, vendedores, recompensas. |
| `/senda objeto señalar <objeto>` y `/senda objeto borrar` | La flecha va a la fuente más cercana; borrar la quita. |
| Pestaña «Objetos» | Caja de búsqueda (sin tildes también), resultados con «Señalar» y el detalle. |
| Opciones > Objetos, apagar la línea | No vuelve a salir en las descripciones. |

## 10. La Horda no afecta a la Alianza

Con el brujo, en la pestaña «Guía» solo salen guías de la Alianza. Si tienes un personaje de la Horda, prueba que
entra en su guía de raza sin elegir nada.

## 11. Profesiones (cambios sin publicar)

Con el **brujo gnomo**, empezando sin profesiones. Instructores de Forjaz: Sastrería **Jormund Stonebrow** (43,1 29,3;
Aprendiz y Oficial), Encantamiento **Gimble Thistlefuzz** (59,8 45,4; Aprendiz y Oficial).

| Qué haces | Qué deberías ver |
|---|---|
| Pestaña «Profesiones» sin ninguna aprendida | «Profesiones recomendadas para tu clase: Sastrería + Encantamiento» con el porqué, y para cada una «No tienes...» con su instructor y el botón «Flecha al instructor». |
| Clic en «Flecha al instructor» estando en Forjaz | La flecha va al instructor **de Forjaz** (el más cercano), no al de Ventormenta. Comprueba que el PNJ está en ese punto. |
| Aprendes Sastrería y Encantamiento (Aprendiz, a cualquier nivel) | La pestaña cambia sola: barras «Sastrería 1 / 75» y «Encantamiento 1 / 75», y el primer tramo de cada una: Sastrería «fabrica unas 7 x Capa de lino» (antes 7 Madejas de paño de lino), Encantamiento «Encantar brazales: aguante menor» con la Vara de cobre rúnico. Colores (naranja/amarillo/verde/gris), «Receta: ...», el material con «tienes N / M». |
| Abres el banco una vez | Deja de salir «Abre el banco una vez...» y el material cuenta lo que guardas. |
| Hablas con el instructor con habilidad ~15 en Sastrería | En la ventana de Senda junto al instructor, la receta de tu ruta que ya puedes aprender (Cinturón de lino) sale resaltada con «receta de tu ruta de Sastrería (15-70)». |
| Llegas a 50-60 de habilidad (con nivel 10) | «Entrena Oficial de Sastrería ya...» y la flecha al instructor que enseña Oficial. Sin nivel 10: «Te acercas al tope. Oficial pide nivel 10». |
| Aprendes una de recolección (p. ej. Minería) | Sale también en la pestaña, con su barra, el tramo y la sección «Minería: dónde recoger» con zonas de tu guía. |
| **Anota** el nivel que piden **Experto** (20) y **Artesano** (35) y la habilidad a la que el instructor enseña las recetas marcadas «sin verificar» | Son datos de Classic sin comprobar en Forever: si no coinciden, `/senda informe` en la ventana del instructor. |

Con el **druida** (Herboristería + Alquimia): la recomendación dice Herboristería + Alquimia y, con Herboristería, la
sección «dónde recoger» empieza en Teldrassil y sigue con Costa Oscura.

## Cómo informar

1. Cuando veas algo raro, escribe **`/senda informe`** en ese momento (o pulsa el botón del bicho en la cabecera del
   HUD). Se abre «Informar de un problema» con tu guía, el paso (id y texto), la posición, nivel, raza y clase, la
   versión, otros addons y los últimos errores de Lua de Senda. No lleva nombre de personaje ni de reino.
2. Escribe en la caja qué esperabas y qué viste (una o dos frases).
3. Pulsa «Copiar» y luego Ctrl+C. Pega el texto en la incidencia; la ventana también da un enlace de GitHub listo
   para copiar en el navegador.

Para errores de datos (un PNJ que no está donde dice, una misión que no se puede coger), basta el informe en ese punto:
lleva el id del paso y las coordenadas.
