# Explicación técnica del simulador de tráfico urbano basado en autómata celular

Este documento describe la arquitectura, el flujo de información, los algoritmos,
las estructuras de datos, el diseño de la interfaz y las reglas formales del
autómata celular implementado en este proyecto.

---

## 1. Arquitectura general del sistema

El sistema está organizado en cuatro capas bien diferenciadas, con dependencias
que apuntan siempre hacia abajo (la interfaz conoce al coordinador, el
coordinador conoce al modelo, pero el modelo no conoce a la interfaz).

```
┌──────────────────────────────────────────────────────────────────────┐
│ CAPA DE PRESENTACIÓN                                                 │
│ interface.py  → UserInterface, Button, Slider                       │
│   - dibuja mapa, panel de control y estadísticas                     │
│   - traduce clics de ratón y teclado a acciones del modelo           │
└───────────────────────────┬──────────────────────────────────────────┘
                            │  llama a start/step/reset/place_courier...
┌───────────────────────────▼──────────────────────────────────────────┐
│ CAPA DE COORDINACIÓN                                                 │
│ simulation.py → Simulation                                           │
│   - parámetros (tasa de generación, densidad, duración de semáforos) │
│   - bucle de generaciones, generación estocástica de vehículos       │
│   - delega el paso al autómata y las métricas a TrafficStatistics    │
└──────────┬───────────────────────────────┬───────────────────────────┘
           │                               │
┌──────────▼──────────────────┐  ┌─────────▼──────────────────────────┐
│ CAPA DE MODELO / DOMINIO    │  │ CAPA DE OBSERVABILIDAD              │
│ cellular_automaton.py       │  │ statistics.py → TrafficStatistics  │
│ city_generator.py           │  │   - series temporales (deques)     │
│ vehicle.py                  │  │   - indicadores en tiempo real     │
│ traffic_light.py            │  └─────────────────────────────────────┘
│ courier.py                  │
└─────────────────────────────┘
```

### Responsabilidades por módulo

| Módulo | Responsabilidad principal |
|---|---|
| `main.py` | Punto de entrada: crea `Simulation` y `UserInterface`. |
| `simulation.py` | Orquesta el ciclo de simulación y los parámetros configurables. |
| `cellular_automaton.py` | Dueño de la retícula, los agentes y la regla de transición simultánea. |
| `city_generator.py` | Construye calles, intersecciones, semáforos, obstáculos y puntos de entrada. |
| `vehicle.py` | Modelo de cada vehículo (identidad, posición, dirección, esperas). |
| `traffic_light.py` | Semáforo independiente con temporizador rojo/verde. |
| `courier.py` | Repartidor y planificador de ruta (grafo dirigido, BFS, greedy, 2-opt). |
| `statistics.py` | Cálculo y almacenamiento de métricas e historial. |
| `interface.py` | Renderizado Pygame, controles, eventos y estadísticas. |

Separar la **infraestructura** (`base`) del **contenido dinámico** (`grid`) es una
decisión arquitectural clave: permite que un vehículo o el repartidor pisen una
celda y que, al salir de ella, se restaure exactamente lo que había debajo
(calle, semáforo o parada amarilla).

---

## 2. Flujo de información

### 2.1 Arranque

1. `main.py` crea `Simulation(rows=41, cols=51)`.
2. `Simulation` llama a `generate_city()`, que:
   - rellena toda la retícula con obstáculos;
   - abre calles horizontales y verticales cada 10 celdas, con sentidos alternos;
   - coloca un semáforo en **cada intersección interna**;
   - guarda en `ca.street_rows` y `ca.street_cols` el sentido original de cada calle.
3. `entry_points()` deriva los puntos de entrada de esos sentidos: calles hacia el
   Este entran por la izquierda, hacia el Oeste por la derecha, hacia el Sur por
   arriba y hacia el Norte por abajo.
4. `Simulation.reset()` siembra vehículos iniciales según `initial_density`.
5. `UserInterface` consulta el tamaño del escritorio, escala el tamaño de celda y
   construye botones y deslizadores.

