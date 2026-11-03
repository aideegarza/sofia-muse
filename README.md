# Sofía × Muse Spark: extractor de llamadas

Cuando termina una llamada con Sofía en Retell, este servidor manda el transcript a **Muse Spark** (Meta Model API). Muse Spark devuelve los **18 campos** del post-call, más un resumen en español, la urgencia y la siguiente acción para el equipo. El resultado se guarda como una fila en Google Sheets.

```
Retell (voz)  ──webhook call_ended──▶  Servidor (Render)  ──transcript + esquema──▶  Muse Spark 1.3
                                              │                                         │
                                              ◀──────── JSON validado (18 + 3 campos) ───┘
                                              │
                                              └──▶  Google Sheets (una fila por llamada)
```

**Qué hace Muse Spark aquí:** extracción con *structured output*. El esquema JSON de `schema.py` obliga a que la respuesta traiga los 18 campos con sus tipos y valores permitidos. El servidor valida esa respuesta. Luego aplica los datos que Retell conoce con certeza (el horario de oficina del nodo HORARIO y si hubo transferencia) por encima de lo que interpretó el modelo.

## Archivos

| Archivo | Qué es |
|---|---|
| `schema.py` | Los 18 campos + 3 de enriquecimiento. Es la única fuente: de aquí salen el esquema, la validación y las columnas |
| `extractor.py` | Llamada a Muse Spark con reintentos y validación |
| `app.py` | Servidor: `/retell` (webhook), `/test` (prueba manual), `/health` |
| `sheets.py` + `apps_script.gs` | Guardado en Google Sheets, sin duplicados (upsert por `call_id`) |
| `render.yaml` | Configuración para Render |
| `tests/` | Pruebas sin conexión (Muse y Sheets simulados) y una llamada de ejemplo |

## Variables de entorno

| Variable | Qué poner |
|---|---|
| `MODEL_API_KEY` | Tu API key de Meta Model API |
| `RETELL_API_KEY` | La API key de Retell que tiene la etiqueta *webhook* (para verificar que el aviso viene de Retell) |
| `SHEETS_WEBAPP_URL` | La URL del Apps Script publicado |
| `SHEETS_TOKEN` | Una palabra secreta inventada; la misma que pongas en `TOKEN` del Apps Script |
| `TEST_TOKEN` | Otra palabra secreta para usar `/test` |
| `MUSE_MODEL` | `muse-spark-1.3` (por defecto) |
| `MUSE_REASONING_EFFORT` | `low` (por defecto; `medium` si quieres más precisión a cambio de tiempo) |

## Pruebas locales

```
pip install -r requirements.txt pytest
python -m pytest -q
```

Construido durante el Meta Global AI Developer Hackathon (noviembre 2026).
