# Senda

**Guía de leveo paso a paso para WoW Forever, del 1 al 60, con datos verificados.**

Senda te lleva de la mano desde el primer paso hasta el nivel máximo:

- **HUD paso a paso**: qué misión coger, adónde ir, qué matar, qué entregar y qué entrenar.
  Detecta solo cuándo has terminado cada paso y pasa al siguiente.
- **Flecha propia**: muestra distancia y tiempo estimado. Si mueres, te guía hasta tu cadáver. No necesitas
  TomTom.
- **Rutas específicas de Forever**, no copiadas de Classic: zonas rehechas, mazmorras nuevas y misiones
  nuevas.
- **Para principiantes y expertos**: instrucciones claras, más consejos de experto opcionales en cada paso.
- **Conocimiento por clase**:
  - Talentos, hechizos, rotación y macros.
  - Profesiones, equipo, oro y subir en pareja.
- **Ayudas en el juego**:
  - Mejoras de equipo en la descripción emergente.
  - Lista de la compra en vendedores y qué aprender en instructores.
  - Botón de Desencantar.
  - Asesor «Qué hago».
- **Datos con procedencia**: cada paso indica si está verificado, sin verificar o en disputa, con sus fuentes.
- **Convive con Questie**: Senda guía la ruta y Questie sigue mostrando las misiones en el mapa.

Guías disponibles: **brujo gnomo**, **mago humano** y **druida elfo de la noche**. Más razas y clases próximamente.

Web con la guía detallada: https://e-omunoz.github.io/senda/

Métricas (horas y XP por hora de cada guía, verificación, malla de navegación, cobertura de datos; en español e
inglés): https://e-omunoz.github.io/senda/metricas/ (se generan con `tools/site_metrics.py`).

## Instalación

1. Descarga `Senda-x.y.z.zip` desde [Releases](https://github.com/e-omunoz/senda/releases).
2. Descomprímelo en `World of Warcraft\_forever_\Interface\AddOns\`. Deben quedar cinco carpetas: `Senda`,
   `Senda_Nav`, `Senda_Nav_EK`, `Senda_Nav_Kalimdor` y `Senda_Lookup` (las tres primeras llevan los caminos a pie de la
   flecha y `Senda_Lookup` el buscador de objetos; Senda las carga solo cuando hacen falta, fuera de combate).
3. En el juego, escribe `/senda`.

| Comando | Qué hace |
|---|---|
| `/senda` | Abre el panel |
| `/senda hud` | Muestra u oculta el HUD |
| `/senda way 45.2 60.1 Texto` | Pone la flecha en un punto del mapa actual |
| `/senda map` | Muestra el mapa y las coordenadas actuales |
| `/senda objeto agua` | De dónde sale un objeto (botín, vendedores, misiones) y «Señalar» el sitio más cercano |

## Cómo se mantiene la información al día

```
fuentes oficiales y comunitarias ──► harness de IA ──► PR con informe ──► revisión humana ──► release
QuestieDB local + lo grabado en partida ──► verificador ──┘
```

- [Arquitectura](docs/ARCHITECTURE.md)
- [Verificación](docs/VERIFICATION.md)
- [Prueba en el juego (lista para el jugador)](docs/TESTING-INGAME.md)
- [Harness de IA](docs/HARNESS.md)
- [Datos de WoW Forever](docs/FOREVER.md)

## Desarrollo

Requiere Python 3.11 o superior (solo la biblioteca estándar).

```bash
python tools/validate.py      # comprueba los datos
python tools/build.py         # genera el Lua de las guías
python tools/package.py       # crea dist/Senda-x.y.z.zip
```

Más detalles en [tools/README.md](tools/README.md) y [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

Senda es software libre bajo [GPL-3.0](LICENSE) desde la 0.4.0. Las versiones hasta la 0.3.5 se publicaron con
licencia MIT y lo siguen siendo para quien las tenga.

Lo que viene de otros proyectos (Polestar y sus datos abiertos forever-db, ambos GPL-3.0) está en
[THIRD_PARTY.md](THIRD_PARTY.md), con su licencia, su origen y la versión fijada. Senda no incluye datos de
terceros con licencia restrictiva: QuestieDB solo se lee en local para verificar.

World of Warcraft es una marca de Blizzard Entertainment. Senda es un proyecto de la comunidad sin
afiliación con Blizzard.
