# Plan de análisis consolidado (F5) — QoS de subida en hogar-oficina

**Estado:** versión 2 (17-10-2026), redactada por Claude Code en Linux. Aplica los seis cambios de `REVISION_PLAN_ANALISIS_desde_Mac_2026-10-17.md` sobre la v1 (SHA-256 `93d17c72…1c633`). **Se congela con su SHA-256 en el plan (§54) antes de calcular ninguna prueba.** El Mac lo revisa antes de que se ejecute nada (§53.1).

**Fuentes que reúne:**
- `F3_protocolo/PROTOCOLO_v3.1.md` (P3a, SHA-256 `c84b7f58…98e2f8f`): §§2, 6, 7, 9 y 11;
- valores de P3b (§41.1 del plan);
- cambios posteriores: §§36, 40, 41.5, 43.5, 43.7, 47.2, 50, 51.7 y 53.

**Marcas:**
- **[P3a]**: literal del protocolo congelado.
- **[§n]**: decisión posterior aprobada por Ronald, en esa sección del plan.
- **[OP-Mac]**: cambio pedido por el Mac en su revisión de la v1.
- **[OP-Linux]**: operativización mía de algo que P3a dejó sin precisar. Va marcada para que el Mac la revise; si la cambia, se cambia aquí antes de congelar.

Ninguna prueba se ha calculado al escribir este plan. Lo único que he mirado de la campaña es descriptivo y no compara políticas: completitud, checksums, motivos de invalidez, suelos a 1 Mbps y el registro de entrada de LXR (§§52–54).

---

## 1. Datos y reglas de inclusión

### 1.1 Corridas

- **Directorio:** `F4_campana/campaign/`, con una carpeta por corrida válida. La lista es `state.json["done"]` (4304 corridas, §52).
- **Corridas que entran en el análisis principal:**
  - las 233 celdas × repeticiones 1–17 y los 12 suelos × repeticiones 1–20;
  - **las 103 corridas de la lista `battery_runs_20261014.json` se sustituyen por su repetición `_ac`** [§47.2]. La original queda solo para la sensibilidad del §5.4;
  - **las 10 celdas IOU con k = 1 a 2 y 3 Mbps** (`SHAPER_EXEMPT`) entran con su caudal medido (`shaper_rate_bps`, `shaper_err`) [§50];
  - **las corridas marcadas por pérdidas de entrada** (`marcada` = true) entran [§36]; la sensibilidad las excluye (§5.1);
  - **el c7200 solo entra en E4(b)** y en su suelo [§40.7, §43.4].
- **No entran:** las tentativas de `_invalid/` (salvo en la sensibilidad del §5.5), las corridas de `pilot/`, `csmoke*/`, `diag42/` y `fix_tests/`, y las celdas retiradas (c7200 a 5 Mbps).

### 1.2 Bloques y emparejamiento

- **Bloque:** el identificador de celda sin plataforma ni política, más la repetición. Por ejemplo, `E1_L2000k_k3_m0.2_c1_f1514` r05 contiene las seis políticas de E1 con L = 2 Mbps y k = 3 en la repetición 5.
- **Par CBWFQ–LLQ:** las dos corridas del mismo bloque y repetición.
  - Si una corrida se sustituyó por su `_ac`, el par usa la `_ac`.
  - Comprobado: ningún par CBWFQ–LLQ quedó partido por el corte del 14-10. Ambos miembros de cada par están en la lista de batería o ninguno lo está. El único bloque partido es E2 5 Mbps k = 3 r09, y solo en CAKE.
  - El mismo emparejamiento se usa para LLQ frente a FQC y CAKE (H4), cuyos bloques incluyen las dos plataformas.
- **Las 10 celdas exentas:** sus repeticiones 1–9 se corrieron como bloque propio (`campaign1k`) y las 10–17 en la sesión 2. El par se forma igual, por repetición.

### 1.3 Variables por corrida (se recalculan desde los ficheros crudos)

- **Ventana de medida:** paquetes de voz con tiempo de envío en [W, W + D) s, con W = 20 s [§41.1] y D = 40 s (D = 120 s en las 4 celdas S de 120 s de medida). El tiempo cuenta desde el primer envío de ese flujo.
- **Retardo unidireccional:** `recv_ns − send_ns` por paquete (`recv_0.csv`, flujo 100 = la llamada medida).
- **Percentil p de la ventana:** el valor ordenado de índice `round(p · (n − 1))` sobre los paquetes recibidos (el mismo método que `f2lib.owd_stats`).
  - Primaria: **p99**. Secundarias: p50 y p95.
  - [OP-Linux] Se recalcula desde el CSV y se compara con `summary.json["probe0"]["p99"]`. Si alguna diferencia supera 1 µs, se para (auditoría, §3).
