# Protocolo experimental — QoS de subida en hogar-oficina (F3)

**Estado: VERSIÓN 3.1 (10-10-2026), redactada por Claude Code en Linux. CONGELADA EN P3a** (diseño, hipótesis, análisis y reglas): fecha, hora de Guayaquil y SHA-256 de este fichero en el §28 del plan.
Sustituye a `PROTOCOLO_v3.md`. Solo añade los cinco puntos que Ronald aprobó el 10-10 a las 10:14 (§27 del plan), sobre `REVISION_PROTOCOLO_v3_desde_Mac_2026-10-10.md`; el diseño y el recuento de celdas no cambian. Qué se aplicó: §16.
**Congelación en dos pasos (§27.1):** P3a = este fichero. **P3b** = los valores numéricos que el piloto obtiene con las reglas del §10, anotados en el plan con fecha **antes** de la primera corrida de la campaña; la campaña no empieza sin que Ronald los vea.
Se congela cuando Ronald lo apruebe: fecha y SHA-256 de este fichero en el plan y, si se usa, commit en el repositorio nuevo. Lo que se decida después se declara como cambio posterior o como análisis exploratorio.

Fuentes: plan (`0. Revisiones/PLAN_REHACER_PAPER_QoS_2026-10-08.md`, §§5, 15, 17, 19–22); `F2_viabilidad/ESTADO_F2.md`; `SLR_rehacer/TABLA_GAPS.md` (v6) y `EXTRACCION_TEXTO_COMPLETO.md`; las dos revisiones del Mac; normas en `fuentes/` (con `LEEME.md` de procedencia).
Ya no quedan marcas de decisión ni de verificación: las decisiones están en los §§22–25 del plan y las normas, verificadas (`fuentes/LEEME.md`, `VERIFICACION_NORMAS_VOZ_2026-10-10.md`).

---

## 0. Qué es confirmatorio y qué no

- **Exploratorio:** todo F2 (09–10-10-2026), incluidas las pruebas de reservas y Bc del 10-10.
- Las hipótesis se formularon después de ver F2 (v0, 09-10) y se reformularon el 10-10 en dos pasos: v1, tras la primera revisión del Mac (dependencia de la regla de reserva), v2, tras la segunda (cota de RFC 2212, H3 solo con k = 3, pruebas pareadas), y v3, tras la tercera (control negativo entre CBWFQ y LLQ, referencias de H3 por variable, MOS). Ningún dato de F2 se usa como evidencia confirmatoria.
- **Confirmatorio:** solo la campaña F4 con este protocolo congelado y datos nuevos. Todo análisis no previsto aquí se presenta como exploratorio.

## 1. Pregunta de investigación

En un enlace de subida lento compartido (hogar-oficina), ¿en qué región de **(capacidad de la línea L, número de clases saturadas k, reserva de voz, tamaño de la trama competidora, número de llamadas)** deja CBWFQ de proteger la voz y hace falta LLQ? ¿Cuánto hay que sobrerreservar para que CBWFQ baste? ¿Cuánto cuesta LLQ a las demás clases? ¿Cómo se comparan con fq_codel y CAKE?

Huecos: G2, G3, G4 y G5 de `TABLA_GAPS.md` (v6). No se afirma ser la primera comparación CBWFQ/LLQ en GNS3 (G1: Q005).

## 2. Hipótesis

Notación, por corrida:
- `T_s = MTU_L2 · 8 / L`: tiempo de transmisión de la trama competidora en la línea.
- `T_r = M · 8 / B_v`, con M = 214 B (trama de voz a nivel 2): tiempo de un paquete de voz a la tasa reservada `B_v`.
- `Δ = p99(CBWFQ) − p99(LLQ)` del retardo unidireccional de la voz, entre corridas emparejadas del mismo bloque.

**Cotas de referencia (de la teoría, no del banco):**
- LLQ, **cota del p99**: argumento de prioridad sin expropiación; la voz espera, como mucho, la trama competidora en transmisión: `≈ T_s + T_voz`. Esto no sale de Q017.
- Q017 (espera media exacta de la clase de prioridad, con llegadas de Poisson y carga < 1) queda **solo como trabajo relacionado**: en la campaña la voz es de tasa constante y las celdas con competencia están saturadas, así que no hay celdas donde aplicarla (§27.5).
- CBWFQ: cota de las colas justas ponderadas según **RFC 2212** (verificado en el texto oficial, `fuentes/RFC2212.txt`): retardo ≤ `(M + C)/R + D`, con «C is set to M» y «D is set to the link MTU divided by the link bandwidth». Para voz de tasa constante y un salto: **retardo ≤ 2·T_r + T_s**. Parekh y Gallager (IEEE/ACM ToN, 1993) se cita solo como origen de la disciplina: su Teorema 1 lo confirmó el Mac; la forma σ/g no.

