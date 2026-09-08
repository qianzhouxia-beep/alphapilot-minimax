# -*- coding: utf-8 -*-
"""上传 AlphaPilot 备份: 本地 → 上海 → 新加坡 (中转链路)
本地→上海 paramiko sftp; 上海→新加坡 免密 scp
断线重试, 批级校验 (文件存在+大小一致)
"""
import os, sys, time, stat
import paramiko

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SH_HOST = "150.158.100.236"
SH_USER = "ubuntu"
SH_KEY = r"C:\Users\elvisq\Downloads\AlphaPiolot.pem"
SG_HOST = "43.156.119.47"
SG_USER = "ubuntu"
SG_PWD = "Sef-9i7k]1zjicK6Nv"

LOCAL = r"C:\Users\elvisq\Projects\alphapilot\backup_alphapilot_20260829_214851.tar.gz"
SH_TMP = "/home/ubuntu/alphapilot/backup_alphapilot_20260829.tar.gz"
SG_DIR = "/home/ubuntu/alphapilot/backups"
MAX_ATTEMPTS = 6


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh_connect():
    sh = paramiko.SSHClient()
    sh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sh.connect(SH_HOST, username=SH_USER, key_filename=SH_KEY, timeout=30)
    return sh


def sg_connect():
    sg = paramiko.SSHClient()
    sg.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sg.connect(SG_HOST, username=SG_USER, password=SG_PWD, timeout=30)
    return sg


def up_sh(sftp, local, remote, size):
    sftp.put(local, remote)
    # 校验大小
    try:
        st = sftp.stat(remote)
        if st.st_size == size:
            return True
        log(f"  上海大小不符 {st.st_size} vs {size}, 重传")
        sftp.remove(remote)
        return False
    except Exception:
        return False


def main():
    if not os.path.exists(LOCAL):
        log(f"本地文件不存在: {LOCAL}")
        return 1
    size = os.path.getsize(LOCAL)
    log(f"本地备份: {size/1024/1024:.1f}MB")

    # 阶段1: 本地→上海 (若上海已有完整文件则复用)
    log("阶段1: 本地→上海")
    sh = sh_connect()
    ok = False
    for attempt in range(MAX_ATTEMPTS):
        try:
            sftp = sh.open_sftp()
            try:
                st = sftp.stat(SH_TMP)
                if st.st_size == size:
                    log("  上海已有完整文件, 跳过重传")
                    ok = True
                    sftp.close()
                    break
            except FileNotFoundError:
                pass
            ok = up_sh(sftp, LOCAL, SH_TMP, size)
            sftp.close()
            if ok:
                break
        except Exception as e:
            log(f"  本地→上海断线(第{attempt+1}次): {str(e)[:60]}")
            time.sleep(3)
            try:
                sh.close()
            except Exception:
                pass
            sh = sh_connect()
    if not ok:
        log("本地→上海失败")
        return 1
    log("  本地→上海完成")

    # 阶段2: 上海→新加坡 (免密 scp)
    log("阶段2: 上海→新加坡")
    # 先在新加坡创建目标目录 (scp 目标必须是已存在目录或完整文件名)
    try:
        sg0 = sg_connect()
        sg0.exec_command(f"mkdir -p {SG_DIR}", timeout=30)
        sg0.close()
    except Exception as e:
        log(f"  新加坡建目录异常: {str(e)[:60]}")
    cmd = (
        f"cd /home/ubuntu/alphapilot && "
        f"timeout 3600 scp -o StrictHostKeyChecking=no -o ConnectTimeout=30 "
        f"{SH_TMP} {SG_USER}@{SG_HOST}:{SG_DIR}/backup_alphapilot_20260829.tar.gz && echo SCP_OK"
    )
    sg_ok = False
    for attempt in range(MAX_ATTEMPTS):
        try:
            stdin, stdout, stderr = sh.exec_command(cmd, timeout=3700)
            out = stdout.read().decode()
            err = stderr.read().decode()
            if "SCP_OK" in out:
                sg_ok = True
                break
            log(f"  scp未确认(第{attempt+1}次): {out[-60:]} {err[-60:]}")
            time.sleep(10)
        except Exception as e:
            log(f"  scp异常(第{attempt+1}次): {str(e)[:60]}")
            time.sleep(10)
            try:
                sh.close()
            except Exception:
                pass
            sh = sh_connect()
    if not sg_ok:
        log("上海→新加坡失败")
        return 1
    log("  上海→新加坡完成")

    # 阶段3: 新加坡校验
    log("阶段3: 新加坡校验")
    try:
        sg = sg_connect()
        stdin, stdout, stderr = sg.exec_command(f"ls -la {SG_DIR}/backup_alphapilot_20260829.tar.gz", timeout=30)
        out = stdout.read().decode()
        log(out.strip())
        sg.close()
    except Exception as e:
        log(f"校验异常: {str(e)[:60]}")

    # 清理上海临时文件
    try:
        sh.exec_command(f"rm -f {SH_TMP}")
        log("已清理上海临时文件")
    except Exception:
        pass
    sh.close()
    log("全部完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
