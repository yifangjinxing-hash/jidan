<p align="center">
  <img src="docs/assets/jidan-hero.png" alt="Jidan conecta una intención de IA con adaptadores intercambiables, mientras una persona conserva la acción final" width="100%" />
</p>

<h1 align="center">Jidan</h1>

<p align="center">
  <strong>Primero las microacciones reales: un paso menos, observable y seguro.</strong><br />
  Preparación local, traspaso honesto y confirmación irreversible en manos de la persona.
</p>

<p align="center">
  <a href="docs/11-daily-note-cross-app-hand-zh.md"><img src="https://img.shields.io/badge/Android_Acción_diaria-0.3-7B61A8?style=for-the-badge" alt="Acción diaria entre apps de Jidan Shell 0.3" /></a>
  <a href="reference-app/ios-shell/README.md"><img src="https://img.shields.io/badge/iOS_Prototipo_observable-0.1-8B7AC8?style=for-the-badge" alt="Jidan iOS Shell 0.1" /></a>
  <a href="#-inicio-rápido-para-desarrolladores"><img src="https://img.shields.io/badge/Inicio_para_desarrolladores-195A41?style=for-the-badge" alt="Inicio rápido para desarrolladores" /></a>
  <a href="profiles/message.compose.tool.json"><img src="https://img.shields.io/badge/Perfil_JCL-0.1-2F8F68?style=for-the-badge" alt="Perfil JCL 0.1" /></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Contribuciones-Bienvenidas-3978C6?style=for-the-badge" alt="Contribuciones bienvenidas" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> [!IMPORTANT]
> Jidan es un prototipo experimental. El laboratorio Android incluye tres APK: la Shell, una lista local de tareas y un entorno aislado, con evidencia integral en un emulador Android 17. No son productos firmados para tienda, launchers predeterminados ni un sistema operativo independiente. Utilízalo con aplicaciones controladas, dispositivos de prueba y datos desechables.

<p align="center">
  <a href="reference-app/shell/README.md"><img src="docs/assets/jidan-shell-daily-0.3.png" alt="Pantalla mínima de acciones Android de Jidan Shell 0.3" width="360" /></a>
  <a href="reference-app/ios-shell/README.md"><img src="docs/assets/jidan-ios-shell-0.1.png" alt="Jidan iOS Shell 0.1 ejecutándose a pantalla completa en un simulador de iPhone 16" width="360" /></a>
</p>

## ✨ Por qué Jidan

El software móvil todavía se organiza en silos de aplicaciones. Un objetivo sencillo puede atravesar páginas, anuncios, permisos y API de plataforma incompatibles. Jidan explora una unidad más pequeña de software: un **contrato de capacidad** que un planificador no confiable puede proponer, pero que solo un host determinista puede autorizar y ejecutar.

```text
objetivo humano → acción semántica → contrato de capacidad → control de política
                → adaptador elegido → recibo del traspaso → acción humana
                                                       (el envío final no se verifica aún)
```

El objetivo a largo plazo no es crear «otra superaplicación», sino una capa de compatibilidad fina y abierta en la que Android, Apple, Web, HarmonyOS, Windows y futuros hosts puedan implementar la misma semántica estable de intención.

> **Se comparte la semántica, no la implementación.** El lenguaje natural y la interfaz quedan fuera del contrato de máquina JCL; Kotlin, Swift, JavaScript y C/C++ son decisiones internas del host o adaptador. Un binding web sigue limitado por el sandbox del navegador. El experimento Pinyin 0.1 está congelado y no es la base del proyecto. Consulta las [lecciones históricas y límites de la ruta](docs/06-history-lessons-and-route-guardrails-zh.md) (en chino).

## 🧭 Primero, pequeñas acciones reales

