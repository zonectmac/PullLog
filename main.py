import sys
import os
import subprocess
import traceback
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QDialog,
    QListWidget,
    QListWidgetItem,
)
from pull_log import adb_command, get_files_in_folder


# 在启动时异步触发 PyInstaller 打包（仅源码运行时触发，已打包环境跳过）
def trigger_pack_once():
    try:
        if getattr(sys, "frozen", False):
            return
        project_dir = os.path.dirname(os.path.abspath(__file__))
        cmd = [r"D:\python\Scripts\pyinstaller", "-w", "-F", "-i", "img.png", "-n", "PullLogUI", "main.py"]
        # 后台执行，不阻塞 UI，且隐藏控制台窗口
        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(cmd, cwd=project_dir, shell=False, startupinfo=startupinfo, creationflags=creationflags)
    except Exception:
        traceback.print_exc()

SERVICES = [
    "NavigationService",
    "pudutech-maptools",
    "RunTimeInfoService",
    "launcher",
    "can_service",
    "OTAService",
    "IOTService",
    "CoreService",
    "CloudService",
    "SpeechService",
    "Diagnose",
    "pudutech-mirsdk.g3log",
    "mirsdk.g3log"
]

KILL_PACKAGES = [
    "com.pudutech.usher",
    "com.pudutech.resource.manager.service",
    "com.pudutech.solicit",
    "com.pudutech.business.usher",
    "com.pudutech.remotemaintenance",
    "com.pudutech.ad.service",
    "com.pudutech.business.delivery",
    "com.pudutech.business.recycle",
    "com.pudutech.business.call",
    "com.pudutech.business.function",
    "com.pudutech.function",
    "com.pudutech.puduossetting",
    "com.pudutech.business.gohome",
    "com.pudutech.robot.peanut",
    "com.pudutech.factory_test",
    "com.pudutech.bumblebee",
    "com.pudutech.business.cruise",
    "com.pudutech.project_one.business_delivery",
    "com.pudutech.map",
    "com.pudutech.iot2",
    "com.pudutech.cloud",
    "com.pudutech.hardware2",
    "com.pudutech.navigation",
    "com.pudutech.ota",
    "com.pudutech.maptools",
    "com.pudutech.setupwizard",
    "com.pudutech.hls2robot",
    "com.pudutech.robot.vacuum",
    "com.pudutech.launcher",
    "com.pudutech.core",
    "puduos.app",
    "run_time_info_service",
    "com.pudutech.diagnose",
]

class LogPullWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, service_names, count, need_logcat, need_kernel, need_anr, selected_files=None):
        super().__init__()
        self.service_names = service_names or []
        self.count = count
        self.need_logcat = need_logcat
        self.need_kernel = need_kernel
        self.need_anr = need_anr
        self.selected_files = selected_files or []

    def _emit(self, message):
        self.progress.emit(message)

    def _ensure_dir(self, base_dir):
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

    def _select_by_threshold(self, filenames, count):
        # 参考 pull_process_log：以 max_id - count 为阈值，取编号大于阈值的日志
        id_list = []
        for name in filenames:
            parts = name.split(".")
            if len(parts) > 3 and parts[3].isdigit():
                id_list.append(int(parts[3]))
        if not id_list:
            return []
        max_id = max(id_list)
        threshold = max_id - count
        selected = []
        for name in filenames:
            parts = name.split(".")
            if len(parts) > 3 and parts[3].isdigit():
                if int(parts[3]) > threshold:
                    selected.append(name)
        return selected

    def _select_top_n(self, filenames, count):
        candidates = []
        for name in filenames:
            parts = name.split(".")
            if len(parts) > 3 and parts[3].isdigit():
                candidates.append((int(parts[3]), name))
        if not candidates:
            return []
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [name for _, name in candidates[:max(0, count)]]

    def _select_logs(self, all_filenames, service_names, count):
        if not service_names:
            return []
        union_set = []
        seen = set()
        multiple = len(service_names) > 1
        for svc in service_names:
            svc_files = [name for name in all_filenames if name.startswith(svc)]
            # 多选/ALL：精确每个服务取前 N 份；单选：沿用阈值法以兼容原逻辑
            if multiple:
                chosen = self._select_top_n(svc_files, count)
            else:
                chosen = self._select_by_threshold(svc_files, count)
            for item in chosen:
                if item not in seen:
                    seen.add(item)
                    union_set.append(item)
        return union_set

    def _pull_file_safely(self, remote_path, local_dir):
        try:
            self._emit(f"Pull: {remote_path}")
            result = adb_command(["pull", remote_path, local_dir])
            if result is None:
                result = ""
            self._emit(result)
        except Exception as e:
            traceback.print_exc()
            self._emit(f"Error pulling {remote_path}: {e}")

    def _dump_logcat(self, local_dir):
        try:
            # 改为按需求拉取 /sdcard/pudu/log/kernel/log 文件夹
            self._emit("Pull logcat folder: /sdcard/pudu/log/kernel/log")
            self._pull_file_safely("/sdcard/pudu/log/kernel/log", local_dir)
        except Exception as e:
            traceback.print_exc()
            self._emit(f"Error pull logcat folder: {e}")

    def _pull_anr(self, local_dir):
        try:
            self._emit("Pull /data/anr ...")
            # Attempt pull; may require permissions depending on device
            self._pull_file_safely("/data/anr", local_dir)
        except Exception as e:
            traceback.print_exc()
            self._emit(f"Error pulling ANR: {e}")

    def run(self):
        try:
            self._emit("Listing device logs: sdcard/pudu/log")
            filenames = get_files_in_folder("sdcard/pudu/log")
            if not filenames:
                self.failed.emit("No logs found in sdcard/pudu/log")
                return
            now = datetime.now().strftime("%Y%m%d%H%M%S")
            target_dir = os.path.join("E:\\pudu\\log", now)
            self._ensure_dir(target_dir)
            # 若显式选择了文件，则优先拉取这些文件
            if self.selected_files:
                selected = list(self.selected_files)
            else:
                selected = self._select_logs(filenames, self.service_names, self.count)
            if not selected:
                self._emit("No matching logs by selection; continue with options if any.")
            else:
                for name in selected:
                    self._pull_file_safely(f"sdcard/pudu/log/{name}", target_dir)
            if self.need_kernel:
                self._pull_file_safely("/sdcard/pudu/log/kernel", target_dir)
            if self.need_anr:
                self._pull_anr(target_dir)
            if self.need_logcat:
                self._dump_logcat(target_dir)
            subprocess.call(["explorer", target_dir])
            self.done.emit(target_dir)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class KillWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, packages, delete_pdlog):
        super().__init__()
        self.packages = list(dict.fromkeys(packages or []))
        self.delete_pdlog = delete_pdlog

    def _emit(self, text):
        self.progress.emit(text)

    def run(self):
        try:
            # 先删除日志（按你的要求与命令）
            if self.delete_pdlog:
                try:
                    self._emit('Run: find /sdcard/pudu/log -type f -name "*pdlog*" -exec rm {} \;')
                    cmd_str = 'find /sdcard/pudu/log -type f -name "*pdlog*" -exec rm {} \;'
                    _ = adb_command(["shell", cmd_str])
                    # 简单校验
                    listing = adb_command(["shell", r'ls -l /sdcard/pudu/log 2>/dev/null'])
                    remain = [line for line in listing.splitlines() if ("pdlog" in line or "PDLOG" in line)]
                    if remain:
                        self._emit("Remain pdlog files:")
                        for r in remain[:100]:
                            self._emit(r)
                    else:
                        self._emit("All pdlog files removed.")
                except Exception as e:
                    traceback.print_exc()
                    self._emit(f"Delete pdlog failed: {e}")
            # 再执行 kill
            for pkg in self.packages:
                try:
                    self._emit(f"force-stop {pkg}")
                    _ = adb_command(["shell", "am", "force-stop", pkg])
                except Exception as e:
                    traceback.print_exc()
                    self._emit(f"force-stop failed for {pkg}: {e}")
            self.done.emit()
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class LogPullWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUDU Log Puller")
        self._worker = None
        self._kill_worker = None
        self.selected_services = []
        self._init_ui()

    def _init_ui(self):
        services = ["all", "None"] + SERVICES
        root = QWidget()
        layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Service:"))
        self.combo_service = QComboBox()
        self.combo_service.addItems(services)
        self.combo_service.setCurrentIndex(0)
        row1.addWidget(self.combo_service)
        self.btn_multi = QPushButton("多选日志类型")
        self.btn_multi.clicked.connect(self.on_multi_select_clicked)
        row1.addWidget(self.btn_multi)
        self.lbl_multi = QLabel("(未选择)")
        row1.addWidget(self.lbl_multi)
        self.btn_clear = QPushButton("清除多选")
        self.btn_clear.clicked.connect(self.on_clear_multi_clicked)
        row1.addWidget(self.btn_clear)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("份数:"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 1000)
        self.spin_count.setValue(1)
        row2.addWidget(self.spin_count)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.chk_logcat = QCheckBox("拉取当前 logcat")
        self.chk_kernel = QCheckBox("拉取 kernel")
        self.chk_anr = QCheckBox("拉取 ANR")
        row3.addWidget(self.chk_logcat)
        row3.addWidget(self.chk_kernel)
        row3.addWidget(self.chk_anr)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        self.btn_pull = QPushButton("开始拉取")
        self.btn_pull.clicked.connect(self.on_pull_clicked)
        row4.addWidget(self.btn_pull)
        self.chk_delete_pdlog = QCheckBox("Kill时删除 pdlog")
        row4.addWidget(self.chk_delete_pdlog)
        self.btn_kill = QPushButton("Kill")
        self.btn_kill.clicked.connect(self.on_kill_clicked)
        row4.addWidget(self.btn_kill)
        layout.addLayout(row4)

        row5 = QHBoxLayout()
        self.btn_browse = QPushButton("遍历日志")
        self.btn_browse.clicked.connect(self.on_browse_logs_clicked)
        row5.addWidget(self.btn_browse)
        self.lbl_browse_count = QLabel("(0)")
        row5.addWidget(self.lbl_browse_count)
        layout.addLayout(row5)

        self.lst_logs = QListWidget()
        self.lst_logs.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.lst_logs)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

        root.setLayout(layout)
        self.setCentralWidget(root)
        self.resize(640, 420)

    def append_log(self, text):
        self.txt_log.append(text)

    def on_multi_select_clicked(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("选择日志类型（多选）")
        v = QVBoxLayout()
        lst = QListWidget()
        lst.setSelectionMode(QListWidget.MultiSelection)
        for svc in SERVICES:
            item = QListWidgetItem(svc)
            lst.addItem(item)
            if svc in self.selected_services:
                item.setSelected(True)
        v.addWidget(lst)
        btns = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        v.addLayout(btns)
        dlg.setLayout(v)
        btn_ok.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            sel = [i.text() for i in lst.selectedItems()]
            self.selected_services = sel
            if sel:
                self.lbl_multi.setText(",".join(sel))
            else:
                self.lbl_multi.setText("(未选择)")

    def on_clear_multi_clicked(self):
        self.selected_services = []
        self.lbl_multi.setText("(未选择)")

    def on_pull_clicked(self):
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(self, "Busy", "Task is running, please wait...")
            return
        service = self.combo_service.currentText()
        count = int(self.spin_count.value())
        need_logcat = self.chk_logcat.isChecked()
        need_kernel = self.chk_kernel.isChecked()
        need_anr = self.chk_anr.isChecked()
        self.txt_log.clear()
        if self.selected_services:
            service_names = list(self.selected_services)
        else:
            if service.lower() == "all":
                service_names = list(SERVICES)
            elif service.lower() == "none":
                service_names = []
            else:
                service_names = [service]
        # 若列表中用户手动选择了日志，则仅拉取所选
        selected_items = [i.text() for i in self.lst_logs.selectedItems()]
        if selected_items:
            self.append_log(f"Start pull (manual list): files={selected_items}, logcat={need_logcat}, kernel={need_kernel}, anr={need_anr}")
            self._worker = LogPullWorker(service_names, count, need_logcat, need_kernel, need_anr, selected_files=selected_items)
        else:
            self.append_log(f"Start pull: services={service_names}, count={count}, logcat={need_logcat}, kernel={need_kernel}, anr={need_anr}")
            self._worker = LogPullWorker(service_names, count, need_logcat, need_kernel, need_anr)
        self._worker.progress.connect(self.append_log)
        self._worker.done.connect(self.on_done)
        self._worker.failed.connect(self.on_failed)
        self._worker.start()

    # 已移除“投屏”功能

    def on_browse_logs_clicked(self):
        # 基于当前选择的服务集合获取候选日志列表
        service = self.combo_service.currentText()
        if self.selected_services:
            service_names = list(self.selected_services)
        else:
            if service.lower() == "all":
                service_names = list(SERVICES)
            elif service.lower() == "none":
                service_names = []
            else:
                service_names = [service]
        files = get_files_in_folder("sdcard/pudu/log")
        if not files:
            self.append_log("No logs found in sdcard/pudu/log")
            return
        # 过滤：服务前缀（若设置）+ 名称包含 pdlog
        def match_service(name: str) -> bool:
            if not service_names:
                return False
            nlow = name.lower()
            for svc in service_names:
                if nlow.startswith(svc.lower()):
                    return True
            return False
        def is_pdlog(name: str) -> bool:
            nl = name.lower()
            return "pdlog" in nl
        candidates = []
        if service.lower() == "all" and not self.selected_services:
            candidates = [n for n in files if is_pdlog(n)]
        else:
            candidates = [n for n in files if is_pdlog(n) and match_service(n)]
        # 去重并按名称排序
        seen = set()
        ordered = []
        for n in candidates:
            if n not in seen:
                seen.add(n)
                ordered.append(n)
        ordered.sort()
        # 刷新列表
        self.lst_logs.clear()
        for n in ordered:
            self.lst_logs.addItem(n)
        self.lbl_browse_count.setText(f"({len(ordered)})")
        self.append_log(f"Listed {len(ordered)} logs.")

    def on_kill_clicked(self):
        if self._kill_worker is not None and self._kill_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Kill task is running, please wait...")
            return
        delete_pdlog = self.chk_delete_pdlog.isChecked()
        self.append_log(f"Start kill. delete_pdlog={delete_pdlog}")
        self._kill_worker = KillWorker(KILL_PACKAGES, delete_pdlog)
        self._kill_worker.progress.connect(self.append_log)
        self._kill_worker.done.connect(lambda: QMessageBox.information(self, "完成", "Kill 完成"))
        self._kill_worker.failed.connect(lambda msg: QMessageBox.critical(self, "失败", f"Kill 失败\n{msg}"))
        self._kill_worker.start()

    def on_done(self, target_dir):
        self.append_log(f"Done. Output: {target_dir}")
        QMessageBox.information(self, "完成", f"拉取完成\n{target_dir}")

    def on_failed(self, message):
        self.append_log(f"Failed: {message}")
        QMessageBox.critical(self, "失败", f"拉取失败\n{message}")


def main():
    # 每次执行 main 时触发一次打包（仅在源码态）
    trigger_pack_once()
    app = QApplication(sys.argv)
    win = LogPullWindow()
    win.show()
    sys.exit(app.exec_())


#打包exe的命令：D:\python\Scripts\pyinstaller -w -F -i img.png -n PullLogUI main.py
# -w 去除控制台窗口；-F 打包dist目录下的文件夹，生成单exe程序，不然只能在dist 目录下运行exe；-i 图标； -n exe的名称
if __name__ == "__main__":
    main()

