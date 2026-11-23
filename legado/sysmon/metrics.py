"""Coleta de métricas do sistema (CPU, GPU, memória, rede, disco, temperaturas, processos)."""

import ctypes
import glob
import os
import time
from collections import deque

import psutil

HISTORY = 60  # amostras (1 por segundo)

# Interfaces virtuais que não representam tráfego real de entrada/saída da máquina
_VIRTUAL_NIC_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "vnet", "tun", "tap", "wg")


# --------------------------------------------------------------------------- GPU (NVML)
class _NvmlUtil(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvmlMem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class NvidiaGPU:
    """Leitura da GPU NVIDIA via libnvidia-ml (sem subprocessos)."""

    def __init__(self):
        self.ok = False
        self.name = "GPU"
        try:
            self.lib = ctypes.CDLL("libnvidia-ml.so.1")
            if self.lib.nvmlInit_v2() != 0:
                return
            self.handle = ctypes.c_void_p()
            if self.lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.handle)) != 0:
                return
            buf = ctypes.create_string_buffer(96)
            if self.lib.nvmlDeviceGetName(self.handle, buf, 96) == 0:
                self.name = buf.value.decode().replace("NVIDIA ", "").replace("GeForce ", "")
            self.power_limit = self._uint("nvmlDeviceGetEnforcedPowerLimit") / 1000 or None
            self.ok = True
        except OSError:
            pass

    def _uint(self, fn, *args):
        val = ctypes.c_uint(0)
        if getattr(self.lib, fn)(self.handle, *args, ctypes.byref(val)) != 0:
            return 0
        return val.value

    def read(self):
        util = _NvmlUtil()
        mem = _NvmlMem()
        self.lib.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(util))
        self.lib.nvmlDeviceGetMemoryInfo(self.handle, ctypes.byref(mem))
        return {
            "util": float(util.gpu),
            "mem_used": mem.used,
            "mem_total": mem.total,
            "temp": self._uint("nvmlDeviceGetTemperature", 0),  # 0 = sensor do chip
            "power": self._uint("nvmlDeviceGetPowerUsage") / 1000,  # mW -> W
            "clock": self._uint("nvmlDeviceGetClockInfo", 0),  # 0 = clock gráfico (MHz)
            "fan": self._uint("nvmlDeviceGetFanSpeed"),
        }


# --------------------------------------------------------------------------- helpers
def _cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    name = line.split(":", 1)[1].strip()
                    for junk in ("AMD ", "Intel(R) ", "Core(TM) ", " Processor", "-Core"):
                        name = name.replace(junk, "")
                    return " ".join(name.split()[:3])
    except OSError:
        pass
    return "CPU"


def _find_hwmon_input(candidates):
    """Acha o arquivo tempN_input do primeiro chip/label da lista [(chip, (labels...)), ...]."""
    base = "/sys/class/hwmon"
    try:
        mons = sorted(os.listdir(base))
    except OSError:
        return None
    for chip, labels in candidates:
        for mon in mons:
            d = os.path.join(base, mon)
            try:
                with open(os.path.join(d, "name")) as f:
                    if f.read().strip() != chip:
                        continue
                files = os.listdir(d)
            except OSError:
                continue
            inputs = sorted(x for x in files if x.startswith("temp") and x.endswith("_input"))
            for inp in inputs:
                lbl_file = os.path.join(d, inp.replace("_input", "_label"))
                try:
                    with open(lbl_file) as f:
                        lbl = f.read().strip()
                except OSError:
                    lbl = ""
                if not labels or lbl in labels:
                    return os.path.join(d, inp)
    return None


def _read_temp(path):
    if not path:
        return None
    try:
        with open(path) as f:
            return int(f.read()) / 1000
    except (OSError, ValueError):
        return None


CPU_TEMP_SOURCES = [("k10temp", ("Tctl", "Tdie")), ("zenpower", ("Tdie",)),
                    ("coretemp", ("Package id 0",)), ("k10temp", ()), ("cpu_thermal", ())]


def _net_bytes():
    rx = tx = 0
    for nic, c in psutil.net_io_counters(pernic=True).items():
        if nic.startswith(_VIRTUAL_NIC_PREFIXES):
            continue
        rx += c.bytes_recv
        tx += c.bytes_sent
    return rx, tx


# Pontos de montagem monitorados (cada um vira uma linha no card)
MOUNTS = ("/", "/home")


class Disk:
    """Uma partição montada: uso do sistema de arquivos + velocidade de leitura/escrita."""

    def __init__(self, mount, device):
        self.mount = mount
        self.dev = os.path.basename(os.path.realpath(device))  # ex.: nvme1n1p2, sdb1, dm-0
        sys_path = os.path.realpath(f"/sys/class/block/{self.dev}")
        parent = os.path.dirname(sys_path) if os.path.exists(f"{sys_path}/partition") else sys_path
        disk = os.path.basename(parent)
        self.model = _read_str(f"{parent}/device/model")
        if disk.startswith("nvme"):
            self.kind = "NVMe"
        else:
            self.kind = "HD" if _read_str(f"{parent}/queue/rotational") == "1" else "SSD"
        # NVMe expõe hwmon direto; SATA só com o módulo drivetemp carregado
        temps = glob.glob(f"{parent}/device/hwmon*/temp1_input") + \
            glob.glob(f"{parent}/device/hwmon/hwmon*/temp1_input")
        self.temp_path = temps[0] if temps else None
        self._last = None

    def io(self, counters, dt):
        c = counters.get(self.dev)
        if not c:
            return 0.0, 0.0
        now = (c.read_bytes, c.write_bytes)
        last, self._last = self._last, now
        if not last:
            return 0.0, 0.0
        return max(now[0] - last[0], 0) / dt, max(now[1] - last[1], 0) / dt