### 2.2 Bucle principal

En cada frame de `UserInterface.run()`:

1. `_handle_events()` procesa eventos:
   - teclado (ESCAPE = salir, ESPACIO = pausa);
   - botones y deslizadores del panel;
   - **clic izquierdo** sobre el mapa → `ca.toggle_stop(r, c)`;
   - **clic derecho** sobre el mapa → `ca.place_courier(r, c)`.
2. `_apply_ui_params()` copia los valores de los deslizadores al modelo.
3. Se acumula `sim.speed` en `_step_accumulator`; por cada unidad completa se
   ejecuta `sim.step()`. Esto permite velocidades **fraccionarias** (0.1x … 10x):
   a 0.1x se da un paso cada 10 frames.
4. `sim.step()`:
   - incrementa la generación;
   - genera vehículos de forma estocástica según `gen_rate` y `max_vehicles`;
   - llama a `ca.step()`, que devuelve los vehículos que salieron;
   - calcula `moved_last_gen` y llama a `stats.record(...)`.
5. Se redibuja la retícula, el panel de control y las estadísticas.

### 2.3 Flujo del repartidor

```
clic izquierdo → toggle_stop() ─┐
clic derecho   → place_courier() ├→ replan_courier() → Courier.plan()
                                 │                       │
                                 │                       ├→ build_road_graph()
                                 │                       ├→ BFS + matriz de distancias
                                 │                       ├→ greedy + 2-opt
                                 │                       └→ path + ordered + unreachable
                                 │
                                 └→ ca.step() avanza al repartidor respetando
                                    semáforos y vehículos → stats.record()
```

Cualquier cambio en las paradas mientras el repartidor está en marcha provoca una
replanificación desde su **posición actual**, conservando las paradas ya
entregadas que sigan existiendo.

---

## 3. Algoritmos utilizados

### 3.1 Generación de la ciudad

- Calles horizontales en las filas `0, 10, 20, 30, 40` y verticales en las
  columnas `0, 10, 20, 30, 40, 50`.
- Sentidos alternos: horizontal `Este, Oeste, Este, …`; vertical `Sur, Norte, …`.
- Un **segundo carril inverso justo dentro de cada borde**: fila 1 (Oeste), fila
  39 (Oeste), columna 1 (Norte) y columna 49 (Sur). Cada lado forma así un par
  de sentido único (*one-way couplet*), lo que permite al repartidor regresar y
  alcanzar zonas antes inaccesibles.
- Un conector corto `(0,1) → (0,0)` evita que la esquina superior izquierda sea
  un nodo sin entradas. Con esto la red vial es fuertemente conexa: las **629**
  celdas de calle se alcanzan desde cualquier otra.
- Un semáforo en cada intersección interna (**30** en la configuración por
  defecto, incluidas las nuevas intersecciones de los carriles inversos), con
  estado inicial alternado según `(i + j) % 4`.
- El resto de celdas son edificios (obstáculos).

### 3.2 Actualización del autómata

Algoritmo de **actualización sincrónica libre de conflictos**: se decide todo el
movimiento observando únicamente la generación actual (`self.grid`) y se aplica
sobre un grid temporal (`new_grid`) construido desde `self.base`. Un conjunto
`targets_taken` garantiza que dos agentes nunca reclamen la misma celda.

### 3.3 Planificación de la ruta del repartidor

1. **Grafo dirigido**: cada celda de calle apunta a su vecino según el sentido de
   su calle; en una intersección se añaden las aristas de ambas calles.
2. **BFS** desde el inicio y desde cada parada para construir una matriz de
   distancias en celdas.
3. **Greedy vecino más cercano**: se elige repetidamente la parada alcanzable
   más próxima; se omiten las inalcanzables.
4. **2-opt**: se prueban inversiones de segmentos de la secuencia mientras
   reduzcan el coste total calculado con la matriz.
5. **Reconstrucción**: para cada tramo se ejecuta un BFS **desde la posición
   actual** hacia la parada destino y se reconstruye el camino mediante los
   punteros `prev`. Esto es necesario porque, al ser el grafo dirigido, la
   alcanzabilidad no es simétrica.

