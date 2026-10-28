import sys
import math
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QLinearGradient,
    QBrush,
    QPixmap,
    QFont,
    QTextCursor,
    QKeyEvent,
)


# =========================================================
# HIMORA UI v3.5
# =========================================================
# Frontend only.
# main.py controls logic, execution, voice processing, and responses.
#
# Solves:
# - duplicate message risk
# - voice wave stopping immediately
# - visible voice ON/OFF state
# - premium layout
# - better wrapping
# - copy button
# - sidebar animation
# - multiline input
# - Shift+Enter newline
# - Enter send
# =========================================================


class Theme:
    BG_0 = "#020617"
    BG_1 = "#050816"
    BG_2 = "#0f172a"
    BG_3 = "#1e1b4b"
    CARD = "rgba(255, 255, 255, 0.055)"
    BORDER = "rgba(255, 255, 255, 0.10)"
    TEXT = "#f8fafc"
    TEXT_SOFT = "rgba(248, 250, 252, 0.70)"
    MUTED = "rgba(248, 250, 252, 0.46)"
    PURPLE = "#8b5cf6"
    BLUE = "#2563eb"
    CYAN = "#06b6d4"
    PINK = "#ec4899"
    AMBER = "#f59e0b"
    GREEN = "#22c55e"
    RED = "#ef4444"


def project_path(*parts: str) -> Path:
    return Path(__file__).resolve().parent.joinpath(*parts)


class PremiumBackground(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        gradient = QLinearGradient(0, 0, rect.width(), rect.height())
        gradient.setColorAt(0.00, QColor("#020617"))
        gradient.setColorAt(0.22, QColor("#050816"))
        gradient.setColorAt(0.48, QColor("#1e1b4b"))
        gradient.setColorAt(0.74, QColor("#0f172a"))
        gradient.setColorAt(1.00, QColor("#000000"))

        painter.fillRect(rect, QBrush(gradient))

        glow_1 = QLinearGradient(0, 0, rect.width() * 0.65, rect.height() * 0.65)
        glow_1.setColorAt(0, QColor(124, 58, 237, 80))
        glow_1.setColorAt(1, QColor(124, 58, 237, 0))
        painter.setBrush(QBrush(glow_1))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-180, -130, 520, 420)

        glow_2 = QLinearGradient(rect.width(), rect.height(), rect.width() * 0.2, rect.height() * 0.2)
        glow_2.setColorAt(0, QColor(6, 182, 212, 60))
        glow_2.setColorAt(1, QColor(6, 182, 212, 0))
        painter.setBrush(QBrush(glow_2))
        painter.drawEllipse(rect.width() - 260, rect.height() - 260, 520, 420)

        painter.setPen(QColor(255, 255, 255, 13))
        painter.drawLine(0, rect.height() - 1, rect.width(), rect.height() - 1)