def _read_str(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _resolve_disks(mounts):
    by_mount = {p.mountpoint: p.device for p in psutil.disk_partitions(all=False)}
    disks, seen = [], set()
    for m in mounts:
        dev = by_mount.get(m)
        if not dev:
            continue
        d = Disk(m, dev)
        if d.dev in seen:  # /home na mesma partição do /
            continue
        seen.add(d.dev)
        disks.append(d)
    return disks


# --------------------------------------------------------------------------- coletor
class Collector:
    def __init__(self):
        self.cpu_model = _cpu_model()
        self.threads = psutil.cpu_count()
        self.gpu = NvidiaGPU()
        self._cpu_temp_path = _find_hwmon_input(CPU_TEMP_SOURCES)
        self.disks = _resolve_disks(MOUNTS)

        z = lambda: deque([0.0] * HISTORY, maxlen=HISTORY)  # noqa: E731
        self.h = {k: z() for k in ("cpu", "gpu", "ram", "rx", "tx", "rd", "wr")}
        self.cur = {}
        self.procs = []
        self._seeded = False
        self._procs_at = 0.0

        psutil.cpu_percent(percpu=True)
        self._net = _net_bytes()
        counters = psutil.disk_io_counters(perdisk=True) or {}
        for d in self.disks:
            d.io(counters, 1)
        self._t = time.monotonic()
        self._prime_procs()

    def _prime_procs(self):
        for p in psutil.process_iter():
            try:
                p.cpu_percent(None)
            except psutil.Error:
                pass

    def sample(self, with_procs=False):
        now = time.monotonic()
        dt = max(now - self._t, 1e-3)
        self._t = now

        cores = psutil.cpu_percent(percpu=True)
        cpu = sum(cores) / len(cores)
        freq = psutil.cpu_freq()
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()

        rx, tx = _net_bytes()
        rx_s, tx_s = max(rx - self._net[0], 0) / dt, max(tx - self._net[1], 0) / dt
        self._net = (rx, tx)

        counters = psutil.disk_io_counters(perdisk=True) or {}
        disks = []
        for d in self.disks:
            r, w = d.io(counters, dt)
            try:
                u = psutil.disk_usage(d.mount)
            except OSError:
                continue
            disks.append({"mount": d.mount, "kind": d.kind, "model": d.model, "rd": r, "wr": w,
                          "used": u.used, "total": u.total, "percent": u.percent,
                          "temp": _read_temp(d.temp_path)})
        rd_s = sum(x["rd"] for x in disks)
        wr_s = sum(x["wr"] for x in disks)

        gpu = self.gpu.read() if self.gpu.ok else None

        self.cur = {
            "cpu": cpu,
            "cores": cores,
            "freq": freq.current if freq else 0,
            "load": os.getloadavg()[0],
            "cpu_temp": _read_temp(self._cpu_temp_path),
            "ram": vm.percent,
            "ram_used": vm.total - vm.available,
            "ram_total": vm.total,
            "ram_cache": getattr(vm, "cached", 0) + getattr(vm, "buffers", 0),
            "swap": sw.percent,
            "swap_used": sw.used,
            "swap_total": sw.total,
            "rx": rx_s,
            "tx": tx_s,
            "rx_total": rx,
            "tx_total": tx,
            "rd": rd_s,
            "wr": wr_s,
            "disks": disks,
            "gpu": gpu,
        }
        for k, v in (("cpu", cpu), ("gpu", gpu["util"] if gpu else 0), ("ram", vm.percent),
                     ("rx", rx_s), ("tx", tx_s), ("rd", rd_s), ("wr", wr_s)):
            if not self._seeded and k in ("cpu", "gpu", "ram"):
                self.h[k].extend([v] * HISTORY)  # evita o "degrau" a partir do zero no início
            else:
                self.h[k].append(v)
        self._seeded = True

        # Processos são mais caros de ler: só no modo avançado e a cada 2 s
        if with_procs and now - self._procs_at >= 2:
            self._procs_at = now
            self.procs = self._top_procs()
        return self.cur

    def _top_procs(self, n=3):
        ncpu = self.threads or 1
        rows = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                c = p.cpu_percent(None) / ncpu  # % da máquina inteira, não de 1 núcleo
            except psutil.Error:
                continue
            mi = p.info["memory_info"]
            rows.append((c, mi.rss if mi else 0, p.info["name"] or "?"))
        rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
        return rows[:n]