**Hipótesis:**
- **H1 (un competidor: equivalencia).** Con k = 1 y la voz dentro de su reserva, CBWFQ y LLQ son equivalentes en p99 de voz: TOST con margen δ = efecto mínimo de interés (EMI), fijado antes de la campaña (§10). El p99 de ambas queda cerca de la cota de LLQ, `T_s + T_voz + suelo(L)`.
- **H2 (varias clases: ventaja de LLQ).** Con k ≥ 2 y la reserva base (m = 0,2), Δ > 0 en cada L (prueba pareada, §11).
- **H3 (de qué depende la ventaja; solo k = 3).** Dos regresiones sobre T_s y T_r, **solo con k = 3**, que es donde el diseño hace variar T_r (E1-R); con k = 2, T_r es constante y b no es identificable, y así se declara. Cada una se compara con su referencia teórica:

  | Variable | Modelo | Referencia de a (T_s) | Referencia de b (T_r) |
  |---|---|---|---|
  | p99 de CBWFQ | `p99 ≈ a·T_s + b·T_r + c` | 1 | 2 |
  | Δ = p99 CBWFQ − p99 LLQ | `Δ ≈ a·T_s + b·T_r + c` | 0 (T_s se cancela: la cota de LLQ también lo contiene) | 2 |

  - IOS no implementa la disciplina ideal (Q007): se informa cuánto se aparta.
  - Un a > 0 en Δ significaría que CBWFQ de IOS hace esperar a la voz más de una trama competidora, cosa que la disciplina ideal no hace. En F2 (exploratorio) Δ/T_s rondaba 2.
  - Resultado práctico: **sobrerreserva mínima** m*(L) con la que el p99 de CBWFQ queda por debajo de cada presupuesto (§9), con IC. Se estima con cuatro niveles de m (0,2; 0,5; 1; 3); entre niveles se interpola en log(1 + m) y la resolución se declara.
- **H4 (fq_codel y CAKE).**
  - fq_codel da a la voz un p99 comparable al de LLQ mientras su tasa esté por debajo de la parte que le toca a su flujo (≈ R / n.º de flujos activos, que se registra por corrida).
  - CAKE `diffserv4`, mientras la voz no supere el umbral de la clase Voice (25 % de R; al superarlo pierde prioridad, no se corta; `tc-cake(8)`).
  - Por encima de esos umbrales, ambos se degradan.
  - Como la ráfaga que llega al módem difiere entre plataformas (§3), cada política se compara también con el suelo de **su** plataforma (§7.8, §11).
- **H5 (coste de LLQ).** Con la voz dentro de la tasa de prioridad, el caudal útil TCP de datos y residencial con LLQ no es menor que con CBWFQ en más de **δ_c = 5 % del caudal con CBWFQ** (TOST). Con la voz por encima (1,5 × B_v) se mide sin hipótesis direccional.

## 3. Banco

- GNS3 3.0.6. Topología reducida:
  - extremos CW-VOZ y CW-DAT (VLAN 10) y RES-1 (VLAN 20);
  - conmutador integrado de GNS3 (troncal 802.1Q);
  - **R-BORDE** (IOU L3 15.5(2)T) y **LXR** (Linux `tc`) en paralelo;
  - **MODEM** (Linux, `netem rate` = L, cola de 64 paquetes) y SINK.
  - IOSv se añade para E4(b) cuando pase las pruebas 2.3 y 2.4. **Si no las pasa, E4(b) se retira, se declara en el paper y la fidelidad se apoya en E4(a), (c) y (d)** (§27.4).
