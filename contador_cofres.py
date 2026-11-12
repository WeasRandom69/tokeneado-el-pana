"""
Tokeneado el pana - contador de cofres para Fortnite.
creado x weasrandomexe

Superposicion con fotos/GIFs que van cambiando. No toca el juego: solo escucha teclas.

TECLAS POR DEFECTO (se pueden cambiar con el boton "Teclas")
  E mantenida 0,5 s -> +1 cofre (el tiempo y si cuenta solo se ajustan en "Teclas")
  F8  -> +1 cofre
  F7  -> -1 (deshacer)
  F9  -> mostrar / ocultar la foto
  F10 -> cerrar y guardar
  F12 dos veces seguidas -> reiniciar todo (sesion, hoy y total) y guardar respaldo

MANDO DE XBOX POR DEFECTO (tambien se cambian en "Teclas")
  X mantenido  -> +1 cofre (X es interactuar en Fortnite)
  View + ↑     -> +1
  View + ↓     -> -1
  View + ←     -> mostrar / ocultar foto
  View + →     -> reiniciar todo (dos veces seguidas)

CON EL MOUSE SOBRE LA VENTANA
  Arrastrar            -> mover la ventana
  Rueda                -> agrandar / achicar la foto
  Ctrl + rueda         -> mas o menos transparente
  Botones de arriba    -> foto anterior / siguiente, ocultar foto, tamano,
                          anadir fotos/GIFs, teclas, cerrar

FOTOS
  Todas las imagenes (.png .jpg .jpeg .gif .webp .bmp) de la carpeta "fotos"
  se van turnando; los GIF se ven animados. Con el boton "Anadir" eliges
  archivos y se copian a esa carpeta al tiro.
"""

import csv
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog
from datetime import datetime, date
import urllib.request

import keyboard
from PIL import Image, ImageSequence, ImageTk

NOMBRE_APP = "Tokeneado el pana"
VERSION = "1.1"   # subir este numero en cada version nueva (y el de version.txt en GitHub)

# Novedades de cada version: se le muestran al usuario UNA vez, apenas se actualiza.
# En cada version nueva se agrega una entrada arriba.
NOVEDADES = {
    "1.1": [
        "Version de prueba: si ves esto, las actualizaciones funcionan.",
    ],
    "1.0": [
        "Actualizaciones automaticas: cuando haya algo nuevo te va a aparecer un aviso.",
        "Soporte para mando de Xbox (X mantenido = cofre).",
        "Botones del mando y teclas configurables en \"Teclas\".",
        "Fotos y GIFs con el boton \"Anadir\".",
    ],
}

# Actualizacion online: el programa revisa estos archivos en GitHub al abrirse
USUARIO_GITHUB = "WeasRandom69"
REPO_GITHUB = "tokeneado-el-pana"
RAMA_GITHUB = "main"
URL_BASE = f"https://raw.githubusercontent.com/{USUARIO_GITHUB}/{REPO_GITHUB}/{RAMA_GITHUB}/"
URL_VERSION = URL_BASE + "version.txt"
URL_SCRIPT = URL_BASE + "contador_cofres.py"

CARPETA = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(CARPETA, "cofres_registro.csv")
CARPETA_FOTOS = os.path.join(CARPETA, "fotos")
CONFIG = os.path.join(CARPETA, "config.json")

TECLAS_INICIALES = {
    "cofre": "e",
    "sumar": "f8",
    "restar": "f7",
    "foto": "f9",
    "salir": "f10",
    "reiniciar": "f12",
}
NOMBRES_ACCIONES = {
    "cofre": "Abrir cofre (mantener)",
    "sumar": "Sumar +1",
    "restar": "Restar -1",
    "foto": "Mostrar / ocultar foto",
    "salir": "Cerrar",
    "reiniciar": "Reiniciar todo (x2)",
}

SEGUNDOS_CONFIRMAR = 3
SEGUNDOS_POR_FOTO = 8
TAMANO_MIN, TAMANO_MAX = 120, 700
EXTENSIONES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
MAX_CUADROS_GIF = 300

FONDO = "#141414"
BARRA = "#262626"
DORADO = "#ffd34d"
GRIS = "#9a9a9a"
VERDE = "#2e9e4f"
ROJO = "#b33a3a"
AZUL = "#2f6fb3"

CONFIG_INICIAL = {"tamano": 260, "opacidad": 0.92, "mostrar_foto": True, "x": 40, "y": 40,
                  "auto_cofre": True,       # contar solo al mantener la tecla de cofre
                  "segundos_cofre": 0.5,    # cuanto hay que mantenerla
                  "teclas": dict(TECLAS_INICIALES)}

eventos = queue.Queue()


# ---------- Archivos ----------
def leer_registro():
    if not os.path.exists(ARCHIVO):
        return []
    with open(ARCHIVO, newline="", encoding="utf-8") as f:
        return [fila for fila in csv.reader(f) if fila]


def guardar_registro_en(ruta, filas):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(filas)


def guardar_registro(filas):
    guardar_registro_en(ARCHIVO, filas)


def leer_config():
    cfg = dict(CONFIG_INICIAL)
    cfg["teclas"] = dict(TECLAS_INICIALES)
    cfg["mando"] = mando_inicial()
    try:
        with open(CONFIG, encoding="utf-8") as f:
            guardado = json.load(f)
        teclas = guardado.pop("teclas", {}) or {}
        mando = guardado.pop("mando", {}) or {}
        guardado.pop("deteccion", None)   # ajuste de una version anterior que ya no se usa
        cfg.update(guardado)
        for accion in TECLAS_INICIALES:
            if isinstance(teclas.get(accion), str) and teclas[accion]:
                cfg["teclas"][accion] = teclas[accion]
        if "usar" in mando:
            cfg["mando"]["usar"] = bool(mando["usar"])
        for accion, botones in (mando.get("botones") or {}).items():
            if accion in cfg["mando"]["botones"] and isinstance(botones, list):
                cfg["mando"]["botones"][accion] = [b for b in botones if b in NOMBRES_BOTONES]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return cfg


def mando_inicial():
    return {"usar": True, "botones": {a: list(b) for a, b in MANDO_INICIAL.items()}}