- **Pérdida de voz en la ventana:** 1 − recibidos / enviados entre los paquetes enviados en la ventana. [OP-Linux] El `summary.json` guarda la pérdida de toda la corrida; el análisis usa la de la ventana.
- **Jitter RFC 3550** sobre los paquetes de la ventana, ordenados por número de secuencia [P3a §9].
- **Caudal útil TCP:** `rx_bps_steady` del servidor iperf3 (intervalos con inicio ≥ W y fin ≤ duración − 1 s). El flujo se identifica por su puerto en `meta.json["flows"]`: 5302 = datos (AF21) y 5301 = residencial.
  - Con `tcp_hambre` el caudal es 0 y se cuenta por celda [§40.6].
- **Caudal del shaper:** `shaper_rate_bps` y `shaper_err` (ventana [10, D − 2] s en SINK).
- **Retardo máximo** (obligatorio a L ≤ 1 Mbps [P3a §9]) y, en FQC, flujos activos (`fqc_flows.txt`, cada 100 ms).

### 1.4 Constantes

- R = 0,95·L (Q004: 364,8 kbit/s; Q034: 480 kbit/s).
- T_s = 1514·8 / L (590·8 / L en las celdas de E2 con trama de 590 B).
- T_voz = 214·8 / L.
- T_r = 214·8 / B_v, con B_v = llamadas × 85,6 × (1 + m) kbit/s.
- EMI(L) = 3,02 ms a 0,5 Mbps y 2,00 ms de 1 a 10 Mbps [§41.1].

---

## 2. Análisis confirmatorio

**Reglas comunes:**
- α = 0,05 por familia, con Holm dentro de cada familia (experimento × k) [P3a §11].
- [OP-Linux] Para las pruebas de igualdad se usa el TOST emparejado con t exacta: p_TOST = máx(p_inferior, p_superior) de las dos pruebas t unilaterales sobre la media de las diferencias emparejadas. Es la forma con la que se calculó n [§40.3, §41-previo].
- «Se cumple» y «no se cumple» se deciden con el p ajustado por Holm. Todo se informa tal como salga, incluido lo que no se cumpla [§53].

### 2.1 H1 — un competidor: equivalencia CBWFQ ≡ LLQ

- **Celdas:** E1, IOU, k = 1, L ∈ {0,5; 1; 2; 3; 5}. Las de 2 y 3 Mbps son exentas, con caudal medido [§50].
- **Variable:** d_r = p99(CBWFQ) − p99(LLQ) por par, n = 17.
- **Prueba:** TOST con margen ±EMI(L). **Familia:** H1 (5 L).
- **Se cumple en L** si p_TOST ajustado < 0,05.
- **También se informa:** la media y la mediana de d con IC 95 % por bootstrap, y el p99 de cada política frente a `T_s + T_voz + suelo(L)` (mediana del suelo IOU de esa L) [P3a §2].

### 2.2 H2 — varias clases: ventaja de LLQ (Δ > 0)

- **Celdas:** las de m = 0,2 con k ≥ 2 [P3a §2], en tres familias:
  - E1 × k = 2 (5 L);
  - E1 × k = 3 (5 L);
  - E2 × k = 3: 10 celdas, L {0,5; 1; 5} × trama {590; 1514} × llamadas {1; 4}, sin L = 0,5 con 4 llamadas.
- **Variable:** Δ_r = p99(CBWFQ) − p99(LLQ) por par.
- **Prueba principal:** permutación de signos **exacta** (las 2¹⁷ asignaciones) sobre la media de Δ, unilateral (Δ > 0) [P3a §11].
  - Comprobación: Wilcoxon de rangos con signo, unilateral.
- **Se cumple en la celda** si p ajustado < 0,05 en la prueba principal.
- [OP-Linux] Se informa también la mediana de Δ con IC 95 % por bootstrap y el delta de Cliff.

### 2.3 H3 — de qué depende la ventaja (solo k = 3)

- **Datos:** E1 (m = 0,2) + E1-R (m ∈ {0,5; 1; 3}), IOU, k = 3, las 5 L; 19 celdas por política.
- **Modelos:**
  - p99(CBWFQ) ≈ a·T_s + b·T_r + c. Referencia: a = 1, b = 2.
  - Δ ≈ a·T_s + b·T_r + c. Referencia: a = 0, b = 2.