- Extremos Docker `qos-endpoint:f2` (Debian 12, iperf 3.12); el digest de la imagen se guarda en cada `meta.json`.
- Host: Ubuntu, kernel 7.0.0-34, AMD Ryzen 5 7535HS, conectado a la corriente. Gobernador `performance` y C2/C3 desactivados (obligatorio).
- **R-BORDE:**
  - `ip cef`, `no cdp run`, `no keepalive`;
  - PARENT `shape average R Bc 0` con R = 0,95·L, **Bc = R × 4 ms** (el mínimo que IOS acepta) y **Be = 0**: sustituye a la condición 2 de P2, que no es realizable; se declara en el paper.
  - Ráfaga que llega al módem ≈ Bc + 1 trama: ≈ 4 tramas a 10 Mbps y ≈ 2 a ≤ 2 Mbps (F2 exploratorio).
  - El ejecutor **aborta** la corrida si `show policy-map interface` no muestra PARENT aplicada (IOS puede aceptar la configuración y no aplicarla sin avisar).
- **LXR:** HTB raíz a R (`burst`/`cburst` 1600 B) con hoja pfifo (`limit` Q) o fq_codel (por defecto); CAKE `bandwidth R diffserv4`; GSO/TSO/GRO desactivados (Q159).
- **Asimetría de ráfaga entre plataformas** (IOU ≈ Bc; HTB 1600 B; CAKE sin ráfaga):
  - control positivo en las dos plataformas (§6, C);
  - cada política se compara con el suelo de su plataforma;
  - FIFO-C frente a FIFO-L se informa como diferencia entre bancos;
  - celdas de sensibilidad con la ráfaga de HTB igualada a Bc (§6, S).

## 4. Políticas

| Código | Plataforma | Configuración |
|---|---|---|
| FIFO-C | IOU | Solo PARENT; FIFO con `queue-limit` Q |
| CBWFQ | IOU | CHILD: voz `bandwidth B_v`; vídeo `bandwidth B_vid`; datos `bandwidth B_dat`; class-default `fair-queue` |
| LLQ | IOU | Igual, con la voz en `priority B_v` |
| FIFO-L | Linux | HTB a R + pfifo `limit` Q |
| FQC | Linux | HTB a R + fq_codel |
| CAKE | Linux | `cake bandwidth R diffserv4` |

- **Reservas en kbps:**
  - `B_v = llamadas × 85,6 × (1 + m)`;
  - `B_vid = 0,25 × R`;
  - `B_dat = 0,20 × R`.
- **El policy-map es idéntico para todo k:** las clases de vídeo y datos existen aunque no lleven tráfico (k = 1 o 2). Así la factibilidad y los pesos no cambian con k.
- **Factibilidad.** IOU aplica la política hasta una reserva total del 99 % de R y la rechaza, sin mensaje, desde el 100 % (`F2_viabilidad/results/t_c12_reservations.jsonl` y `t_c2_limit.jsonl`).
  - Regla: celda factible si `B_v + B_vid + B_dat ≤ 0,99·R`.
  - Las no factibles se excluyen y se listan por script en `cells_excluded.csv`.
- **CAKE y el marcado.** Mismo DSCP en todas las plataformas. En `diffserv4`, AF41 (vídeo) y AF21 (datos) comparten la clase Video; se declara. En CAKE, k = 3 son dos clases (Video y Best Effort) más la voz.
  - Sensibilidad (decisión 2): 2 celdas con los datos remarcados a CS1 (clase Bulk de CAKE), para tener tres clases distintas (§6, S).

## 5. Tráfico

Diseño anidado de k:

| Clase | Entra con | Generador | DSCP | Perfil |
|---|---|---|---|---|
| Voz | siempre | `udpprobe.py` | EF | G.711 a 20 ms: 172 B de UDP (214 B a nivel 2, 85,6 kbps) por llamada |
| Residencial | k ≥ 1 | iperf3 TCP (1 flujo) + `udpprobe.py` UDP de 1472 B a 0,8·L | 0 | Masivo |
| Vídeo | k ≥ 2 | `udpprobe.py` UDP de 1000 B a 0,6·L | AF41 | Fracción fija de L |
| Datos | k = 3 | iperf3 TCP (1 flujo) | AF21 (CS1 en las 2 celdas de sensibilidad de CAKE) | Masivo, reactivo |

- Opus y el perfil de videollamada de Q313 quedan fuera de la campaña confirmatoria.
- La carga ofrecida se mide en el emisor y el caudal en el receptor; la utilización se reporta medida.

## 6. Experimentos

Unidad de análisis: la corrida. Duración: 40 s de medida más calentamiento (lo fija el piloto; propuesta inicial: 5 s). Base: 1 llamada, m = 0,2, trama competidora de 1514 B, Q = 64.