def guardar_config(cfg):
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


def abrir_imagen(ruta):
    """Devuelve (cuadros, duraciones_ms). Una foto normal tiene 1 cuadro; un GIF, varios."""
    img = Image.open(ruta)
    cuadros, duraciones = [], []
    for cuadro in ImageSequence.Iterator(img):
        cuadros.append(cuadro.convert("RGBA"))
        duraciones.append(max(20, int(cuadro.info.get("duration", 80) or 80)))
        if len(cuadros) >= MAX_CUADROS_GIF:
            break
    return cuadros, duraciones


def cargar_fotos():
    if not os.path.isdir(CARPETA_FOTOS):
        return []
    fotos = []
    for nombre in sorted(os.listdir(CARPETA_FOTOS), key=str.lower):
        if nombre.lower().endswith(EXTENSIONES):
            try:
                cuadros, duraciones = abrir_imagen(os.path.join(CARPETA_FOTOS, nombre))
                fotos.append((nombre, cuadros, duraciones))
            except (OSError, ValueError):
                pass
    return fotos


def mostrar_tecla(tecla):
    return tecla.upper()


# ======================================================================
# Actualizacion online
# ======================================================================
def numero_version(texto):
    """'1.10' -> (1, 10) para poder comparar versiones."""
    partes = []
    for p in str(texto).strip().split("."):
        digitos = "".join(c for c in p if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes)


def descargar_texto(url, segundos=6):
    # el ?t= evita que se quede con una copia vieja guardada
    req = urllib.request.Request(f"{url}?t={int(time.time())}",
                                 headers={"User-Agent": f"{NOMBRE_APP}/{VERSION}",
                                          "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=segundos) as r:
        return r.read().decode("utf-8")


def buscar_actualizacion():
    """
    Devuelve (version_nueva, notas) si en GitHub hay una version mayor, o None.
    version.txt: la primera linea es el numero; las siguientes (opcional) son las novedades.
    """
    texto = descargar_texto(URL_VERSION)
    lineas = [l.rstrip() for l in texto.splitlines()]
    if not lineas or not lineas[0].strip():
        return None
    nueva = lineas[0].strip()
    if numero_version(nueva) > numero_version(VERSION):
        return nueva, "\n".join(l for l in lineas[1:] if l.strip())
    return None


def instalar_actualizacion():
    """Descarga el script nuevo, lo revisa, respalda el actual y lo reemplaza."""
    codigo = descargar_texto(URL_SCRIPT, segundos=20)
    # Revisar que lo descargado sea de verdad este programa y no tenga errores
    if "NOMBRE_APP" not in codigo or "def main" not in codigo:
        raise ValueError("El archivo descargado no es el contador.")
    compile(codigo, "contador_cofres.py", "exec")
    actual = os.path.abspath(__file__)
    shutil.copy2(actual, os.path.join(CARPETA, "contador_cofres_respaldo.py"))
    temporal = actual + ".nuevo"
    with open(temporal, "w", encoding="utf-8", newline="\n") as f:
        f.write(codigo)
    os.replace(temporal, actual)


def reiniciar_programa():
    ejecutable = sys.executable
    # si se abrio con pythonw (sin ventana negra), se reabre igual
    subprocess.Popen([ejecutable, os.path.abspath(__file__)], cwd=CARPETA)


# ======================================================================
# Mando de Xbox (XInput, viene con Windows: no hay que instalar nada)
# ======================================================================
BOTONES_XINPUT = {
    "DPAD_UP": 0x0001, "DPAD_DOWN": 0x0002, "DPAD_LEFT": 0x0004, "DPAD_RIGHT": 0x0008,
    "MENU": 0x0010, "VIEW": 0x0020, "L3": 0x0040, "R3": 0x0080,
    "LB": 0x0100, "RB": 0x0200, "A": 0x1000, "B": 0x2000, "X": 0x4000, "Y": 0x8000,
}
NOMBRES_BOTONES = {
    "DPAD_UP": "↑", "DPAD_DOWN": "↓", "DPAD_LEFT": "←", "DPAD_RIGHT": "→",
    "MENU": "Menu", "VIEW": "View", "L3": "L3", "R3": "R3", "LB": "LB", "RB": "RB",
    "LT": "LT", "RT": "RT", "A": "A", "B": "B", "X": "X", "Y": "Y",
}
ORDEN_BOTONES = ["VIEW", "MENU", "LB", "RB", "LT", "RT", "L3", "R3",
                 "A", "B", "X", "Y", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"]
UMBRAL_GATILLO = 60          # 0-255: cuanto apretar LT / RT para que cuente como apretado

MANDO_INICIAL = {
    "cofre": ["X"],                       # X = interactuar en Fortnite (mantener)
    "sumar": ["VIEW", "DPAD_UP"],
    "restar": ["VIEW", "DPAD_DOWN"],
    "foto": ["VIEW", "DPAD_LEFT"],
    "salir": [],
    "reiniciar": ["VIEW", "DPAD_RIGHT"],
}


def mostrar_combo(botones):
    if not botones:
        return "—"
    orden = sorted(botones, key=lambda b: ORDEN_BOTONES.index(b) if b in ORDEN_BOTONES else 99)
    return " + ".join(NOMBRES_BOTONES.get(b, b) for b in orden)


class LectorMando(threading.Thread):
    """Lee el mando unas 60 veces por segundo y avisa cuando se aprietan/sueltan botones."""

    def __init__(self, al_apretar, al_soltar):
        super().__init__(daemon=True)
        self.al_apretar = al_apretar
        self.al_soltar = al_soltar
        self.apretados = frozenset()
        self.conectado = False
        self.disponible = False
        self.pausado = False
        self._xinput = None
        self._estado_cls = None
        self._cargar()

    def _cargar(self):
        try:
            import ctypes
            from ctypes import wintypes

            class XINPUT_GAMEPAD(ctypes.Structure):
                _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte),
                            ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                            ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                            ("sThumbRY", ctypes.c_short)]

            class XINPUT_STATE(ctypes.Structure):
                _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]

            for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    self._xinput = getattr(ctypes.windll, dll)
                    break
                except (AttributeError, OSError):
                    continue
            if self._xinput:
                self._estado_cls = XINPUT_STATE
                self._ctypes = ctypes
                self.disponible = True
        except (ImportError, AttributeError, OSError):
            self.disponible = False

    def _leer(self, ultimo_reintento, slots_conectados):
        """Junta los botones apretados de todos los mandos conectados."""
        apretados = set()
        ahora = time.monotonic()
        revisar_todos = ahora - ultimo_reintento[0] > 2.0
        if revisar_todos:
            ultimo_reintento[0] = ahora
        for slot in range(4):
            # Preguntar por un mando desconectado es lento: se reintenta cada 2 s
            if slot not in slots_conectados and not revisar_todos:
                continue
            estado = self._estado_cls()
            if self._xinput.XInputGetState(slot, self._ctypes.byref(estado)) != 0:
                slots_conectados.discard(slot)
                continue
            slots_conectados.add(slot)
            pad = estado.Gamepad
            for nombre, bit in BOTONES_XINPUT.items():
                if pad.wButtons & bit:
                    apretados.add(nombre)
            if pad.bLeftTrigger >= UMBRAL_GATILLO:
                apretados.add("LT")
            if pad.bRightTrigger >= UMBRAL_GATILLO:
                apretados.add("RT")
        return frozenset(apretados)

    def run(self):
        if not self.disponible:
            return
        ultimo_reintento = [0.0]
        slots = set()
        while True:
            try:
                ahora = self._leer(ultimo_reintento, slots)
            except Exception:
                ahora = frozenset()
            self.conectado = bool(slots)
            antes = self.apretados
            self.apretados = ahora
            if not self.pausado:
                nuevos, soltados = ahora - antes, antes - ahora
                if nuevos:
                    self.al_apretar(nuevos, ahora)
                if soltados:
                    self.al_soltar(soltados, ahora)
            time.sleep(1 / 60)


