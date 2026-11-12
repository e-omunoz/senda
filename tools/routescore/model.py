"""Modelo del filtro de eficiencia: XP, tiempos y decisión (funciones puras, sin base de datos).

Fuentes de cada constante (ver docs/EFFICIENCY.md):

- LEVEL_XP: tabla de XP por nivel de Classic 1.12 tal como la usa Polestar
  (tools/lib/game/xp.js y rust/crates/forge-guide/src/xp.rs, GPL-3.0): «Forever has not published a
  different one; recordings will show if it changed». Adaptado de Polestar.
- quest_xp_share, zero_diff, grey_level, mob_xp: reglas de XP de Classic portadas por Polestar
  (forge-guide/src/xp.rs), con la regla de Forever (#30) para enemigos por debajo del jugador.
  Adaptado de Polestar (GPL-3.0).
- RUN 7 yd/s, montura +60% a 40, épica +100% a 60, Forma de viaje +40% a 30: cMaNGOS mangos-classic
  (baseMoveSpeed) y hechizos de Classic/Forever, citados en Polestar tools/lib/nav/move.js.
- WALK_DETOUR 1,25: Polestar addon/Polestar/Nav/Travel.lua («straight lines are not walkable»).
- Vuelo 30 yd/s + 2 s por salto, piedra de hogar 15 s: Polestar Nav/Travel.lua.

Lo que es ESTIMACIÓN (sin fuente medida; lo sustituirán los tiempos del Grabador) lleva el prefijo
EST_ y sale marcado en cada resultado.
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------------------------
# XP (adaptado de Polestar, GPL-3.0)
# --------------------------------------------------------------------------------------------

#: XP para pasar del nivel L al L+1 (índice L); 1.12, adoptada por Polestar para Forever.
LEVEL_XP = (
    0, 400, 900, 1400, 2100, 2800, 3600, 4500, 5400, 6500, 7600,
    8800, 10100, 11400, 12900, 14400, 16000, 17700, 19400, 21300, 23200,
    25200, 27300, 29400, 31700, 34000, 36400, 38900, 41400, 44300, 47400,
    50800, 54500, 58600, 62800, 67100, 71600, 76100, 80800, 85700, 90700,
    95800, 101000, 106300, 111800, 117500, 123200, 129100, 135100, 141200, 147500,
    153900, 160400, 167100, 173900, 180800, 187900, 195000, 202300, 209800,
)
MAX_LEVEL = 60


def level_xp(level: int) -> int:
    """XP que pide el nivel (a 60, la del 59 para seguir midiendo en la misma escala)."""
    level = max(1, min(int(level), MAX_LEVEL - 1))
    return LEVEL_XP[level]


def quest_xp_share(player_level: int, quest_level: int) -> float:
    d = player_level - quest_level
    if d <= 5:
        return 1.0
    if d >= 10:
        return 0.1
    return {6: 0.8, 7: 0.6, 8: 0.4, 9: 0.2}[d]


def zero_diff(level: int) -> int:
    for top, v in ((7, 5), (9, 6), (11, 7), (15, 8), (19, 9), (29, 11), (39, 12), (44, 13), (49, 14),
                   (54, 15), (59, 16)):
        if level <= top:
            return v
    return 17


def grey_level(level: int) -> int:
    if level <= 5:
        return 0
    if level <= 39:
        return level - level // 10 - 5
    if level <= 59:
        return level - level // 5 - 1
    return level - 9


def mob_xp(player_level: int, mob_level: int, elite: bool = False) -> int:
    """XP por muerte (regla de Forever #30 para enemigos por debajo)."""
    base = player_level * 5 + 45
    if mob_level >= player_level:
        v = base * (1 + 0.05 * min(mob_level - player_level, 4))
    elif mob_level <= grey_level(player_level):
        v = 0
    else:
        v = max(0.0, (mob_level * 5 + 45) * (1 - (player_level - mob_level) / zero_diff(player_level)))
    return int(math.floor(v + 0.5)) * (2 if elite else 1)


# --------------------------------------------------------------------------------------------
# Velocidades y viaje (hechos citados arriba)
# --------------------------------------------------------------------------------------------

RUN = 7.0
MOUNT_LEVEL, MOUNT_MUL = 40, 1.6
EPIC_LEVEL, EPIC_MUL = 60, 2.0
TRAVEL_FORM_LEVEL, TRAVEL_FORM_MUL = 30, 1.4
WALK_DETOUR = 1.25
FLIGHT_SPEED, FLIGHT_STOP = 30.0, 2.0
HEARTH_SECONDS = 15.0


def ground_speed(level: int, cls: str | None = None) -> float:
    """yd/s al aire libre a ese nivel (la mejor de montura y Forma de viaje del druida)."""
    mul = 1.0
    if level >= EPIC_LEVEL:
        mul = EPIC_MUL
    elif level >= MOUNT_LEVEL:
        mul = MOUNT_MUL
    if cls == "DRUID" and level >= TRAVEL_FORM_LEVEL:
        mul = max(mul, TRAVEL_FORM_MUL)
    return RUN * mul


def walk_seconds(yards: float, level: int, cls: str | None = None) -> float:
    return yards * WALK_DETOUR / ground_speed(level, cls)


# --------------------------------------------------------------------------------------------
# Tiempo de objetivo: ESTIMACIONES (las sustituirán los tiempos del Grabador)
# --------------------------------------------------------------------------------------------

#: segundos por muerte de un enemigo normal de tu nivel, con el saqueo y la parte de descanso
#: (comer/beber) que le toca. Estimación de experto: 12 s + 0,25 s por nivel de combate y botín
#: (de ~13 s al 4 a ~27 s al 60) y un 30% más de descanso.
EST_KILL_BASE, EST_KILL_PER_LEVEL, EST_DOWNTIME = 12.0, 0.25, 0.30


def est_kill_seconds(level: int) -> float:
    """ESTIMACIÓN: segundos por muerte de un enemigo normal de tu nivel, descanso incluido."""
    return (EST_KILL_BASE + EST_KILL_PER_LEVEL * level) * (1 + EST_DOWNTIME)
#: multiplicador por rango del enemigo (1 élite, 2 raro élite, 3 jefe, 4 raro): estimación.
EST_RANK_MUL = {0: 1.0, 1: 3.0, 2: 3.0, 3: 5.0, 4: 1.5}
#: segundos por clic en un objeto del mundo (lanzar 2-5 s y saquear): estimación.
EST_CLICK_SECONDS = 6.0
#: reaparición de un enemigo normal en Classic: 5 min (valor típico de classic-db; no lo trae
#: forever-db). Estimación.
EST_RESPAWN_SECONDS = 300.0
#: objetivo de evento/hablar/usar objeto en un sitio: estimación.
EST_EVENT_SECONDS = 45.0
#: escolta: estimación (las de Classic duran de 3 a 8 min; las grabaciones la cambiarán).
EST_ESCORT_SECONDS = 300.0
#: radio del área de un objetivo alrededor del paso `complete` (yardas).
AREA_RADIUS = 250.0
#: si el área no tiene apariciones bastantes para lo que pide el objetivo, se amplía a estos radios
#: (el jugador recorre el campamento entero antes que esperar reapariciones)
AREA_GROWTH = (400.0, 600.0, 900.0)
#: constante de Beardwood-Halton-Hammersley: recorrido mínimo por n puntos al azar en un área A
#: ≈ 0,7124·sqrt(n·A) (Beardwood, Halton y Hammersley, 1959; constante de Applegate et al. 2006).
BHH = 0.7124


def kill_seconds(player_level: int, mob_level: int, rank: int = 0) -> float:
    """Segundos por muerte (ESTIMACIÓN): +15% por nivel por encima, -8% por nivel por debajo (mín. 50%)."""
    d = mob_level - player_level
    f = 1 + 0.15 * d if d > 0 else max(0.5, 1 + 0.08 * d)
    return est_kill_seconds(player_level) * f * EST_RANK_MUL.get(rank, 1.0)


def tour_yards(n_visits: float, n_points: int, radius: float) -> float:
    """Yardas para visitar `n_visits` de `n_points` puntos repartidos en un círculo de `radius`.

    Recorrido BHH sobre los puntos que hace falta visitar (como mucho los que hay): 0,7124·sqrt(k·A).
    """
    if n_visits <= 0 or n_points <= 0:
        return 0.0
    k = min(n_visits, n_points)
    area = math.pi * max(radius, 20.0) ** 2 * (k / n_points)
    return BHH * math.sqrt(k * area) * (n_visits / k)


def farm_seconds(needed: float, n_spawns: int, radius: float, per_kill: float, level: int,
                 cls: str | None = None) -> float:
    """Segundos para `needed` muertes (o clics) en un campo de `n_spawns` apariciones.

    Si hacen falta más que las que hay, el ritmo queda limitado por la reaparición
    (EST_RESPAWN_SECONDS / n_spawns por muerte).
    """
    if needed <= 0:
        return 0.0
    if n_spawns <= 0:
        return needed * per_kill
    move = walk_seconds(tour_yards(needed, n_spawns, radius), level, cls) / max(needed, 1)
    step = per_kill + move
    if needed > n_spawns:
        extra = needed - n_spawns
        return n_spawns * step + extra * max(step, EST_RESPAWN_SECONDS / n_spawns)
    return needed * step


#: campamento típico para la referencia de «matar bichos»: 10 apariciones en 150 yd (estimación)
GRIND_SPAWNS, GRIND_RADIUS = 10, 150.0


def grind_xp_per_min(level: int, cls: str | None = None) -> float:
    """XP/min matando enemigos de tu nivel sin misiones: la alternativa a una misión (ESTIMACIÓN)."""
    per = farm_seconds(GRIND_SPAWNS, GRIND_SPAWNS, GRIND_RADIUS, kill_seconds(level, level), level, cls)
    return mob_xp(level, level) * GRIND_SPAWNS / per * 60


def grind_rate(level: int, cls: str | None = None) -> float:
    """La misma referencia en % del nivel por hora."""
    return 100.0 * grind_xp_per_min(level, cls) * 60 / level_xp(level)


# --------------------------------------------------------------------------------------------
# Bandas, percentiles y decisión
# --------------------------------------------------------------------------------------------

BAND_WIDTH = 5


def band_of(level: int) -> str:
    lo = (max(1, int(level)) - 1) // BAND_WIDTH * BAND_WIDTH + 1
    return f"{lo}-{lo + BAND_WIDTH - 1}"


def percentile(sorted_values: list[float], q: float) -> float:
    """Percentil q (0-1) con interpolación lineal."""
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def rank_percentile(sorted_values: list[float], v: float) -> float:
    """Porcentaje de valores de la banda que quedan por debajo de v (0-100)."""
    if not sorted_values:
        return float("nan")
    import bisect
    lo = bisect.bisect_left(sorted_values, v)
    hi = bisect.bisect_right(sorted_values, v)
    return 100.0 * (lo + hi) / 2 / len(sorted_values)


#: umbrales relativos a la distribución de la banda (ver docs/EFFICIENCY.md)
DROP_FRACTION_OF_MEDIAN = 0.5   # por debajo de la mitad de la mediana: fuera, salvo cadena o recompensa
KEEP_PERCENTILE = 0.25          # desde el percentil 25 de la banda: se queda


def decide(rate: float, chain_rate: float | None, band: dict, *, class_quest: bool = False,
           unknown: bool = False, dungeon: bool = False, has_reward: bool = False,
           blocked_by: list | None = None, grind: float = 0.0) -> tuple[str, str]:
    """-> (decision, motivo) con decision en keep/optional/drop.

    rate y chain_rate: % de nivel por hora (XP / XP del nivel, por hora) de la misión sola y de la
    misión con todo lo que desbloquea en la guía. band: {"p25", "median"} de su banda. grind: la misma
    tasa matando enemigos sin misión; lo que la supera nunca sale (quitarla obligaría a matar bichos).
    """
    if blocked_by:
        return "drop", "requires"
    if class_quest:
        return "keep", "class"
    if dungeon:
        return "keep", "dungeon"
    if unknown:
        return "keep", "unknown"
    p25, med = band["p25"], band["median"]
    if rate >= p25:
        return "keep", "rate"
    if chain_rate is not None and chain_rate >= p25:
        return "keep", "chain"
    best = max(rate, chain_rate or 0.0)
    if best >= DROP_FRACTION_OF_MEDIAN * med:
        return "optional", "weak"
    if best >= grind:
        return "optional", "grind"
    if has_reward:
        return "optional", "reward"
    return "drop", "slow"


# --------------------------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------------------------

def fmt_int(n: float) -> str:
    """1150 -> «1.150» (separador de miles español)."""
    s = f"{int(round(n)):,}".replace(",", ".")
    return s


def fmt_minutes(m: float) -> str:
    if m < 1:
        return "<1 min"
    if m < 10:
        return f"~{m:.0f} min" if abs(m - round(m)) < 0.25 else f"~{m:.1f} min".replace(".", ",")
    return f"~{round(m):.0f} min"


def why_line(xp: float, minutes: float, decision: str, reason: str, *, unlocks: str | None = None,
             band: str | None = None, rel: float | None = None, requires: str | None = None) -> str:
    parts = [f"+{fmt_int(xp)} XP", fmt_minutes(minutes)]
    if reason == "class":
        parts.append("misión de clase")
    elif reason == "dungeon":
        parts.append("mazmorra: se decide con la mazmorra")
    elif reason == "unknown":
        parts.append("sin datos de botín: no se filtra")
    elif reason == "requires":
        parts.append(f"requiere {requires}, que sale de la ruta")
    elif reason == "chain":
        parts.append(f"desbloquea {unlocks}" if unlocks else "abre una cadena que compensa")
    elif reason == "rate":
        if unlocks:
            parts.append(f"desbloquea {unlocks}")
        elif rel is not None and rel >= 1.5:
            parts.append(f"{rel:.1f}× la mediana del {band}".replace(".", ","))
    elif reason == "weak":
        parts.append(f"floja: {rel:.0%} de la mediana del {band}".replace(".", ","))
    elif reason == "grind":
        parts.append(f"floja ({rel:.0%} de la mediana del {band}), pero mejor que matar bichos")
    elif reason == "reward":
        parts.append(f"solo por la recompensa ({rel:.0%} de la mediana del {band})")
    elif reason == "slow":
        parts.append(f"lenta: {rel:.0%} de la mediana del {band}")
    return " · ".join(parts)