| Exp. | Pregunta | Factores | Celdas |
|---|---|---|---|
| **E1** | H1, H2, H4 | k = 1 y k = 3: las 6 políticas × L {0,5; 1; 2; 5; 10} (60). k = 2: CBWFQ, LLQ, FQC, CAKE × 5 L (20) | 80 |
| **E1-R** Reserva | H3, sobrerreserva | CBWFQ, LLQ × 5 L × m {0,5; 1; 3}; k = 3. Excluida por factibilidad: L = 0,5 con m = 3. (m = 0,2 está en E1) | 28 |
| **E2** Trama y llamadas | ¿Cambia la frontera? | CBWFQ, LLQ, FQC, CAKE × L {0,5; 1; 5} × trama {590; 1514} B × llamadas {1; 4}; k = 3. Excluida: L = 0,5 con 4 llamadas | 40 |
| **E3** Coste | H5 | CBWFQ, LLQ × L {1; 5} × voz {dentro de la reserva; 1,5 × B_v}; k = 3 | 8 |
| **E4** Fidelidad | Banco frente a teoría, otro emulador y hardware | (a) sin corridas nuevas: LLQ de E1 frente a la cota de prioridad sin expropiación y **CBWFQ de E1/E1-R frente a 2·T_r + T_s (RFC 2212)**; (b) IOSv frente a IOU: L {1; 5} × k {1; 3} × {CBWFQ, LLQ}; (c) repetición de 4 celdas de E1 otro día; (d) escenarios de Q004 (384 kbps) y Q034 (480 kbps) frente a sus cifras de hardware (sin c7200) | ≈ 18 |
| **S** Sensibilidad | ¿Sobrevive el resultado a lo que elegimos? | Sobre L {1; 5} × k 3 × {CBWFQ, LLQ}: Q {16; 256}, fracción del shaper 0,90, Be = Bc (por defecto) y duración de 120 s (20). Ráfaga de HTB = Bc con FQC a L {5; 10}, k 3 (2). CAKE con los datos en CS1, L {1; 5}, k 3 (2) | 24 |
| **S-H** Host cargado | Robustez frente al estado del equipo | CBWFQ, LLQ × L {1; 5}; k = 3; 10 de 12 núcleos ocupados; sin el criterio de invalidez por carga | 4 |
| **C** Controles | §7 | Negativo: CBWFQ y LLQ con todo sin marcar, k {1; 3} × 5 L (20). Positivo, en las dos plataformas: FIFO-C y FIFO-L a 0,5·R × 5 L (10) | 30 |

**Total ≈ 232 celdas** (80 + 28 + 40 + 8 + 18 + 24 + 4 + 30). El coste se calcula con el tiempo por corrida medido en el piloto. Estimación sin medir, a ~75 s por corrida: unas 145 h con n = 30 y unas 97 h con n = 20.

## 7. Controles obligatorios

1. **Negativo:** con todo el tráfico sin marcar, todo cae en `class-default`, que es idéntica en las dos políticas. Criterio: **CBWFQ sin marcas ≡ LLQ sin marcas** (TOST, δ = EMI), en k = 1 y k = 3. Así se demuestra que la diferencia entre ellas viene de la clasificación y la prioridad. FIFO-C se informa como referencia, sin criterio de aprobado: no se espera que coincida, porque `fair-queue` reparte por flujo y protege la voz aunque no esté marcada. Lo que mide (cuánto protege `fair-queue` por sí solo) es un dato para el paper. El piloto incluye este control (§10) para confirmar el comportamiento antes de la campaña.
2. **Positivo**, en IOU y en Linux: sin congestión (0,5·R), FIFO-C y FIFO-L quedan en el suelo de su plataforma y su L.
3. **Contabilidad de paquetes:** por clase en R-BORDE (UDP), agregada en LXR, y de TCP por captura en el emisor y en SINK.
4. **Carga ofrecida y caudal recibido** medidos.
5. **Orden aleatorizado** con semilla, por bloques (cada bloque contiene todas las políticas de una combinación de factores), en al menos dos sesiones en días distintos.
6. **Calentamiento** descartado.
7. **`meta.json` por corrida:**
   - configuración efectiva y `tc -s` antes y después;
   - cola del módem en bytes cada 20 ms;
   - en FQC, flujos activos (`new_flows_len` y `old_flows_len`, muestreados);
   - estado de energía de la CPU, carga del host y CPU de IOU;
   - semilla, hash de los scripts, digest de la imagen y versiones.
