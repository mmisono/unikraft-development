#!/usr/bin/env python3

import json
import os
import re
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from shlex import quote
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator, List, Text, Optional

from root import TEST_ROOT, PROJECT_ROOT
from procs import run, pprint_cmd, ChildFd


@dataclass
class VmImage:
    kernel: Path
    ## kernel headers & buildsystem
    kerneldir: Path
    squashfs: Path
    initial_ramdisk: Path
    kernel_params: List[str]


@dataclass
class VmSpec:
    kernel: Path
    app_cmdline: str
    netbridge: bool
    ushell_devices: bool
    initrd: Optional[Path]
    rootfs_9p: Optional[Path]


class QmpSession:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.pending_events: Queue[Dict[str, Any]] = Queue()
        self.reader = sock.makefile("r")
        self.writer = sock.makefile("w")
        hello = self._result()
        assert "QMP" in hello, f"Unexpected result: {hello}"
        self.send("qmp_capabilities")

    def _readmsg(self) -> Dict[str, Any]:
        line = self.reader.readline()
        return json.loads(line)

    def _raise_unexpected_msg(self, msg: Dict[str, Any]) -> None:
        m = json.dumps(msg, sort_keys=True, indent=4)
        raise RuntimeError(f"Got unexpected qmp response: {m}")

    def _result(self) -> Dict[str, Any]:
        while True:
            # QMP is in the handshake
            res = self._readmsg()
            if "return" in res or "QMP" in res:
                return res
            elif "event" in res:
                self.pending_events.put(res)
                continue
            else:
                self._raise_unexpected_msg(res)

    def events(self) -> Iterator[Dict[str, Any]]:
        while not self.pending_events.empty():
            yield self.pending_events.get()

        res = self._readmsg()

        if "event" not in res:
            self._raise_unexpected_msg(res)
        yield res

    def send(self, cmd: str, args: Dict[str, str] = {}) -> Dict[str, str]:
        data: Dict[str, Any] = dict(execute=cmd)
        if args != {}:
            data["arguments"] = args

        json.dump(data, self.writer)
        self.writer.write("\n")
        self.writer.flush()
        return self._result()


def is_port_open(ip: str, port: int, wait_response: bool = False) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((ip, int(port)))
        if wait_response:
            s.recv(1)
        s.shutdown(2)
        return True
    except Exception:
        return False


@contextmanager
def connect_qmp(path: Path) -> Iterator[QmpSession]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(path))

    try:
        yield QmpSession(sock)
    finally:
        sock.close()


def parse_regs(qemu_output: str) -> Dict[str, int]:
    regs = {}
    for match in re.finditer(r"(\S+)\s*=\s*([0-9a-f ]+)", qemu_output):
        name = match.group(1)
        content = match.group(2).replace(" ", "")
        regs[name.lower()] = int(content, 16)
    return regs


def get_ssh_port(session: QmpSession) -> int:
    usernet_info = session.send(
        "human-monitor-command", args={"command-line": "info usernet"}
    )
    ssh_port = None
    for l in usernet_info["return"].splitlines():
        fields = l.split()
        if "TCP[HOST_FORWARD]" in fields and "22" in fields:
            ssh_port = int(l.split()[3])
    assert ssh_port is not None
    return ssh_port


def ssh_cmd(port: int) -> List[str]:
    key_path = TEST_ROOT.joinpath("..", "nix", "ssh_key")
    key_path.chmod(0o400)
    return [
        "ssh",
        "-i",
        str(key_path),
        "-p",
        str(port),
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=no",
        "-oConnectTimeout=5",
        "-oUserKnownHostsFile=/dev/null",
        "root@127.0.1",
    ]