Jidan valida primero molestias cotidianas y deriva el protocolo desde esa evidencia. El primer experimento financiero solo verifica, en un laboratorio Android/ADB controlado, la versión, firma y componente frontal de Alipay fijados por el Host, y abre esa puerta de entrada confiada. No recibe destinatario, cuenta ni importe, no usa esquemas privados y nunca afirma que se pagó. Es evidencia de un adaptador, no un producto para usuarios ni una «transferencia automática por IA». Consulta [microacciones de Alipay y lecciones para el protocolo](docs/09-alipay-micro-actions-and-protocol-lessons-zh.md) (en chino).

## 🔌 Un contrato, múltiples adaptadores

[`message.compose`](profiles/message.compose.tool.json) es el primer perfil de Jidan Capability Layer (JCL). La primera serialización pública de JCL 0.1 utiliza un perfil Tool compatible con MCP; JCL no es un lenguaje nuevo ni queda ligado a un único transporte o modelo de sesión.

```python
from jidan.models import Step, TaskPlan

# El llamador propone una capacidad; no elige plataforma ni llama al adaptador.
plan = TaskPlan(
    id="compose-demo",
    goal="preparar un borrador de mensaje",
    steps=(Step(
        id="compose",
        capability="message.compose",
        arguments={"content": "Nos vemos a las tres."},
    ),),
)
# El host confiable valida, autoriza, confirma, elige el binding, ejecuta
# y registra el recibo.
```

| Contrato estable | Adaptador reemplazable | Evidencia actual |
|---|---|---|
| `message.compose` | Intent de Android | Plan basado solo en datos; existe un traspaso verificado a WeChat |
| `message.compose` | Atajo de Apple / Share Sheet | Plan basado solo en datos |
| `message.compose` | Borrador web editable | Plan basado solo en datos |
| `message.compose` | Adaptador comunitario | Registro local, sin lista blanca central de publicación |

Cada resultado expresa con precisión lo que ocurrió:

```json
{
  "state": "handoff_planned",
  "delivery": {
    "attempted": false,
    "sent": false,
    "verified": false
  },
  "nextAction": "user_review_and_send"
}
```

`handoff_planned` significa que existe un plan de traspaso; nunca se presenta como una interfaz ya abierta. Un selector de Android abierto y comprobado informa `handoff_opened`, pero la entrega sigue con `sent: false`: Jidan no elige al destinatario ni pulsa **Enviar**.

## 🧪 Laboratorio de conformidad: Nine Lights