8. **Suelo por L y por plataforma** (voz sola, por IOU y por Linux): 10 corridas por L, plataforma y sesión.

## 8. Criterios de invalidez (automáticos; la corrida se guarda aparte con el motivo y se repite)

- La política PARENT no está aplicada.
- Contabilidad con discrepancia > 1 %.
- Caudal del shaper fuera de R ± 5 % con saturación.
- Cola del módem > Bc + 2 tramas + 3 de voz (en bytes) o algún descarte en el módem. Umbral derivado de F2; el piloto lo revisa.
- Gobernador distinto de `performance` o C-states profundos activos.
- **Carga del host** por encima de **el máximo de la carga media de 1 min observado en el piloto × 1,5** (§25.3 del plan). El piloto se corre **sin ningún otro uso del equipo**. No se aplica en S-H.
- «Ignored» de entrada o fallos de búfer de R-BORDE que crecen durante la corrida.
- Receptor o iperf3 incompleto, o recuento de la sonda que no cuadra.
- **Nunca se escribe 0 ni se rellena un valor por un fallo.**

## 9. Métricas

- **Voz:**
  - retardo unidireccional p50, p95 y p99 por corrida, y pérdida;
  - jitter RFC 3550 §6.4.1: `J(i) = J(i−1) + (|D(i−1,i)| − J(i−1))/16`, con `D(i,j) = (Rj − Ri) − (Sj − Si)`;
- **Factor R y MOS (métrica secundaria y estimada; §24 del plan).** Se calcula después de la campaña desde las trazas por paquete, sin corridas extra. Ecuaciones de ITU-T G.107 (06/2015), copiadas viendo el PDF (`fuentes/`):
  - (7-1) `R = Ro − Is − Id − Ie-eff + A`;
  - (7-18) `Id = Idte + Idle + Idd`;
  - (7-27) `Idd = 25·{(1 + X^(6·sT))^(1/(6·sT)) − 3·(1 + [X/3]^(6·sT))^(1/(6·sT)) + 2}` si `Ta > mT` (`Idd = 0` si `Ta ≤ mT`);
  - (7-28) `X = log(Ta/mT)/log 2`;
  - (7-29) `Ie-eff = Ie + (95 − Ie)·Ppl/(Ppl/BurstR + Bpl)`;
  - (B-4) `MOS = 1 + 0,035·R + R·(R − 60)·(100 − R)·7·10⁻⁶` para 0 < R < 100 (1 si R < 0; 4,5 si R > 100).

  **Cálculo por corrida** (voz, sin el calentamiento):
  1. `d_i` = retardo unidireccional del paquete i; `d_min` = el mínimo de la corrida.
  2. Búfer de reproducción estático de tamaño `B`: el paquete i llega tarde si `d_i > d_min + B`.
  3. `Ppl` = (perdidos en red + tardíos) / enviados, en %. G.113 indica que la pérdida que cuenta es la de salida del búfer.
  4. `Ta = d_min + B + T_resto`.
  5. `R = 93,2 − Idd − Ie-eff` (resto de parámetros por defecto, R = 93,2); MOS con (B-4).

  **Parámetros (fijados antes de la campaña):**

  | Parámetro | Caso principal | Sensibilidad | Origen |
  |---|---|---|---|
  | Búfer `B` | 60 ms | 40 y 100 ms | Elección del proyecto; no sale de una norma |
  | Retardo del resto del camino `T_resto` | 100 ms | 50 y 150 ms | Elección del proyecto; no sale de una norma |
  | `Bpl` de G.711 | 4,3 (sin ocultación) | 25,1 (con ocultación) | G.113 (09/2024), Tabla I.4 |
  | `Ie` de G.711 | 0 | — | G.113, Tablas I.1 e I.4 |
  | `BurstR` | 1 | — | G.113: el ajuste por ráfagas solo se recomienda con Bpl ≥ 16 |
  | `sT`, `mT` | 1 y 100 ms | — | G.107, Tabla 1, clase por defecto |

  **Simplificaciones que se declaran en el paper:**
  - solo se usa `Idd`; `Idte` e `Idle` (eco) quedan en su valor por defecto;
  - los Bpl de la Tabla I.4 son para paquetes de 10 ms y la sonda es de 20 ms;
  - el búfer es estático (G.113 remite a G.1020 para emularlo; no se ha abierto);
  - el MOS es estimado por un modelo de planificación, no medido; la calidad sobre audio real (PESQ, POLQA) queda fuera y se declara como limitación.

  **Presentación:** figura del MOS frente a `T_resto` por política, con el caso principal marcado. La conclusión se da como robusta solo si no cambia en el rango de sensibilidad. Comprobación de cordura (cálculo con la ecuación 7-27): Idd = 0 hasta 100 ms de Ta, 0,16 a 150 ms, 3,0 a 200 ms y 14,8 a 300 ms; con Bpl = 4,3, un 1 % de pérdida da Ie-eff ≈ 17,9.
