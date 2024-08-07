import sys
import serial
import time
import struct
import folium
from PyQt6.QtWidgets import QApplication, QMainWindow, QComboBox, QPushButton, QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QMessageBox, QLineEdit, QGroupBox, QGridLayout, QFrame, QScrollArea, QSplashScreen
from PyQt6.QtCore import QThread, pyqtSignal, QUrl, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QSplitter, QGridLayout, QSizePolicy
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QTextCursor, QFont, QPixmap, QIcon
from datetime import datetime

class SerialThread(QThread):
    data_received = pyqtSignal(int, bytearray, str)  
    data_received_bypass = pyqtSignal(int, bytes, str)
    error_occurred = pyqtSignal(str)
    crc_failed = pyqtSignal()
    frame_error = pyqtSignal()

    def set_mode(self, is_rf):
        self.is_rf_mode = is_rf

    def __init__(self, serial_port, baud_rate):
        super().__init__()
        self.serial_port_name = serial_port
        self.baud_rate = baud_rate
        self.running = False
        self.serial_port = None
        self.auto_report_enabled = True 
        self.is_rf_mode = True 

    def clear_buffer(self):
        self.buffer = bytearray()

    def run(self):
        try:
            self.serial_port = serial.Serial(self.serial_port_name, baudrate=self.baud_rate, timeout=1)
            self.running = True

            self.serial_port.write(b'B')

            self.buffer = bytearray()
            while self.running:
                data = self.serial_port.read()
                if data:
                    if self.auto_report_enabled:
                        if self.is_rf_mode:
                            if data[0] == 0xCA:  # Start of frame
                                self.buffer = bytearray(data)
                            elif data[0] == 0xEF:  # End of frame
                                self.buffer.extend(data)
                                frame_data = self.destuff_frame(self.buffer)
                                if len(frame_data) != 284:
                                    self.frame_error.emit()
                                    self.data_received.emit(len(frame_data), frame_data, "length_fail") 
                                else:
                                    crc_received = (frame_data[-4] << 8) | frame_data[-3]
                                    crc_calculated = self.calculate_crc(frame_data[2:-4])
                                    if crc_received != crc_calculated:
                                        self.crc_failed.emit()
                                        self.data_received.emit(len(frame_data), frame_data, "crc_fail") 
                                    else:
                                        self.data_received.emit(len(frame_data), frame_data, "ok")  
                                self.buffer = bytearray()
                            else:
                                self.buffer.extend(data)
                        else:  # RS422 mode
                            self.buffer.extend(data)
                            if len(self.buffer) == 282:
                                self.buffer.insert(0, 0xCA)  # Add 0xCA at the beginning
                                self.buffer.append(0xEF)
                                frame_data = self.buffer
                                crc_received = (frame_data[-4] << 8) | frame_data[-3]
                                crc_calculated = self.calculate_crc(frame_data[2:-4])
                                if crc_received != crc_calculated:
                                    self.crc_failed.emit()
                                    self.data_received.emit(len(frame_data), frame_data, "crc_fail") 
                                else:
                                    self.data_received.emit(len(frame_data), frame_data, "ok")  
                                self.buffer = bytearray()

                    else:
                        self.data_received_bypass.emit(1, data, "ok")  
        except serial.SerialException as e:
            print("Serial Error") 
            self.error_occurred.emit(str(e))
        finally:
            if self.serial_port is not None and self.serial_port.is_open:
                self.serial_port.close()

    def stop(self):
        self.running = False
        if self.serial_port is not None and self.serial_port.is_open:
            self.serial_port.close()

    def set_auto_report(self, enabled):
        self.auto_report_enabled = enabled

    def destuff_frame(self, frame_data):
        destuffed_data = bytearray()
        escape_received = False
        for byte in frame_data:
            if escape_received:
                if byte == 0xDC:
                    destuffed_data.append(0xCA)
                elif byte == 0xDE:
                    destuffed_data.append(0xEF)
                elif byte == 0xDB:
                    destuffed_data.append(0xBD)
                escape_received = False
            elif byte == 0xBD:
                escape_received = True
            else:
                destuffed_data.append(byte)
        return destuffed_data

    def calculate_crc(self, data):
        crc = 0x0000
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
        return crc & 0xFFFF

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serial Frame Collector v1.2.0")
        self.setGeometry(40, 40, 800, 600)
        self.resize(1450, 750)

        self.auto_report_enabled = True
        self.is_rf_mode = True
        self.history_count = 0

        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("font-size: 11pt; font-weight: bold;")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_clock)
        self.timer.start(1000)
        self.update_clock()

        self.com_port_combo = QComboBox()
        self.com_port_combo.addItems(["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "COM10",
                                      "COM11", "COM12", "COM13", "COM14", "COM15", "COM16", "COM17", "COM18", "COM19", "COM20"])
        self.com_port_combo.setFixedWidth(100)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_collection)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_text_edit)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_counters)

        self.theme_button = QPushButton("Light Theme")
        self.theme_button.clicked.connect(self.toggle_theme)

        self.mode_button = QPushButton("Mode: RF")
        self.mode_button.clicked.connect(self.toggle_mode)

        self.hex_text_edit = QTextEdit()
        self.hex_text_edit.setReadOnly(True)

        self.command_text_edit = QTextEdit()
        self.command_text_edit.setReadOnly(True)

        self.gps_text_edit = QTextEdit()
        self.gps_text_edit.setReadOnly(True)

        self.map_view = QWebEngineView()
        self.map_data = None
        self.marker_list = []

        self.param_group_box = QGroupBox("Value Received")
        self.param_layout = QGridLayout()
        self.param_group_box.setLayout(self.param_layout)
        self.param_group_box.setFixedSize(800, 450)

        self.command_input = QLineEdit()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_command)


    #Create top layout
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.com_port_combo)
        top_layout.addWidget(self.mode_button)
        top_layout.addWidget(self.clock_label)
        top_layout.addStretch(1)
        top_layout.addWidget(self.start_button)
        top_layout.addWidget(self.clear_button)
        top_layout.addWidget(self.reset_button)
        top_layout.addWidget(self.theme_button)

    #Create infor group box
        info_group_box = QGroupBox("Frame Analyzer")
        info_layout = QGridLayout()

        total_frame_label = QLabel("Total Frame:")
        total_img_label = QLabel("Img Frame:")
        frame_ok_label = QLabel("Frame OK:")
        frame_error_label = QLabel("Length Wrong:")
        crc_fail_label = QLabel("CRC Fail:")

        self.total_frame_value = QLabel("0")
        self.total_img_value = QLabel("0")
        self.frame_ok_value = QLabel("0")
        self.frame_error_value = QLabel("0")
        self.crc_fail_value = QLabel("0")

        info_layout.addWidget(total_frame_label, 0, 0)
        info_layout.addWidget(self.total_frame_value, 0, 1)
        info_layout.addWidget(total_img_label, 3, 0)
        info_layout.addWidget(self.total_img_value, 3, 1)

        in_that_label = QLabel("In That:")
        in_that_label.setStyleSheet("font-weight: bold")
        info_layout.addWidget(in_that_label, 1, 0)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        info_layout.addWidget(line, 2, 0, 1, 2)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        info_layout.addWidget(line, 4, 0, 1, 2)

        info_layout.addWidget(frame_ok_label, 5, 0)
        info_layout.addWidget(self.frame_ok_value, 5, 1)
        info_layout.addWidget(frame_error_label, 6, 0)
        info_layout.addWidget(self.frame_error_value, 6, 1)
        info_layout.addWidget(crc_fail_label, 7, 0)
        info_layout.addWidget(self.crc_fail_value, 7, 1)

        info_group_box.setLayout(info_layout)
        info_group_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        info_widget = QWidget()
        info_widget_layout = QVBoxLayout()
        info_widget_layout.addWidget(info_group_box)
        info_widget.setLayout(info_widget_layout)
        info_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        top_left_widget = QWidget()
        top_left_layout = QVBoxLayout()
        top_left_layout.addWidget(self.param_group_box)
        top_left_widget.setLayout(top_left_layout)
        top_left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        gps_group_box = QGroupBox("GPS Messages")
        gps_layout = QVBoxLayout()
        gps_layout.addWidget(self.gps_text_edit)
        gps_group_box.setLayout(gps_layout)
        top_right_widget = QWidget()
        top_right_layout = QVBoxLayout()
        top_right_layout.addWidget(gps_group_box)  
        top_right_widget.setLayout(top_right_layout)
        top_right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        map_group_box = QGroupBox("Map Tracking")
        map_layout = QVBoxLayout()
        map_layout.addWidget(self.map_view)
        map_group_box.setLayout(map_layout)
        bottom_right_widget = QWidget()
        bottom_right_layout = QVBoxLayout()
        bottom_right_layout.addWidget(map_group_box) 
        bottom_right_widget.setLayout(bottom_right_layout)
        bottom_right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        hex_group_box = QGroupBox("Command Guide")
        hex_layout = QVBoxLayout()

        commands = [
            ("---", "SIMPLE COMMAND"),
            ("help", "Display list of simple help commands"),
            ("help_all", "Display list of ALL!!! commands"),
            ("help_cpoc", "Display list of CPOC commands"),
            ("help_pmu", "Display list of PMU commands"),
            ("help_pdu", "Display list of PDU commands"),
            ("help_cam", "Display list of CAM commands"),
            ("help_iou", "Display list of IOU commands"),
            ("splash", "Splash screen again"),
            ("---", "CPOC CMD"),
            ("status_now", "Display <Date&Time>, <Temp> *C, <HardwareVer>, <FirmwareVer>, <Enable>, <Mode>"),
            ("auto_report_ena", "Enable Mirror 282 byte to Text as Debug Port [ESC]"),
            ("rs422_report_ena", "Report 282 byte packet to RS422, [ESC] to stop***"),
            ("set_byte_rs422 <size>", "Set Size of packet RS422, Default 282 (150<x<1000)"),
            ("set_baud_rs422 <baudrate>", "[9600|19200|38400|115200|230400|460800], Default 115200"),
            ("set_fre_rs422 <packet>", "[0(0.5)|1|2|3|4|5|6|7|8|9|10|11|12], Packet per second"),
            ("swap_byte_ena", "Enable swap byte RS422, 0x02->0xFE, 0x03->0xFD"),
            ("swap_byte_dis", "Disable swap byte RS422"),
            ("push_data <data> <position>", "Test push data to FRAM"),
            ("pop_data <position>", "Test pop data from FRAM"),
            ("recovery_setmode <0-off/1-on>", "PowerLost - Returns to previous state"),
            ("send_frame_status", "Send Frame Status"),
            ("send_frame_cam <packet_count>", "Send Frame CAM with packet_count [0-26]"),
            ("memory_usage", "%RAM and %FLASH Used"),
            ("time_get", "Get RTC Time"),
            ("time_set <hh> <mm> <ss> <DD> <MM> <YY>", "Time Setting, Eg. 12:01 31/7/2024 -> 12 01 0 31 7 24"),
            ("cpoc_reset", "Reset CPOC Board"),
            ("board_alive", "Hello to specified board, check alive"),
            ("mux_mode", "Set Mux UART Mode"),
            ("rf_ena", "Enable RF Module"),
            ("rf_dis", "Disable RF Module"),
            ("gps_get", "Get GPS Data"),
            ("gps_auto", "Continuously send  GPS Data to LORA"),
            ("gps_format <1-On/0-Off>", "Format GPS Data"),
            ("---", "PMU CMD"),
            ("pmu_get_temp", "Response 4 NTC channel in Celsius "),
            ("pmu_bat_vol", "Response 4 BAT channel in Voltage"),
            ("pmu_parag_in", "Response V_in, I_in from 28V source"),
            ("pmu_parag_out", "Response V_out, I_out from output 14.4V source"),
            ("pmu_set_tpoint <low> <high>", "Set lowpoint < highpoint to control heater temp"),
            ("pmu_set_output <0/1 EN/DIS>", "Enable/disable output 14.4v"),
            ("pmu_set_pwm <Duty>", "Set PWM control in %(0-100) of 14.4v ->(0-100)"),
            ("pmu_set_heater <channel> <state>", "Turn on/off the heater ->(0: OFF, 1: ON)"),
            ("pmu_auto_heater <state>", "Turn on/off auto control heater ->(0: OFF, 1: ON)"),
            ("pmu_get_all", "Response all Params in this board"),
            ("---", "PDU CMD"),
            ("pdu_set_channel <channel> <state>", "Turn on/off channel N ->(0: OFF, 1: ON)"),
            ("pdu_set_buck <buck> <state>", "Turn on/off buck N ->(0: OFF, 1: ON)"),
            ("pdu_set_all <state>", "Turn on/off buck + channel ->(0: OFF, 1: ON)"),
            ("pdu_get_channel <channel>", "Get parameter of channel N"),
            ("pdu_get_buck <buck>", "Get parameter of Buck N"),
            ("pdu_get_all", "Get all parameters"),
            ("---", "CAM CMD"),
            ("cam_check_cam", "Check Camera connection"),
            ("cam_check_spec", "Check Spectrometer connection"),
            ("cam_set_cam_exp <time_ms>", "Set Camera exposure time, default 10"),
            ("cam_get_cam_exp", "Get current Camera exposure time"),
            ("cam_set_spec_exp <time_ms>", "Set Spectrometer exposure time, default 10"),
            ("cam_get_spec_exp", "Get current Spectrometer exposure time"),
            ("cam_set_routine <time_ms>", "Set routine interval time"),
            ("cam_get_routine", "Get current routine interval, default 1000"),
            ("cam_start_routine", "Start periodic routine"),
            ("cam_stop_routine", "Stop periodic routine"),
            ("cam_get_data", "Get CAM datapacket"),
            ("cam_get_img", "Get CAM datapacket"),
            ("---", "IOU CMD"),
            ("iou_set_temp <channel> <temp>", "Set temperature of channel ->(250 mean 25.0Cel)"),
            ("iou_get_temp <device> <channel>", "Response temperature of this channel ->(0: NTC, 1: 1Wire, 2: I2C-channel0)"),
            ("iou_temp_setpoint <channel>", "Response temperature set point of this channel"),
            ("iou_tec_ena <channel>", "Enable operation of this channel TEC"),
            ("iou_tec_dis <channel>", "Disable operation of this channel TEC"),
            ("iou_tec_ena_auto <channel>", "Enable auto control this channel TEC"),
            ("iou_tec_dis_auto <channel>", "Disable auto control this channel TEC"),
            ("iou_tec_set_output <channel> <mode> <vol>", "Set output TEC Voltage (Channel) (0: Cool, 1: Heat) (150 mean 1.50)"),
            ("iou_tec_set_auto_vol <channel> <vol>", "Automatically control TEC Voltage"),
            ("iou_tec_status", "Get TEC status data"),
            ("iou_ringled_setrgbw <r> <g> <b> <w>", "Set display mode for RingLed (0-255)"),
            ("iou_ringled_getrgbw", "Get display mode of RingLed"),
            ("iou_get_accel", "Get Accelerometer-Gyroscope"),
            ("iou_get_press", "Get Pressure Sensor Data"),
            ("iou_irled_set_bri <percent>", "Set brightness (0-100%) of IR led"),
            ("iou_irled_get_bri", "Get brightness (0-100%) of IR led"),
            ("iou_get_all", "Show all status of device in IOU board"),
            ("iou_auto_status", "Auto update status IOU")
        ]


        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        def copy_to_clipboard(text):
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

        def bold_label(label):
            font = label.font()
            font.setBold(True)
            label.setFont(font)

        def unbold_label(label):
            font = label.font()
            font.setBold(False)
            label.setFont(font)

        class ClickableLabel(QLabel):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def mousePressEvent(self, event):
                copy_to_clipboard(self.text())
                bold_label(self)

            def leaveEvent(self, event):
                unbold_label(self)

        for command in commands:
            if command[0] == "---":
                separator = QFrame()
                separator.setFrameShape(QFrame.Shape.HLine)
                separator.setFrameShadow(QFrame.Shadow.Sunken)
                scroll_layout.addWidget(separator)

                title_label = QLabel(command[1])
                title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                font = title_label.font()
                font.setBold(True)
                title_label.setFont(font)
                scroll_layout.addWidget(title_label)
            else:
                label = ClickableLabel(command[0])
                label.setToolTip(command[1])
                scroll_layout.addWidget(label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)

        hex_layout.addWidget(scroll_area)
        hex_group_box.setLayout(hex_layout)
        
        bottom_left_widget = QWidget()
        bottom_left_layout = QVBoxLayout()
        bottom_left_layout.addWidget(hex_group_box)
        bottom_left_widget.setLayout(bottom_left_layout)
        bottom_left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        command_group_box = QGroupBox("Terminal")
        command_layout = QVBoxLayout()

        command_input_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("> ")
        self.command_input.returnPressed.connect(self.send_command_with_enter)
        command_input_layout.addWidget(QLabel("> "))
        command_input_layout.addWidget(self.command_input)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_command)

        self.auto_report_start_button = QPushButton("Auto report Start")
        self.auto_report_start_button.clicked.connect(self.send_auto_report_start)

        self.auto_report_stop_button = QPushButton("Auto report Stop")
        self.auto_report_stop_button.clicked.connect(self.send_auto_report_stop)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.auto_report_start_button)
        button_layout.addWidget(self.auto_report_stop_button)

        command_layout.addWidget(self.command_text_edit)
        command_layout.addLayout(command_input_layout)
        command_layout.addLayout(button_layout)

        command_group_box.setLayout(command_layout)
        command_group_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        command_widget = QWidget()
        command_widget_layout = QVBoxLayout()
        command_widget_layout.addWidget(command_group_box)
        command_widget.setLayout(command_widget_layout) 
        command_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding) 

        grid_layout = QGridLayout()
        grid_layout.addWidget(bottom_left_widget, 0, 0)
        grid_layout.addWidget(top_left_widget, 0, 1)
        grid_layout.addWidget(top_right_widget, 0, 2)
        grid_layout.addWidget(info_widget, 1, 0) 
        grid_layout.addWidget(command_widget, 1, 1)
        grid_layout.addWidget(bottom_right_widget, 1, 2)
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 2)
        grid_layout.setColumnStretch(2, 1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(grid_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)


        self.serial_thread = None
        self.total_frames = 0
        self.total_imgs = 0
        self.frame_error_count = 0
        self.crc_fail_count = 0
        self.frame_ok = 0
        self.log_file = None
    def update_clock(self):
        current_time = datetime.now().strftime("%H:%M:%S")
        self.clock_label.setText(current_time)

    def start_collection(self):
        try:
            if self.serial_thread is None:
                com_port = self.com_port_combo.currentText()
                baud_rate = 115200
                self.serial_thread = SerialThread(com_port, baud_rate)
                self.serial_thread.data_received.connect(self.handle_data_received)
                self.serial_thread.data_received_bypass.connect(self.handle_data_received)
                self.serial_thread.error_occurred.connect(self.handle_error)
                self.serial_thread.frame_error.connect(self.handle_frame_error)
                self.serial_thread.crc_failed.connect(self.handle_crc_fail)
                self.serial_thread.start()
                self.start_button.setText("Stop")
                

                current_time = time.strftime("%H_%M_%S")
                log_filename = f"log_{current_time}.txt"
                self.log_file = open(log_filename, "w")
                error_filename = f"error_{current_time}.txt"
                self.error_file = open(error_filename, "w")
            else:
                self.serial_thread.stop()
                self.serial_thread.wait()
                self.serial_thread = None
                self.start_button.setText("Start")
                
                if self.log_file:
                    self.log_file.close()
                    self.log_file = None
                if self.error_file:
                    self.error_file.close()
                    self.error_file = None
        except Exception as e:                
            print(f"Error in start: {str(e)}") 

    def handle_data_received(self, frame_count, data, status):
        try:
            if self.auto_report_enabled:
                timestamp = time.strftime("%H:%M:%S")
                text = f"{timestamp}: Frame {frame_count}: "
                text += ", ".join([f"0x{byte:02X}" for byte in data])
                text += f"\nTotal bytes: {frame_count}\n"
       #         self.hex_text_edit.append(text)
                self.total_frames += 1

                if status == "ok":
                    text += "Status: OK\n\n"
                elif status == "crc_fail":
                    text += "Status: CRC Failed\n\n"
                elif status == "length_fail":
                    text += "Status: Frame Length Failed\n\n"
                
                self.update_labels()
                    
                if status == "ok" and self.log_file:
                    self.log_file.write(text)
                    self.log_file.flush()

                if status != "ok" and self.error_file:
                    self.error_file.write(text)
                    self.error_file.flush()

                if len(data) == 284 and data[2] != 0xFF:
                    if not hasattr(self, 'image_file') or data[2] == 0x00:
                        # Open a new file if no file is currently open or if byte[2] is 0x00
                        timestamp = time.strftime("%H_%M_%S")
                        self.image_file = open(f"{timestamp}_img.txt", "wb")
                        self.image_frame_counter = 0

                    # Write the image data (byte[3] to byte[280]) to the file
                    self.image_file.write(bytes(data[3:281]))
                    self.image_file.flush()
                    self.image_frame_counter += 1
                    self.total_imgs += 1
                    if data[2] == 0x1A or self.image_frame_counter == 27:
                        # Close the file if byte[2] is 0x1A or 27 frames have been written
                        self.image_file.close()
                        del self.image_file
                        del self.image_frame_counter

                    return
                    
                if len(data) == 284 and data[2] == 0xFF:
                    for i in reversed(range(self.param_layout.count())):
                        widget = self.param_layout.itemAt(i).widget()
                        if widget is not None:
                            widget.deleteLater()
                    self.history_count = self.history_count + 1
                    if self.history_count > 11:
                        self.history_count = 0
                        self.clear_text_edit()
                    # Decode and display parameters
                    row = 0
                    col = 0
                    def add_param(name, value="", unit=""):
                        nonlocal row, col
                        if name:
                            self.param_layout.addWidget(QLabel(f"{name}:"), row, col)
                        else:
                            self.param_layout.addWidget(QLabel(""), row, col)
                        self.param_layout.addWidget(QLabel(f"{value}{unit}"), row, col + 1)
                        col += 2
                        if col >= 8:
                            col = 0
                            row += 1
                            


                    def add_line():
                        nonlocal row, col
                        row += 1  
                        line = QFrame()
                        line.setFrameShape(QFrame.Shape.HLine)
                        line.setFrameShadow(QFrame.Shadow.Sunken)
                        self.param_layout.addWidget(line, row, 0, 1, 8)  # Span columns
                        row += 1
                        col = 0 

                    def format_value_100(value):
                        return "<b>{:.2f}</b>".format(value / 100)

                    def format_value_10(value):
                        return "<b>{:.2f}</b>".format(value / 10)

                    def format_value_10_1_decimal(value):
                        return "<b>{:.1f}</b>".format(value / 10)
                    
                    def format_value_bold(value):
                        return "<b>{:.2f}</b>".format(value)

                    def format_value_bold_ori(value):
                        return "<b>{}</b>".format(value)

                    def to_int16(value):
                        if value >= 0x8000:
                            value = value - 0x10000
                        return value

                    time_str = "<b>{:02d}:{:02d}:{:02d}</b>".format(data[5], data[4], data[3])
                    date_str = "<b>{:02d}/{:02d}</b>".format(data[6], data[7])
                    add_param("Time", time_str)
                    add_param("Date", date_str)

                    # Extract RGBW values
                    neo_led_r = data[39]
                    neo_led_g = data[40]
                    neo_led_b = data[41]
                    neo_led_w = data[42]
                    rgbw_value = "<b>{}/{}/{}/{}</b>".format(neo_led_r, neo_led_g, neo_led_b, neo_led_w)
                    add_param("RGBW", rgbw_value)

                    add_line()

                    # Skip byte 8 (0xFF)
                    iou_data = data[9:39]
                    param_names = [
                        "t°NTC CH0", "t°NTC CH1", "t°NTC CH2", "t°NTC CH3",
                        "t°1Wire CH0", "t°1Wire CH1", "t°Sensor", "",
                        "SetPoint CH0", "SetPoint CH1", "SetPoint CH2", "SetPoint CH3",
                        "Vol TEC0", "Vol TEC1", "Vol TEC2", "Vol TEC3",
                    ]

                    param_units = {
                        "t°NTC CH0": "°C", "t°NTC CH1": "°C", "t°NTC CH2": "°C", "t°NTC CH3": "°C",
                        "t°1Wire CH0": "°C", "t°1Wire CH1": "°C", "t°Sensor": "°C",
                        "SetPoint CH0": "°C", "SetPoint CH1": "°C", "SetPoint CH2": "°C", "SetPoint CH3": "°C",
                        "Vol TEC0": "V", "Vol TEC1": "V", "Vol TEC2": "V", "Vol TEC3": "V",
                    }

                    data_index = 0
                    for name in param_names:
                        if name:  # Not a blank field
                            if 2 * data_index + 1 < len(iou_data):
                                high_byte = iou_data[2 * data_index]
                                low_byte = iou_data[2 * data_index + 1]
                                value = to_int16((high_byte << 8) | low_byte)
                                unit = param_units.get(name, "")  # Get the unit for the current parameter
                                
                                if name in ["t°NTC CH0", "t°NTC CH1", "t°NTC CH2", "t°NTC CH3", "t°1Wire CH0", "t°1Wire CH1", "t°Sensor"]:
                                    if value in [-32768, 32767]:
                                        add_param(name, "<b>FAIL</b>", "")
                                    else:
                                        add_param(name, format_value_10(value), unit)
                                elif name in ["SetPoint CH0", "SetPoint CH1", "SetPoint CH2", "SetPoint CH3"]:
                                    add_param(name, format_value_10(value), unit)
                                elif name in ["Vol TEC0", "Vol TEC1", "Vol TEC2", "Vol TEC3"]:
                                    add_param(name, format_value_100(value), unit)
                                else:
                                    add_param(name, format_value_bold(value), unit)
                                    
                                data_index += 1
                        else:
                            add_param(name)  # Add the blank field



                    irled = data[43]
                    irled_value = format_value_bold_ori(irled)
                    add_param("irLED", irled_value, "%")

                    aX = to_int16((data[44] << 8) | data[45])
                    aY = to_int16((data[46] << 8) | data[47])
                    aZ = to_int16((data[48] << 8) | data[49])
                    Press = to_int16((data[56] << 8) | data[57])
                    gX = to_int16((data[50] << 8) | data[51])
                    gY = to_int16((data[52] << 8) | data[53])
                    gZ = to_int16((data[54] << 8) | data[55])

                    if aX >= 32767 or aY >= 32767 or aZ >= 32767 or gX >= 32767 or gY >= 32767 or gZ >= 32767:
                        add_param("aX", format_value_bold_ori("FAIL"), "")
                        add_param("aY", format_value_bold_ori("FAIL"), "")
                        add_param("aZ", format_value_bold_ori("FAIL"), "")
                        if Press >= 32767:
                            add_param("Press", format_value_bold_ori("FAIL"), "")
                        else:
                            add_param("Press", format_value_10_1_decimal(Press), "hPa")
                        add_param("gX", format_value_bold_ori("FAIL"), "")
                        add_param("gY", format_value_bold_ori("FAIL"), "")
                        add_param("gZ", format_value_bold_ori("FAIL"), "")
                    else:
                        add_param("aX", format_value_100(aX), "m/s²")
                        add_param("aY", format_value_100(aY), "m/s²")
                        add_param("aZ", format_value_100(aZ), "m/s²")
                        if Press >= 32767:
                            add_param("Press", format_value_bold_ori("FAIL"), "")
                        else:
                            add_param("Press", format_value_10_1_decimal(Press), "hPa")
                        add_param("gX", format_value_bold_ori(gX), "°/s")
                        add_param("gY", format_value_bold_ori(gY), "°/s")
                        add_param("gZ", format_value_bold_ori(gZ), "°/s")


                    add_line()

                    pdu_data = data[58:112]

                    # Extract and display PDU parameters
                    sBUCK_TEC1 = pdu_data[0]
                    Vol_BUCK_TEC1 = (pdu_data[1] << 8) | pdu_data[2]
                    sBUCK_TEC2 = pdu_data[3]
                    Vol_BUCK_TEC2 = (pdu_data[4] << 8) | pdu_data[5]
                    sBUCK_TEC3 = pdu_data[6]
                    Vol_BUCK_TEC3 = (pdu_data[7] << 8) | pdu_data[8]
                    sBUCK_TEC4 = pdu_data[9]
                    Vol_BUCK_TEC4 = (pdu_data[10] << 8) | pdu_data[11]
                    sBUCK_MCU = pdu_data[12]
                    Vol_BUCK_MCU = (pdu_data[13] << 8) | pdu_data[14]
                    sBUCK_LED = pdu_data[15]
                    Vol_BUCK_LED = (pdu_data[16] << 8) | pdu_data[17]
                    sBUCK_CM4 = pdu_data[18]
                    Vol_BUCK_CM4 = (pdu_data[19] << 8) | pdu_data[20]
                    sTEC1 = pdu_data[21]
                    Amp_TEC1 = (pdu_data[22] << 8) | pdu_data[23]
                    sTEC2 = pdu_data[24]
                    Amp_TEC2 = (pdu_data[25] << 8) | pdu_data[26]
                    sTEC3 = pdu_data[27]
                    Amp_TEC3 = (pdu_data[28] << 8) | pdu_data[29]
                    sTEC4 = pdu_data[30]
                    Amp_TEC4 = (pdu_data[31] << 8) | pdu_data[32]
                    sCOPC = pdu_data[33]
                    Amp_COPC = (pdu_data[34] << 8) | pdu_data[35]
                    sIOU = pdu_data[36]
                    Amp_IOU = (pdu_data[37] << 8) | pdu_data[38]
                    sRGB = pdu_data[39]
                    Amp_RGB = (pdu_data[40] << 8) | pdu_data[41]
                    sIR = pdu_data[42]
                    Amp_IR = (pdu_data[43] << 8) | pdu_data[44]
                    sCM4 = pdu_data[45]
                    Amp_CM4 = (pdu_data[46] << 8) | pdu_data[47]
                    sVIN = pdu_data[48]
                    Vol_VIN = (pdu_data[49] << 8) | pdu_data[50]
                    sVBUS = pdu_data[51]
                    Vol_VBUS = (pdu_data[52] << 8) | pdu_data[53]

                    # Add extracted PDU parameters
                    def get_status_string(status):
                        status_map = {
                            0: "<b>OFF</b>",
                            1: "<b>READY</b>",
                            2: "<b>OverVOL!</b>",
                            3: "<b>OverCUR!</b>",
                            4: "<b>ON</b>"
                        }
                        return status_map.get(status, "Unknown")

                    add_param("sBUCK TEC1", get_status_string(sBUCK_TEC1))
                    add_param("Vol BUCK TEC1", format_value_100(Vol_BUCK_TEC1), "V")
                    add_param("sBUCK TEC2", get_status_string(sBUCK_TEC2))
                    add_param("Vol BUCK TEC2", format_value_100(Vol_BUCK_TEC2), "V")
                    add_param("sBUCK TEC3", get_status_string(sBUCK_TEC3))
                    add_param("Vol BUCK TEC3", format_value_100(Vol_BUCK_TEC3), "V")
                    add_param("sBUCK TEC4", get_status_string(sBUCK_TEC4))
                    add_param("Vol BUCK TEC4", format_value_100(Vol_BUCK_TEC4), "V")
                    add_param("sBUCK MCU", get_status_string(sBUCK_MCU))
                    add_param("Vol BUCK MCU", format_value_100(Vol_BUCK_MCU), "V")
                    add_param("sBUCK LED", get_status_string(sBUCK_LED))
                    add_param("Vol BUCK LED", format_value_100(Vol_BUCK_LED), "V")
                    add_param("sBUCK CM4", get_status_string(sBUCK_CM4))
                    add_param("Vol Buck CM4", format_value_100(Vol_BUCK_CM4), "V")
                    add_param("sTEC1", get_status_string(sTEC1))
                    add_param("Amp TEC1", format_value_100(Amp_TEC1), "A")
                    add_param("sTEC2", get_status_string(sTEC2))
                    add_param("Amp TEC2", format_value_100(Amp_TEC2), "A")
                    add_param("sTEC3", get_status_string(sTEC3))
                    add_param("Amp TEC3", format_value_100(Amp_TEC3), "A")
                    add_param("sTEC4", get_status_string(sTEC4))
                    add_param("Amp TEC4", format_value_100(Amp_TEC4), "A")
                    add_param("sCOPC", get_status_string(sCOPC))
                    add_param("Amp COPC", format_value_100(Amp_COPC), "A")
                    add_param("sIOU", get_status_string(sIOU))
                    add_param("Amp IOU", format_value_100(Amp_IOU), "A")
                    add_param("sRGB", get_status_string(sRGB))
                    add_param("Amp RGB", format_value_100(Amp_RGB), "A")
                    add_param("sIR", get_status_string(sIR))
                    add_param("Amp IR", format_value_100(Amp_IR), "A")
                    add_param("sCM4", get_status_string(sCM4))
                    add_param("Amp CM4", format_value_100(Amp_CM4), "A")
                    add_param("sVIN", get_status_string(sVIN))
                    add_param("Vol VIN", format_value_100(Vol_VIN), "V")
                    add_param("sVBUS", get_status_string(sVBUS))
                    add_param("Vol VBUS", format_value_100(Vol_VBUS), "V")

                    add_line()

                    pmu_data = data[112:136]
                    pmu_param_names = [
                        "NTC0", "NTC1", "NTC2", "NTC3",
                        "BAT0", "BAT1", "BAT2", "BAT3",
                        "VIN", "IIN", "VOUT", "IOUT"
                    ]
                    pmu_param_units = [
                        "°C", "°C", "°C", "°C",
                        "V", "V", "V", "V",
                        "V", "A", "V", "A"
                    ]

                    def format_pmu_value(name, value):
                        if name in ["NTC0", "NTC1", "NTC2", "NTC3"]:
                            if value in [-32768, 32767]:
                                return "<b>FAIL</b>", ""
                            else:
                                return format_value_100(value), "°C"
                        elif name in ["BAT0", "BAT1", "BAT2", "BAT3", "VIN", "VOUT"]:
                            return format_value_100(value), "V"
                        elif name in ["IIN", "IOUT"]:
                            return format_value_100(value), "A"
                        else:
                            return str(value), ""

                    for i, name in enumerate(pmu_param_names):
                        if 2 * i + 1 < len(pmu_data):
                            high_byte = pmu_data[2 * i]
                            low_byte = pmu_data[2 * i + 1]
                            value = to_int16((high_byte << 8) | low_byte)
                            formatted_value, unit = format_pmu_value(name, value)
                            add_param(name, formatted_value, unit)


                    # Decode GPS
                    if len(data) >= 160:
                        utc_time = f"{data[137]:02d}:{data[138]:02d}:{data[139]:02d}.{data[140]:02d}"
                        
                        lat_bytes = data[141:149]
                        lat = struct.unpack('d', bytes(lat_bytes))[0]
                        lat_dir = chr(data[149])

                        lon_bytes = data[150:158]
                        lon = struct.unpack('d', bytes(lon_bytes))[0]
                        lon_dir = chr(data[158])

                        lat_deg = int(lat / 100)
                        lat_min = lat - (lat_deg * 100)

                        lon_deg = int(lon / 100)
                        lon_min = lon - (lon_deg * 100)
                        
                        latitude = lat_deg + (lat_min / 60)
                        longitude = lon_deg + (lon_min / 60)

                        if lat_dir == 'S':
                            latitude = -latitude
                        if lon_dir == 'W':
                            longitude = -longitude

                        gps_text = f"UTC Time: {utc_time}\n"
                        gps_text += f"[Lat, Lon]: {latitude}, {longitude}\n"
                        self.gps_text_edit.append(gps_text)

                        try:
                            if self.map_data is None:
                                self.map_data = folium.Map(location=[latitude, longitude], zoom_start=17)
                            
                            marker = folium.Marker(location=[latitude, longitude])
                            marker.add_to(self.map_data)
                            self.marker_list.append(marker)
                            
                            map_html = self.map_data.get_root().render()
                            self.map_view.setHtml(map_html)
                            self.map_data.save("map.html")

                        except Exception as e:
                            print(f"Error creating or loading map: {str(e)}") 
            else:
                    # Display raw bytes in the Terminal text box
                raw_data = ' '.join([f'{chr(byte)}' for byte in data])
                self.command_text_edit.moveCursor(QTextCursor.MoveOperation.End)
                self.command_text_edit.insertPlainText(raw_data)
        except Exception as e:
            print(f"Massive Error: {str(e)}") 

    def update_labels(self):
        self.total_frame_value.setText(str(self.total_frames))
        self.total_img_value.setText(str(self.total_imgs))
        self.frame_ok_value.setText(str(self.total_frames - self.frame_error_count - self.crc_fail_count))


    def handle_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Could not open port: {error_message}")
        QApplication.quit()

    def handle_frame_error(self):
        self.frame_error_count += 1
        self.frame_error_value.setText(str(self.frame_error_count))

    def handle_crc_fail(self):
        self.crc_fail_count += 1
        self.crc_fail_value.setText(str(self.crc_fail_count))

    def clear_text_edit(self):
        #self.hex_text_edit.clear()
        self.gps_text_edit.clear()
        self.clear_map_markers()

    def reset_counters(self):
        self.total_frames = 0
        self.total_imgs = 0
        self.frame_error_count = 0
        self.crc_fail_count = 0
        self.total_frame_value.setText(str(0))
        self.total_img_value.setText(str(0))
        self.frame_error_value.setText(str(0))
        self.crc_fail_value.setText(str(0))
        self.frame_ok_value.setText(str(0))
    def send_command(self):
        command = self.command_input.text()
        if self.serial_thread is not None and self.serial_thread.isRunning():
            try:
                self.serial_thread.serial_port.write(command.encode())
                self.command_input.clear()
                self.command_text_edit.append(f"Sent: {command}")  
            except serial.SerialException as e:
                QMessageBox.critical(self, "Error", f"Error sending command: {str(e)}")
        else:
            QMessageBox.warning(self, "Warning", "Serial port is not connected")
            
    def toggle_theme(self):
        if self.theme_button.text() == "Dark Theme":
            self.apply_night_theme()
            self.theme_button.setText("Light Theme")
        else:
            self.apply_light_theme()
            self.theme_button.setText("Dark Theme")

    def apply_night_theme(self):
        app.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #4a4a4a;
                color: #ffffff;
            }
            QComboBox {
                background-color: #4a4a4a;
                color: #ffffff;
            }
        """)

    def apply_light_theme(self):
        app.setStyleSheet("")

    def send_command_with_enter(self):
        command = self.command_input.text()
        self.send_serial_command(command + "\n")
        self.command_input.clear()
        if command == "rs422_report_ena":
            self.auto_report_enabled = True
            self.serial_thread.set_auto_report(True)

    def send_command(self):
        command = self.command_input.text()
        self.send_serial_command(command)
        self.command_input.clear()

    def send_auto_report_start(self):
        command = "rs422_report_ena\n"
        self.send_serial_command(command)
        self.auto_report_enabled = True
        self.serial_thread.set_auto_report(True)

    def send_auto_report_stop(self):
        command = "\x1b"  # ESC
        self.send_serial_command(command)
        self.command_text_edit.append("Stop Auto Report")
        self.auto_report_enabled = False
        self.serial_thread.set_auto_report(False)

    def send_serial_command(self, command):
        if self.serial_thread is not None and self.serial_thread.isRunning():
            try:
                self.serial_thread.serial_port.write(command.encode())
                self.command_text_edit.append(f"Sent: {command}")
            except serial.SerialException as e:
                QMessageBox.critical(self, "Error", f"Error sending command: {str(e)}")
        else:
            QMessageBox.warning(self, "Warning", "Serial port is not connected")

    def clear_map_markers(self):
        if self.map_data is not None:
            center = self.map_data.location
            self.marker_list.clear()
            self.map_data = folium.Map(location=center, zoom_start=17)
            map_html = self.map_data.get_root().render()
            self.map_view.setHtml(map_html)
            self.map_data.save("map.html")

    def toggle_mode(self):
        self.is_rf_mode = not self.is_rf_mode
        mode_text = "RF" if self.is_rf_mode else "RS422"
        self.mode_button.setText(f"Mode: {mode_text}")
        if self.serial_thread:
            self.serial_thread.set_mode(self.is_rf_mode)
            self.serial_thread.clear_buffer()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    pixmap = QPixmap("NEWLOGO.png")
    scaled_pixmap = pixmap.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    splash = QSplashScreen(scaled_pixmap)
    splash.show()

    app.processEvents()

    app.setStyleSheet("""
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QTextEdit {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        QLineEdit {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        QLabel {
            color: #ffffff;
        }
        QPushButton {
            background-color: #4a4a4a;
            color: #ffffff;
        }
        QComboBox {
            background-color: #4a4a4a;
            color: #ffffff;
        }
    """)

    window = MainWindow()
    icon = QIcon(scaled_pixmap)
    window.setWindowIcon(icon)

    splash.finish(window)
    window.show()

    sys.exit(app.exec())