### 3.4 Generación estocástica de vehículos

Se acumula `gen_rate` en `_spawn_accumulator`; cada vez que supera 1.0 se intenta
un spawn en un punto de entrada aleatorio, respetando `max_vehicles`.

### 3.5 Métricas

Densidad, congestión, velocidad media y tiempo medio de viaje se calculan en
`TrafficStatistics.record()` a partir del estado del autómata en esa generación.

---

## 4. Estructuras de datos empleadas

| Estructura | Uso concreto |
|---|---|
| `numpy.ndarray[int]` `grid` | Estado visible de cada celda en la generación actual. |
| `numpy.ndarray[int]` `base` | Infraestructura subyacente; se restaura al desocupar una celda. |
| `numpy.ndarray[bool]` `has_road` | Indica si una celda es transitable. |
| `numpy.ndarray[int]` `road_dir` | Dirección por celda (se sobrescribe en intersecciones). |
| `dict[int, Vehicle]` `vehicles` | Vehículos activos indexados por identificador. |
| `dict[(fila,col), TrafficLight]` `traffic_lights` | Semáforos indexados por posición. |
| `dict[int, tuple]` `street_rows` / `street_cols` | Sentido **original** de cada calle (fuente de verdad para entradas y grafo). |
| `set[tuple]` `extra_edges` | Conectores especiales de los carriles inversos, p. ej. `(0,1) → (0,0)`. |
| `list[tuple]` `stops` | Paradas amarillas, en orden de creación. |
| `list[tuple]` `Courier.path` | Secuencia de celdas a recorrer. |
| `set[tuple]` `Courier.delivered` | Paradas ya entregadas. |
| `set[tuple]` `targets_taken` | Celdas reclamadas por un agente en la generación actual. |
| `set[int]` `remaining` | Índices de paradas pendientes en el greedy. |
| `list[list[float]]` `matrix` | Matriz de distancias entre inicio y paradas. |
| `dict[tuple,int]` / `dict[tuple,tuple]` | Distancias y predecesores devueltos por BFS. |
| `collections.deque` | Cola del BFS e historial limitado a 300 generaciones de las métricas. |
| `dict[str, Any]` | Diccionario devuelto por `current_stats()` y `history()`. |

---

## 5. Diseño de interfaces (si aplica)

La interfaz gráfica usa **Pygame** y se adapta al escritorio detectado
(`min(1650, ancho-40) × min(940, alto-60)`). Se divide en tres zonas:

1. **Mapa (izquierda)**: retícula de celdas. Colores: gris claro (calle), azul
   (vehículo), rojo/verde (semáforo), gris oscuro (edificio), **amarillo (parada)**
   y **naranja (repartidor)**. Los agentes llevan un marcador blanco con su
   dirección; las paradas entregadas muestran un punto oscuro.
2. **Columna central**: botones (*Start, Pause, Reset, Generate Vehicle,
   Clear Vehicles, Clear Route*) y seis deslizadores (*tasa de generación,
   máximo de vehículos, duración roja, duración verde, velocidad, densidad
   inicial*).
3. **Columna derecha**: panel compacto de estadísticas con generación,
   vehículos, congestión, densidad, tiempos y métricas del repartidor. Ambos
   paneles se dimensionan según su contenido, sin gráficas, para que el mapa
   ocupe el mayor espacio posible (celdas de hasta 20 px).

**Interacción**:
- Clic izquierdo sobre el mapa alterna una parada amarilla. Se ignora en
  edificios, semáforos y celdas ocupadas por un vehículo.
- Clic derecho coloca o reubica al repartidor (único) y lanza la planificación.
  Se ignora en edificios, semáforos y celdas ocupadas.
- Espacio pausa/reanuda; ESC cierra la aplicación.
- El botón *Clear Route* elimina paradas y repartidor sin afectar al tráfico.

---

## 6. Explicación Técnica

### 6.1 Estructura del código

