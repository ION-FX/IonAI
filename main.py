import sys
import os
import markdown
from pynput import keyboard

from PyQt6.QtCore import (
    Qt, QThread, pyqtSlot, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit,
    QLineEdit, QHBoxLayout, QLabel, QFrame, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtGui import QColor, QFont, QTextCursor

# --- IMPORTS ---
from ai_worker import LocalAIWorker
import system_tools
from ion_overlay import ScreenAnnotationOverlay

SOCKET_NAME = "ORION_Socket_Instance"

HEIGHT_COLLAPSED = 350
HEIGHT_EXPANDED = 650

class HotkeyWorker(QThread):
    triggered = pyqtSignal()
    def run(self):
        with keyboard.GlobalHotKeys({'<ctrl>+<shift>': self.on_activate}) as h:
            h.join()
    def on_activate(self):
        self.triggered.emit()

class LauncherWindow(QWidget):
    request_ai_response = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("O.R.I.O.N")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.current_ai_response = ""
        self.ai_response_block_start = 0
        self.has_active_chat = False

        self.setup_ui()
        self.setup_ai_worker()
        self.setup_hotkey_worker()
        self.center_on_screen()

        self.hide()

    def setup_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: #1e1e1e;
                border: 1px solid #3daee9;
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setYOffset(8)
        self.container.setGraphicsEffect(shadow)

        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(15, 15, 15, 15)
        self.container_layout.setSpacing(10)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        self.brand_label = QLabel("ORION")
        self.brand_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.brand_label.setStyleSheet("color: #3daee9; margin-right: 10px;")
        header_layout.addWidget(self.brand_label)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Chat or Command...")
        self.input_box.setFont(QFont("Segoe UI", 12))
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #ffffff;
                padding-bottom: 2px;
                border-bottom: 1px solid #333;
            }
            QLineEdit:focus {
                border-bottom: 1px solid #3daee9;
            }
        """)
        self.input_box.returnPressed.connect(self.on_send_message)
        header_layout.addWidget(self.input_box)

        self.container_layout.addLayout(header_layout)

        # --- OUTPUT AREA ---
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Consolas", 11))
        self.chat_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #ccc;
            }
        """)
        # Start visible but empty
        self.container_layout.addWidget(self.chat_display)

        self.layout.addWidget(self.container)

        self.setFixedWidth(850)
        self.setFixedHeight(HEIGHT_COLLAPSED)
        self.screen_marker = ScreenAnnotationOverlay()

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() // 4)
        self.move(x, y)

    def toggle_visibility(self):
        if self.isVisible():
            # Just hide - DON'T clear anything
            self.hide()
        else:
            # Show window
            self.show()
            self.raise_()
            self.activateWindow()
            self.input_box.setFocus()
            self.input_box.selectAll()

            # If we have history, open expanded. Otherwise compact.
            if self.has_active_chat:
                self.set_height(HEIGHT_EXPANDED)
                self.scroll_to_bottom()
            else:
                self.set_height(HEIGHT_COLLAPSED)

    def set_height(self, target_height):
        """Animate to target height."""
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        start = self.geometry()
        end = QRect(start.x(), start.y(), start.width(), target_height)

        self.anim.setStartValue(start)
        self.anim.setEndValue(end)
        self.anim.start()

    def scroll_to_bottom(self):
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def setup_ai_worker(self):
        self.ai_thread = QThread()
        self.ai_worker = LocalAIWorker()
        self.ai_worker.moveToThread(self.ai_thread)
        self.ai_worker.streaming_chunk.connect(self.handle_streaming_chunk)
        self.ai_worker.generation_done.connect(self.handle_generation_done)
        self.ai_worker.error_occurred.connect(self.handle_error)
        self.ai_worker.tool_call_requested.connect(self.handle_tool_call)
        self.ai_worker.image_generated.connect(self.handle_image_generated)
        self.request_ai_response.connect(self.ai_worker.generate_response)
        self.ai_thread.start()

    def setup_hotkey_worker(self):
        self.hk_worker = HotkeyWorker()
        self.hk_worker.triggered.connect(self.toggle_visibility)
        self.hk_worker.start()

    def replace_tool_tags_with_icons(self):
        """Replace [[TOOL:ARGS]] with emoji icons + tooltips."""
        import re

        full_html = self.chat_display.toHtml()

        def icon_replacer(match):
            full_tag = match.group(0)  # [[RUN_APP:spotify]]
            content = match.group(1)   # RUN_APP:spotify

            # Default icon
            icon = "⚙️"

            # Map tool names to emojis
            if "TAKE_SCREENSHOT" in content: icon = "📸"
            elif "SEARCH_WEB" in content: icon = "🌐"
            elif "OPEN_URL" in content: icon = "🔗"
            elif "RUN_APP" in content: icon = "🚀"
            elif "GET_APP_LIST" in content: icon = "📂"
            elif "READ_FILE" in content: icon = "📄"
            elif "WRITE_FILE" in content: icon = "💾"
            elif "LIST_FILES" in content: icon = "📂"
            elif "ANNOTATE" in content: icon = "🖌️"
            elif "GET_SCREEN_SIZE" in content: icon = "📏"
            elif "MOUSE_CLICK" in content: icon = "🖱️"
            elif "KEYBOARD_TYPE" in content: icon = "⌨️"

            # Return styled span with tooltip
            return f'<span title="{full_tag}" style="font-size: 14px; cursor: help; background-color: #333; border-radius: 4px; padding: 2px 6px; margin: 0 2px;">{icon}</span>'

        # Replace all [[...]] patterns
        new_html = re.sub(r'\[\[(.*?)\]\]', icon_replacer, full_html)

        if new_html != full_html:
            # Preserve scroll position
            scroll_pos = self.chat_display.verticalScrollBar().value()
            self.chat_display.setHtml(new_html)
            self.chat_display.verticalScrollBar().setValue(scroll_pos)

    @pyqtSlot()
    def on_send_message(self):
        text = self.input_box.text().strip()
        if not text: return

        if text.lower() == "exit":
            QApplication.quit()
            return

        if text.lower() == "clear":
            # EXPLICIT CLEAR: Reset everything
            self.chat_display.clear()
            self.has_active_chat = False
            self.ai_worker.chat_history = [{'role': 'system', 'content': self.ai_worker.chat_history[0]['content']}] # Reset to system prompt only
            self.set_height(HEIGHT_COLLAPSED)
            return

        self.has_active_chat = True
        self.set_height(HEIGHT_EXPANDED)

        # USER MESSAGE
        self.chat_display.append(f"""
            <div style='margin-top: 15px; margin-bottom: 5px; color: #3daee9; font-weight: bold;'>
                You
            </div>
            <div style='color: #ffffff; margin-bottom: 15px;'>
                {text}
            </div>
        """)
        self.scroll_to_bottom()

        self.request_ai_response.emit(text)
        self.input_box.clear()

        # PREPARE AI BLOCK
        self.chat_display.append(f"""
            <div style='color: #50fa7b; font-weight: bold; margin-bottom: 5px;'>
                Orion
            </div>
        """)

        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
        self.ai_response_block_start = self.chat_display.textCursor().position()

    @pyqtSlot(str)
    def handle_streaming_chunk(self, chunk):
        self.current_ai_response += chunk
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.chat_display.ensureCursorVisible()

    @pyqtSlot()
    def handle_generation_done(self):
        if self.current_ai_response:
            html = markdown.markdown(self.current_ai_response, extensions=['fenced_code'])

            cursor = self.chat_display.textCursor()
            cursor.setPosition(self.ai_response_block_start)
            cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)

            styled_html = f"""
            <div style='color: #e0e0e0; line-height: 1.4;'>
                <style>
                    code {{ background-color: #2d2d2d; color: #f8f8f2; padding: 2px 4px; border-radius: 4px; }}
                    pre {{ background-color: #1e1e1e; padding: 10px; border-radius: 6px; border: 1px solid #333; }}
                    a {{ color: #3daee9; text-decoration: none; }}
                    p {{ margin: 0 0 10px 0; }}
                    ul {{ margin-bottom: 10px; }}
                </style>
                {html}
            </div>
            <br>
            """

            cursor.insertHtml(styled_html)
            self.scroll_to_bottom()

        self.current_ai_response = ""

        # Replace tool tags with emoji icons (ADD THIS LINE)
        self.replace_tool_tags_with_icons()


    @pyqtSlot(str, str)
    def handle_tool_call(self, tool_name, tool_args):
        try:
            self.chat_display.append(f"<div style='color:#666; font-size: 10pt;'><i>Running: {tool_name}...</i></div>")

            result = f"Error: Tool {tool_name} not found."
            if tool_name == "SEARCH_WEB": result = system_tools.search_web(tool_args)
            elif tool_name == "OPEN_URL": result = system_tools.open_url(tool_args)
            elif tool_name == "RUN_APP": result = system_tools.launch_application(tool_args)
            elif tool_name == "GET_APP_LIST": result = system_tools.get_application_list()
            elif tool_name == "TAKE_SCREENSHOT": result = system_tools.take_screenshot()
            elif tool_name == "GET_SCREEN_SIZE": result = system_tools.get_screen_size()
            elif tool_name == "MOUSE_CLICK": result = system_tools.mouse_click(tool_args)
            elif tool_name == "KEYBOARD_TYPE": result = system_tools.keyboard_type(tool_args)
            elif tool_name == "READ_FILE": result = system_tools.read_file(tool_args)
            elif tool_name == "WRITE_FILE": result = system_tools.write_file(tool_args)
            elif tool_name == "ANNOTATE":
                self.screen_marker.draw_boxes(tool_args)
                result = "ANNOTATED_PATH: displayed_on_screen"

            self.ai_worker.handle_tool_result(result)
        except Exception as e:
            self.ai_worker.handle_tool_result(f"Tool Error: {str(e)}")

    @pyqtSlot(str)
    def handle_image_generated(self, path):
        self.chat_display.append(f'<br><img src="{path}" width="600" style="border-radius:8px;"><br>')
        self.scroll_to_bottom()

    @pyqtSlot(str)
    def handle_error(self, msg):
        self.chat_display.append(f"<div style='color:#ff5555;'>Error: {msg}</div>")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.toggle_visibility()
        else:
            super().keyPressEvent(event)

if __name__ == "__main__":
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    def run_single_instance_check():
        socket = QLocalSocket()
        socket.connectToServer(SOCKET_NAME)
        if socket.waitForConnected(500):
            return True
        return False

    if run_single_instance_check():
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    server = QLocalServer()
    QLocalServer.removeServer(SOCKET_NAME)
    server.listen(SOCKET_NAME)

    window = LauncherWindow()
    print("Orion Daemon Running. Press Ctrl+Alt+Space to toggle.")
    print("Context persists until you type 'clear' or kill the daemon.")

    def handle_socket():
        client = server.nextPendingConnection()
        if client.waitForReadyRead(1000):
            msg = client.readAll().data().decode()
            if msg == "TOGGLE": window.toggle_visibility()
    server.newConnection.connect(handle_socket)

    if "--toggle" in sys.argv:
        window.show()

    sys.exit(app.exec())
