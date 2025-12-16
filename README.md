# Klaviyo Email Campaign Repository

Extrae campañas de email desde Klaviyo y las convierte a un formato estructurado y legible para análisis con IA.

## Objetivo

Construir un repositorio de campañas de email con todas las campañas en un formato estándar, legible para modelos de IA, para análisis de:

- Copy y estructura del correo
- Diseño y elementos visuales
- Relación entre estructura y métricas (open rate, click rate, conversiones)

## Instalación

```bash
# Clonar el repositorio
git clone <repo-url>
cd klaviyo

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu API key de Klaviyo
```

## Configuración

Edita el archivo `.env`:

```bash
KLAVIYO_API_KEY=your_private_api_key_here
MIN_SENDS_THRESHOLD=100  # Mínimo de envíos para incluir campaña
```

## Uso

```bash
# Procesar todas las campañas
python main.py

# Modo test (solo primeras 5 campañas)
python main.py --test

# Limitar número de campañas
python main.py --limit 10

# Filtrar por mínimo de envíos
python main.py --min-sends 500

# Procesar campaña específica
python main.py --campaign-id abc123

# Guardar reportes individuales por campaña
python main.py --individual

# Directorio de salida personalizado
python main.py --output ./mis-reportes
```

## Formato de Salida

Cada campaña se convierte a un reporte estructurado con:

### 1. Identificación
- ID de campaña
- Nombre
- Asunto
- Preview text
- Fecha de envío

### 2. Métricas
- Enviados / Entregados
- Open Rate (aperturas únicas)
- Click Rate (clicks únicos)
- Unsubscribes
- Conversiones y Revenue (si aplica)

### 3. Estructura del Correo (bloque por bloque)

El contenido se convierte a bloques estructurados:

**[IMAGEN]**
```
Alt: Descripción alternativa
URL: https://...
```

**[TEXTO]**
```
Contenido de texto limpio, sin HTML
```

**[BOTÓN / CTA]**
```
Texto: COMPRAR AHORA
URL destino: https://...
Estilo: fondo #FF0000, texto blanco
```

**[SOCIAL]**
```
INSTAGRAM: https://instagram.com/...
```

### 4. Links Detectados
Lista de todos los enlaces en el correo

### 5. CTAs Principales
Resumen de los call-to-action más importantes

## Estructura del Proyecto

```
klaviyo/
├── main.py              # Script principal
├── requirements.txt     # Dependencias
├── .env.example        # Ejemplo de configuración
├── src/
│   ├── __init__.py
│   ├── config.py       # Configuración desde env vars
│   ├── models.py       # Modelos de datos (Campaign, Blocks, etc)
│   ├── klaviyo_client.py   # Cliente API de Klaviyo
│   ├── html_parser.py      # Convertidor HTML → Bloques
│   └── report_generator.py # Generador de reportes
└── output/             # Reportes generados
```

## Flujo de Procesamiento

1. **Obtener Campañas** → API `/campaigns/` con paginación
2. **Obtener Métricas** → API `/campaign-values-reports/`
3. **Obtener Contenido** → API `/campaigns/{id}/campaign-messages/`
4. **Obtener Template HTML** → API `/campaign-messages/{id}/template/`
5. **Parsear HTML** → Convertir a bloques estructurados
6. **Generar Reporte** → Formato Markdown legible para IA

## Próximos Pasos

- [ ] Integración con visión AI para describir imágenes
- [ ] Exportación a Google Docs
- [ ] Extracción masiva automatizada
- [ ] Clustering de campañas similares
- [ ] Dashboard de insights