```
Proy/
├── main.py                 # Punto de entrada
├── simulation.py           # Coordinador: parámetros, spawn, step, escenarios ya retirados
├── cellular_automaton.py   # Retícula, estados, transición simultánea, API de paradas/repartidor
├── city_generator.py       # Construcción de calles, semáforos y puntos de entrada
├── vehicle.py              # Entidad vehículo
├── traffic_light.py        # Entidad semáforo
├── courier.py              # Repartidor + planificador de ruta
├── statistics.py           # Métricas e historial
├── interface.py            # Interfaz Pygame
├── requirements.txt        # Dependencias
├── README.md               # Manual de uso
└── explicacion.md          # Este documento
```

### 6.2 Clases, funciones o módulos principales

- **`CellularAutomaton`**: núcleo del modelo. Expone `set_road`,
  `set_obstacle`, `add_traffic_light`, `spawn_vehicle`, `toggle_stop`,
  `place_courier`, `clear_route`, `replan_courier`, `_legal_courier_step` y
  `step`. `step()` es la única función que muta la retícula por generación.
- **`generate_city` / `entry_points`** (`city_generator.py`): construyen la
  infraestructura y calculan las entradas válidas en los cuatro bordes.
- **`Courier`** (`courier.py`): guarda `path`, `path_index`, `delivered`,
  `unreachable`, `status` y expone `next_step` y `plan()`.
- **`plan_route` / `build_road_graph` / `_bfs` / `_two_opt`** (`courier.py`):
  planificación completa de la ruta.
- **`Vehicle`**: mantiene tiempos de espera y de viaje para las estadísticas.
- **`TrafficLight`**: `update()` hace avanzar su temporizador alternando rojo y
  verde; `cell_state` devuelve el estado 2 o 3.
- **`TrafficStatistics`**: `record()` toma una instantánea por generación;
  `current_stats()` alimenta el panel de estadísticas (`history()` se mantiene
  disponible como historial, aunque ya no se dibuja).
- **`Simulation`**: puente entre la interfaz y el modelo; gestiona `start`,
  `stop`, `pause`, `reset` y los parámetros.
- **`UserInterface`**: `draw_grid`, `draw_panel`, `_handle_events`, `_cell_at`
  y el bucle `run`.

### 6.3 Algoritmos implementados

1. **Transición simultánea de autómata celular 2D** (vecindad de von Neumann).
2. **Resolución de conflictos** mediante `targets_taken` y un grid temporal.
3. **Generación de red vial** con calles alternas y semáforos por intersección.
4. **Selección de puntos de entrada** según el sentido de cada calle.
5. **BFS** para distancias y reconstrucción de caminos en un grafo dirigido.
6. **Heurística greedy + 2-opt** para el orden de las paradas (aproximación al
   problema del viajante).
7. **Acumulador de paso fraccionario** para velocidades inferiores a 1x.
8. **Ventana deslizante** (`deque(maxlen=300)`) para el historial de métricas.

### 6.4 Relación entre la teoría y el programa desarrollado

| Concepto teórico | Implementación |
|---|---|
| Retícula regular 2D | Arrays `grid`, `base`, `has_road` de `numpy` (41×51 por defecto). |
| Conjunto finito de estados | Constantes `EMPTY…COURIER` (0…6). |
| Vecindad de von Neumann | Deltas `DIR_NORTH`, `DIR_SOUTH`, `DIR_WEST`, `DIR_EAST`; sin diagonales. |
| Función de transición | `CellularAutomaton.step()`. |
| Actualización sincrónica | Cálculo sobre `self.grid`, aplicación sobre `new_grid`. |
| Frontera / condición de salida | Una celda fuera de la retícula implica que el vehículo abandona el sistema. |
| Estocasticidad | Generación de vehículos con probabilidad `gen_rate`. |
| Infraestructura estática vs. agentes | `base` frente a `grid`; semáforos y paradas son infraestructura. |
| Autómata con estado interno | `TrafficLight.timer` y `Courier.path_index`. |
| Grafo dirigido y TSP | `courier.build_road_graph()` y `plan_route()`. |
| Invariantes | Un agente por celda, máximo una celda por generación, sin diagonales. |