class VoiceWave(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(58)
        self.running = False
        self.phase = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)

    def start_wave(self):
        self.running = True
        if not self.timer.isActive():
            self.timer.start(28)
        self.update()

    def stop_wave(self):
        self.running = False
        self.timer.stop()
        self.update()

    def set_listening(self, active: bool):
        if active:
            self.start_wave()
        else:
            self.stop_wave()

    def animate(self):
        self.phase += 0.22
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        center_y = h // 2

        if not self.running:
            painter.setPen(QColor(255, 255, 255, 16))
            painter.drawLine(34, center_y, max(34, w - 34), center_y)
            return

        colors = [
            QColor(139, 92, 246),
            QColor(37, 99, 235),
            QColor(6, 182, 212),
            QColor(236, 72, 153),
        ]

        bar_count = max(28, min(58, w // 14))
        spacing = w / (bar_count + 1)
        bar_width = max(5, min(8, int(spacing * 0.38)))

        for i in range(bar_count):
            x = int((i + 1) * spacing)

            wave = math.sin(self.phase + i * 0.55)
            wave2 = math.sin(self.phase * 1.6 + i * 0.27)
            normalized = abs((wave + wave2) / 2)
            bar_h = int(8 + normalized * 38)

            gradient = QLinearGradient(x, center_y - bar_h, x, center_y + bar_h)
            gradient.setColorAt(0, colors[i % len(colors)])
            gradient.setColorAt(1, colors[(i + 1) % len(colors)])

            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                x - bar_width // 2,
                center_y - bar_h // 2,
                bar_width,
                bar_h,
                bar_width // 2,
                bar_width // 2,
            )


class SmartInput(QTextEdit):
    send_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAcceptRichText(False)
        self.setPlaceholderText("Message Himora...")
        self.setFixedHeight(52)
        self.setMinimumHeight(52)
        self.setMaximumHeight(132)
        self.textChanged.connect(self.auto_resize)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(255, 255, 255, 0.065);
                color: {Theme.TEXT};
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 18px;
                padding: 13px 14px;
                font-size: 14px;
                selection-background-color: {Theme.PURPLE};
            }}
            QTextEdit:focus {{
                border: 1px solid rgba(139, 92, 246, 0.55);
                background: rgba(255, 255, 255, 0.085);
            }}
        """)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return

            self.send_requested.emit()
            return

        super().keyPressEvent(event)

    def auto_resize(self):
        doc_height = int(self.document().size().height()) + 24
        new_height = max(52, min(132, doc_height))

        if new_height != self.height():
            self.setFixedHeight(new_height)

    def text_value(self) -> str:
        return self.toPlainText().strip()

    def clear_input(self):
        self.clear()
        self.setFixedHeight(52)


class IconButton(QPushButton):
    def __init__(self, text: str, size: int = 44, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ChatBubble(QWidget):
    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)

        self.text = str(text)
        self.is_user = is_user

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self.card = QFrame()
        self.card.setObjectName("UserBubble" if is_user else "AssistantBubble")

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(15, 12, 15, 12)
        self.card_layout.setSpacing(8)

        self.label = QLabel(self.text)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.label.setMaximumWidth(560 if is_user else 610)
        self.label.setMinimumWidth(300 if is_user else 480)
        self.label.setFont(QFont("Arial", 14))

        if is_user:
            self.card.setStyleSheet("""
                QFrame#UserBubble {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:1,
                        stop:0 #7c3aed,
                        stop:0.50 #2563eb,
                        stop:1 #06b6d4
                    );
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 20px;
                }
                QLabel {
                    color: white;
                    background: transparent;
                }
            """)
        else:
            self.card.setStyleSheet("""
                QFrame#AssistantBubble {
                    background: rgba(255, 255, 255, 0.045);
                    border: 1px solid rgba(255, 255, 255, 0.075);
                    border-radius: 20px;
                }
                QLabel {
                    color: #f8fafc;
                    background: transparent;
                }
            """)

        self.card_layout.addWidget(self.label)

        if not is_user:
            tools = QHBoxLayout()
            tools.setContentsMargins(0, 0, 0, 0)
            tools.addStretch()

            self.copy_btn = QPushButton("Copy")
            self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.copy_btn.setFixedSize(58, 24)
            self.copy_btn.clicked.connect(self.copy_text)
            self.copy_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(139, 92, 246, 0.14);
                    color: #c4b5fd;
                    border: 1px solid rgba(139, 92, 246, 0.20);
                    border-radius: 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: rgba(139, 92, 246, 0.24);
                }
            """)

            tools.addWidget(self.copy_btn)
            self.card_layout.addLayout(tools)

        outer.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.card.setGraphicsEffect(shadow)

    def copy_text(self):
        QApplication.clipboard().setText(self.text)
        self.copy_btn.setText("Copied")
        QTimer.singleShot(1100, lambda: self.copy_btn.setText("Copy"))


class SidebarButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.045);
                color: rgba(248, 250, 252, 0.82);
                border: 1px solid rgba(255, 255, 255, 0.055);
                border-radius: 14px;
                text-align: left;
                padding-left: 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(139, 92, 246, 0.18);
                color: white;
                border: 1px solid rgba(139, 92, 246, 0.30);
            }
        """)


class HimoraUI(PremiumBackground):
    def __init__(
        self,
        send_callback: Optional[Callable] = None,
        voice_callback: Optional[Callable] = None,
    ):
        super().__init__()

        self.send_callback = send_callback
        self.voice_callback = voice_callback

        self.sidebar_open = False
        self.has_messages = False
        self.voice_active = False
        self.busy = False
        self.anim = None

        self.setup_window()
        self.setup_ui()
        self.position_window()

    def setup_window(self):
        self.resize(820, 720)
        self.setMinimumSize(540, 520)
        self.setWindowTitle("Himora")
        self.setObjectName("HimoraRoot")

    def setup_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                color: {Theme.TEXT};
                font-family: Arial;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                width: 0px;
                background: transparent;
            }}
            QToolTip {{
                background: rgba(15, 23, 42, 0.95);
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                padding: 6px;
            }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(12)

        self.build_sidebar(root)
        self.build_main_area(root)

    def build_sidebar(self, root: QHBoxLayout):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(0)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.sidebar.setStyleSheet("""
            QFrame#Sidebar {
                background: rgba(255, 255, 255, 0.045);
                border: 1px solid rgba(255, 255, 255, 0.075);
                border-radius: 22px;
            }
        """)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Workspace")
        title.setStyleSheet(f"""
            color: {Theme.TEXT_SOFT};
            font-size: 12px;
            font-weight: bold;
            background: transparent;
        """)
        layout.addWidget(title)

        new_chat = SidebarButton("＋  New Chat")
        new_chat.clicked.connect(self.clear_chat)
        layout.addWidget(new_chat)

        layout.addWidget(SidebarButton("◌  Recent Chats"))
        layout.addWidget(SidebarButton("◈  Skills"))
        layout.addWidget(SidebarButton("◎  Voice Mode"))
        layout.addWidget(SidebarButton("▣  Settings"))
        layout.addStretch()

        small = QLabel("Himora v3.5\nDesktop AI Assistant")
        small.setStyleSheet(f"""
            color: {Theme.MUTED};
            font-size: 11px;
            background: transparent;
        """)
        layout.addWidget(small)

        root.addWidget(self.sidebar)

    def build_main_area(self, root: QHBoxLayout):
        main_shell = QFrame()
        main_shell.setObjectName("MainShell")
        main_shell.setStyleSheet("""
            QFrame#MainShell {
                background: rgba(255, 255, 255, 0.032);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 26px;
            }
        """)

        main = QVBoxLayout(main_shell)
        main.setContentsMargins(14, 14, 14, 8)
        main.setSpacing(10)

        self.build_top_bar(main)
        self.build_chat_area(main)
        self.build_voice_wave(main)
        self.build_input_area(main)
        self.build_footer(main)

        root.addWidget(main_shell, 1)

    def build_top_bar(self, main: QVBoxLayout):
        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 4, 0)
        top.setSpacing(10)

        self.menu_btn = IconButton("☰", 42)
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.055);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.085);
                border-radius: 14px;
                font-size: 18px;
            }
            QPushButton:hover {
                background: rgba(139, 92, 246, 0.22);
                border: 1px solid rgba(139, 92, 246, 0.35);
            }
        """)
        top.addWidget(self.menu_btn)

        brand = QHBoxLayout()
        brand.setSpacing(10)

        self.logo = QLabel()
        self.logo.setFixedSize(42, 42)
        self.logo.setStyleSheet("background: transparent;")

        logo_path = project_path("assets", "logo.png")
        pix = QPixmap(str(logo_path))

        if not pix.isNull():
            pix = pix.scaled(
                42,
                42,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo.setPixmap(pix)
        else:
            self.logo.setText("H")
            self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.logo.setStyleSheet("""
                QLabel {
                    background: qlineargradient(
                        x1:0,y1:0,x2:1,y2:1,
                        stop:0 #7c3aed,
                        stop:1 #06b6d4
                    );
                    border-radius: 21px;
                    color: white;
                    font-weight: bold;
                    font-size: 20px;
                }
            """)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)

        self.logo_text = QLabel("Himora")
        self.logo_text.setStyleSheet("""
            QLabel {
                background: transparent;
                color: white;
                font-size: 22px;
                font-weight: bold;
            }
        """)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {Theme.MUTED};
                font-size: 11px;
            }}
        """)

        title_col.addWidget(self.logo_text)
        title_col.addWidget(self.status_label)

        brand.addWidget(self.logo)
        brand.addLayout(title_col)

        brand_widget = QWidget()
        brand_widget.setStyleSheet("background: transparent;")
        brand_widget.setLayout(brand)
        top.addWidget(brand_widget)
        top.addStretch()

        self.voice_pill = QLabel("● Idle")
        self.voice_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voice_pill.setFixedHeight(32)
        self.voice_pill.setMinimumWidth(86)
        self.voice_pill.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,0.055);
                color: rgba(248,250,252,0.68);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 13px;
                font-size: 12px;
            }
        """)
        top.addWidget(self.voice_pill)

        self.upgrade = QPushButton("Upgrade")
        self.upgrade.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upgrade.setFixedSize(96, 34)
        self.upgrade.setStyleSheet("""
            QPushButton {
                border-radius: 14px;
                color: white;
                font-weight: bold;
                border: 1px solid rgba(255,255,255,0.16);
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 #9333ea,
                    stop:0.55 #ec4899,
                    stop:1 #f59e0b
                );
            }
            QPushButton:hover {
                border: 1px solid rgba(255,255,255,0.35);
            }
        """)
        top.addWidget(self.upgrade)

        main.addLayout(top)

    def build_chat_area(self, main: QVBoxLayout):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")

        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(10, 8, 10, 8)
        self.chat_layout.setSpacing(2)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.welcome_wrap = QWidget()
        self.welcome_wrap.setStyleSheet("background: transparent;")

        welcome_layout = QVBoxLayout(self.welcome_wrap)
        welcome_layout.setContentsMargins(20, 110, 20, 20)
        welcome_layout.setSpacing(12)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.welcome_title = QLabel("Welcome back, Aayu")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_title.setStyleSheet("""
            QLabel {
                background: transparent;
                color: white;
                font-size: 34px;
                font-weight: bold;
            }
        """)

        self.welcome_subtitle = QLabel("Ask, command, code, search, or turn on voice mode.")
        self.welcome_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_subtitle.setWordWrap(True)
        self.welcome_subtitle.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {Theme.TEXT_SOFT};
                font-size: 14px;
            }}
        """)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        chip_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for chip in ["Open YouTube", "Fix code", "Message WhatsApp"]:
            chip_btn = QPushButton(chip)
            chip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            chip_btn.setFixedHeight(32)
            chip_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.06);
                    color: rgba(248,250,252,0.78);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 14px;
                    padding-left: 12px;
                    padding-right: 12px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: rgba(139,92,246,0.18);
                    color: white;
                }
            """)
            chip_btn.clicked.connect(lambda _, t=chip: self.quick_prompt(t))
            chip_row.addWidget(chip_btn)

        welcome_layout.addWidget(self.welcome_title)
        welcome_layout.addWidget(self.welcome_subtitle)
        welcome_layout.addLayout(chip_row)

        self.chat_layout.addWidget(self.welcome_wrap)
        self.chat_layout.addStretch(1)

        self.scroll.setWidget(self.chat_widget)
        main.addWidget(self.scroll, 1)

    def build_voice_wave(self, main: QVBoxLayout):
        self.wave_container = QFrame()
        self.wave_container.setObjectName("WaveContainer")
        self.wave_container.setStyleSheet("""
            QFrame#WaveContainer {
                background: rgba(255,255,255,0.035);
                border: 1px solid rgba(255,255,255,0.065);
                border-radius: 20px;
            }
        """)

        wave_layout = QVBoxLayout(self.wave_container)
        wave_layout.setContentsMargins(10, 0, 10, 0)

        self.wave = VoiceWave()
        wave_layout.addWidget(self.wave)

        main.addWidget(self.wave_container)

    def build_input_area(self, main: QVBoxLayout):
        input_shell = QFrame()
        input_shell.setObjectName("InputShell")
        input_shell.setStyleSheet("""
            QFrame#InputShell {
                background: rgba(255,255,255,0.035);
                border: 1px solid rgba(255,255,255,0.065);
                border-radius: 24px;
            }
        """)

        row = QHBoxLayout(input_shell)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(8)

        self.input_box = SmartInput()
        self.input_box.send_requested.connect(self.send_message)
        row.addWidget(self.input_box, 1)

        self.voice_btn = IconButton("◎", 48)
        self.voice_btn.setToolTip("Voice mode on/off")
        self.voice_btn.clicked.connect(self.handle_voice)
        row.addWidget(self.voice_btn)

        self.send_btn = IconButton("➜", 48)
        self.send_btn.setToolTip("Send")
        self.send_btn.clicked.connect(self.send_message)
        row.addWidget(self.send_btn)

        main.addWidget(input_shell)

        self.update_voice_button()
        self.update_send_button(active=True)

    def build_footer(self, main: QVBoxLayout):
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(4, 0, 2, 0)

        footer = QLabel("Himora can make mistakes. Check important actions before sending.")
        footer.setStyleSheet(f"""
            QLabel {{
                color: {Theme.MUTED};
                background: transparent;
                font-size: 11px;
            }}
        """)

        footer_row.addWidget(footer)
        footer_row.addStretch()
        footer_row.addWidget(QSizeGrip(self))

        main.addLayout(footer_row)

    def position_window(self):
        screen = QApplication.primaryScreen()

        if not screen:
            return

        available = screen.availableGeometry()

        self.move(
            available.width() - self.width() - 28,
            available.height() - self.height() - 54,
        )

    def toggle_sidebar(self):
        start = self.sidebar.maximumWidth()
        end = 236 if not self.sidebar_open else 0

        self.anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
        self.anim.setDuration(260)
        self.anim.setStartValue(start)
        self.anim.setEndValue(end)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        self.sidebar_open = not self.sidebar_open

    def add_message(self, text: str, is_user: bool = False):
        text = str(text).strip()

        if not text:
            return

        self.remove_welcome_if_needed()

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")

        row = QHBoxLayout(wrapper)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(8)

        bubble = ChatBubble(text, is_user)

        if is_user:
            row.addStretch(1)
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            row.addStretch(1)

        stretch_index = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(max(0, stretch_index), wrapper)

        QTimer.singleShot(40, self.scroll_bottom)

    def remove_welcome_if_needed(self):
        if self.has_messages:
            return

        self.has_messages = True

        if self.welcome_wrap:
            self.chat_layout.removeWidget(self.welcome_wrap)
            self.welcome_wrap.deleteLater()
            self.welcome_wrap = None

    def scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_chat(self):
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        self.has_messages = False

        self.welcome_wrap = QWidget()
        self.welcome_wrap.setStyleSheet("background: transparent;")

        welcome_layout = QVBoxLayout(self.welcome_wrap)
        welcome_layout.setContentsMargins(20, 110, 20, 20)
        welcome_layout.setSpacing(12)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.welcome_title = QLabel("Welcome back, Aayu")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_title.setStyleSheet("""
            QLabel {
                background: transparent;
                color: white;
                font-size: 34px;
                font-weight: bold;
            }
        """)

        self.welcome_subtitle = QLabel("Ask, command, code, search, or turn on voice mode.")
        self.welcome_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_subtitle.setWordWrap(True)
        self.welcome_subtitle.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {Theme.TEXT_SOFT};
                font-size: 14px;
            }}
        """)

        welcome_layout.addWidget(self.welcome_title)
        welcome_layout.addWidget(self.welcome_subtitle)

        self.chat_layout.addWidget(self.welcome_wrap)
        self.chat_layout.addStretch(1)

    def send_message(self):
        text = self.input_box.text_value()

        if not text:
            return

        self.add_message(text, True)
        self.input_box.clear_input()
        self.set_busy(True)

        if self.send_callback:
            try:
                response = self.send_callback(text)

                if isinstance(response, str) and response.strip():
                    self.add_message(response, False)
                    self.set_busy(False)

            except Exception as error:
                self.add_message(f"UI send error: {error}", False)
                self.set_busy(False)
        else:
            self.set_busy(False)

    def handle_voice(self):
        self.set_voice_state(not self.voice_active)

        if self.voice_callback:
            try:
                self.voice_callback()
            except Exception as error:
                self.add_message(f"Voice error: {error}", False)
                self.set_voice_state(False)

    def set_voice_state(self, active: bool, status: Optional[str] = None):
        self.voice_active = bool(active)

        if self.voice_active:
            self.wave.start_wave()
            self.status_label.setText(status or "Listening in background")
            self.voice_pill.setText("● Listening")
            self.voice_pill.setStyleSheet("""
                QLabel {
                    background: rgba(34,197,94,0.13);
                    color: #86efac;
                    border: 1px solid rgba(34,197,94,0.28);
                    border-radius: 13px;
                    font-size: 12px;
                }
            """)
        else:
            self.wave.stop_wave()
            self.status_label.setText(status or "Ready")
            self.voice_pill.setText("● Idle")
            self.voice_pill.setStyleSheet("""
                QLabel {
                    background: rgba(255,255,255,0.055);
                    color: rgba(248,250,252,0.68);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 13px;
                    font-size: 12px;
                }
            """)

        self.update_voice_button()

    def update_voice_button(self):
        if self.voice_active:
            self.voice_btn.setText("■")
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 24px;
                    color: white;
                    border: 1px solid rgba(255,255,255,0.24);
                    background: qlineargradient(
                        x1:0,y1:0,x2:1,y2:1,
                        stop:0 #ef4444,
                        stop:0.55 #ec4899,
                        stop:1 #8b5cf6
                    );
                    font-size: 15px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    border: 1px solid rgba(255,255,255,0.42);
                }
            """)
        else:
            self.voice_btn.setText("◎")
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    border-radius: 24px;
                    color: white;
                    border: 1px solid rgba(255,255,255,0.14);
                    background: qlineargradient(
                        x1:0,y1:0,x2:1,y2:1,
                        stop:0 #9333ea,
                        stop:1 #06b6d4
                    );
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    border: 1px solid rgba(255,255,255,0.34);
                }
            """)

    def set_busy(self, busy: bool):
        self.busy = bool(busy)
        self.update_send_button(active=not self.busy)

        if self.busy:
            self.status_label.setText("Thinking...")
        elif not self.voice_active:
            self.status_label.setText("Ready")

    def update_send_button(self, active: bool = True):
        self.send_btn.setEnabled(active)

        self.send_btn.setStyleSheet("""
            QPushButton {
                border-radius: 24px;
                color: white;
                border: 1px solid rgba(255,255,255,0.14);
                background: qlineargradient(
                    x1:0,y1:0,x2:1,y2:1,
                    stop:0 #2563eb,
                    stop:0.52 #7c3aed,
                    stop:1 #ec4899
                );
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                border: 1px solid rgba(255,255,255,0.34);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.07);
                color: rgba(255,255,255,0.35);
            }
        """)

    def mark_response_finished(self):
        self.set_busy(False)

    def quick_prompt(self, text: str):
        self.input_box.setText(text)
        self.input_box.moveCursor(QTextCursor.MoveOperation.End)
        self.input_box.setFocus()

    def set_status(self, text: str):
        self.status_label.setText(str(text))

    def show_voice_on(self):
        self.set_voice_state(True)

    def show_voice_off(self):
        self.set_voice_state(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    def demo_send(text):
        return f"Received: {text}"

    def demo_voice():
        print("voice toggled")

    ui = HimoraUI(
        send_callback=demo_send,
        voice_callback=demo_voice,
    )

    ui.show()
    sys.exit(app.exec())