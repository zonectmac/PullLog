import subprocess
import os
from datetime import datetime


def adb_command(command):
    try:
        # Windows 下隐藏控制台窗口
        startupinfo = None
        creationflags = 0
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            ['adb', *command],
            capture_output=True,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        return stdout.strip()
    except Exception as e:
        # 失败保底返回空
        return ""


def get_files_in_folder(folder_path):
    files = adb_command(['shell', 'ls', folder_path]).splitlines()
    return files


def find_files_recursive(folder_path, file_extension):
    files = []
    folder_contents = get_files_in_folder(folder_path)
    for item in folder_contents:
        item_path = os.path.join(folder_path, item)
        if item.endswith(file_extension):
            files.append(item_path)
        elif adb_command(['shell', 'test', '-d', item_path]):
            files.extend(find_files_recursive(item_path, file_extension))
    return files


def pull_recent_log(number):
    logs = get_files_in_folder("sdcard/pudu/log")
    need_pull_log_name = []
    log_list_number = []
    for log in logs:
        if len(log.split(".")) > 3:
            log_list_number.append(int(log.split(".")[3]))
            print(log, log.split(".")[3])
        else:
            print(log)
    maxid = max(log_list_number)
    print(maxid, maxid - number)
    for log in logs:
        if len(log.split(".")) > 3:
            if int(log.split(".")[3]) > (maxid - number):
                need_pull_log_name.append(log)
    now = datetime.now()
    current_time = now.strftime("%Y%m%d%H%M%S")
    pull_to_dir = "E:\\pudu\\log\\" + current_time
    os.makedirs(pull_to_dir)
    for log in need_pull_log_name:
        adb_command(['pull', "sdcard/pudu/log/" + log, pull_to_dir])
        # os.system("adb pull sdcard/pudu/log/"+log+" "+pull_to_dir)
        print("need pull ", log)
    # adb_command(['pull', "sdcard/pudu/log/kernel", pull_to_dir])
    # adb_command(['pull', "data/anr", pull_to_dir])
    subprocess.call(["explorer", pull_to_dir])


def pull_process_log(process, number):
    command = "adb shell ls sdcard/pudu/log | findstr " + process
    logs = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()
    need_pull_log_name = []
    log_list_number = []
    for log in logs:
        if len(log.split(".")) > 3:
            log_list_number.append(int(log.split(".")[3]))
            print(log, log.split(".")[3])
        else:
            print(log)
    maxid = max(log_list_number)
    print(maxid, maxid - number)
    for log in logs:
        if len(log.split(".")) > 3:
            if int(log.split(".")[3]) > (maxid - number):
                need_pull_log_name.append(log)
    now = datetime.now()
    current_time = now.strftime("%Y%m%d%H%M%S")
    pull_to_dir = "E:\\pudu\\log\\" + current_time
    os.makedirs(pull_to_dir)
    for log in need_pull_log_name:
        adb_command(['pull', "sdcard/pudu/log/" + log, pull_to_dir])
        # os.system("adb pull sdcard/pudu/log/"+log+" "+pull_to_dir)
        print("need pull ", log)
    adb_command(['pull', "sdcard/pudu/log/kernel", pull_to_dir])
    # adb_command(['pull', "data/anr", pull_to_dir])
    subprocess.call(["explorer", pull_to_dir])


if __name__ == '__main__':
    pull_recent_log(30)
    # pull_process_log("pudutech-maptools", 5)
    # pull_process_log("HardwareService", 1)