- [OP-Linux] **Ajuste:** mínimos cuadrados ordinarios sobre las observaciones por corrida (p99 de CBWFQ) y por par (Δ), con T_s y T_r en ms.
- **Dos IC 95 % de a, b y c**, por bootstrap de percentiles con 10 000 remuestreos (semilla del §7):
  - (a) [OP-Linux] remuestreando las corridas o pares **dentro de cada celda** (estratificado): incertidumbre de medida;
  - (b) [OP-Mac] **por conglomerados**, remuestreando las 19 celdas enteras con todas sus corridas: incluye la falta de ajuste entre celdas.
- **La compatibilidad con la referencia** (a = 1 y b = 2 en p99 de CBWFQ; a = 0 y b = 2 en Δ) **se juzga con el IC (b)** [OP-Mac].
- Se informa:
  - a, b y c con los dos IC y R²;
  - los residuos por celda (media de la celda menos lo que predice el ajuste);
  - [OP-Mac] la **prueba F de falta de ajuste**: el modelo lineal frente al modelo de medias por celda (19 medias).
  - Con k = 2, T_r es constante y b no es identificable; así se declara [P3a §2].
- **Resultado práctico (exploratorio, §6):** m*(L) por presupuesto.

### 2.4 H4 — fq_codel y CAKE frente a LLQ

- **Celdas:** E1 con k ∈ {1; 2; 3} y L ∈ {0,5; 1; 2; 3; 5} (las capacidades de las dos plataformas), más E2 × k = 3.
- **Variable:** p99(X) − p99(LLQ) por bloque, con X ∈ {FQC, CAKE}.
- **Prueba que decide «comparable»:** [OP-Mac] el **TOST** con margen ±EMI(L), que es lo que afirma H4.
  - Familias de Holm: E1 × k (2 comparaciones × 5 L = 10 pruebas por k) y E2 × k = 3 (20 pruebas).
- **La permutación de signos exacta bilateral es descriptiva** [OP-Mac]: informa la dirección y el tamaño de la diferencia, con su p sin ajustar, y no decide nada.
- **También se informa** [P3a §11]:
  - el exceso de cada política sobre la mediana del suelo de su plataforma y L;
  - la región donde FQC y CAKE dejan de ser comparables, con el número de flujos activos de FQC (mediana de `new_flows_len + old_flows_len`) como covariable descriptiva;
  - el umbral de 25 % de R de la clase Voice de CAKE frente a la tasa de voz de cada celda (E2 con 4 llamadas).
- Las celdas a 10 Mbps solo tienen políticas Linux: se informan de forma descriptiva.

### 2.5 H5 — coste de LLQ en caudal TCP

- **Celdas:** E3, IOU, k = 3, L ∈ {1; 5}, con la voz dentro de la reserva.
- **Variable:** caudal útil de datos y residencial por separado; [OP-Mac] por par, **ln(caudal LLQ / caudal CBWFQ)**.
- **Prueba:** TOST sobre la media de ese logaritmo con margen **[ln 0,95; ln 1,05]** [OP-Mac]. Es la pregunta de P3a (δ_c = 5 % del caudal con CBWFQ) con el margen fijado de antemano y no estimado con los datos.
  - [OP-Linux] Familia: E3 (2 L × 2 clases = 4 pruebas).
- **Pares con `tcp_hambre`** en cualquiera de los dos miembros (caudal 0, cociente indefinido) [OP-Mac]:
  - se cuentan e informan aparte, y el TOST se hace sin ellos;
  - si una celda y clase tiene **más de 2**, se informa como **«no evaluable»**.
- **Con la voz a 1,5 × B_v:** el mismo cociente, descriptivo y sin hipótesis direccional [P3a §2].
- Se cuenta `tcp_hambre` por celda.

### 2.6 Controles

- **Negativo** [P3a §7.1]:
  - TOST de p99(CBWFQ sin marcas) − p99(LLQ sin marcas) con margen ±EMI(L);
  - familias CNEG × k = 1 y CNEG × k = 3, de 5 L cada una;
  - se informa tal como salga [§40.5].
  - Complemento descriptivo: §6.3.