### 6.5 Principales desafíos encontrados

1. **Sentidos sobrescritos en las intersecciones**: el paso de calles verticales
   sobrescribía `road_dir`, de modo que los bordes izquierdo/derecho parecían no
   tener calles horizontales. Se resolvió guardando `street_rows`/`street_cols`
   como fuente de verdad.
2. **Solo dos semáforos**: la condición original `i % 2 == 0 and j % 2 == 0`
   reducía las intersecciones señalizadas a dos. Se cambió por un bucle sobre
   todas las intersecciones internas (actualmente 30 semáforos).
3. **Vehículos exclusivamente verticales**: `entry_points()` deducía la dirección
   de `road_dir`; al estar sobrescrito, solo había entradas verticales. Ahora se
   deriva de los sentidos almacenados (7 horizontales + 8 verticales).
4. **Estadísticas no visibles**: el panel original apilaba controles, parámetros,
   estadísticas y gráficas en una sola columna que excedía la pantalla. Se
   reorganizó en dos columnas, se adaptó la ventana al escritorio y, dado que
   las gráficas ocupaban casi toda la altura, se eliminaron para agrandar la
   ciudad y dejar un panel de estadísticas compacto.
5. **Velocidad mínima de 1x**: el redondeo `max(1, round(speed))` impedía ir más
   despacio. Se sustituyó por un acumulador fraccionario.
6. **Integrar un tercer agente sin romper la sincronía**: el repartidor se decide
   después de los vehículos, usando el mismo snapshot y añadiendo su destino a
   `targets_taken`, por lo que no hay solapes ni movimientos dobles.
7. **Paradas transitables**: las celdas amarillas tienen estado propio, así que
   hubo que permitir explícitamente `STOP` como destino tanto de vehículos como
   del repartidor.
8. **BFS asimétrico en calles unidireccionales**: reconstruir cada tramo desde la
   parada fallaba porque la parada no siempre podía alcanzar el origen. Se
   corrigió ejecutando un BFS desde la posición actual hacia la parada.
9. **Replanificación en caliente**: editar paradas durante la ruta exige
   recalcular desde la posición actual y conservar solo las entregas vigentes.
10. **Escalado de la interfaz**: el tamaño de celda se calcula en función del
    ancho disponible para que mapa y paneles quepan en pantallas pequeñas.
11. **Celdas inalcanzables en las esquinas**: con un único anillo de sentido
    único, la esquina superior izquierda no tenía entradas y otras celdas del
    borde solo se podían abandonar. Se añadieron carriles inversos en los cuatro
    bordes y el conector `(0,1) → (0,0)`, logrando una red fuertemente conexa.

---

## 7. Definición de las reglas del autómata

### 7.1 Retícula y estados

Sea `G` una retícula bidimensional de `R × C` celdas ( por defecto `41 × 51`).
Cada celda `(r, c)` toma un estado en:

| Valor | Símbolo | Significado |
|---|---|---|
| 0 | `EMPTY` | Calle vacía |
| 1 | `VEHICLE` | Vehículo |
| 2 | `RED_LIGHT` | Semáforo en rojo |
| 3 | `GREEN_LIGHT` | Semáforo en verde |
| 4 | `OBSTACLE` | Edificio (no transitable) |
| 5 | `STOP` | Parada de reparto (amarilla) |
| 6 | `COURIER` | Repartidor (naranja) |

Además, cada celda posee infraestructura subyacente `base(r,c)` y un indicador
`has_road(r,c)`. Los agentes (1 y 6) son temporales; la infraestructura (0, 2, 3,
4, 5) se restaura cuando el agente se marcha.

### 7.2 Vecindad

Se utiliza la **vecindad de von Neumann** de radio 1:

```
N(r,c) = { (r-1,c), (r+1,c), (r,c-1), (r,c+1) }
```

No se permiten desplazamientos diagonales. En cada generación un agente puede
moverse como máximo una celda.

### 7.3 Reglas de la infraestructura