Nine Lights se conserva únicamente como fixture de semántica compartida. No es una función para usuarios ni demuestra automatización de apps multiplataforma.
El Host Python y un Host JavaScript independiente reproducen los mismos [vectores de conformidad](profiles/conformance/game.ninelights.vectors.json). El código y la compilación permanecen en la [guía del prototipo](prototype/README.md#nine-lights-conformance-spike), con su alcance limitado por la [nota de evidencia](docs/07-universal-game-spike-zh.md) (en chino).

> [!NOTE]
> El experimento Pinyin Frontend 0.1 quedó congelado el 2026-08-02. Su código,
> perfil, demo y pruebas se conservan para compatibilidad y reproducción, pero
> ya no forman parte de la ruta activa ni del inicio rápido. No se aceptan
> sintaxis ni alias nuevos.

## 🧭 Arquitectura

```mermaid
flowchart LR
    H["Objetivo humano"] --> P["Propuesta no confiable<br/>planificador IA · entrada de interfaz"]
    P --> C["Capacidad estable<br/>message.compose"]
    C --> G{"Puerta determinista<br/>schema · scope · grant · confirmación"}
    G --> R["Binding elegido por el Host"]
    R --> A["Android"]
    R --> I["Apple"]
    R --> W["Web"]
    R --> N["Nueva plataforma"]
    A --> M["Revisión móvil nativa"]
    I --> M
    W --> E["Revisión Web editable"]
    N --> S["Revisión propia del Binding"]
    M --> Q["Recibo observado del traspaso<br/>sent = false"]
    E --> Q
    S --> Q
    M --> X["Acción humana final<br/>envío aún fuera de verificación"]
    E --> X
    S --> X
    G --> L["Libro mayor de Grants"]

    classDef core fill:#195A41,color:#F2F8F5,stroke:#2F8F68,stroke-width:2px;
    classDef human fill:#F5E7BF,color:#3B2A00,stroke:#D9A441;
    class C,G,R,Q core;
    class H,X human;
```

## ✅ Estado actual

| Capa | Estado | Evidencia y límite |
|---|---:|---|
| Registro de capacidades y validación de esquemas | ✅ | Prototipo Python sin dependencias externas |
| Grafos de tareas, permisos con alcance y puerta de confirmación | ✅ | Preflight y ejecución deterministas |
| Rechazo persistente de repeticiones | ✅ | Libro mayor de permisos en SQLite |
| Recibos de ejecución encadenados por hash | ✅ | Registro de recibos del runtime |
| Android 17 AppFunctions | ✅ | Proveedor controlado de referencia y harness en vivo |
| Descubrimiento de superficies semánticas | ✅ | AppFunctions → RemoteInput → atajo → compartir público |
| Traspaso nativo controlado a WeChat | 🧪 | El laboratorio ADB comprueba el selector exacto; no elige destinatario ni pulsa Enviar |
| Traspaso fijado a la puerta de Alipay | 🧪 Lab | Adaptador ADB sin datos de pago; faltan pruebas de aceptación en dispositivos reales |
| Perfil multiplataforma `message.compose` | 🧪 | Planes Android, iOS y Web; binding de Android verificado |
| Conformance Lab: Nine Lights | 🧪 Lab | Runtime/recibos Python + Host JS independiente; no es un producto para usuarios |
| Pinyin Frontend 0.1 | ⏸️ | Experimento de compatibilidad congelado; sin sintaxis ni alias nuevos |
| Producto Android para usuarios comunes | 🗺️ | Aún no construido; un laboratorio ADB no es onboarding de consumo |
| [Jidan iOS Shell 0.1](reference-app/ios-shell/README.md) | 🧪 | SwiftUI, Apple Speech y navegación directa de bajo riesgo; compilada, probada y capturada en un iPhone Simulator remoto |
| Sistema operativo móvil de agentes listo para producción | 🗺️ | Todavía no se afirma |

El perfil multiplataforma `message.compose` sigue siendo experimental. La Shell iOS ya es código SwiftUI ejecutable, pero el adaptador de entrada de Alipay en iOS permanece desconectado hasta que exista un contrato público y auditable. Jidan todavía no afirma ser un sistema operativo de agentes móvil listo para producción.

## 🛡️ Seguridad por diseño

- **El planificador no es el límite de seguridad.** La salida del modelo se valida como datos no confiables.
- **Publicación abierta no significa ejecución ciega.** Cualquiera puede implementar un adaptador, pero cada dispositivo conserva sus propias decisiones de confianza, instalación, política y aislamiento.
- **Una sugerencia de destinatario no concede autoridad.** `message.compose.recipient` nunca se entrega al adaptador de plataforma.
- **Un adaptador no puede declarar el éxito.** El host genera el estado de entrega; no lo copia de la salida de terceros.
- **La autorización no se vincula solo a un nombre.** El Grant fija la definición efectiva; un cambio de esquema, efecto o identidad del adaptador exige una autorización nueva.
- **Un efecto ambiguo no se reintenta como si hubiera tenido éxito.** Los resultados desconocidos permanecen desconocidos y se registran de forma conservadora.
- **La persona conserva la última palabra.** Enviar, pagar, eliminar y cambiar ajustes de seguridad exige un límite explícito de confirmación.

Lee [SECURITY.md](SECURITY.md) antes de conectar un dispositivo real.

## 🚀 Inicio rápido para desarrolladores

Ejecuta con Python 3.11 o posterior el conjunto completo de pruebas del prototipo, que no requiere dependencias externas:

```bash
cd prototype
python -m unittest discover -s tests -p "test_*.py"
python message_compose_demo.py
python appfunctions_smoke.py
```

La demostración de mensajes se detiene por defecto en `awaiting_confirmation`; `--simulate-approval` queda marcado como simulación y no demuestra una confirmación real. Este bloque es una ruta para desarrolladores, no onboarding para usuarios comunes. Nine Lights permanece indexado en el Conformance Lab y no forma parte de esta ruta.

Desde la raíz del repositorio, valida los paquetes de idioma de Android:

```bash
python prototype/tools/check_locales.py
```

Con JDK 17 o posterior y Android SDK 37, compila la aplicación de referencia controlada:

```bash
cd reference-app
./gradlew :app:assembleDebug
```

En Windows utiliza `gradlew.bat`. Consulta la [guía del prototipo](prototype/README.md#windows-unicode-arguments) para las consideraciones sobre argumentos Unicode en PowerShell 5.1.

## 🗂️ Estructura del repositorio

```text
profiles/       perfiles de capacidad JCL compatibles con MCP
prototype/      núcleo, adaptadores, políticas, permisos, recibos y demostraciones
reference-app/  proveedor controlado de Android 17 AppFunctions
docs/           arquitectura, investigación, hoja de ruta e internacionalización
```

Los APK generados, imágenes de emulador, registros sin procesar de dispositivos, capturas de pantalla, recibos y bases SQLite se excluyen deliberadamente de Git.

## 🌍 Idiomas sin fragmentar el protocolo

Jidan mantiene el lenguaje humano separado del protocolo de máquina:

- el contenido Unicode puede atravesar JSON, grafos de tareas, ADB, AppFunctions, almacenamiento, lectura e interfaz sin transliteración ni normalización implícita;
- la interfaz Android de referencia contiene **23 paquetes semilla de configuración regional**, incluido árabe de derecha a izquierda;
- `memo: <content>` ofrece una entrada determinista independiente del idioma;
- los identificadores de capacidades, campos de esquema, permisos, hashes y valores de recibos permanecen como contratos ASCII estables;
- añadir traducciones de interfaz o adaptadores lingüísticos revisados no requiere bifurcar el protocolo.

> [!NOTE]
> El experimento `zh-Latn-pinyin` está congelado y se conserva únicamente para compatibilidad y reproducción. No se amplían sus alias ni su sintaxis.

Las traducciones semilla son un punto de partida abierto y no implican revisión por hablantes nativos. Consulta [Idiomas e internacionalización](docs/i18n/README.md) para ayudar a mejorarlas.

## 🤝 Colabora con Jidan

Son especialmente útiles:

- un nuevo adaptador de plataforma para `message.compose`;
- una prueba de conformidad que detecte falsos estados de éxito;
- la revisión por una persona hablante nativa de uno de los 23 paquetes semilla;
- un adaptador lingüístico restringido que emita identificadores semánticos existentes;
- pruebas reproducibles con una aplicación o un dispositivo controlados.

Empieza por [CONTRIBUTING.md](CONTRIBUTING.md), el [límite de microacciones y Alipay](docs/09-alipay-micro-actions-and-protocol-lessons-zh.md), la [hoja de ruta de 90 días](docs/04-90-day-execution-roadmap-zh.md) y la [revisión de protocolos de los últimos siete días](docs/08-seven-day-protocol-review-zh.md) (en chino simplificado).

> [!NOTE]
> Este README es una traducción inicial asistida por máquina y no afirma haber sido revisada por una persona hablante nativa. Si una traducción difiere, el [README en inglés](README.md) y los perfiles de capacidad legibles por máquina son las referencias técnicas canónicas.

## Licencia

Apache License 2.0. Consulta [LICENSE](LICENSE) y [NOTICE](NOTICE).
