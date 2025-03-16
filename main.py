import sys
import pyperclip
import ollama
import keyboard
import time
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, QLineEdit, 
                            QPushButton, QVBoxLayout, QHBoxLayout, QWidget, 
                            QLabel, QFrame, QSplitter, QTabWidget, QComboBox,
                            QAction, QMenu, QShortcut, QSystemTrayIcon, QToolButton)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QSize
from PyQt5.QtGui import QFont, QIcon, QColor, QPalette, QKeySequence, QPixmap
import pyautogui
import pytesseract
from PIL import Image, ImageGrab

class OllamaThread(QThread):
    response_ready = pyqtSignal(str)
    
    def __init__(self, prompt, code_context="", system_prompt=""):
        super().__init__()
        self.prompt = prompt
        self.code_context = code_context
        self.system_prompt = system_prompt
        
    def run(self):
        try:
            messages = []
            
            # Add system prompt if provided
            if self.system_prompt:
                messages.append({'role': 'system', 'content': self.system_prompt})
            
            # Prepare the user message with context
            full_prompt = f"Code context:\n```python\n{self.code_context}\n```\n\nUser request: {self.prompt}"
            messages.append({'role': 'user', 'content': full_prompt})
            
            # Call Ollama API
            response = ollama.chat(
                model='deepseek-coder-v2:latest',
                messages=messages
            )
            
            response_text = response['message']['content']
            self.response_ready.emit(response_text)
        except Exception as e:
            self.response_ready.emit(f"Error: {str(e)}")

class CodeGenerationThread(QThread):
    response_ready = pyqtSignal(str)
    
    def __init__(self, prompt, system_prompt=""):
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt
        
    def run(self):
        try:
            messages = []
            
            # Add system prompt if provided
            if self.system_prompt:
                messages.append({'role': 'system', 'content': self.system_prompt})
            
            # Add the user prompt for code generation
            messages.append({'role': 'user', 'content': f"Generate code for: {self.prompt}"})
            
            # Call Ollama API
            response = ollama.chat(
                model='deepseek-coder-v2:latest',
                messages=messages
            )
            
            response_text = response['message']['content']
            self.response_ready.emit(response_text)
        except Exception as e:
            self.response_ready.emit(f"Error: {str(e)}")

class ScreenMonitorThread(QThread):
    code_detected = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.last_selection = ""
    
    def run(self):
        while self.running:
            try:
                # Check for selection
                selected_text = self.get_selected_text()
                if selected_text and selected_text != self.last_selection and self.is_code(selected_text):
                    self.last_selection = selected_text
                    self.code_detected.emit(selected_text)
                    time.sleep(1)  # Avoid rapid-fire detections
                else:
                    time.sleep(0.5)
            except Exception as e:
                print(f"Screen monitoring error: {str(e)}")
                time.sleep(1)
    
    def get_selected_text(self):
        # First try to get from clipboard (most reliable)
        try:
            # Simulate Ctrl+C to copy selected text
            keyboard.send('ctrl+c')
            time.sleep(0.1)  # Give system time to process
            return pyperclip.paste()
        except:
            pass
            
        # Fallback to OCR for selected regions
        try:
            # If there's a visible selection, attempt to capture it via screenshot + OCR
            selection = self.capture_selection()
            if selection:
                return selection
        except:
            pass
            
        return ""
    
    def is_code(self, text):
        # Simple heuristic to detect if text might be code
        code_indicators = ['def ', 'class ', 'import ', 'from ', '    ', '\t', ';', '==', '+=', '-=', '>=', '<=']
        return any(indicator in text for indicator in code_indicators)
    
    def capture_selection(self):
        # This is a simplified version - would need OS-specific enhancements
        try:
            # Try to find a selection (highlighted text)
            # This is a placeholder - actual implementation would be more complex
            screenshot = ImageGrab.grab()
            # Would need image processing to detect highlighted areas
            # For now, this is a simplified placeholder
            return ""
        except:
            return ""
    
    def stop(self):
        self.running = False