- **R1 (semáforos)**: todo semáforo incrementa su temporizador en una unidad por
  generación; al alcanzar `red_duration` pasa a verde y al alcanzar
  `green_duration` pasa a rojo, reiniciando el contador. Su estado no depende de
  los vehículos.
- **R2 (paradas)**: una celda puede ser parada si es calle, no es semáforo y no
  está ocupada por un vehículo. Un clic izquierdo alterna `STOP ↔ EMPTY` en
  `base`. Toda modificación de paradas provoca una nueva planificación.
- **R3 (calles)**: los sentidos de las calles son fijos y alternos; determinan
  tanto los puntos de entrada de vehículos como las aristas del grafo de
  planificación. Cada borde tiene un carril inverso adyacente y un conector en
  la esquina superior izquierda, de modo que toda celda de calle es alcanzable
  desde cualquier otra.

### 7.4 Reglas de los vehículos

Para un vehículo `v` en `(r, c)` con dirección `(dr, dc)`, sea `(tr, tc) =
(r+dr, c+dc)`:

- **R4 (salida)**: si `(tr, tc)` está fuera de la retícula, `v` abandona el
  sistema y se registra su tiempo de viaje.
- **R5 (obstáculo)**: si `base(tr,tc) = OBSTACLE`, `v` no se mueve.
- **R6 (avance)**: `v` avanza a `(tr, tc)` solo si el estado actual de esa celda
  es `EMPTY`, `GREEN_LIGHT` o `STOP` **y** la celda no ha sido reclamada por otro
  agente en esta generación.
- **R7 (espera)**: si el destino es `RED_LIGHT`, `VEHICLE`, `COURIER` o ya está
  reclamado, `v` permanece en su celda e incrementa su contador de espera.
- **R8 (dirección)**: los vehículos no giran; conservan la dirección asignada al
  entrar.
- **R9 (congestión)**: un vehículo con `generations_waited ≥ 3` cuenta como
  congestionado.

### 7.5 Reglas del repartidor

Sea el repartidor `k` con ruta planificada `P = [p_1, p_2, …, p_n]` e índice
`i`:

- **R10 (colocación)**: un clic derecho sitúa a `k` en una celda de calle que no
  sea semáforo ni esté ocupada por un vehículo, y calcula `P`. Si ya existía `k`,
  se reubica y se reinicia la ruta.
- **R11 (planificación)**: `P` es la concatenación de los caminos más cortos
  entre la posición actual y las paradas, ordenadas por greedy + 2-opt. Cada paso
  de `P` debe ser una arista válida del grafo dirigido de calles.
- **R12 (avance)**: si `k` está en estado `moving`, apunta a `p_i`, el paso es
  legal según los sentidos de las calles y `p_i` está libre (o es verde/parada) y
  no reclamada, entonces `k` avanza una celda, `i ← i + 1` y su dirección de
  dibujo se actualiza.
- **R13 (espera)**: si `p_i` tiene semáforo rojo o contiene un vehículo, `k`
  espera en su celda incrementando su contador de espera.
- **R14 (entrega)**: al entrar en una celda que es parada, esa parada se añade a
  `delivered`. Si la parada se elimina, se retira también del conjunto.
- **R15 (fin)**: cuando `i = n`, `k` pasa a estado `done` y permanece detenido
  hasta una nueva colocación o un cambio en las paradas. Las paradas inalcanzables
  se excluyen de `P` y se contabilizan por separado.

### 7.6 Reglas globales de actualización

- **R16 (sincronía)**: todas las decisiones se toman observando únicamente
  `grid` en la generación `t`; los resultados se escriben en `new_grid` y se
  publican al final (`grid ← new_grid`).
- **R17 (exclusividad)**: `targets_taken` impide que dos agentes ocupen la misma
  celda en la generación `t+1`.
- **R18 (generación)**: la aparición de vehículos es estocástica y está acotada
  por `max_vehicles`; nunca se generan sobre celdas ocupadas.
- **R19 (estadística)**: al final de cada generación se registra una instantánea
  de todas las métricas, incluidas las del repartidor.