class QemuVm:
    def __init__(self, qmp_session: QmpSession, tmux_session: str, pid: int, ushell_socket: Optional[Path]) -> None:
        self.qmp_session = qmp_session
        self.tmux_session = tmux_session
        self.pid = pid
        self.ssh_port = 0 # get_ssh_port(qmp_session) # TODO
        self.ushell_socket = ushell_socket

    def events(self) -> Iterator[Dict[str, Any]]:
        return self.qmp_session.events()

    def wait_for_ssh(self) -> None:
        """
        Block until ssh port is accessible
        """
        print(f"wait for ssh on {self.ssh_port}")
        while True:
            if (
                self.ssh_cmd(
                    ["echo", "ok"],
                    check=False,
                    stderr=subprocess.DEVNULL,
                    verbose=False,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.1)

    def wait_for_ping(self, host: str) -> None:
        """
        Block until icmp is responding
        @host: example: 172.44.0.2
        """
        timeout = 0.5
        max_ = int(1/timeout * 60)
        for i in range(0, max_):
            response = run(["ping", "-c", "1", "-W", f"{timeout}", f"{host}"], check=False)
            if response.returncode == 0:
                return # its up
        raise Exception(f"VM is still not responding after {max_}sec")

    def ssh_Popen(
        self,
        stdout: ChildFd = subprocess.PIPE,
        stderr: ChildFd = None,
        stdin: ChildFd = None,
    ) -> subprocess.Popen:
        """
        opens a background process with an interactive ssh session
        """
        cmd = ssh_cmd(self.ssh_port)
        pprint_cmd(cmd)
        return subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr)

    def ssh_cmd(
        self,
        argv: List[str],
        extra_env: Dict[str, str] = {},
        check: bool = True,
        stdin: ChildFd = None,
        stdout: ChildFd = subprocess.PIPE,
        stderr: ChildFd = None,
        verbose: bool = True,
    ) -> "subprocess.CompletedProcess[Text]":
        """
        @return: CompletedProcess.stderr/stdout contains output of `cmd` which
        is run in the vm via ssh.
        """
        env_cmd = []
        if len(extra_env):
            env_cmd.append("env")
            env_cmd.append("-")
            for k, v in extra_env.items():
                env_cmd.append(f"{k}={v}")
        cmd = ssh_cmd(self.ssh_port) + ["--"] + env_cmd + [" ".join(map(quote, argv))]
        return run(
            cmd, stdin=stdin, stdout=stdout, stderr=stderr, check=check, verbose=verbose
        )

    def regs(self) -> Dict[str, int]:
        """
        Get cpu register:
        TODO: add support for multiple cpus
        """
        res = self.send(
            "human-monitor-command", args={"command-line": "info registers"}
        )
        return parse_regs(res["return"])

    def dump_physical_memory(self, addr: int, num_bytes: int) -> bytes:
        res = self.send(
            "human-monitor-command",
            args={"command-line": f"xp/{num_bytes}bx 0x{addr:x}"},
        )
        hexval = "".join(
            m.group(1) for m in re.finditer("0x([0-9a-f]{2})", res["return"])
        )
        return bytes.fromhex(hexval)

    def attach(self) -> None:
        """
        Attach to qemu session via tmux. This is useful for debugging
        """
        subprocess.run(["tmux", "-L", self.tmux_session, "attach"])

    def send(self, cmd: str, args: Dict[str, str] = {}) -> Dict[str, str]:
        """
        Send a Qmp command (https://wiki.qemu.org/Documentation/QMP)
        """
        return self.qmp_session.send(cmd, args)


def qemu_command_unreachable(
    image: VmImage, qmp_socket: Path, ssh_port: int = 0
) -> List:
    """
    @image VM image to boot
    @qmp_socket unixsocket path of the QEMU qmp control socket
    @ssh_port host port bound to vm guest port (0 means dynamic port)
    """
    params = " ".join(image.kernel_params)
    return [
        "qemu-system-x86_64",
        "-enable-kvm",
        "-name",
        "test-os",
        "-m",
        "512",
        "-drive",
        f"id=drive1,file={image.squashfs},readonly=on,media=cdrom,format=raw,if=none",
        "-device",
        "virtio-blk-pci,drive=drive1,bootindex=1",
        "-kernel",
        f"{image.kernel}/bzImage",
        "-initrd",
        str(image.initial_ramdisk),
        "-nographic",
        "-serial",
        "null",
        "-device",
        "virtio-serial",
        "-chardev",
        "stdio,mux=on,id=char0,signal=off",
        "-mon",
        "chardev=char0,mode=readline",
        "-device",
        "virtconsole,chardev=char0,nr=0",
        "-append",
        f"console=hvc0 {params} quiet panic=-1",
        "-netdev",
        f"user,id=n1,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
        "-device",
        "virtio-net-pci,netdev=n1",
        "-virtfs",
        f"local,path={PROJECT_ROOT},security_model=none,mount_tag=vmsh",
        "-qmp",
        f"unix:{str(qmp_socket)},server,nowait",
        "-no-reboot",
        "-device",
        "virtio-rng-pci",
    ]