# ---------- Ventana principal ----------
class Superposicion:
    def __init__(self, root):
        self.root = root
        self.cfg = leer_config()
        self.filas = leer_registro()
        self.sesion = 0
        self.fotos = cargar_fotos()
        self.indice = 0
        self.cuadros_tk = []
        self.duraciones = []
        self.cuadro_actual = 0
        self.timer_animacion = None
        self.timer_foto = None
        self.arrastre = (0, 0)
        self.confirmando = False
        self.timer_confirmar = None
        self.ventana_teclas = None
        self.capturando = None
        self.etiquetas_teclas = {}
        self.lbl_aviso_teclas = None
        self.e_estado = {"apretada": False, "id": 0}       # tecla de cofre (teclado)
        self.mando_estado = {"apretada": False, "id": 0}   # boton de cofre (mando)
        self.etiquetas_mando = {}
        self.lbl_estado_mando = None
        self.captura_mando = set()
        self.captura_inicio = 0.0

        root.title(NOMBRE_APP)
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.cfg["opacidad"])
        root.configure(bg=FONDO)
        root.geometry(f"+{self.cfg['x']}+{self.cfg['y']}")

        # Barra de arriba
        barra = tk.Frame(root, bg=BARRA)
        barra.pack(fill="x")
        for texto, accion in (("◀", self.foto_anterior), ("▶", self.foto_siguiente),
                              ("Foto", self.alternar_foto), ("−", lambda: self.cambiar_tamano(-30)),
                              ("+", lambda: self.cambiar_tamano(30))):
            self.boton_chico(barra, texto, accion).pack(side="left", padx=1, pady=2)
        self.boton_chico(barra, "✕", self.salir, ROJO).pack(side="right", padx=2, pady=2)
        self.boton_chico(barra, "Teclas", self.abrir_teclas, AZUL).pack(side="right", padx=1, pady=2)
        self.boton_chico(barra, "Añadir", self.agregar_fotos, VERDE).pack(side="right", padx=1, pady=2)

        # Nombre de la app, arriba de las fotos
        self.lbl_titulo = tk.Label(root, text=NOMBRE_APP, font=("Segoe UI", 13, "bold"),
                                   fg=DORADO, bg=FONDO)
        self.lbl_titulo.pack(pady=(5, 0))

        # Foto
        self.lbl_foto = tk.Label(root, bg=FONDO, bd=0)

        # Contador
        self.zona_contador = tk.Frame(root, bg=FONDO)
        self.zona_contador.pack(fill="x", side="bottom")
        fila = tk.Frame(self.zona_contador, bg=FONDO)
        fila.pack(pady=(4, 0))
        self.boton_chico(fila, "−1", self.restar, ROJO).pack(side="left", padx=6)
        self.lbl_sesion = tk.Label(fila, font=("Segoe UI", 26, "bold"), fg=DORADO, bg=FONDO, width=4)
        self.lbl_sesion.pack(side="left")
        self.boton_chico(fila, "+1", self.sumar, VERDE).pack(side="left", padx=6)
        self.lbl_info = tk.Label(self.zona_contador, font=("Segoe UI", 9, "bold"), fg=GRIS, bg=FONDO)
        self.lbl_info.pack(pady=(0, 0))
        self.lbl_mando = tk.Label(self.zona_contador, font=("Segoe UI", 8), fg=GRIS, bg=FONDO)
        self.lbl_mando.pack(pady=(0, 1))
        self.lbl_firma = tk.Label(self.zona_contador, text=f"creado x weasrandomexe  ·  v{VERSION}",
                                  font=("Segoe UI", 7, "italic"), fg="#6e6e6e", bg=FONDO)
        self.lbl_firma.pack(pady=(0, 4))

        for w in (root, barra, self.lbl_titulo, self.lbl_foto, self.zona_contador, fila,
                  self.lbl_sesion, self.lbl_info, self.lbl_mando, self.lbl_firma):
            w.bind("<ButtonPress-1>", self.empezar_arrastre)
            w.bind("<B1-Motion>", self.arrastrar)
            w.bind("<ButtonRelease-1>", lambda e: self.guardar_posicion())
            w.bind("<MouseWheel>", self.rueda)

        self.registrar_teclas()
        self.lector = LectorMando(self.mando_apretar, self.mando_soltar)
        self.lector.start()
        self.mostrar_u_ocultar_foto()
        self.actualizar()
        self.programar_cambio_foto()
        self.revisar_eventos()
        self.revisar_mando_conectado()
        # Si se acaba de actualizar, mostrar las novedades una sola vez
        self.root.after(800, self.revisar_novedades)
        # Buscar actualizacion en segundo plano (si no hay internet, no pasa nada)
        threading.Thread(target=self.hilo_buscar_actualizacion, daemon=True).start()

    # --- elementos ---
    def boton_chico(self, padre, texto, accion, color="#3a3a3a"):
        return tk.Button(padre, text=texto, command=accion, font=("Segoe UI", 9, "bold"),
                         fg="white", bg=color, activebackground=color, activeforeground="white",
                         relief="flat", bd=0, padx=7, pady=1, cursor="hand2")

    # --- tecla de cofre mantenida ---
    def empezar_mantener(self, estado):
        """Sirve para la tecla del teclado y para el boton del mando."""
        if estado["apretada"]:
            return   # Windows repite el evento mientras la tecla esta abajo
        estado["apretada"] = True
        estado["id"] += 1
        if not self.cfg.get("auto_cofre", True):
            return
        mi_id = estado["id"]

        def revisar():
            if estado["apretada"] and estado["id"] == mi_id:
                eventos.put("sumar")

        segundos = max(0.1, float(self.cfg.get("segundos_cofre", 0.5)))
        threading.Timer(segundos, revisar).start()

    def e_presionada(self, _evento):
        self.empezar_mantener(self.e_estado)

    def e_soltada(self, _evento):
        self.e_estado["apretada"] = False

    # --- mando (estas dos funciones corren en el hilo del lector) ---
    def mando_apretar(self, nuevos, apretados):
        if not self.cfg["mando"]["usar"] or self.capturando:
            return
        botones = self.cfg["mando"]["botones"]
        for accion in ("sumar", "restar", "foto", "salir", "reiniciar"):
            combo = set(botones.get(accion) or [])
            # se activa cuando todos los botones de la combinacion estan apretados
            # y uno de ellos se acaba de apretar
            if combo and combo <= apretados and combo & nuevos:
                eventos.put(accion)
        cofre = botones.get("cofre") or []
        if cofre and cofre[0] in nuevos:
            self.empezar_mantener(self.mando_estado)

    def mando_soltar(self, soltados, _apretados):
        cofre = self.cfg["mando"]["botones"].get("cofre") or []
        if cofre and cofre[0] in soltados:
            self.mando_estado["apretada"] = False

    def texto_estado_mando(self):
        if not self.lector.disponible:
            return "Mando: no disponible en este PC", GRIS
        if not self.cfg["mando"]["usar"]:
            return "Mando: desactivado", GRIS
        if self.lector.conectado:
            return "Mando: conectado ✔", VERDE
        return "Mando: no detectado", GRIS

    def revisar_mando_conectado(self):
        texto, color = self.texto_estado_mando()
        self.lbl_mando.config(text=texto, fg=color)
        if self.lbl_estado_mando and self.ventana_teclas and self.ventana_teclas.winfo_exists():
            self.lbl_estado_mando.config(text=texto, fg=color)
        self.root.after(1000, self.revisar_mando_conectado)

    # --- teclas ---
    def registrar_teclas(self):
        keyboard.unhook_all()
        self.e_estado["apretada"] = False
        t = self.cfg["teclas"]
        for accion in ("sumar", "restar", "foto", "salir", "reiniciar"):
            try:
                keyboard.add_hotkey(t[accion], lambda a=accion: eventos.put(a))
            except ValueError:
                t[accion] = TECLAS_INICIALES[accion]
                keyboard.add_hotkey(t[accion], lambda a=accion: eventos.put(a))
        try:
            keyboard.on_press_key(t["cofre"], self.e_presionada)
            keyboard.on_release_key(t["cofre"], self.e_soltada)
        except ValueError:
            t["cofre"] = TECLAS_INICIALES["cofre"]
            keyboard.on_press_key(t["cofre"], self.e_presionada)
            keyboard.on_release_key(t["cofre"], self.e_soltada)

    def abrir_teclas(self):
        if self.ventana_teclas and self.ventana_teclas.winfo_exists():
            self.ventana_teclas.lift()
            return
        v = tk.Toplevel(self.root)
        self.ventana_teclas = v
        v.title(f"{NOMBRE_APP} - Teclas")
        v.configure(bg=FONDO)
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.protocol("WM_DELETE_WINDOW", self.cerrar_teclas)
        v.geometry(f"+{self.root.winfo_x() + 30}+{self.root.winfo_y() + 30}")

        tk.Label(v, text="Cambiar teclas", font=("Segoe UI", 12, "bold"),
                 fg=DORADO, bg=FONDO).grid(row=0, column=0, columnspan=3, pady=(10, 6))

        self.etiquetas_teclas = {}
        for i, accion in enumerate(TECLAS_INICIALES, start=1):
            tk.Label(v, text=NOMBRES_ACCIONES[accion], font=("Segoe UI", 9), fg="white",
                     bg=FONDO, anchor="w").grid(row=i, column=0, sticky="w", padx=(12, 8), pady=2)
            lbl = tk.Label(v, text=mostrar_tecla(self.cfg["teclas"][accion]), width=12,
                           font=("Segoe UI", 9, "bold"), fg=DORADO, bg=BARRA)
            lbl.grid(row=i, column=1, padx=4, pady=2)
            self.etiquetas_teclas[accion] = lbl
            self.boton_chico(v, "Cambiar", lambda a=accion: self.capturar_tecla(a)).grid(
                row=i, column=2, padx=(4, 12), pady=2)

        fila = len(TECLAS_INICIALES) + 1

        # --- Mando de Xbox ---
        tk.Label(v, text="Mando de Xbox", font=("Segoe UI", 12, "bold"),
                 fg=DORADO, bg=FONDO).grid(row=fila, column=0, columnspan=3, pady=(12, 0))
        fila += 1
        self.var_usar_mando = tk.BooleanVar(value=bool(self.cfg["mando"]["usar"]))
        tk.Checkbutton(v, text="Usar el mando", variable=self.var_usar_mando,
                       command=self.guardar_usar_mando, font=("Segoe UI", 9), fg="white", bg=FONDO,
                       selectcolor=BARRA, activebackground=FONDO, activeforeground="white"
                       ).grid(row=fila, column=0, sticky="w", padx=10)
        texto, color = self.texto_estado_mando()
        self.lbl_estado_mando = tk.Label(v, text=texto, font=("Segoe UI", 8, "bold"), fg=color, bg=FONDO)
        self.lbl_estado_mando.grid(row=fila, column=1, columnspan=2, sticky="e", padx=12)
        fila += 1
        self.etiquetas_mando = {}
        for accion in MANDO_INICIAL:
            tk.Label(v, text=NOMBRES_ACCIONES[accion], font=("Segoe UI", 9), fg="white",
                     bg=FONDO, anchor="w").grid(row=fila, column=0, sticky="w", padx=(12, 8), pady=2)
            lbl = tk.Label(v, text=mostrar_combo(self.cfg["mando"]["botones"][accion]), width=12,
                           font=("Segoe UI", 9, "bold"), fg=DORADO, bg=BARRA)
            lbl.grid(row=fila, column=1, padx=4, pady=2)
            self.etiquetas_mando[accion] = lbl
            par = tk.Frame(v, bg=FONDO)
            par.grid(row=fila, column=2, padx=(4, 12), pady=2, sticky="w")
            self.boton_chico(par, "Cambiar", lambda a=accion: self.capturar_boton(a)).pack(side="left")
            self.boton_chico(par, "✕", lambda a=accion: self.quitar_boton(a)).pack(side="left", padx=(3, 0))
            fila += 1
        tk.Label(v, text="Para las acciones usa combinaciones (ej. View + ↑) asi no chocan\n"
                         "con los controles del juego. Cofre = un solo boton (mantener).",
                 font=("Segoe UI", 8), fg=GRIS, bg=FONDO, justify="left"
                 ).grid(row=fila, column=0, columnspan=3, sticky="w", padx=12, pady=(2, 0))
        fila += 1

        # --- Ajustes del contador de cofres con la tecla mantenida ---
        cofre = tk.Frame(v, bg=BARRA)
        cofre.grid(row=fila, column=0, columnspan=3, sticky="we", padx=12, pady=(10, 2))
        self.lbl_titulo_cofre = tk.Label(cofre, font=("Segoe UI", 10, "bold"), fg=DORADO, bg=BARRA,
                                         anchor="w")
        self.lbl_titulo_cofre.pack(fill="x", padx=10, pady=(8, 2))

        self.var_auto = tk.BooleanVar(value=bool(self.cfg.get("auto_cofre", True)))
        tk.Checkbutton(cofre, text="Contar solo al mantener la tecla", variable=self.var_auto,
                       command=self.guardar_ajustes_cofre, font=("Segoe UI", 9), fg="white", bg=BARRA,
                       selectcolor=FONDO, activebackground=BARRA, activeforeground="white",
                       anchor="w").pack(fill="x", padx=8)

        tk.Label(cofre, text="Segundos que hay que mantenerla:", font=("Segoe UI", 9), fg="white",
                 bg=BARRA, anchor="w").pack(fill="x", padx=10, pady=(4, 0))
        self.var_segundos = tk.DoubleVar(value=float(self.cfg.get("segundos_cofre", 0.5)))
        tk.Scale(cofre, variable=self.var_segundos, from_=0.2, to=2.0, resolution=0.1,
                 orient="horizontal", length=300, bg=BARRA, fg="white", troughcolor=FONDO,
                 highlightthickness=0, activebackground=DORADO,
                 command=lambda _v: self.guardar_ajustes_cofre()).pack(padx=10)
        tk.Label(cofre, text="Menos tiempo = cuenta mas rapido, pero puede contar cosas cortas.\n"
                             "Mas tiempo = mas seguro, pero tienes que mantenerla mas.",
                 font=("Segoe UI", 8), fg=GRIS, bg=BARRA, justify="left", anchor="w"
                 ).pack(fill="x", padx=10, pady=(0, 8))
        self.actualizar_titulo_cofre()

        self.lbl_aviso_teclas = tk.Label(v, text="", font=("Segoe UI", 8), fg=GRIS, bg=FONDO,
                                         wraplength=300)
        self.lbl_aviso_teclas.grid(row=fila + 1, column=0, columnspan=3, pady=(6, 2))

        botones = tk.Frame(v, bg=FONDO)
        botones.grid(row=fila + 2, column=0, columnspan=3, pady=(2, 10))
        self.boton_chico(botones, "Restaurar", self.restaurar_teclas).pack(side="left", padx=4)
        self.boton_chico(botones, "Listo", self.cerrar_teclas, VERDE).pack(side="left", padx=4)

    def actualizar_titulo_cofre(self):
        if self.ventana_teclas and self.ventana_teclas.winfo_exists():
            tecla = mostrar_tecla(self.cfg["teclas"]["cofre"])
            boton = mostrar_combo(self.cfg["mando"]["botones"].get("cofre") or [])
            if boton == "—":
                self.lbl_titulo_cofre.config(text=f"Abrir cofres con la {tecla}")
            else:
                self.lbl_titulo_cofre.config(text=f"Abrir cofres con la {tecla} o la {boton} del mando")

    def guardar_ajustes_cofre(self):
        self.cfg["auto_cofre"] = bool(self.var_auto.get())
        self.cfg["segundos_cofre"] = round(float(self.var_segundos.get()), 1)
        guardar_config(self.cfg)

    def guardar_usar_mando(self):
        self.cfg["mando"]["usar"] = bool(self.var_usar_mando.get())
        guardar_config(self.cfg)

    def capturar_boton(self, accion):
        if self.capturando:
            return
        if not self.lector.disponible or not self.lector.conectado:
            self.lbl_aviso_teclas.config(text="No se detecta ningun mando. Conectalo y prueba de nuevo.", fg=ROJO)
            return
        self.capturando = ("mando", accion)
        self.lector.pausado = True
        self.captura_mando = set()
        self.captura_inicio = time.monotonic()
        self.etiquetas_mando[accion].config(text="Aprieta...", fg="white")
        if accion == "cofre":
            msg = "Aprieta UN boton en el mando y suelta."
        else:
            msg = "Aprieta los botones juntos en el mando (ej. View + ↑) y suelta. Espera 8 s para cancelar."
        self.lbl_aviso_teclas.config(text=msg, fg=GRIS)
        self.root.after(30, self.revisar_captura_boton)

    def revisar_captura_boton(self):
        if not (isinstance(self.capturando, tuple) and self.capturando[0] == "mando"):
            return
        ahora = self.lector.apretados
        self.captura_mando |= set(ahora)
        if self.captura_mando and not ahora:
            self.terminar_captura_boton(sorted(self.captura_mando))
        elif time.monotonic() - self.captura_inicio > 8:
            self.terminar_captura_boton(None)
        else:
            self.root.after(30, self.revisar_captura_boton)

    def terminar_captura_boton(self, botones):
        accion = self.capturando[1]
        self.capturando = None
        self.lector.pausado = False
        mensaje, color = "", GRIS
        actuales = self.cfg["mando"]["botones"]
        if not botones:
            mensaje = "Cancelado."
        elif accion == "cofre" and len(botones) > 1:
            mensaje, color = "Para abrir cofres tiene que ser UN solo boton.", ROJO
        else:
            otra = next((a for a, b in actuales.items() if a != accion and set(b) == set(botones)), None)
            if otra:
                mensaje, color = f"{mostrar_combo(botones)} ya se usa para \"{NOMBRES_ACCIONES[otra]}\".", ROJO
            else:
                actuales[accion] = list(botones)
                guardar_config(self.cfg)
                mensaje = f"Listo: {NOMBRES_ACCIONES[accion]} = {mostrar_combo(botones)}"
                if accion != "cofre" and len(botones) == 1:
                    mensaje += "  (OJO: un solo boton tambien lo usa el juego)"
                    color = DORADO
        if self.ventana_teclas and self.ventana_teclas.winfo_exists():
            self.etiquetas_mando[accion].config(text=mostrar_combo(actuales[accion]), fg=DORADO)
            self.lbl_aviso_teclas.config(text=mensaje, fg=color)
            self.actualizar_titulo_cofre()

    def quitar_boton(self, accion):
        if self.capturando:
            return
        self.cfg["mando"]["botones"][accion] = []
        guardar_config(self.cfg)
        self.etiquetas_mando[accion].config(text="—", fg=DORADO)
        self.lbl_aviso_teclas.config(text=f"{NOMBRES_ACCIONES[accion]}: sin boton en el mando.", fg=GRIS)
        self.actualizar_titulo_cofre()

    def capturar_tecla(self, accion):
        if self.capturando:
            return
        self.capturando = accion
        keyboard.unhook_all()   # para que la tecla que apretes no active nada
        self.etiquetas_teclas[accion].config(text="Aprieta...", fg="white")
        self.lbl_aviso_teclas.config(text="Aprieta la tecla nueva (Esc para cancelar)", fg=GRIS)

        def hilo():
            try:
                tecla = keyboard.read_hotkey(suppress=False)
            except Exception:
                tecla = "esc"
            eventos.put(("tecla_nueva", accion, tecla))

        threading.Thread(target=hilo, daemon=True).start()

    def recibir_tecla(self, accion, tecla):
        self.capturando = None
        tecla = (tecla or "").lower()
        if accion == "cofre":
            tecla = tecla.split("+")[-1]   # la de cofre tiene que ser una sola tecla
        mensaje, color = "", GRIS
        if not tecla or tecla == "esc":
            mensaje = "Cancelado."
        else:
            otra = next((a for a, t in self.cfg["teclas"].items() if t == tecla and a != accion), None)
            if otra:
                mensaje, color = f"{mostrar_tecla(tecla)} ya se usa para \"{NOMBRES_ACCIONES[otra]}\".", ROJO
            else:
                self.cfg["teclas"][accion] = tecla
                mensaje = f"Listo: {NOMBRES_ACCIONES[accion]} = {mostrar_tecla(tecla)}"
        self.registrar_teclas()
        guardar_config(self.cfg)
        if self.ventana_teclas and self.ventana_teclas.winfo_exists():
            self.etiquetas_teclas[accion].config(text=mostrar_tecla(self.cfg["teclas"][accion]), fg=DORADO)
            self.lbl_aviso_teclas.config(text=mensaje, fg=color)
            self.actualizar_titulo_cofre()
        self.actualizar()

    def restaurar_teclas(self):
        if self.capturando:
            return
        self.cfg["teclas"] = dict(TECLAS_INICIALES)
        self.cfg["mando"] = mando_inicial()
        self.var_usar_mando.set(True)
        for accion, lbl in self.etiquetas_mando.items():
            lbl.config(text=mostrar_combo(self.cfg["mando"]["botones"][accion]), fg=DORADO)
        self.cfg["auto_cofre"] = CONFIG_INICIAL["auto_cofre"]
        self.cfg["segundos_cofre"] = CONFIG_INICIAL["segundos_cofre"]
        self.var_auto.set(self.cfg["auto_cofre"])
        self.var_segundos.set(self.cfg["segundos_cofre"])
        guardar_config(self.cfg)
        self.registrar_teclas()
        for accion, lbl in self.etiquetas_teclas.items():
            lbl.config(text=mostrar_tecla(self.cfg["teclas"][accion]), fg=DORADO)
        self.lbl_aviso_teclas.config(text="Teclas y ajustes originales restaurados.", fg=GRIS)
        self.actualizar_titulo_cofre()
        self.actualizar()

    def cerrar_teclas(self):
        if self.capturando:
            return
        if self.ventana_teclas:
            self.ventana_teclas.destroy()
        self.ventana_teclas = None
        self.lbl_estado_mando = None

    # --- fotos y GIFs ---
    def dibujar_foto(self):
        if self.timer_animacion:
            self.root.after_cancel(self.timer_animacion)
            self.timer_animacion = None
        if not self.fotos or not self.cfg["mostrar_foto"]:
            return
        lado = int(self.cfg["tamano"])
        _nombre, cuadros, duraciones = self.fotos[self.indice % len(self.fotos)]
        self.cuadros_tk = []
        for cuadro in cuadros:
            img = cuadro.copy()
            img.thumbnail((lado, lado), Image.LANCZOS)
            fondo = Image.new("RGBA", img.size, FONDO)
            fondo.alpha_composite(img)
            self.cuadros_tk.append(ImageTk.PhotoImage(fondo.convert("RGB")))
        self.duraciones = duraciones
        self.cuadro_actual = 0
        self.lbl_foto.config(image=self.cuadros_tk[0], width=lado, height=lado)
        if len(self.cuadros_tk) > 1:
            self.timer_animacion = self.root.after(self.duraciones[0], self.animar)

    def animar(self):
        if not self.cuadros_tk:
            return
        self.cuadro_actual = (self.cuadro_actual + 1) % len(self.cuadros_tk)
        self.lbl_foto.config(image=self.cuadros_tk[self.cuadro_actual])
        self.timer_animacion = self.root.after(self.duraciones[self.cuadro_actual], self.animar)

    def agregar_fotos(self):
        # Se quita "siempre encima" un momento para que la ventana de archivos no quede detras
        self.root.attributes("-topmost", False)
        try:
            rutas = filedialog.askopenfilenames(
                parent=self.root, title="Elige fotos o GIFs",
                filetypes=[("Imagenes y GIFs", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                           ("Todos los archivos", "*.*")])
        finally:
            self.root.attributes("-topmost", True)
        if not rutas:
            return
        os.makedirs(CARPETA_FOTOS, exist_ok=True)
        primera = None
        for ruta in rutas:
            if not ruta.lower().endswith(EXTENSIONES):
                continue
            base, ext = os.path.splitext(os.path.basename(ruta))
            nombre = base + ext
            n = 2
            while os.path.exists(os.path.join(CARPETA_FOTOS, nombre)):
                nombre = f"{base} ({n}){ext}"
                n += 1
            try:
                shutil.copy2(ruta, os.path.join(CARPETA_FOTOS, nombre))
                primera = primera or nombre
            except OSError:
                pass
        if not primera:
            return
        self.fotos = cargar_fotos()
        nombres = [f[0] for f in self.fotos]
        self.indice = nombres.index(primera) if primera in nombres else 0
        self.cfg["mostrar_foto"] = True
        guardar_config(self.cfg)
        self.mostrar_u_ocultar_foto()
        self.programar_cambio_foto()

    def programar_cambio_foto(self):
        if self.timer_foto:
            self.root.after_cancel(self.timer_foto)
        self.timer_foto = self.root.after(SEGUNDOS_POR_FOTO * 1000, self.foto_siguiente)

    def foto_siguiente(self):
        if self.fotos:
            self.indice = (self.indice + 1) % len(self.fotos)
            self.dibujar_foto()
        self.programar_cambio_foto()

    def foto_anterior(self):
        if self.fotos:
            self.indice = (self.indice - 1) % len(self.fotos)
            self.dibujar_foto()
        self.programar_cambio_foto()

    def mostrar_u_ocultar_foto(self):
        if self.cfg["mostrar_foto"] and self.fotos:
            self.lbl_foto.pack(before=self.zona_contador, padx=6, pady=(4, 0))
            self.dibujar_foto()
        else:
            if self.timer_animacion:
                self.root.after_cancel(self.timer_animacion)
                self.timer_animacion = None
            self.lbl_foto.pack_forget()

    def alternar_foto(self):
        self.cfg["mostrar_foto"] = not self.cfg["mostrar_foto"]
        self.mostrar_u_ocultar_foto()
        guardar_config(self.cfg)

    def cambiar_tamano(self, delta):
        self.cfg["tamano"] = max(TAMANO_MIN, min(TAMANO_MAX, self.cfg["tamano"] + delta))
        self.dibujar_foto()
        guardar_config(self.cfg)

    def cambiar_opacidad(self, delta):
        self.cfg["opacidad"] = round(max(0.3, min(1.0, self.cfg["opacidad"] + delta)), 2)
        self.root.attributes("-alpha", self.cfg["opacidad"])
        guardar_config(self.cfg)

    def rueda(self, evento):
        paso = 1 if evento.delta > 0 else -1
        if evento.state & 0x0004:  # Ctrl apretado
            self.cambiar_opacidad(0.05 * paso)
        else:
            self.cambiar_tamano(20 * paso)

    # --- mover ventana ---
    def empezar_arrastre(self, evento):
        self.arrastre = (evento.x_root - self.root.winfo_x(), evento.y_root - self.root.winfo_y())

    def arrastrar(self, evento):
        x = evento.x_root - self.arrastre[0]
        y = evento.y_root - self.arrastre[1]
        self.root.geometry(f"+{x}+{y}")

    def guardar_posicion(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        guardar_config(self.cfg)

    # --- actualizacion online ---
    def hilo_buscar_actualizacion(self):
        try:
            hay = buscar_actualizacion()
        except Exception:
            return   # sin internet o GitHub no responde: se sigue normal
        if hay:
            eventos.put(("actualizacion", hay[0], hay[1]))

    def revisar_novedades(self):
        vista = self.cfg.get("version_vista")
        self.cfg["version_vista"] = VERSION
        guardar_config(self.cfg)
        # Primera vez que se abre (instalacion nueva): no hay nada que mostrar
        if not vista or numero_version(vista) >= numero_version(VERSION):
            return
        # Juntar las novedades de todas las versiones que se salto
        versiones = sorted((v for v in NOVEDADES
                            if numero_version(vista) < numero_version(v) <= numero_version(VERSION)),
                           key=numero_version, reverse=True)
        if versiones:
            self.mostrar_novedades(versiones)

    def mostrar_novedades(self, versiones):
        v = tk.Toplevel(self.root)
        v.title(f"{NOMBRE_APP} - Novedades")
        v.configure(bg=FONDO)
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.geometry(f"+{self.root.winfo_x() + 30}+{self.root.winfo_y() + 30}")
        tk.Label(v, text="¡Se actualizo!", font=("Segoe UI", 14, "bold"),
                 fg=DORADO, bg=FONDO).pack(padx=24, pady=(16, 0))
        tk.Label(v, text=f"Ahora tienes la version {VERSION}", font=("Segoe UI", 9),
                 fg=GRIS, bg=FONDO).pack(padx=24, pady=(0, 6))
        for ver in versiones:
            caja = tk.Frame(v, bg=BARRA)
            caja.pack(fill="x", padx=16, pady=4)
            tk.Label(caja, text=f"Novedades {ver}", font=("Segoe UI", 10, "bold"), fg="white",
                     bg=BARRA, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
            for punto in NOVEDADES[ver]:
                tk.Label(caja, text=f"•  {punto}", font=("Segoe UI", 9), fg="white", bg=BARRA,
                         anchor="w", justify="left", wraplength=320).pack(fill="x", padx=12, pady=1)
            tk.Frame(caja, bg=BARRA, height=6).pack()
        tk.Label(v, text="creado x weasrandomexe", font=("Segoe UI", 7, "italic"),
                 fg="#6e6e6e", bg=FONDO).pack(pady=(6, 0))
        self.boton_chico(v, "¡Bacan!", v.destroy, VERDE).pack(pady=(6, 14))

    def ofrecer_actualizacion(self, nueva, notas):
        v = tk.Toplevel(self.root)
        v.title(f"{NOMBRE_APP} - Actualizacion")
        v.configure(bg=FONDO)
        v.attributes("-topmost", True)
        v.resizable(False, False)
        v.geometry(f"+{self.root.winfo_x() + 30}+{self.root.winfo_y() + 30}")
        tk.Label(v, text="¡Hay una version nueva!", font=("Segoe UI", 12, "bold"),
                 fg=DORADO, bg=FONDO).pack(padx=20, pady=(14, 2))
        tk.Label(v, text=f"Tienes la {VERSION}  →  nueva: {nueva}", font=("Segoe UI", 9),
                 fg="white", bg=FONDO).pack(padx=20)
        if notas:
            tk.Label(v, text=notas, font=("Segoe UI", 9), fg=GRIS, bg=FONDO, justify="left",
                     wraplength=320).pack(padx=20, pady=(8, 0))
        tk.Label(v, text="Tu conteo, fotos y teclas no se borran.", font=("Segoe UI", 8),
                 fg=GRIS, bg=FONDO).pack(padx=20, pady=(8, 0))
        estado = tk.Label(v, text="", font=("Segoe UI", 9, "bold"), fg="white", bg=FONDO,
                          wraplength=320)
        estado.pack(padx=20, pady=(6, 0))
        botones = tk.Frame(v, bg=FONDO)
        botones.pack(pady=12)

        def actualizar():
            for b in botones.winfo_children():
                b.config(state="disabled")
            estado.config(text="Descargando...", fg="white")
            v.update()
            try:
                instalar_actualizacion()
            except Exception as e:
                estado.config(text=f"No se pudo actualizar: {e}", fg=ROJO)
                for b in botones.winfo_children():
                    b.config(state="normal")
                return
            estado.config(text="Listo, reiniciando...", fg=VERDE)
            v.update()
            guardar_registro(self.filas)
            self.guardar_posicion()
            keyboard.unhook_all()
            reiniciar_programa()
            self.root.after(300, self.root.destroy)

        self.boton_chico(botones, "Actualizar", actualizar, VERDE).pack(side="left", padx=4)
        self.boton_chico(botones, "Ahora no", v.destroy).pack(side="left", padx=4)

    # --- contador ---
    def total_hoy(self):
        hoy = date.today().isoformat()
        return sum(1 for f in self.filas if f[0].startswith(hoy))

    def actualizar(self):
        self.lbl_sesion.config(text=str(self.sesion))
        if self.confirmando:
            tecla = mostrar_tecla(self.cfg["teclas"]["reiniciar"])
            self.lbl_info.config(text=f"¿Borrar TODO? Aprieta {tecla} otra vez", fg=ROJO)
        else:
            self.lbl_info.config(text=f"Hoy: {self.total_hoy()}   ·   Total: {len(self.filas)}", fg=GRIS)

    def pedir_reinicio(self):
        if not self.confirmando:
            self.confirmando = True
            self.actualizar()
            self.timer_confirmar = self.root.after(SEGUNDOS_CONFIRMAR * 1000, self.cancelar_reinicio)
            return
        self.root.after_cancel(self.timer_confirmar)
        if self.filas:
            sello = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            guardar_registro_en(os.path.join(CARPETA, f"respaldo_cofres_{sello}.csv"), self.filas)
        self.filas = []
        self.sesion = 0
        guardar_registro(self.filas)
        self.confirmando = False
        self.actualizar()

    def cancelar_reinicio(self):
        self.confirmando = False
        self.actualizar()

    def sumar(self):
        self.filas.append([datetime.now().isoformat(timespec="seconds")])
        self.sesion += 1
        guardar_registro(self.filas)
        self.actualizar()

    def restar(self):
        if self.filas and self.sesion > 0:
            self.filas.pop()
            self.sesion -= 1
            guardar_registro(self.filas)
            self.actualizar()

    def revisar_eventos(self):
        while not eventos.empty():
            evento = eventos.get()
            if isinstance(evento, tuple):
                if evento[0] == "tecla_nueva":
                    self.recibir_tecla(evento[1], evento[2])
                elif evento[0] == "actualizacion":
                    self.ofrecer_actualizacion(evento[1], evento[2])
                continue
            if self.capturando:
                continue
            if evento == "sumar":
                self.sumar()
            elif evento == "restar":
                self.restar()
            elif evento == "foto":
                self.alternar_foto()
            elif evento == "reiniciar":
                self.pedir_reinicio()
            elif evento == "salir":
                self.salir()
                return
        self.root.after(50, self.revisar_eventos)

    def salir(self):
        guardar_registro(self.filas)
        self.guardar_posicion()
        keyboard.unhook_all()
        self.root.destroy()


def main():
    root = tk.Tk()
    Superposicion(root)
    root.mainloop()


if __name__ == "__main__":
    main()