- **Positivo** [P3a §7.2]: FIFO-C y FIFO-L a 0,5·R.
  - [OP-Linux] El criterio literal es «quedan en el suelo de su plataforma y su L»: se informa la mediana de p99(CPOS) − mediana de p99(suelo) frente al EMI(L).
  - El aprobado o suspenso se informa con el criterio literal.
  - [OP-Mac] **Criterio físico secundario, fijado ahora:** exceso sobre el suelo ≤ T_s + EMI(L). Con una trama de 1514 B en competencia, la voz puede esperar hasta T_s (24 ms a 0,5 Mbps) incluso sin cola. Por eso el criterio literal no puede cumplirse a L baja, y en el paper se explicará si falla.
  - Se informa también el exceso en unidades de T_s.
- **Contabilidad, carga ofrecida y caudal recibido:** tablas por celda [P3a §7.3–4].

### 2.7 E4(a) — banco frente a teoría

En cada celda de E1 y E1-R, IOU, se calcula el cociente medido/cota, con IC 95 % por bootstrap de la mediana [P3a §11]:
- **LLQ:** el cociente **principal** es p99 / (T_s + T_voz + suelo(L)) [OP-Mac], porque la cota teórica no incluye el retardo propio del banco; se informa también p99 / (T_s + T_voz);
- **CBWFQ:** p99 / (2·T_r + T_s) (RFC 2212).

---

## 3. Auditoría de datos (antes de cualquier prueba) [§53.2]

1. **Tabla de inclusión por celda:** corridas, marcadas, exentas, `_ac`, `tcp_hambre` y tentativas inválidas.
2. **Por cada variable del §1.3:** valores no nulos sobre el total, mínimo y máximo, por celda y global.
   - Una columna entera a cero o vacía para el análisis.
3. **Comprobaciones físicas.** Si alguna sale imposible, se para:
   - p99 de LLQ ≥ mediana del suelo de su L menos la amplitud del suelo;
   - caudal del shaper ≤ R × 1,05;
   - pérdida de voz con LLQ ≈ 0 con la voz dentro de la reserva;
   - retardo mínimo ≥ 0;
   - recibidos ≤ enviados.
4. **El p99 recalculado coincide con `summary.json`** (§1.3) y con la ruta de captura (`voice_owd_capture_path`, ≤ 0,1 ms) en todas las corridas que la tienen.
   - Las 3 celdas Q004 no tienen voz en el rango de puertos de la captura (la sonda es de vídeo); se declara.

---

## 4. Validación del código (antes de usarlo sobre la campaña) [§53.3]

1. **Reproducción del piloto:** con el código de análisis, los p99 por celda, el EMI y las desviaciones de `F4_campana/pilot/ANALISIS_PILOTO.txt` y `ANALISIS_P3b.txt` tienen que salir iguales (redondeo aparte).
2. **Etiquetas barajadas:**
   - en E1 con k = 3 se permutan al azar, dentro de cada bloque, las etiquetas CBWFQ/LLQ (semilla del §7) y se corren H2 y el TOST;
   - [OP-Linux] 200 barajados.
   - **H2:** se informa la fracción de p < 0,05, que debería rondar 0,05.
   - **TOST** [OP-Mac]: con las etiquetas barajadas la diferencia real es 0, así que el TOST debería declarar equivalencia a menudo (según su potencia). Se comprueba que:
     - la media de d en los 200 barajados ronda 0;
     - el IC 95 % de la media contiene 0 en ~95 % de ellos;
     - y se informa la fracción de equivalencias, que se espera alta.
   - Si sale efecto sistemático, el código está mal y se para.
3. **Caso sintético de H3:**
   - datos simulados con a = 1, b = 2, c = 1 ms, con los T_s y T_r reales de las 19 celdas, 17 réplicas y ruido normal de DE = 1,3 ms (la mayor DE entre corridas del piloto en CBWFQ con k = 3);
   - el código debe recuperar a y b con IC que los contengan.
   - Se repite con Δ y la referencia a = 0, b = 2.

---

## 5. Sensibilidades (fijadas antes de ver los datos que afectan)

1. **Sin las corridas marcadas** [§36]: H1, H2 y control negativo.
2. **Sin las capacidades de 2 y 3 Mbps de IOU** [§51.7]: H1, H2 y control negativo.
3. **Por sesión (E4(c))** [§43.5]:
   - Δ_ses = mediana del p99 en la sesión 2 menos la de la sesión 1, por celda con prueba (E1 CBWFQ y LLQ, E1-R y control negativo), frente al EMI, con IC por bootstrap (semilla 20261016);
   - se informa el número y la lista de celdas con |Δ_ses| > EMI;
   - las pruebas de H1–H5 y del control negativo se repiten dentro de cada sesión, y se informa si alguna conclusión cambia.
   - **Sesión 1:** repeticiones 1–9; incluye las `_ac` y el bloque `campaign1k`.
   - **Sesión 2:** repeticiones 10–17.
   - [OP-Linux] Se declara que las repeticiones 1–9 de las 10 celdas exentas (`campaign1k`, 15-10 de 01:30 a 04:04) se corrieron el mismo día en que empezó la sesión 2.
