# AURIA — Riesgo de salidas de Bomberos de Bizkaia por parque

Predice, hora a hora y para las próximas 6 horas, cuántas salidas tendrá cada uno de los 8 parques del SPEIS foral (Urioste, Artaza, Derio, Basauri, Iurreta, Arratzu, Markina, Zalla) y por qué. Bilbao tiene servicio propio y queda fuera.

## Cómo funciona (coste cero)

```
GitHub Actions ─ cada 30 min ─▶ captura bizkaia.eus (salidas activas + contadores)
                              ─▶ predicción 6 h por parque ─▶ prediccion/ultima.json
               ─ cada noche ───▶ reentrena LightGBM horario (solo se activa si mejora)
               ─ lunes ────────▶ descarga histórico Open Data Bizkaia y recalcula tasas base
Mac (launchd)  ─ cada 5 min ──▶ captura más densa (datos/online/mac, opcional)
Streamlit Cloud ─────────────▶ panel con mapa, semáforo por parque y factores
                ─ cada minuto ─▶ lee bizkaia.eus en directo: actuaciones en curso, parque y estado de cada vehículo
```

**Predicción** = tasa normal del parque para ese mes y franja horaria (histórico 2023-hoy) × multiplicadores:
- **Meteo** (Open-Meteo, previsión horaria por parque): rachas, lluvia 1 h y 12 h, días sin llover, viento sur seco, frío, hielo.
- **Calendario**: festivos de Euskadi, noches de fin de semana, operaciones salida y retorno.
- **Tráfico** (Open Data Euskadi, en tiempo real): accidentes e incidencias de seguridad vial cerca de cada parque.
- **Eventos**: se añaden a mano en `datos/eventos.csv`.

Los multiplicadores iniciales están en `auria/reglas.py` y son provisionales. Cada noche se intenta entrenar un modelo LightGBM con las variables reales de cada hora y las salidas que ha visto el recolector. Solo sustituye a las reglas si predice mejor en los últimos 7 días. Para entrenar exige al menos 21 días y 300 actuaciones; hasta entonces se sigue con las reglas.

**Semáforo** según cuántas veces supera lo normal: 🟢 <1,5 · 🟡 1,5-2,5 · 🟠 2,5-4 · 🔴 ≥4.

## Puesta en marcha

1. **GitHub**: las tareas ya están en `.github/workflows`. La primera vez lanza *Reentrenamiento nocturno AURIA* desde la pestaña Actions con la casilla `historico` marcada. Así se generan las tasas base.
2. **Streamlit Cloud**: share.streamlit.io → *New app* → este repositorio → `streamlit_app.py`. Para leer siempre la última predicción sin esperar al redespliegue, añade en *Secrets*:
   ```toml
   GITHUB_TOKEN = "github_pat_..."   # token fine-grained: solo lectura de Contents de este repo
   GITHUB_REPO  = "bsendagorta/auria"
   ```
3. **Mac (opcional)**: `bash instalar.sh` crea el entorno y la captura cada 5 min. Después usa `./auria.sh` o AURIA.app.

## Órdenes locales (`./auria.sh …`)

| Orden | Qué hace |
|---|---|
| `historico` | Descarga y limpia el histórico de Open Data Bizkaia y recalcula las tasas base |
| `prevision` | Predicción de las próximas 6 horas por parque |
| `panel` | Abre el panel en el navegador |
| `directo` | Actuaciones en curso ahora: parque, tipo y estado de cada vehículo (en ruta / en siniestro / regresando) |
| `captura` / `resumen` / `estado` | Recolector en directo |
| `entrenar` | Reentrena el modelo horario |
| `meteo` / `modelo` / `todo` | Modelo mensual por municipio (análisis de qué variables pesan) |

Pruebas sin red: `python -m tests.test_basico`

## Datos y sus límites

- **Histórico** ([Open Data Bizkaia](https://www.opendatabizkaia.eus/es/catalogo/intervenciones-speis)): solo trae mes y franja horaria (M 8-14, T 14-20, N 20-8), sin día. Va por municipio, y el parque se deduce de la zona oficial de cada uno (`auria/parques.py`). En 2023 cambió la clasificación de tipos, que se agrupan en 10 familias (`auria/familias.py`).
- **En directo** (bizkaia.eus): muestra solo las actuaciones activas, sin hora, y dos contadores. El total exacto por hora sale del contador anual. Las actuaciones muy cortas pueden no llegar a verse; se corrige con un factor de cobertura.
- **No disponibles en abierto**: si intervino un segundo parque en apoyo, y las dotaciones ocupadas por parque (se aproximan con las actuaciones activas).
- **Ríos (URA)**: pendiente. Necesita la API de Euskalmet con clave. El hueco ya está previsto en `reglas.py`.
- **Lo que más mejoraría el modelo**: pedir a bomberos@bizkaia.eus el histórico con fecha y hora.

Herramienta experimental de apoyo. No sustituye a la información oficial del 112 ni de Bizkaia Prest.