- **Coste:** caudal útil TCP de datos y residencial, y su RTT.
- **Secundarias:** retardo máximo (obligatorio a L ≤ 1 Mbps; Q048), ráfagas de pérdida, descartes por clase.
- **Presupuestos de retardo (decisión 4):**
  - el resultado principal son las **curvas continuas**;
  - 20, 50 y 100 ms se presentan como **ilustrativos**. Lo defendible: 100 ms es todo el presupuesto de retardo medio y 50 ms todo el de variación de la clase 0 de Y.1541, de extremo a extremo (según RFC 5976, que cita la edición de 2006; Y.1541 no se abrió); 20 ms es una fracción arbitraria y se declara como tal. Ninguna norma reparte el presupuesto al tramo de acceso;
  - G.114 (verificado): 150 ms en un sentido como objetivo de extremo a extremo y 400 ms como máximo; no da límite de jitter;
  - los 30 ms de jitter y el 1 % de pérdida son recomendaciones de diseño de Cisco y no se atribuyen a la ITU.
- **Doble camino (decisión 5):** el retardo se recalcula desde capturas `tcpdump` en el emisor y en SINK en un 10 % de las corridas, estratificado (al menos una por celda), y en todas las del piloto. Discrepancia del p99 ≤ 0,1 ms.

## 10. Piloto y tamaño de muestra

- **Celdas del piloto:**
  - E1 con L {0,5; 1; 5}, k {1; 3}, CBWFQ y LLQ;
  - **FQC y CAKE con L = 1 y k = 3** (tiempo por corrida y carga del host en Linux);
  - E1-R con L 1 y m 3;
  - **control negativo con L = 1 y k = 3** (CBWFQ y LLQ sin marcas, más FIFO-C), para confirmar el comportamiento de `class-default`;
  - suelo por L y plataforma;
  - 5 corridas por celda. No entra en el análisis confirmatorio.
- **El piloto se corre sin ningún otro uso del equipo** (fija el umbral de carga).
- **Doble camino en todas las corridas del piloto.**
- **Reglas congeladas en P3a (§27.2–3); el piloto solo aplica las reglas, no elige los valores:**

  | Valor | Regla |
  |---|---|
  | **EMI** (= δ de H1 y del control negativo; base del cálculo de n) | El mayor entre **2 ms** y el **10 % del p99 de LLQ en esa L**, medido en el piloto. Es un umbral de relevancia práctica: el piloto solo comprueba que es detectable con n ≤ 30 (a 0,5 Mbps la amplitud del suelo con línea ronda 1,7–2,4 ms). Si no lo es, se informa y decide Ronald |
  | **n por celda** | El menor n entre 10 y 30 que da potencia 0,80 (α = 0,05 con Holm) para el EMI, con la desviación entre corridas del piloto en la **celda más ruidosa**. Si hace falta más de 30, se informa y decide Ronald |
  | **Calentamiento** | El menor múltiplo de 5 s tras el cual la mediana del retardo en ventanas de 5 s deja de cambiar más que la amplitud del suelo, en todas las celdas del piloto |
  | **Duración** | 40 s, salvo que el p99 de 40 s y el de 120 s difieran en más del EMI en el piloto; entonces 120 s |
  | **Cola del módem** (§8) | El máximo observado en el piloto en corridas válidas, más una trama |
  | **Carga del host** (§8) | Máximo de la carga media de 1 min del piloto × 1,5 |
  | Tiempo por corrida | Se mide (horas de máquina reales) |