class VivirAICoder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VivirAI Coder")
        self.setGeometry(100, 100, 800, 700)
        
        # Make window resizable but stay on top
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        
        # Set modern dark theme inspired by Cursor
        self.apply_cursor_theme()
        
        # Initialize system tray
        self.setup_system_tray()
        
        # Initialize screen monitoring
        self.start_screen_monitoring()
        
        # Initialize UI
        self.init_ui()
        
        # Setup global shortcuts
        self.setup_global_shortcuts()
        
        # System prompt for consistent responses
        self.system_prompt = """You are a coding assistant. 
        Your primary role is to help with code improvements, bug fixes, and writing new code.
        Always provide well-documented, efficient code. 
        For code improvements, clearly explain what you changed and why.
        For bug fixes, explain the issue and your solution. 
        For new code, provide complete implementations with comments."""
    
    def apply_cursor_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Segoe UI', 'SF Pro Text', sans-serif;
            }
            QTextEdit, QLineEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'SF Mono', monospace;
                font-size: 14px;
                selection-background-color: #264f78;
            }
            QTabWidget::pane {
                border: 1px solid #3E3E42;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #252526;
                border-bottom: 2px solid #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #00559B;
            }
            QPushButton:disabled {
                background-color: #3a3d41;
                color: #848484;
            }
            QLabel {
                color: #d4d4d4;
                font-weight: bold;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
                min-height: 30px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 1px;
                border-left-color: #3E3E42;
                border-left-style: solid;
            }
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #5a5a5a;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                padding: 5px;
            }
            QToolButton:hover {
                background-color: #3e3e42;
                border-radius: 4px;
            }
        """)
    
    def init_ui(self):
        # Main layout with tabs
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.assistant_tab = QWidget()
        self.code_gen_tab = QWidget()
        
        self.setup_assistant_tab()
        self.setup_code_gen_tab()
        
        self.tab_widget.addTab(self.assistant_tab, "Code Assistant")
        self.tab_widget.addTab(self.code_gen_tab, "Code Generator")
        
        self.setCentralWidget(self.tab_widget)
        
        # Create menu bar
        self.setup_menu_bar()
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def setup_assistant_tab(self):
        # Main layout
        layout = QVBoxLayout()
        
        # Header with logo
        header = QHBoxLayout()
        logo_label = QLabel("✨ VivirAI Coder")
        logo_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.addWidget(logo_label)
        
        # Add model selector
        model_label = QLabel("Model:")
        self.model_selector = QComboBox()
        self.model_selector.addItems(["deepseek-coder-v2", "codellama", "mistral"])
        header.addWidget(model_label)
        header.addWidget(self.model_selector)
        
        header.addStretch()
        layout.addLayout(header)
        
        # Splitter for code and output
        splitter = QSplitter(Qt.Vertical)
        
        # Input area (top)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        
        # Code context
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.StyledPanel)
        input_layout_inner = QVBoxLayout(input_frame)
        
        input_header = QHBoxLayout()
        input_label = QLabel("Code Context")
        input_header.addWidget(input_label)
        
        refresh_button = QPushButton("Refresh")
        refresh_button.setMaximumWidth(100)
        refresh_button.clicked.connect(self.refresh_from_clipboard)
        input_header.addWidget(refresh_button)
        input_layout_inner.addLayout(input_header)
        
        self.code_context = QTextEdit()
        self.code_context.setMinimumHeight(200)
        self.code_context.setPlaceholderText("Code will appear here when you select text in your editor...")
        input_layout_inner.addWidget(self.code_context)
        
        # Prompt input
        prompt_label = QLabel("What would you like to do with this code?")
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("E.g., 'Optimize this function' or 'Fix the bugs'...")
        self.prompt_input.returnPressed.connect(self.get_assistance)
        
        input_layout_inner.addWidget(prompt_label)
        input_layout_inner.addWidget(self.prompt_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.get_help_button = QPushButton("Get Assistance")
        self.get_help_button.clicked.connect(self.get_assistance)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_fields)
        
        button_layout.addWidget(self.get_help_button)
        button_layout.addWidget(self.clear_button)
        input_layout_inner.addLayout(button_layout)
        
        input_layout.addWidget(input_frame)
        
        # Output area (bottom)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        
        output_frame = QFrame()
        output_frame.setFrameShape(QFrame.StyledPanel)
        output_layout_inner = QVBoxLayout(output_frame)
        
        output_header = QHBoxLayout()
        output_label = QLabel("AI Suggestions")
        output_header.addWidget(output_label)
        output_layout_inner.addLayout(output_header)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(200)
        self.output_text.setPlaceholderText("AI suggestions will appear here...")
        output_layout_inner.addWidget(self.output_text)
        
        # Action buttons
        action_layout = QHBoxLayout()
        self.copy_button = QPushButton("Copy Code")
        self.copy_button.clicked.connect(self.copy_code)
        self.copy_all_button = QPushButton("Copy All")
        self.copy_all_button.clicked.connect(self.copy_all)
        self.apply_button = QPushButton("Apply to Editor")
        self.apply_button.clicked.connect(self.apply_to_editor)
        
        action_layout.addWidget(self.copy_button)
        action_layout.addWidget(self.copy_all_button)
        action_layout.addWidget(self.apply_button)
        output_layout_inner.addLayout(action_layout)
        
        output_layout.addWidget(output_frame)
        
        # Add both to splitter
        splitter.addWidget(input_widget)
        splitter.addWidget(output_widget)
        
        # Set initial sizes
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
        
        # Set the layout
        self.assistant_tab.setLayout(layout)
    
    def setup_code_gen_tab(self):
        # Main layout for code generation tab
        layout = QVBoxLayout()
        
        # Header
        header = QHBoxLayout()
        gen_label = QLabel("🚀 Code Generator")
        gen_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.addWidget(gen_label)
        header.addStretch()
        layout.addLayout(header)
        
        # Splitter for input and output
        splitter = QSplitter(Qt.Vertical)
        
        # Input area (top)
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        
        input_frame = QFrame()
        input_frame.setFrameShape(QFrame.StyledPanel)
        input_layout_inner = QVBoxLayout(input_frame)
        
        prompt_label = QLabel("What code would you like me to generate?")
        self.gen_prompt = QTextEdit()
        self.gen_prompt.setMinimumHeight(100)
        self.gen_prompt.setPlaceholderText("Describe the code you need in detail. For example: 'Create a function that sorts a list of dictionaries by a specific key' or 'Write a class for managing a simple inventory system'...")
        
        input_layout_inner.addWidget(prompt_label)
        input_layout_inner.addWidget(self.gen_prompt)
        
        # Options
        options_layout = QHBoxLayout()
        
        language_label = QLabel("Language:")
        self.language_selector = QComboBox()
        self.language_selector.addItems(["Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "PHP", "Ruby"])
        self.language_selector.setCurrentText("Python")
        
        options_layout.addWidget(language_label)
        options_layout.addWidget(self.language_selector)
        options_layout.addStretch()
        
        input_layout_inner.addLayout(options_layout)
        
        # Generate button
        self.generate_button = QPushButton("Generate Code")
        self.generate_button.clicked.connect(self.generate_code)
        input_layout_inner.addWidget(self.generate_button)
        
        input_layout.addWidget(input_frame)
        
        # Output area (bottom)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        
        output_frame = QFrame()
        output_frame.setFrameShape(QFrame.StyledPanel)
        output_layout_inner = QVBoxLayout(output_frame)
        
        output_label = QLabel("Generated Code")
        self.gen_output = QTextEdit()
        self.gen_output.setReadOnly(True)
        self.gen_output.setMinimumHeight(200)
        self.gen_output.setPlaceholderText("Generated code will appear here...")
        
        output_layout_inner.addWidget(output_label)
        output_layout_inner.addWidget(self.gen_output)
        
        # Action buttons
        action_layout = QHBoxLayout()
        self.gen_copy_button = QPushButton("Copy Code")
        self.gen_copy_button.clicked.connect(self.copy_generated_code)
        self.gen_insert_button = QPushButton("Insert at Cursor")
        self.gen_insert_button.clicked.connect(self.insert_at_cursor)
        
        action_layout.addWidget(self.gen_copy_button)
        action_layout.addWidget(self.gen_insert_button)
        output_layout_inner.addLayout(action_layout)
        
        output_layout.addWidget(output_frame)
        
        # Add both to splitter
        splitter.addWidget(input_widget)
        splitter.addWidget(output_widget)
        
        # Set initial sizes
        splitter.setSizes([300, 400])
        
        layout.addWidget(splitter)
        
        # Set the layout
        self.code_gen_tab.setLayout(layout)
    
    def setup_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        new_action = QAction('New Session', self)
        new_action.setShortcut('Ctrl+N')
        new_action.triggered.connect(self.clear_fields)
        file_menu.addAction(new_action)
        
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close_application)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu('Edit')
        
        copy_action = QAction('Copy', self)
        copy_action.setShortcut('Ctrl+C')
        copy_action.triggered.connect(self.copy_selection)
        edit_menu.addAction(copy_action)
        
        paste_action = QAction('Paste', self)
        paste_action.setShortcut('Ctrl+V')
        paste_action.triggered.connect(self.paste_clipboard)
        edit_menu.addAction(paste_action)
        
        # Settings menu
        settings_menu = menubar.addMenu('Settings')
        
        always_on_top = QAction('Always on Top', self)
        always_on_top.setCheckable(True)
        always_on_top.setChecked(True)
        always_on_top.triggered.connect(self.toggle_always_on_top)
        settings_menu.addAction(always_on_top)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_system_tray(self):
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("icon.png"))  # Replace with your icon
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        tray_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close_application)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    def setup_global_shortcuts(self):
        # Set up global shortcut for quick access
        self.shortcut_get_selected = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.shortcut_get_selected.activated.connect(self.get_selected_code)
        
        self.shortcut_toggle_visibility = QShortcut(QKeySequence("Ctrl+Shift+V"), self)
        self.shortcut_toggle_visibility.activated.connect(self.toggle_visibility)
    
    def start_screen_monitoring(self):
        self.screen_monitor = ScreenMonitorThread()
        self.screen_monitor.code_detected.connect(self.update_code_context)
        self.screen_monitor.start()
    
    def update_code_context(self, code):
        if code:
            self.code_context.setText(code)
            self.statusBar().showMessage("Code detected!", 3000)
    
    def get_selected_code(self):
        # Force a check for selected code
        keyboard.send('ctrl+c')
        time.sleep(0.1)
        selected_text = pyperclip.paste()
        
        if selected_text:
            self.code_context.setText(selected_text)
            self.show()
            self.raise_()
            self.activateWindow()
    
    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def get_assistance(self):
        prompt = self.prompt_input.text()
        code = self.code_context.toPlainText()
        
        if not prompt:
            self.statusBar().showMessage("Please enter a prompt")
            return
            
        self.statusBar().showMessage("Thinking...")
        self.get_help_button.setEnabled(False)
        
        # Start thread to call Ollama
        self.ollama_thread = OllamaThread(prompt, code, self.system_prompt)
        self.ollama_thread.response_ready.connect(self.update_response)
        self.ollama_thread.start()
    
    def update_response(self, response):
        self.output_text.setText(response)
        self.statusBar().showMessage("Ready")
        self.get_help_button.setEnabled(True)
    
    def generate_code(self):
        prompt = self.gen_prompt.toPlainText()
        language = self.language_selector.currentText()
        
        if not prompt:
            self.statusBar().showMessage("Please describe the code you need")
            return
        
        self.statusBar().showMessage("Generating code...")
        self.generate_button.setEnabled(False)
        
        # Enhance system prompt with language preference
        enhanced_prompt = f"{self.system_prompt}\nGenerate code in {language} programming language."
        
        # Start thread to generate code
        self.code_gen_thread = CodeGenerationThread(prompt, enhanced_prompt)
        self.code_gen_thread.response_ready.connect(self.update_generated_code)
        self.code_gen_thread.start()
    
    def update_generated_code(self, response):
        self.gen_output.setText(response)
        self.statusBar().showMessage("Code generated")
        self.generate_button.setEnabled(True)
    
    def copy_code(self):
        response = self.output_text.toPlainText()
        if response:
            # Extract code blocks if they exist
            if "```" in response:
                start = response.find("```") + 3
                # Skip the language identifier if present
                if not response[start:].startswith("\n"):
                    start = response.find("\n", start) + 1
                end = response.find("```", start)
                if end > start:
                    code_only = response[start:end].strip()
                    pyperclip.copy(code_only)
                    self.statusBar().showMessage("Code copied to clipboard!", 3000)
                    return
            
            # If no code block, copy the whole response
            pyperclip.copy(response)
            self.statusBar().showMessage("Response copied to clipboard!", 3000)
    
    def copy_all(self):
        response = self.output_text.toPlainText()
        if response:
            pyperclip.copy(response)
            self.statusBar().showMessage("Full response copied to clipboard!", 3000)
    
    def copy_generated_code(self):
        response = self.gen_output.toPlainText()
        if response:
            # Extract code blocks if they exist
            if "```" in response:
                start = response.find("```") + 3
                # Skip the language identifier if present
                if not response[start:].startswith("\n"):
                    start = response.find("\n", start) + 1
                end = response.find("```", start)
                if end > start:
                    code_only = response[start:end].strip()
                    pyperclip.copy(code_only)
                    self.statusBar().showMessage("Generated code copied to clipboard!", 3000)
                    return
            
            # If no code block, copy the whole response
            pyperclip.copy(response)
            self.statusBar().showMessage("Generated code copied to clipboard!", 3000)
    
    def apply_to_editor(self):
        # Extract code from response
        response = self.output_text.toPlainText()
        if not response:
            return
            
        # Get code from response
        code = ""
        if "```" in response:
            start = response.find("```") + 3
            # Skip the language identifier if present
            if not response[start:].startswith("\n"):
                start = response.find("\n", start) + 1
            end = response.find("```", start)
            if end > start:
                code = response[start:end].strip()
        else:
            code = response
        
        # Copy to clipboard
        pyperclip.copy(code)
        
        # Simulate paste at cursor position
        keyboard.send('ctrl+v')
        self.statusBar().showMessage("Code applied to editor", 3000)
    
    def insert_at_cursor(self):
        # Extract code from generated output
        response = self.gen_output.toPlainText()
        if not response:
            return
            
        # Get code from response
        code = ""
        if "```" in response:
            start = response.find("```") + 3
            # Skip the language identifier if present
            if not response[start:].startswith("\n"):
                start = response.find("\n", start) + 1
            end = response.find("```", start)
            if end > start:
                code = response[start:end].strip()
        else:
            code = response
        
        # Copy to clipboard
        pyperclip.copy(code)
        
        # Simulate paste at cursor position
        keyboard.send('ctrl+v')
        self.statusBar().showMessage("Code inserted at cursor", 3000)
    
    def refresh_from_clipboard(self):
        clipboard_content = pyperclip.paste()
        if clipboard_content:
            self.code_context.setText(clipboard_content)
            self.statusBar().showMessage("Code context updated from clipboard", 3000)
    
    def copy_selection(self):
        # Get the currently focused widget
        focused_widget = QApplication.focusWidget()
        
        # If it's a text edit widget, copy the selection
        if isinstance(focused_widget, QTextEdit) or isinstance(focused_widget, QLineEdit):
            focused_widget.copy()
    
    def paste_clipboard(self):
        # Get the currently focused widget
        focused_widget = QApplication.focusWidget()
        
        # If it's a text edit widget, paste from clipboard
        if isinstance(focused_widget, QTextEdit) or isinstance(focused_widget, QLineEdit):
            focused_widget.paste()
    
    def clear_fields(self):
        self.code_context.clear()
        self.prompt_input.clear()
        self.output_text.clear()
        self.gen_prompt.clear()
        self.gen_output.clear()
        self.statusBar().showMessage("Ready")
    
    def toggle_always_on_top(self, state):
        if state:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        else:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.show()
    
    def show_about(self):
        about_text = """
        <h2>VivirAI Coder</h2>
        <p>An AI-powered coding assistant.</p>
        <p>Version 1.0</p>
        <p>© 2025 VivirAI</p>
        """
        QMessageBox.about(self, "About VivirAI Coder", about_text)
    
    def close_application(self):
        # Stop the screen monitoring thread
        if hasattr(self, 'screen_monitor'):
            self.screen_monitor.stop()
            self.screen_monitor.wait()
        
        # Close the application
        self.close()
        QApplication.quit()
    
    def closeEvent(self, event):
        # Override close event to handle proper shutdown
        self.close_application()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for consistent look across platforms
    
    # Check if Ollama is running
    try:
        ollama.list()
        window = VivirAICoder()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        error_dialog = QMessageBox()
        error_dialog.setIcon(QMessageBox.Critical)
        error_dialog.setWindowTitle("Error")
        error_dialog.setText("Could not connect to Ollama")
        error_dialog.setInformativeText(f"Please make sure Ollama is installed and running.\n\nError: {str(e)}")
        error_dialog.setDetailedText("This application requires Ollama to be installed and running. Please visit https://ollama.ai to download and install Ollama.")
        error_dialog.exec_()
        sys.exit(1)
