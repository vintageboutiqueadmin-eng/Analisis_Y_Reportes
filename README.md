[README.md](https://github.com/user-attachments/files/27647612/README.md)
# Vintage Boutique — Sistema de Asistencia

Dashboard ejecutivo de asistencia para las dos tiendas de Vintage Boutique en
Antigua Guatemala (7ma Avenida y 6ta Avenida).

Streamlit + Google Sheets como backend. Sin base de datos. Sin servidor.

---

## Roles

| Rol | Persona | Acceso |
|---|---|---|
| **admin** | Pablo Orozco | Dashboard + Captura + Administración |
| **manager** | Marisol Caxaj | Captura diaria + Dashboard |
| **viewer** | Lic. Juan Orozco | Solo Dashboard (cualquier fecha) |

---

## Estados que Marisol puede registrar

- **Trabajando** — con hora de entrada, salida, almuerzo, horas extra
- **Llegada tarde** — flag dentro de "Trabajando" con hora real de llegada
- **Hora extra** — minutos adicionales después de la salida programada
- **Día libre** — descanso programado
- **Permiso / Falta justificada**
- **Vacaciones**
- **Incapacidad / Enfermedad**

---

## Paso a paso para desplegar

### 1. Clonar / subir a GitHub

```bash
cd vintage-boutique-attendance
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/vintage-boutique-attendance.git
git push -u origin main
```

> El archivo `.gitignore` ya excluye `secrets.toml` — **nunca** lo subas.

### 2. Crear cuenta de servicio de Google (para Sheets)

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un proyecto nuevo (o usa uno existente)
3. **APIs y servicios → Biblioteca**:
   - Habilita **Google Sheets API**
   - Habilita **Google Drive API**
4. **IAM y administración → Cuentas de servicio → Crear cuenta de servicio**
   - Nombre: `vintage-boutique-bot`
   - Crea sin asignar roles
5. Una vez creada, entra a la cuenta:
   - Pestaña **Claves → Agregar clave → Crear nueva clave → JSON**
   - Se descarga un archivo JSON. **Guárdalo bien**, contiene la `private_key`.

### 3. Crear el Google Sheet

1. Crea un Google Sheet nuevo (puede estar vacío)
2. Cópiale el ID de la URL:
   `https://docs.google.com/spreadsheets/d/AQUI_VA_EL_ID/edit`
3. **Compartir → Pega el `client_email` de la cuenta de servicio** (algo como
   `vintage-boutique-bot@tu-proyecto.iam.gserviceaccount.com`) y dale permisos
   de **Editor**.

> No necesitas crear las pestañas a mano. La app las crea desde la sección
> *Administración → Inicialización* la primera vez que entras.

### 4. Configurar Streamlit Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io)
2. **New app** → Conecta tu repo de GitHub
3. **Main file path**: `app.py`
4. **Advanced settings → Secrets**: pega lo siguiente, **llenando los valores reales**:

```toml
[gcp_service_account]
type = "service_account"
project_id = "tu-proyecto"
private_key_id = "..."
private_key = """-----BEGIN PRIVATE KEY-----
... (líneas del JSON descargado) ...
-----END PRIVATE KEY-----
"""
client_email = "vintage-boutique-bot@tu-proyecto.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"

[sheets]
spreadsheet_id = "1AbC...XYZ"   # ID del sheet que creaste

[auth]
admins   = ["pablo.orozco@ejemplo.com"]
managers = ["marisol.caxaj@gmail.com"]
viewers  = ["juan.orozco@ejemplo.com"]

[display_names]
"pablo.orozco@ejemplo.com" = "Pablo Orozco"
"marisol.caxaj@gmail.com"  = "Marisol Caxaj"
"juan.orozco@ejemplo.com"  = "Lic. Juan Orozco"
```

5. **Sharing → Who can view this app**: cambia a **Private**
   - Agrega los 3 correos exactos (Pablo, Marisol, Juan) como viewers
   - Esto activa el login con Google y `st.user.email` se llena automáticamente

6. **Deploy** — la primera vez tarda 2–3 minutos

### 5. Primer arranque

1. Abre el link de la app, inicia sesión con tu correo (Pablo, admin)
2. Entra a **Administración → Inicialización**
3. Click en **"Crear estructura del libro"** → crea las pestañas en el Sheet
4. Click en **"Sembrar tiendas + empleados demo"** → carga el roster inicial
5. Ya puedes cambiar a **Captura** y empezar a registrar asistencia.

---

## Desarrollo local

```bash
# 1. Crea el entorno virtual
python3 -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate     # Windows

# 2. Instala dependencias
pip install -r requirements.txt

# 3. Configura secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edita .streamlit/secrets.toml con tus valores reales

# 4. Levanta el server
streamlit run app.py
```

En desarrollo local **no hay OAuth** — la app muestra un selector de usuario
con todos los correos configurados en `secrets.toml`, para que puedas
previsualizar cada rol sin loguearte.

---

## Estructura del Google Sheet

La app crea automáticamente estas tres pestañas. Si las creas a mano, deben
tener exactamente estos encabezados:

### Pestaña `stores`
| id | name | marker |
|---|---|---|
| 7ma_ave | 7ma Avenida | Sede 01 |
| 6ta_ave | 6ta Avenida | Sede 02 |

### Pestaña `employees`
| id | name | store_id | active |
|---|---|---|---|
| 1 | Jonathan | 7ma_ave | true |
| 2 | Daisy | 7ma_ave | true |
| ... | ... | ... | ... |

### Pestaña `attendance`
| date | employee_id | status | shift_start | shift_end | lunch_start | lunch_end | overtime_minutes | is_late | actual_start | notes | updated_by | updated_at |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-12 | 1 | working | 10:00 | 19:00 | 13:00 | 14:00 | 0 | false |  |  | marisol.caxaj@gmail.com | 2026-05-12T08:30:00 |

**Status** puede ser: `working`, `day_off`, `permission`, `vacation`, `sick`.

---

## Manejo de horarios flexibles

- Horario regular: **9 AM – 7 PM**
- El timeline del dashboard **se expande automáticamente** cuando hay datos
  fuera de ese rango. Por ejemplo:
  - Si hay capacitación a las 6 AM → el timeline empieza en 6 AM
  - Si alguien hace hora extra hasta las 9 PM → el timeline llega hasta 9 PM
- **Llegada tarde** se marca con el flag `is_late` + `actual_start`. El bar
  visualmente empieza en la hora real de entrada, no la programada.

---

## Estructura del proyecto

```
vintage-boutique-attendance/
├── app.py                          # Entry point + auth gate + routing
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   ├── config.toml                 # Tema (gris ejecutivo)
│   └── secrets.toml.example        # Plantilla de secrets
└── modules/
    ├── auth.py                     # Resolución de rol por email
    ├── sheets.py                   # Lecturas/escrituras a Google Sheets
    ├── dashboard_html.py           # Generador del HTML del dashboard
    ├── dashboard.py                # Página de dashboard (Streamlit)
    ├── capture.py                  # Página de captura (Marisol)
    └── admin.py                    # Página de administración (Pablo)
```

---

## Soporte

Si algo falla:
1. **Administración → Diagnóstico** muestra el estado de la conexión y la
   configuración de roles.
2. Si el Lic. Juan no puede entrar: verifica que su correo esté en `[auth] viewers`
   en los secrets de Streamlit Cloud **y** en la lista de viewers de la app
   privada (Sharing settings).
3. Si los datos no se actualizan: el botón **"↻ Actualizar datos"** en el
   sidebar invalida el caché (de 15–30 seg por defecto).