- Los valores resultantes se anotan en el plan con fecha (**P3b**) antes de la primera corrida de la campaña.

## 11. Plan de análisis (F5)

- **Por celda:** mediana entre corridas e IC 95 % por bootstrap (10 000 remuestreos, semilla fija); delta de Cliff con IC.
- **H1 y control negativo:** TOST de la diferencia de p99 CBWFQ − LLQ, emparejada por bloque, con margen δ = EMI.
- **H2:** prueba **pareada** por celda sobre Δ (permutación de signos; Wilcoxon de rangos con signo como comprobación); Holm por familia (experimento × k).
- **H3** (k = 3): dos regresiones sobre E1 + E1-R (m {0,2; 0,5; 1; 3}), con IC 95 % por bootstrap de a y b: p99 de CBWFQ (referencia a = 1, b = 2) y Δ emparejado por bloque (referencia a = 0, b = 2). Resultado práctico: m*(L) para cada presupuesto, interpolando en log(1 + m).
- **H4:**
  - LLQ frente a FQC y CAKE por celda, Holm por familia (experimento × k);
  - cada política se informa también como exceso sobre el suelo de su plataforma;
  - región donde FQC y CAKE dejan de cumplir, con el n.º de flujos activos como covariable.
- **H5:** TOST del caudal útil TCP con δ_c = 5 %.
- **Frontera:** L* donde el p99 de CBWFQ cruza cada presupuesto, interpolado en log L, con IC por bootstrap.
- **E4(a):** p99 de LLQ frente a `T_s + T_voz` (no expropiación) y p99 de CBWFQ frente a `2·T_r + T_s` (RFC 2212), en cada celda de E1/E1-R (cociente medido / cota, con IC).
- **Reimplementación por otro camino:** percentiles y jitter recalculados desde las capturas, con código distinto.
- **Contraste con la literatura:** E4(d) frente a Q004 y Q034.
- Figuras con la skill `dataviz` (cada PNG se abre y se revisa). Todas las cifras del manuscrito salen de `results/numbers.json`.

## 12. Amenazas a la validez

- IOU no es hardware: se mitiga con E4; las cifras absolutas se declaran propias del banco.
- La política actúa solo en subida (D14).
- La línea es `netem rate`, sin capa física real. Bc mínimo de IOS (Tc ≥ 4 ms, Be = 0) y la fracción 0,95 condicionan dónde se forma la cola; la ráfaga difiere entre plataformas (§3).
- Tráfico sintético; un flujo TCP por clase.
- En CAKE, vídeo y datos comparten clase con el marcado estándar (§4); sensibilidad con CS1.
- Un solo host: la energía y la carga de la CPU cambian la magnitud → criterio de invalidez y S-H.

## 13. Antes de congelar

1. ~~Decisiones de Ronald~~: resueltas (§22 del plan).
2. ~~Normas~~: G.113 verificada (Mac y Linux); Y.1541 solo a través de RFC 5976; presupuestos ilustrativos.
3. ~~Umbral de reserva de IOU~~: hecho (≤ 0,99·R).
4. Validar IOSv (2.3 y 2.4) y repetir 2.3 con Bc mínimo y Be = 0 a 1 y 10 Mbps.
5. Implementar en el ejecutor:
   - reservas en kbps con factibilidad;
   - TCP con contabilidad por captura;
   - muestreo de flujos de fq_codel;
   - ráfaga de HTB configurable;
   - remarcado a CS1;
   - cálculo del MOS (§9) en el análisis, desde las trazas;
   - aleatorización por bloques con semilla;
   - criterios de invalidez y reanudación por corrida.

## 14. Qué se aplicó de §22 en la v2 (histórico)