4. **Con las corridas de batería** [§47.2]: se repite el análisis con las 103 originales en lugar de sus `_ac`.
   - Por celda, diferencia emparejada original − `_ac` del p99 y prueba de signos.
   - [OP-Linux] Ocho de las 103 empezaron entre las 06:30 y las 06:43:30, antes de que empezara la descarga (upower). Se repitieron igualmente y se declara.
5. **Los 12 fallos esporádicos del shaper** [§53.4]: p99 de voz de cada tentativa fallida (`_invalid/`) frente a su sustituta válida, comparado con el EMI.
6. **La corrida que coincidió con la actualización automática del 15-10** (E2 IOU LLQ 5 Mbps r10, 06:42:45; systemd se reejecutó a las 06:42:48) [OP-Linux, nuevo; §54]: H2 de esa celda con y sin ella.
7. **Tabla de S y S-H** frente a su celda base de E1: diferencia de medianas con IC, y si la conclusión de H1 y H2 en esa celda cambia [P3a §6].
8. **MOS:** búfer de 40/60/100 ms, T_resto de 50/100/150 ms y Bpl de 4,3/25,1 [P3a §9].

---

## 6. Exploratorio (etiquetado como tal)

1. **Frontera L\*** donde el p99 de CBWFQ cruza cada presupuesto (20, 50 y 100 ms, ilustrativos), interpolando en log L, con IC por bootstrap [P3a §11].
2. **m\*(L)** por presupuesto, interpolando en log(1 + m). Se informa censurado («> 3») si queda fuera de rango [§40.8].
3. **Cociente del control negativo** [§41.5, §43.7]:
   - ρ = D_sin / D_con por (L, k), con D_sin = media de las diferencias emparejadas CBWFQ − LLQ sin marcas y D_con = la misma media en la celda E1 con marcas (IOU, mismo L y k, m = 0,2);
   - **también D_sin en ms**;
   - IC 95 % por bootstrap de percentiles con 10 000 remuestreos (semilla 20261014), con las repeticiones remuestreadas por separado en cada celda.
4. **FIFO-C frente a FIFO-L**, como diferencia entre bancos [P3a §3].
5. **E4(b):** c7200 frente a IOU a 1 Mbps (k {1; 3} × {CBWFQ, LLQ}).
   - Diferencia de medianas del p99 con IC y exceso de cada uno sobre el suelo de su plataforma (mediana del suelo a 1 Mbps: IOU 2,07 ms; c7200 12,02 ms).
6. **E4(d):** Q004 y Q034 frente a las cifras de hardware publicadas, de forma descriptiva.
7. **MOS** (G.107/G.113) según P3a §9, con la figura de MOS frente a T_resto por política.
8. **Reimplementación por otro camino:** percentiles y jitter desde las capturas, con código distinto [P3a §11].

---

## 7. Semillas y verificación independiente

- **Semillas fijadas aquí** [OP-Linux]:
  - bootstrap por celda: 20261020;
  - bootstrap de H3: 20261021;
  - etiquetas barajadas: 20261022;
  - caso sintético: 20261023;
  - sesiones: 20261016 (§43.5);
  - cociente del control negativo: 20261014 (§41.5).
- **Muestra para la verificación del Mac** [§53.5], con semilla 20261024 y fijada antes de la ejecución confirmatoria:
  - 30 corridas al azar de entre las del análisis principal;
  - Δ y su prueba en E1 IOU k = 3 a 1 y 5 Mbps (H2);
  - el TOST de H1 a 1 Mbps;
  - la regresión de H3 (p99 de CBWFQ).
  - La lista se deja en `F5_analisis/MUESTRA_VERIFICACION.json` antes de calcular.

## 8. Salidas

- `F5_analisis/results/numbers.json`: todas las cifras del manuscrito [P3a §11].
- Tablas CSV por prueba, con la celda, n, estadístico, p, p ajustado e IC.
- Figuras con la skill `dataviz`; cada PNG se abre y se revisa [§53, Mac §3.7].
- Linux entrega tablas y cifras **sin interpretación** [§53.4].