def qemu_command(
    spec: VmSpec,
    qmp_socket: Path,
    ushell_socket = Optional[Path],
    cpu_pinning: Optional[str] = None,
) -> List[str]:
    cmd = [ ]

    # general args

    if cpu_pinning is not None:
        cmd += [
            "taskset",
            "-c",
            cpu_pinning,
        ]

    cmd += [
        "qemu-system-x86_64",
        "-enable-kvm",
        "-cpu",
        "host",
        "-m",
        "1024",
        "-kernel",
        f"{spec.kernel}",
        "-nographic",
        "-qmp",
        f"unix:{str(qmp_socket)},server,nowait",
    ]

    # kernel cmdline

    uk_cmdline = ""
    if spec.netbridge:
        uk_cmdline += "netdev.ipv4_addr=172.44.0.2 netdev.ipv4_gw_addr=172.44.0.1 netdev.ipv4_subnet_mask=255.255.255.0"
    cmdline = f"{uk_cmdline} -- {spec.app_cmdline}"
    cmd += ["-append", cmdline]

    # other devices

    if spec.netbridge:
        cmd += [
            "-netdev",
            "bridge,id=en0,br=virbr0",
            "-device",
            "virtio-net-pci,netdev=en0",
        ]

    if spec.ushell_devices:
        if ushell_socket is None:
            raise Exception("ushell devices are activated but ushell socket is not defined")
        cmd += [
            "-chardev",
            f"socket,path={ushell_socket},server=on,wait=off,id=char0",
            "-device",
            "virtio-serial",
            "-device",
            "virtconsole,chardev=char0,id=ushell,nr=0",
        ]

    if spec.initrd is not None:
        cmd += ["-initrd", f"{spec.initrd}"]

    if spec.rootfs_9p is not None:
        cmd += [
            "-fsdev",
            f"local,id=myid,path={spec.rootfs_9p},security_model=none",
            "-device",
            "virtio-9p-pci,fsdev=myid,mount_tag=fs0,disable-modern=on,disable-legacy=off",
        ]

    return cmd


@contextmanager
def spawn_qemu(
    image: VmSpec,
    extra_args: List[str] = [],
    extra_args_pre: List[str] = [],
    cpu_pinning: Optional[str] = None,
) -> Iterator[QemuVm]:
    with TemporaryDirectory() as tempdir:
        qmp_socket = Path(tempdir).joinpath("qmp.sock")
        ushell_socket: Optional[Path] = Path(tempdir).joinpath("ushell.sock") if image.ushell_devices else None
        cmd = extra_args_pre.copy()
        cmd += qemu_command(image, qmp_socket, ushell_socket)
        cmd += extra_args
        # cmd += [ "&&", "sleep", "99999" ]
        # cmd = [ "bash", "-c", "echo foobar && sleep 99999" ]

        tmux_session = f"pytest-{os.getpid()}"
        tmux = [
            "tmux",
            "-L",
            tmux_session,
            "new-session",
            "-s",
            "qemu",
            "-d",  # QEMU_DEBUG: for debugging early qemu crashes, comment this and switch the following two lines:
            " ".join(map(quote, cmd)),
            # " ".join(map(quote, cmd)) + " |& tee /tmp/foo; sleep 999999",
        ]
        print("$ " + " ".join(map(quote, tmux)))
        # breakpoint()
        subprocess.run(tmux, check=True)
        try:
            proc = subprocess.run(
                [
                    "tmux",
                    "-L",
                    tmux_session,
                    "list-panes",
                    "-a",
                    "-F",
                    "#{pane_pid}",
                ],
                stdout=subprocess.PIPE,
                check=True,
            )
            qemu_pid = int(proc.stdout)
            while not qmp_socket.exists():
                try:
                    os.kill(qemu_pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    raise Exception("Qemu vm was terminated quickly. Check QEMU_DEBUG above.")
            with connect_qmp(qmp_socket) as session:
                yield QemuVm(session, tmux_session, qemu_pid, ushell_socket)
        finally:
            subprocess.run(["tmux", "-L", tmux_session, "kill-server"])
            while True:
                try:
                    os.kill(qemu_pid, 0)
                except ProcessLookupError:
                    break
                else:
                    print("waiting for qemu to stop")
                    time.sleep(1)