| Punto | Estado |
|---|---|
| D1 Bc mínimo y Be = 0, declarado | Aplicado (§3) |
| D2 CAKE: declarar y 2 celdas con datos remarcados | Aplicado (§4, §6 S): datos en CS1 (Bulk) |
| D3 Umbral de carga desde el piloto | Aplicado (§8, §10); regla propuesta ×1,5 sobre el máximo del piloto |
| D4 Curvas continuas; presupuestos ilustrativos | Aplicado (§9); Y.1541: resuelto en la v3 (§15) |
| D5 Doble camino 10 % estratificado + piloto entero | Aplicado (§9, §10) |
| D6 EMI con el piloto | Aplicado (§10) |
| D7 δ de H1 = EMI, fijado antes | Aplicado (§2, §11) |
| D8 δ_c = 5 % | Aplicado (§2, §11) |
| A1 Asimetría de ráfaga | Aplicado: control positivo en las dos plataformas (+5 frente a la v1), suelo por plataforma, FIFO-C frente a FIFO-L, HTB = Bc (+2) |
| A2 H3 solo con k = 3 | Aplicado (§2, §11) |
| A3 Margen del TOST no sale de los datos | Aplicado (D7) |
| A4 Policy-map idéntico para todo k | Aplicado (§4) |
| RFC 2212 para la cota | Aplicado y **verificado también en Linux** contra el texto oficial (`fuentes/RFC2212.txt`) |
| E4(a) con CBWFQ frente a 2·T_r + T_s | Aplicado (§6, §11) |
| Prueba pareada en H2 | Aplicado (§11) |
| G.107 copiada viendo el PDF | Aplicado: ecuaciones 7-1, 7-18, 7-27, 7-28, 7-29 y B-4 y Tabla 1, leídas en las páginas renderizadas (`fuentes/LEEME.md`) |
| G.113 (Ie, Bpl) e Y.1541 | En la v2 seguían pendientes; resueltos en la v3 (§15) |

**Controles, recuento corregido y una propuesta de Linux (no aprobada todavía).** La v1 daba 15 celdas de control, pero su propia descripción sumaba 25 (negativo con CBWFQ y LLQ × k {1; 3} × 5 L = 20, más 5 de positivo): era un error de recuento de la v1. En la v2 propongo hacer el negativo **solo con LLQ** (la clasificación por DSCP es la misma en las dos políticas; si LLQ coincide con FIFO-C sin marcas, no hay otra vía), 10 celdas, más el positivo en las dos plataformas (10): 20 en total. **Si Ronald prefiere mantener CBWFQ en el control negativo, son +10 celdas (222 en total).** *(Superado en la v3: la propuesta era errónea —sin marcas, `fair-queue` también protege la voz— y Ronald aprobó el control con las dos políticas, §25.1.)*

## 15. Qué se aplicó de §§24–25 (v3)

| Punto | Estado |
|---|---|
| §25.1 Control negativo «CBWFQ ≡ LLQ sin marcas», las dos políticas, FIFO-C como referencia, celda en el piloto | Aplicado (§6 C: 20 celdas de negativo; §7.1; §10; §11) |
| §25.2 H3 con dos regresiones y su referencia | Aplicado (§2, tabla; §11) |
| §25.3 Umbral de carga = máximo del piloto × 1,5, piloto sin otro uso del equipo | Aplicado (§8, §10) |
| §25.4 m = 0,5 en E1-R | Aplicado (+10 celdas; L = 0,5 con m = 0,5 suma el 72 % de R: factible) |
| §24 MOS | Aplicado (§9), con la especificación de la revisión |
| FQC y CAKE en el piloto | Aplicado (§10) |
| Q017 separada de la cota del p99 | Aplicado (§2, §11) |
| Marcas de G.113 e Y.1541 | Quitadas; G.113 añadida a `fuentes/LEEME.md`, también comprobada en Linux |
| Recuento | 232 celdas (80 + 28 + 40 + 8 + 18 + 24 + 4 + 30) |

Comprobado también en Linux, por script: Idd (ecuación 7-27) = 0 / 0,16 / 3,04 / 14,76 / 24,07 a 100 / 150 / 200 / 300 / 400 ms, e Ie-eff (7-29) con un 1 % de pérdida = 17,92 (Bpl 4,3) y 3,64 (Bpl 25,1): coinciden con los del Mac.

## 16. Qué se aplicó de §27 (v3.1; congelación P3a)

| Punto | Estado |
|---|---|
| §27.1 Congelación en dos pasos | Aplicado (cabecera; §10) |
| §27.2 Regla del EMI | Aplicado (§10, tabla de reglas) |
| §27.3 Reglas de n, calentamiento, duración, cola del módem y carga | Aplicado (§10, tabla de reglas) |
| §27.4 Salida si IOSv no pasa 2.3/2.4 | Aplicado (§3) |
| §27.5 Q017 fuera de E4(a) y del §11 | Aplicado (§2, §6, §11); queda como trabajo relacionado |

No se tocó nada más: diseño, hipótesis, análisis y recuento (232 celdas) son los de la v3.
