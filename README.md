# Klaviyo Email Campaign Repository

Extrae campañas de email desde Klaviyo y las convierte a un formato estructurado para análisis con IA.

## Objetivo

Construir un repositorio de campañas de email para análisis automatizado de:

- **Qué asuntos generan más aperturas** (y cuáles no)
- **Qué contenido vende** (y por qué)
- **Qué NO funciona** (y por qué) - lo más importante
- Patrones entre estructura y métricas

## Instalación

```bash
# Clonar el repositorio
git clone <repo-url>
cd klaviyo

# Crear entorno virtual
python -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar
cp .env.example .env
# Editar .env con tus API keys
```

## Configuración (.env)

```bash
# Klaviyo (requerido)
KLAVIYO_API_KEY=your_klaviyo_key

# AI Analysis - al menos uno requerido
ANTHROPIC_API_KEY=your_anthropic_key   # Para Claude Opus/Sonnet
OPENAI_API_KEY=your_openai_key         # Para GPT-4o
GOOGLE_API_KEY=your_google_key         # Para Gemini
```

---

## Uso

### 1. Extraer Campañas (Incremental)

```bash
# Primera vez: extrae todas las campañas
python main.py

# Siguiente vez: solo extrae las nuevas
python main.py

# Forzar re-extracción completa
python main.py --full

# Solo ver estadísticas
python main.py --stats
```

Los datos se guardan en `output/campaigns_data.json` - no se vuelven a descargar.

### 2. Analizar con IA

```bash
# Análisis con Claude Opus (mejor calidad)
python main_analysis.py --model opus

# Análisis con Gemini (más barato)
python main_analysis.py --model gemini

# Análisis con GPT-4o
python main_analysis.py --model gpt4o

# Con análisis de imágenes (visión)
python main_analysis.py --model opus --with-images
```

### Modelos Disponibles

| Modelo | Provider | Costo | Calidad | Visión |
|--------|----------|-------|---------|--------|
| `opus` | Anthropic | $$$ | Excelente | ✓ |
| `sonnet` | Anthropic | $$ | Muy bueno | ✓ |
| `gpt4o` | OpenAI | $$ | Muy bueno | ✓ |
| `gemini` | Google | $ | Bueno | ✓ |
| `gemini-flash` | Google | ¢ | OK | ✓ |

---

## Output

```
output/
├── campaigns_data.json              # Datos persistentes (no se re-descargan)
├── campaigns_report_YYYYMMDD.md     # Reporte estructurado de campañas
└── analysis_opus_YYYYMMDD.md        # Análisis de IA
```

### El Análisis Incluye:

1. **Asuntos que generan apertura** - patrones, palabras clave, ejemplos
2. **Asuntos que NO funcionan** - errores comunes, qué evitar
3. **Contenido que vende** - estructura, CTAs, formato
4. **Contenido que NO convierte** - desconexiones, errores
5. **Recomendaciones accionables** - qué hacer y qué NO hacer
6. **Patrones ocultos** - correlaciones temporales, temas

---

## Estructura del Proyecto

```
klaviyo/
├── main.py              # Extracción de campañas (incremental)
├── main_analysis.py     # Análisis con IA
├── requirements.txt
├── .env.example
├── src/
│   ├── config.py           # Configuración
│   ├── models.py           # Modelos de datos
│   ├── klaviyo_client.py   # Cliente API Klaviyo
│   ├── html_parser.py      # HTML → Bloques
│   ├── storage.py          # Persistencia JSON
│   ├── ai_client.py        # Clientes multi-modelo
│   └── report_generator.py
└── output/
```

## Optimización de Tokens

El sistema está diseñado para minimizar el uso de tokens:

1. **Solo datos relevantes** - No pasa HTML crudo, solo bloques estructurados
2. **Categorización** - Analiza top/bottom performers, no todas las campañas
3. **Resúmenes compactos** - Cada campaña se resume en ~500 chars
4. **Imágenes opcionales** - Solo se incluyen si usas `--with-images`

---

## Flujo Completo

```bash
# 1. Extraer todas las campañas (una vez, luego incremental)
python main.py

# 2. Analizar con tu modelo preferido
python main_analysis.py --model opus

# 3. Ver el análisis
cat output/analysis_opus_*.md
```
