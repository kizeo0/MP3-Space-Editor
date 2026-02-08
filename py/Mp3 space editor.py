import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import json
import threading
import queue
from pathlib import Path
import platform
import re
import sys
from typing import List, Dict, Tuple
from datetime import datetime

# Intentar importar tkinterDnD para drag and drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    TKINTERDND_AVAILABLE = True
except ImportError:
    TKINTERDND_AVAILABLE = False
    print("tkinterDnD no está instalado. Drag and drop no disponible.")
    print("Instálalo con: pip install tkinterdnd2")

class MP3Editor:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 Space Editor - El señor de la noche edition")
        self.root.geometry("1080x810")
        self.root.resizable(True, True)
        
        # Configurar para evitar cierre inesperado
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)
        
        # Intentar cargar el icono
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, 'icon.ico')
            else:
                icon_path = 'icon.ico'
            root.iconbitmap(icon_path)
        except:
            pass
        
        # Variables
        self.current_files = []  # Lista de archivos a procesar
        self.processing = False
        self.output_queue = queue.Queue()
        self.output_folder = tk.StringVar(value="")  # Carpeta de salida personalizada
        self.name_pattern = tk.StringVar(value="{filename}_editado")  # Patrón de nombre
        
        # Cargar configuración guardada
        self.config_file = "mp3_editor_config.json"
        self.last_bitrate = self.load_config()
        
        # Configurar estilo
        self.setup_styles()
        
        # Crear interfaz
        self.create_widgets()
        
        # Configurar drag and drop si está disponible
        if TKINTERDND_AVAILABLE:
            self.setup_drag_drop()
        
        # Verificar FFmpeg
        self.check_ffmpeg()
        
        # Iniciar monitor de salida
        self.root.after(100, self.process_output_queue)
    
    def setup_styles(self):
        """Configurar estilos para la interfaz"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configuraciones de estilo
        style.configure('Title.TLabel', font=('Arial', 14, 'bold'))
        style.configure('Subtitle.TLabel', font=('Arial', 11, 'bold'))
        style.configure('Info.TLabel', font=('Courier', 9))
        style.configure('Accent.TButton', font=('Arial', 10, 'bold'))
        
    def load_config(self):
        """Cargar configuración guardada"""
        default_bitrate = "Mantener bitrate original"
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('last_bitrate', default_bitrate)
        except:
            pass
        return default_bitrate
    
    def save_config(self):
        """Guardar configuración"""
        try:
            config = {
                'last_bitrate': self.bitrate_var.get()
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except:
            pass
    
    def setup_drag_drop(self):
        """Configurar funcionalidad de arrastrar y soltar usando tkinterDnD"""
        if not TKINTERDND_AVAILABLE:
            return
            
        try:
            # Configurar el treeview para aceptar archivos arrastrados
            self.files_tree.drop_target_register(DND_FILES)
            self.files_tree.dnd_bind('<<Drop>>', self.on_drop)
            
            # También configurar el frame principal del treeview
            self.tree_frame.drop_target_register(DND_FILES)
            self.tree_frame.dnd_bind('<<Drop>>', self.on_drop)
            
            # Configurar la ventana principal
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.on_drop)
            
            # Actualizar el mensaje de drag & drop
            self.drag_label.config(text="🎯 Arrastra y suelta archivos MP3 directamente aquí")
            
        except Exception as e:
            print(f"Error configurando drag and drop: {e}")
            self.drag_label.config(text="⚠ Drag and drop no disponible. Usa los botones arriba.")
    
    def on_drop(self, event):
        """Manejar archivos arrastrados"""
        try:
            # Obtener los archivos del evento de drop
            files = event.data
            
            # tkinterDnD devuelve una cadena con rutas separadas por espacios
            # Las rutas pueden estar entre llaves si tienen espacios
            file_list = []
            current_file = ""
            inside_braces = False
            
            for char in files:
                if char == '{':
                    inside_braces = True
                    continue
                elif char == '}':
                    inside_braces = False
                    if current_file:
                        file_list.append(current_file)
                        current_file = ""
                    continue
                elif char == ' ' and not inside_braces:
                    if current_file:
                        file_list.append(current_file)
                        current_file = ""
                    continue
                else:
                    current_file += char
            
            # Agregar el último archivo si queda alguno
            if current_file:
                file_list.append(current_file)
            
            # Procesar los archivos
            self.process_dropped_files(file_list)
            
        except Exception as e:
            print(f"Error en on_drop: {e}")
            messagebox.showerror("Error", f"No se pudieron procesar los archivos arrastrados: {e}")
    
    def process_dropped_files(self, files):
        """Procesar archivos arrastrados"""
        if not files:
            return
        
        added_count = 0
        for file_path in files:
            # Limpiar la ruta del archivo
            file_path = file_path.strip()
            # Verificar si el archivo existe y es MP3
            if os.path.exists(file_path) and file_path.lower().endswith('.mp3'):
                if file_path not in self.current_files:
                    self.current_files.append(file_path)
                    self.add_file_to_tree(file_path)
                    added_count += 1
            elif os.path.exists(file_path) and os.path.isdir(file_path):
                # Si es una carpeta, buscar archivos MP3 dentro
                for root_dir, _, filenames in os.walk(file_path):
                    for filename in filenames:
                        if filename.lower().endswith('.mp3'):
                            full_path = os.path.join(root_dir, filename)
                            if full_path not in self.current_files:
                                self.current_files.append(full_path)
                                self.add_file_to_tree(full_path)
                                added_count += 1
        
        if added_count > 0:
            self.update_file_count()
            self.update_status(f"✓ Añadidos {added_count} archivos por arrastre")
        else:
            messagebox.showwarning("Advertencia", "No se encontraron archivos MP3 válidos en los archivos arrastrados.")
    
    def check_ffmpeg(self):
        """Verificar si FFmpeg está instalado"""
        try:
            if os.path.exists("ffmpeg.exe"):
                self.log("✓ FFmpeg encontrado en directorio actual")
                return True
            
            # Verificar en PATH del sistema
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                self.log("✓ FFmpeg encontrado en sistema")
                return True
            else:
                self.show_warning("FFmpeg no encontrado. Algunas funciones pueden no estar disponibles.\n\nPuedes descargarlo de https://ffmpeg.org/ y colocarlo en la misma carpeta que esta aplicación.")
                return False
        except Exception as e:
            self.show_warning(f"FFmpeg no encontrado: {e}\n\nPor favor, instala FFmpeg para usar todas las funciones.")
            return False
    
    def create_widgets(self):
        """Crear todos los widgets de la interfaz"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configurar grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Título
        title_label = ttk.Label(main_frame, text="🎵 MP3 Space Editor - El señor de la noche edition", 
                               style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        
        # Sección: Selección de archivos
        self.create_files_selection_section(main_frame, row=1)
        
        # Sección: Configuración de salida
        self.create_output_section(main_frame, row=2)
        
        # Sección: Cambiar bitrate
        self.create_bitrate_section(main_frame, row=3)
        
        # Sección: Añadir silencio
        self.create_silence_section(main_frame, row=4)
        
        # Sección: Botones principales
        self.create_buttons_section(main_frame, row=5)
        
        # Barra de estado
        self.status_label = ttk.Label(main_frame, text="Listo", relief=tk.SUNKEN, 
                                     anchor=tk.W, padding=(5, 2))
        self.status_label.grid(row=6, column=0, columnspan=4, 
                              sticky=(tk.W, tk.E), pady=(10, 0))
    
    def create_files_selection_section(self, parent, row):
        """Crear sección para seleccionar múltiples archivos"""
        files_frame = ttk.LabelFrame(parent, text="Selección de Archivos", padding="10")
        files_frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        files_frame.columnconfigure(0, weight=1)
        
        # Botones de selección
        btn_frame = ttk.Frame(files_frame)
        btn_frame.grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        
        ttk.Button(btn_frame, text="Añadir Archivos...", 
                  command=self.add_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Añadir Carpeta...", 
                  command=self.add_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Limpiar Lista", 
                  command=self.clear_files).pack(side=tk.LEFT, padx=(0, 5))
        
        # Contador de archivos
        self.file_count_label = ttk.Label(files_frame, text="0 archivos seleccionados")
        self.file_count_label.grid(row=0, column=1, sticky=tk.E, pady=(0, 10))
        
        # Crear un frame para el treeview y scrollbars
        self.tree_frame = ttk.Frame(files_frame)
        self.tree_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 5))
        
        # Treeview para lista de archivos
        columns = ('filename', 'size', 'duration', 'bitrate', 'path')
        self.files_tree = ttk.Treeview(self.tree_frame, columns=columns, 
                                      show='headings', height=8)
        
        # Configurar columnas
        self.files_tree.heading('filename', text='Nombre del Archivo')
        self.files_tree.heading('size', text='Tamaño')
        self.files_tree.heading('duration', text='Duración')
        self.files_tree.heading('bitrate', text='Bitrate')
        self.files_tree.heading('path', text='Ruta')
        
        self.files_tree.column('filename', width=200, minwidth=150)
        self.files_tree.column('size', width=80, minwidth=60)
        self.files_tree.column('duration', width=80, minwidth=60)
        self.files_tree.column('bitrate', width=80, minwidth=60)
        self.files_tree.column('path', width=250, minwidth=150)
        
        # Scrollbars
        vsb = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.files_tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient=tk.HORIZONTAL, command=self.files_tree.xview)
        self.files_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Grid del treeview y scrollbars
        self.files_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # Configurar el grid del tree_frame
        self.tree_frame.columnconfigure(0, weight=1)
        self.tree_frame.rowconfigure(0, weight=1)
        
        files_frame.rowconfigure(1, weight=1)
        files_frame.columnconfigure(0, weight=1)
        
        # Mensaje de drag & drop
        if TKINTERDND_AVAILABLE:
            drag_text = "🎯 Arrastra y suelta archivos MP3 directamente en el área blanca de arriba"
        else:
            drag_text = "⚠ Drag and drop no disponible. Instala tkinterdnd2: pip install tkinterdnd2"
            
        self.drag_label = ttk.Label(files_frame, 
                                   text=drag_text, 
                                   font=('Arial', 9, 'italic'), foreground='blue')
        self.drag_label.grid(row=3, column=0, columnspan=3, pady=(5, 0))
    
    def create_output_section(self, parent, row):
        """Crear sección para configuración de salida"""
        output_frame = ttk.LabelFrame(parent, text="Configuración de Salida", padding="10")
        output_frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Carpeta de salida
        ttk.Label(output_frame, text="Carpeta de salida:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_folder, width=50)
        self.output_entry.grid(row=0, column=1, padx=(0, 5), sticky=(tk.W, tk.E))
        
        ttk.Button(output_frame, text="Seleccionar...", 
                  command=self.select_output_folder).grid(row=0, column=2)
        
        # Patrón de nombre
        ttk.Label(output_frame, text="Patrón de nombre:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(10, 0))
        
        name_frame = ttk.Frame(output_frame)
        name_frame.grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=(10, 0))
        
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_pattern, width=40)
        self.name_entry.pack(side=tk.LEFT, padx=(0, 5))
        
        # Info sobre variables disponibles
        help_btn = ttk.Button(name_frame, text="?", width=3, command=self.show_name_pattern_help)
        help_btn.pack(side=tk.LEFT)
        
        # Opciones de guardado
        self.overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(output_frame, text="Sobrescribir archivos existentes",
                       variable=self.overwrite_var).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        
        self.preserve_folder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(output_frame, text="Mantener estructura de carpetas",
                       variable=self.preserve_folder_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
        
        output_frame.columnconfigure(1, weight=1)
    
    def create_bitrate_section(self, parent, row):
        """Crear sección para cambiar bitrate"""
        bitrate_frame = ttk.LabelFrame(parent, text="Configuración de Bitrate", padding="10")
        bitrate_frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Lista completa de bitrates
        bitrates = [
            ("Mantener bitrate original", "original"),
            ("32 kbps - Muy baja calidad", "32k"),
            ("40 kbps", "40k"),
            ("48 kbps - Baja calidad", "48k"),
            ("56 kbps", "56k"),
            ("64 kbps - Calidad aceptable", "64k"),
            ("80 kbps", "80k"),
            ("96 kbps - Calidad media", "96k"),
            ("112 kbps", "112k"),
            ("128 kbps - Calidad estándar", "128k"),
            ("144 kbps", "144k"),
            ("160 kbps - Buena calidad", "160k"),
            ("176 kbps", "176k"),
            ("192 kbps - Alta calidad", "192k"),
            ("224 kbps", "224k"),
            ("256 kbps - Muy alta calidad", "256k"),
            ("288 kbps", "288k"),
            ("320 kbps - Calidad máxima", "320k"),
            ("Variable (VBR) - Balance calidad/tamaño", "vbr"),
            ("Personalizado", "custom")
        ]
        
        self.bitrate_var = tk.StringVar(value=self.last_bitrate)
        
        ttk.Label(bitrate_frame, text="Bitrate objetivo:").grid(row=0, column=0, 
                                                               sticky=tk.W, pady=(0, 10))
        
        self.bitrate_combo = ttk.Combobox(bitrate_frame, textvariable=self.bitrate_var,
                                         values=[b[0] for b in bitrates], state="readonly",
                                         width=45)
        self.bitrate_combo.grid(row=0, column=1, padx=(10, 0), pady=(0, 10), sticky=tk.W)
        
        # Establecer selección basada en configuración guardada
        self.set_bitrate_selection()
        
        # Entrada personalizada
        self.custom_frame = ttk.Frame(bitrate_frame)
        self.custom_frame.grid(row=1, column=0, columnspan=4, sticky=tk.W)
        
        ttk.Label(self.custom_frame, text="Bitrate personalizado (ej: 192k):").pack(side=tk.LEFT)
        self.custom_bitrate = ttk.Entry(self.custom_frame, width=10)
        self.custom_bitrate.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Label(self.custom_frame, text="kbps").pack(side=tk.LEFT, padx=(5, 0))
        self.custom_frame.grid_remove()
        
        # Checkbox para preservar metadatos
        self.preserve_meta = tk.BooleanVar(value=True)
        ttk.Checkbutton(bitrate_frame, text="Preservar metadatos (etiquetas ID3)",
                       variable=self.preserve_meta).grid(row=2, column=0, 
                                                       columnspan=4, sticky=tk.W, pady=(10, 0))
        
        self.bitrate_combo.bind('<<ComboboxSelected>>', self.on_bitrate_change)
    
    def set_bitrate_selection(self):
        """Establecer la selección del bitrate basado en configuración guardada"""
        bitrate_map = {
            "Mantener bitrate original": "Mantener bitrate original",
            "32 kbps - Muy baja calidad": "32 kbps - Muy baja calidad",
            "40 kbps": "40 kbps",
            "48 kbps - Baja calidad": "48 kbps - Baja calidad",
            "56 kbps": "56 kbps",
            "64 kbps - Calidad aceptable": "64 kbps - Calidad aceptable",
            "80 kbps": "80 kbps",
            "96 kbps - Calidad media": "96 kbps - Calidad media",
            "112 kbps": "112 kbps",
            "128 kbps - Calidad estándar": "128 kbps - Calidad estándar",
            "144 kbps": "144 kbps",
            "160 kbps - Buena calidad": "160 kbps - Buena calidad",
            "176 kbps": "176 kbps",
            "192 kbps - Alta calidad": "192 kbps - Alta calidad",
            "224 kbps": "224 kbps",
            "256 kbps - Muy alta calidad": "256 kbps - Muy alta calidad",
            "288 kbps": "288 kbps",
            "320 kbps - Calidad máxima": "320 kbps - Calidad máxima",
            "Variable (VBR) - Balance calidad/tamaño": "Variable (VBR) - Balance calidad/tamaño",
            "Personalizado": "Personalizado"
        }
        
        # Buscar el texto correspondiente
        for display_text, stored_value in bitrate_map.items():
            if stored_value == self.last_bitrate:
                self.bitrate_combo.set(display_text)
                return
        
        # Si no se encuentra, usar "Mantener bitrate original" por defecto
        self.bitrate_combo.set("Mantener bitrate original")
    
    def create_silence_section(self, parent, row):
        """Crear sección para añadir silencio"""
        silence_frame = ttk.LabelFrame(parent, text="Añadir Silencio", padding="10")
        silence_frame.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Inicio
        ttk.Label(silence_frame, text="Al inicio:").grid(row=0, column=0, sticky=tk.W)
        
        start_frame = ttk.Frame(silence_frame)
        start_frame.grid(row=0, column=1, sticky=tk.W, padx=(5, 20))
        
        self.start_seconds = ttk.Spinbox(start_frame, from_=0, to=3600, 
                                        width=6, increment=1)
        self.start_seconds.insert(0, "0")
        self.start_seconds.pack(side=tk.LEFT)
        ttk.Label(start_frame, text="seg").pack(side=tk.LEFT, padx=(2, 5))
        
        self.start_millis = ttk.Spinbox(start_frame, from_=0, to=999, 
                                       width=5, increment=1)
        self.start_millis.insert(0, "0")
        self.start_millis.pack(side=tk.LEFT)
        ttk.Label(start_frame, text="ms").pack(side=tk.LEFT, padx=(2, 0))
        
        # Final
        ttk.Label(silence_frame, text="Al final:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        
        end_frame = ttk.Frame(silence_frame)
        end_frame.grid(row=0, column=3, sticky=tk.W)
        
        self.end_seconds = ttk.Spinbox(end_frame, from_=0, to=3600, 
                                      width=6, increment=1)
        self.end_seconds.insert(0, "0")
        self.end_seconds.pack(side=tk.LEFT)
        ttk.Label(end_frame, text="seg").pack(side=tk.LEFT, padx=(2, 5))
        
        self.end_millis = ttk.Spinbox(end_frame, from_=0, to=999, 
                                     width=5, increment=1)
        self.end_millis.insert(0, "0")
        self.end_millis.pack(side=tk.LEFT)
        ttk.Label(end_frame, text="ms").pack(side=tk.LEFT, padx=(2, 0))
    
    def create_buttons_section(self, parent, row):
        """Crear sección de botones"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=4, pady=(15, 0))
        
        self.process_btn = ttk.Button(button_frame, text="Procesar Todos", 
                  command=self.process_all_files, 
                  style='Accent.TButton', width=15)
        self.process_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Calcular Tamaños", 
                  command=self.calculate_all_sizes, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Abrir Carpeta Salida", 
                  command=self.open_output_folder, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Salir", 
                  command=self.on_exit, width=10).pack(side=tk.LEFT)
    
    # ===== MÉTODOS PARA MANEJO DE ARCHIVOS =====
    
    def add_files(self):
        """Añadir múltiples archivos MP3"""
        filenames = filedialog.askopenfilenames(
            title="Seleccionar archivos MP3",
            filetypes=[("Archivos MP3", "*.mp3"), ("Todos los archivos", "*.*")]
        )
        
        if filenames:
            for filename in filenames:
                if filename not in self.current_files:
                    self.current_files.append(filename)
                    self.add_file_to_tree(filename)
            
            self.update_file_count()
            self.update_status(f"✓ Añadidos {len(filenames)} archivos")
    
    def add_folder(self):
        """Añadir todos los archivos MP3 de una carpeta"""
        folder = filedialog.askdirectory(title="Seleccionar carpeta con archivos MP3")
        
        if folder:
            mp3_files = []
            for ext in ['*.mp3', '*.MP3']:
                mp3_files.extend(Path(folder).rglob(ext))
            
            added_count = 0
            for mp3_file in mp3_files:
                filename = str(mp3_file)
                if filename not in self.current_files:
                    self.current_files.append(filename)
                    self.add_file_to_tree(filename)
                    added_count += 1
            
            self.update_file_count()
            self.update_status(f"✓ Añadidos {added_count} archivos de la carpeta")
    
    def clear_files(self):
        """Limpiar lista de archivos"""
        if self.current_files:
            if messagebox.askyesno("Confirmar", "¿Estás seguro de que quieres limpiar la lista de archivos?"):
                self.current_files.clear()
                for item in self.files_tree.get_children():
                    self.files_tree.delete(item)
                self.update_file_count()
                self.update_status("✓ Lista de archivos limpiada")
    
    def add_file_to_tree(self, filename):
        """Añadir archivo al Treeview con información básica"""
        try:
            # Obtener información básica del archivo
            file_size = os.path.getsize(filename)
            size_str = f"{file_size / 1024 / 1024:.2f} MB"
            
            # Intentar obtener duración con ffprobe
            duration_str = "Desconocida"
            bitrate_str = "Desconocido"
            
            try:
                cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                      '-show_format', '-show_streams', filename]
                
                if os.path.exists("ffprobe.exe"):
                    cmd[0] = "ffprobe.exe"
                
                # Usar shell=True para Windows
                result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                if result.returncode == 0:
                    info = json.loads(result.stdout)
                    format_info = info.get('format', {})
                    
                    duration = float(format_info.get('duration', 0))
                    mins, secs = divmod(duration, 60)
                    duration_str = f"{int(mins)}:{int(secs):02d}"
                    
                    bitrate = int(format_info.get('bit_rate', 0))
                    bitrate_str = f"{bitrate / 1000:.0f} kbps"
            except Exception as e:
                print(f"Error obteniendo metadatos: {e}")
            
            # Añadir al treeview
            self.files_tree.insert('', 'end', values=(
                os.path.basename(filename),
                size_str,
                duration_str,
                bitrate_str,
                os.path.dirname(filename)
            ))
            
        except Exception as e:
            self.update_status(f"✗ Error al añadir archivo: {str(e)}")
    
    def update_file_count(self):
        """Actualizar contador de archivos"""
        count = len(self.current_files)
        self.file_count_label.config(text=f"{count} archivo{'s' if count != 1 else ''} seleccionado{'s' if count != 1 else ''}")
    
    # ===== MÉTODOS PARA CONFIGURACIÓN DE SALIDA =====
    
    def select_output_folder(self):
        """Seleccionar carpeta de salida personalizada"""
        folder = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if folder:
            self.output_folder.set(folder)
    
    def show_name_pattern_help(self):
        """Mostrar ayuda sobre el patrón de nombres"""
        help_text = """Variables disponibles en el patrón de nombre:

{filename} - Nombre original sin extensión
{ext} - Extensión del archivo (.mp3)
{bitrate} - Bitrate objetivo
{date} - Fecha actual (YYYY-MM-DD)
{time} - Hora actual (HH-MM-SS)
{counter} - Número secuencial (01, 02, etc.)
{artist} - Artista del archivo (si está disponible)
{title} - Título del archivo (si está disponible)

Ejemplos:
{filename}_editado → archivo_editado.mp3
{filename}_{bitrate}kbps → archivo_128kbps.mp3
{filename}_{date} → archivo_2024-01-15.mp3
{filename}_{counter} → archivo_01.mp3
"""
        messagebox.showinfo("Ayuda - Patrón de Nombres", help_text)
    
    def generate_output_filename(self, input_file: str, index: int, total: int) -> str:
        """Generar nombre de archivo de salida basado en el patrón"""
        pattern = self.name_pattern.get()
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        ext = os.path.splitext(input_file)[1]
        
        # Obtener información adicional del archivo si es posible
        artist = "Unknown"
        title = "Unknown"
        
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                  '-show_format', input_file]
            
            if os.path.exists("ffprobe.exe"):
                cmd[0] = "ffprobe.exe"
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                tags = info.get('format', {}).get('tags', {})
                artist = tags.get('artist', 'Unknown')
                title = tags.get('title', 'Unknown')
        except:
            pass
        
        # Reemplazar variables en el patrón
        now = datetime.now()
        
        # Obtener bitrate para el nombre del archivo
        bitrate_str = self.get_target_bitrate()
        bitrate_display = "original" if bitrate_str == "original" else bitrate_str.replace('k', '') + "kbps"
        
        replacements = {
            '{filename}': base_name,
            '{ext}': ext,
            '{bitrate}': bitrate_display,
            '{date}': now.strftime('%Y-%m-%d'),
            '{time}': now.strftime('%H-%M-%S'),
            '{counter}': f"{index + 1:02d}",
            '{total}': f"{total:02d}",
            '{artist}': re.sub(r'[^\w\-_\. ]', '_', artist),
            '{title}': re.sub(r'[^\w\-_\. ]', '_', title)
        }
        
        output_name = pattern
        for key, value in replacements.items():
            output_name = output_name.replace(key, str(value))
        
        # Asegurar que el nombre sea válido
        output_name = re.sub(r'[^\w\-_\. ]', '_', output_name)
        
        # Añadir extensión si no la tiene
        if not output_name.endswith('.mp3'):
            output_name += '.mp3'
        
        return output_name
    
    def get_output_path(self, input_file: str, index: int, total: int) -> str:
        """Obtener ruta completa de salida para un archivo"""
        # Determinar carpeta de salida
        output_dir = self.output_folder.get()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(input_file)
        
        # Si se mantiene estructura de carpetas
        if self.preserve_folder_var.get():
            # Obtener ruta relativa si hay archivos en diferentes carpetas
            if len(self.current_files) > 1:
                try:
                    common_path = os.path.commonpath([os.path.dirname(f) for f in self.current_files])
                    rel_path = os.path.relpath(os.path.dirname(input_file), common_path)
                    output_dir = os.path.join(output_dir, rel_path)
                except:
                    pass
            os.makedirs(output_dir, exist_ok=True)
        
        # Generar nombre de archivo
        filename = self.generate_output_filename(input_file, index, total)
        
        # Verificar si ya existe y manejar sobreescritura
        output_path = os.path.join(output_dir, filename)
        
        if os.path.exists(output_path) and not self.overwrite_var.get():
            # Añadir sufijo único
            base, ext = os.path.splitext(output_path)
            counter = 1
            while os.path.exists(f"{base}_{counter}{ext}"):
                counter += 1
            output_path = f"{base}_{counter}{ext}"
        
        return output_path
    
    # ===== MÉTODOS DE PROCESAMIENTO =====
    
    def process_all_files(self):
        """Procesar todos los archivos en la lista"""
        if not self.current_files:
            messagebox.showerror("Error", "No hay archivos para procesar.")
            return
        
        if self.processing:
            messagebox.showwarning("Advertencia", "Ya hay un proceso en ejecución.")
            return
        
        # Confirmar
        file_count = len(self.current_files)
        confirm_msg = f"¿Estás seguro de que quieres procesar {file_count} archivo{'s' if file_count != 1 else ''}?"
        
        if not messagebox.askyesno("Confirmar", confirm_msg):
            return
        
        # Guardar configuración antes de procesar
        self.save_config()
        
        # Iniciar procesamiento
        self.processing = True
        self.process_btn.config(state='disabled')
        self.update_status(f"Iniciando procesamiento de {file_count} archivos...")
        
        thread = threading.Thread(target=self._process_all_files_thread)
        thread.daemon = True
        thread.start()
    
    def _process_all_files_thread(self):
        """Hilo para procesar todos los archivos"""
        try:
            total_files = len(self.current_files)
            success_count = 0
            error_count = 0
            
            for i, input_file in enumerate(self.current_files):
                if not os.path.exists(input_file):
                    self.output_queue.put(("warning", f"Archivo no encontrado: {input_file}"))
                    error_count += 1
                    continue
                
                # Procesar archivo individual
                output_file = self.get_output_path(input_file, i, total_files)
                result = self._process_single_file(input_file, output_file)
                
                if result:
                    success_count += 1
                    self.update_status(f"Procesando... ({i+1}/{total_files}) - {os.path.basename(input_file)}")
                else:
                    error_count += 1
            
            # Proceso completado
            if success_count > 0:
                self.output_queue.put(("success", 
                    f"¡Procesamiento completado!\n\n"
                    f"Archivos procesados exitosamente: {success_count}\n"
                    f"Archivos con error: {error_count}\n\n"
                    f"Los archivos se han guardado en la carpeta de salida."))
            else:
                self.output_queue.put(("error", 
                    f"No se pudo procesar ningún archivo. Revisa los mensajes de error."))
                
        except Exception as e:
            self.output_queue.put(("error", f"Error inesperado: {str(e)}"))
        finally:
            self.processing = False
            self.process_btn.config(state='normal')
    
    def _process_single_file(self, input_file: str, output_file: str) -> bool:
        """Procesar un solo archivo MP3"""
        try:
            # Calcular duración de silencio
            start_sec = float(self.start_seconds.get() or 0)
            start_ms = float(self.start_millis.get() or 0) / 1000
            end_sec = float(self.end_seconds.get() or 0)
            end_ms = float(self.end_millis.get() or 0) / 1000
            
            silence_start = start_sec + start_ms
            silence_end = end_sec + end_ms
            
            # Obtener bitrate objetivo
            bitrate_str = self.get_target_bitrate()
            
            # Determinar qué ffmpeg usar
            ffmpeg_cmd = "ffmpeg.exe" if os.path.exists("ffmpeg.exe") else "ffmpeg"
            
            # Crear carpeta de salida si no existe
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Si el bitrate es "original", obtener el bitrate original del archivo
            if bitrate_str == "original":
                original_bitrate = self.get_original_bitrate(input_file)
                if original_bitrate:
                    # Convertir a formato de FFmpeg (kbps)
                    bitrate_str = f"{original_bitrate // 1000}k"
                else:
                    bitrate_str = "128k"
            
            # Construir comando base
            cmd_base = [ffmpeg_cmd, '-i', input_file, '-c:a', 'libmp3lame']
            
            # Configurar bitrate
            if bitrate_str != "vbr":
                cmd_base.extend(['-b:a', bitrate_str])
            else:
                cmd_base.extend(['-q:a', '2'])
            
            # Preservar metadatos si está marcado
            if self.preserve_meta.get():
                cmd_base.extend(['-map_metadata', '0', '-id3v2_version', '3'])
            
            # Procesar silencio al inicio si es necesario
            temp_files = []
            current_input = input_file
            
            if silence_start > 0:
                temp_silence = os.path.join(os.path.dirname(input_file), 
                                          f"temp_silence_start_{os.path.basename(input_file)}.mp3")
                temp_files.append(temp_silence)
                
                # Crear archivo de silencio
                silence_cmd = [
                    ffmpeg_cmd, '-f', 'lavfi',
                    '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                    '-t', str(silence_start),
                    '-c:a', 'libmp3lame',
                    '-q:a', '2',
                    temp_silence,
                    '-y'
                ]
                
                result = subprocess.run(silence_cmd, capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    self.output_queue.put(("warning", f"Error al crear silencio inicial para {os.path.basename(input_file)}"))
                    return False
                
                # Combinar silencio + audio original
                temp_combined = os.path.join(os.path.dirname(input_file),
                                          f"temp_combined_{os.path.basename(input_file)}.mp3")
                temp_files.append(temp_combined)
                
                combine_cmd = [
                    ffmpeg_cmd, '-i', temp_silence, '-i', current_input,
                    '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1',
                    '-c:a', 'libmp3lame'
                ]
                
                if bitrate_str != "vbr":
                    combine_cmd.extend(['-b:a', bitrate_str])
                else:
                    combine_cmd.extend(['-q:a', '2'])
                
                if self.preserve_meta.get():
                    combine_cmd.extend(['-map_metadata', '1', '-id3v2_version', '3'])
                
                combine_cmd.append(temp_combined)
                combine_cmd.append('-y')
                
                result = subprocess.run(combine_cmd, capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    self.output_queue.put(("warning", f"Error al combinar silencio inicial para {os.path.basename(input_file)}"))
                    return False
                
                current_input = temp_combined
            
            # Procesar silencio al final si es necesario
            if silence_end > 0:
                temp_silence_end = os.path.join(os.path.dirname(input_file),
                                              f"temp_silence_end_{os.path.basename(input_file)}.mp3")
                temp_files.append(temp_silence_end)
                
                # Crear silencio para el final
                silence_cmd = [
                    ffmpeg_cmd, '-f', 'lavfi',
                    '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                    '-t', str(silence_end),
                    '-c:a', 'libmp3lame',
                    '-q:a', '2',
                    temp_silence_end,
                    '-y'
                ]
                
                result = subprocess.run(silence_cmd, capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    self.output_queue.put(("warning", f"Error al crear silencio final para {os.path.basename(input_file)}"))
                    return False
                
                # Combinar audio actual + silencio final
                final_cmd = [
                    ffmpeg_cmd, '-i', current_input, '-i', temp_silence_end,
                    '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1',
                    '-c:a', 'libmp3lame'
                ]
                
                if bitrate_str != "vbr":
                    final_cmd.extend(['-b:a', bitrate_str])
                else:
                    final_cmd.extend(['-q:a', '2'])
                
                if self.preserve_meta.get():
                    final_cmd.extend(['-map_metadata', '0', '-id3v2_version', '3'])
                
                final_cmd.append(output_file)
                final_cmd.append('-y')
                
                result = subprocess.run(final_cmd, capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    self.output_queue.put(("warning", f"Error al combinar silencio final para {os.path.basename(input_file)}"))
                    return False
                
            else:
                # Solo cambiar bitrate (sin silencio final)
                cmd = cmd_base + [output_file, '-y']
                
                result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                if result.returncode != 0:
                    self.output_queue.put(("warning", f"Error al procesar {os.path.basename(input_file)}"))
                    return False
            
            # Limpiar archivos temporales
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            
            # Eliminar archivo temporal intermedio si existe
            if current_input != input_file and os.path.exists(current_input):
                try:
                    os.remove(current_input)
                except:
                    pass
            
            return True
            
        except Exception as e:
            self.output_queue.put(("warning", f"Error procesando {os.path.basename(input_file)}: {str(e)}"))
            return False
    
    def get_original_bitrate(self, input_file):
        """Obtener el bitrate original de un archivo MP3"""
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                  '-show_format', input_file]
            
            if os.path.exists("ffprobe.exe"):
                cmd[0] = "ffprobe.exe"
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                format_info = info.get('format', {})
                bitrate = int(format_info.get('bit_rate', 128000))
                return bitrate
        except:
            pass
        return None
    
    def calculate_all_sizes(self):
        """Calcular tamaños estimados para todos los archivos"""
        if not self.current_files:
            messagebox.showinfo("Información", "No hay archivos para calcular.")
            return
        
        total_original = 0
        total_estimated = 0
        
        for input_file in self.current_files:
            if os.path.exists(input_file):
                try:
                    # Obtener información del archivo
                    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                          '-show_format', input_file]
                    
                    if os.path.exists("ffprobe.exe"):
                        cmd[0] = "ffprobe.exe"
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                    if result.returncode == 0:
                        info = json.loads(result.stdout)
                        format_info = info.get('format', {})
                        
                        duration = float(format_info.get('duration', 0))
                        original_bitrate = int(format_info.get('bit_rate', 128000))
                        
                        # Calcular duración adicional
                        start_sec = float(self.start_seconds.get() or 0)
                        start_ms = float(self.start_millis.get() or 0) / 1000
                        end_sec = float(self.end_seconds.get() or 0)
                        end_ms = float(self.end_millis.get() or 0) / 1000
                        total_additional = start_sec + start_ms + end_sec + end_ms
                        total_duration = duration + total_additional
                        
                        # Obtener bitrate objetivo
                        bitrate_str = self.get_target_bitrate()
                        target_bitrate = self.parse_bitrate(bitrate_str, original_bitrate)
                        
                        # Calcular tamaños
                        original_size = (original_bitrate * duration) / 8
                        estimated_size = (target_bitrate * total_duration) / 8
                        
                        total_original += original_size
                        total_estimated += estimated_size
                except:
                    pass
        
        # Mostrar resultados
        total_original_mb = total_original / 1024 / 1024
        total_estimated_mb = total_estimated / 1024 / 1024
        difference_mb = total_estimated_mb - total_original_mb
        
        messagebox.showinfo("Cálculo de Tamaños",
                          f"Tamaño total original: {total_original_mb:.2f} MB\n"
                          f"Tamaño total estimado: {total_estimated_mb:.2f} MB\n"
                          f"Diferencia: {difference_mb:+.2f} MB\n\n"
                          f"({len(self.current_files)} archivos analizados)")
    
    # ===== MÉTODOS HEREDADOS/COMPATIBLES =====
    
    def on_bitrate_change(self, event):
        """Manejar cambio en la selección de bitrate"""
        selection = self.bitrate_combo.get()
        
        if "Personalizado" in selection:
            self.custom_frame.grid()
        else:
            self.custom_frame.grid_remove()
    
    def get_target_bitrate(self):
        """Obtener el bitrate objetivo basado en la selección"""
        selection = self.bitrate_combo.get()
        
        bitrate_map = {
            "Mantener bitrate original": "original",
            "32 kbps - Muy baja calidad": "32k",
            "40 kbps": "40k",
            "48 kbps - Baja calidad": "48k", 
            "56 kbps": "56k",
            "64 kbps - Calidad aceptable": "64k",
            "80 kbps": "80k",
            "96 kbps - Calidad media": "96k",
            "112 kbps": "112k",
            "128 kbps - Calidad estándar": "128k",
            "144 kbps": "144k",
            "160 kbps - Buena calidad": "160k",
            "176 kbps": "176k",
            "192 kbps - Alta calidad": "192k",
            "224 kbps": "224k",
            "256 kbps - Muy alta calidad": "256k",
            "288 kbps": "288k",
            "320 kbps - Calidad máxima": "320k",
            "Variable (VBR) - Balance calidad/tamaño": "vbr",
            "Personalizado": "custom"
        }
        
        if selection in bitrate_map:
            if bitrate_map[selection] == "custom":
                custom_val = self.custom_bitrate.get().strip()
                if custom_val:
                    # Asegurar que termina con 'k'
                    if not custom_val.endswith('k'):
                        custom_val += 'k'
                    return custom_val
                else:
                    return "128k"
            else:
                return bitrate_map[selection]
        
        return "original"
    
    def parse_bitrate(self, bitrate_str, original_bitrate=128000):
        """Parsear string de bitrate a bps"""
        if bitrate_str == "vbr":
            # Para previsualización, usar un valor promedio
            return 128000
        elif bitrate_str == "original":
            return original_bitrate
        
        match = re.search(r'(\d+)', bitrate_str)
        if match:
            return int(match.group(1)) * 1000
        
        return 128000
    
    def open_output_folder(self):
        """Abrir la carpeta de salida"""
        folder = self.output_folder.get()
        if not folder or not os.path.exists(folder):
            if self.current_files:
                folder = os.path.dirname(self.current_files[0])
            else:
                messagebox.showinfo("Información", "No hay carpeta de salida definida.")
                return
        
        try:
            if platform.system() == "Windows":
                os.startfile(folder)
            elif platform.system() == "Darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {e}")
    
    def update_status(self, message):
        """Actualizar barra de estado"""
        self.status_label.config(text=message)
        if message.startswith("✓"):
            self.status_label.config(foreground='green')
        elif message.startswith("✗") or "Error" in message:
            self.status_label.config(foreground='red')
        elif message.startswith("⚠"):
            self.status_label.config(foreground='orange')
        else:
            self.status_label.config(foreground='black')
    
    def log(self, message):
        """Método de log para compatibilidad"""
        self.update_status(message)
    
    def show_warning(self, message):
        """Mostrar advertencia"""
        messagebox.showwarning("Advertencia", message)
        self.update_status(f"⚠ {message}")
    
    def on_exit(self):
        """Manejar salida de la aplicación"""
        self.save_config()
        self.root.destroy()
    
    def process_output_queue(self):
        """Procesar mensajes en la cola de salida"""
        try:
            while True:
                msg_type, content = self.output_queue.get_nowait()
                
                if msg_type == "success":
                    messagebox.showinfo("Éxito", content)
                    self.update_status("✓ Procesamiento completado")
                    
                elif msg_type == "error":
                    messagebox.showerror("Error", content)
                    self.update_status(f"✗ Error: {content[:50]}...")
                    
                elif msg_type == "warning":
                    self.update_status(f"⚠ {content[:60]}...")
                    
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_output_queue)


def main():
    """Función principal"""
    try:
        # Si tkinterDnD está disponible, usarlo
        if TKINTERDND_AVAILABLE:
            from tkinterdnd2 import TkinterDnD
            root = TkinterDnD.Tk()
        else:
            root = tk.Tk()
            
        app = MP3Editor(root)
        root.mainloop()
    except Exception as e:
        print(f"Error crítico: {e}")
        input("Presiona Enter para salir...")


if __name__ == "__main__":
    main()
