#!/usr/bin/env python3

import functools
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator
from tqdm import tqdm

from qemu import VmImage, NixosVmSpec, UkVmSpec
from root import PROJECT_ROOT


@functools.lru_cache(maxsize=None)
def nix_build(what: str) -> Any:
    path = PROJECT_ROOT.joinpath(".git/nix-results")
    path.mkdir(parents=True, exist_ok=True)
    # gc root to improve caching
    link_name = path.joinpath(what.lstrip(".#"))
    result = subprocess.run(
        ["nix", "build", "--out-link", str(link_name), "--json", what],
        text=True,
        stdout=subprocess.PIPE,
        # check=True,
        cwd=PROJECT_ROOT,
    )
    return json.loads(result.stdout)


def uk_build(name: str) -> Path:
    build = nix_build(name)
    out = build[0]["outputs"]["out"]
    return Path(out)


def uk_sqlite3_backup(shell: str, bootfs: str, bpf: str = "", lto: bool = False) -> UkVmSpec:
    flake_name = f"uk-sqlite3_backup-{shell}"
    if len(bpf): flake_name += f"-{bpf}"
    flake_name += f"-{bootfs}"
    if lto: flake_name += "-lto"
    build = uk_build(f".#{flake_name}")
    kernel = build / "sqlite3_backup_kvm-x86_64"
    initrd = build / "fs0.cpio"
    ushelldir = build / "fs1"
    symfile = ushelldir / "symbol.txt"
    ushell_devices = shell != "noshell"
    return UkVmSpec(
        flake_name=flake_name,
        kernel=kernel,
        app_cmdline="",
        netbridge=False,
        ushell_devices=ushell_devices,
        initrd=initrd,
        ushelldir=ushelldir,
        symfile=symfile,
        rootfs_9p=PROJECT_ROOT / "apps/sqlite_benchmark/fs0",
        fs1_9p=PROJECT_ROOT / "apps/sqlite_benchmark/fs1",
    )


def uk_sqlite(shell: str, bootfs: str, bpf: str = "", lto: bool = False) -> UkVmSpec:
    flake_name = f"uk-sqlite_benchmark-{shell}"
    if len(bpf): flake_name += f"-{bpf}"
    flake_name += f"-{bootfs}"
    if lto: flake_name += "-lto"
    build = uk_build(f".#{flake_name}")
    kernel = build / "sqlite_benchmark_kvm-x86_64"
    initrd = build / "fs0.cpio"
    ushelldir = build / "fs1"
    symfile = ushelldir / "symbol.txt"
    ushell_devices = shell != "noshell"
    return UkVmSpec(
        flake_name=flake_name,
        kernel=kernel,
        app_cmdline="",
        netbridge=False,
        ushell_devices=ushell_devices,
        initrd=initrd,
        ushelldir=ushelldir,
        symfile=symfile,
        rootfs_9p=PROJECT_ROOT / "apps/sqlite_benchmark/fs0",
        fs1_9p=PROJECT_ROOT / "apps/sqlite_benchmark/fs1",
    )


def uk_redis(shell: str, bootfs: str, bpf: str = "", lto: bool = False) -> UkVmSpec:
    flake_name = f"uk-redis-{shell}"
    if len(bpf): flake_name += f"-{bpf}"
    flake_name += f"-{bootfs}"
    if lto: flake_name += "-lto"
    build = uk_build(f".#{flake_name}")
    kernel = build / "redis_kvm-x86_64"
    initrd = build / "fs0.cpio"
    ushelldir = build / "fs1"
    symfile = ushelldir / "symbol.txt"
    ushell_devices = shell != "noshell"
    return UkVmSpec(
        flake_name=flake_name,
        kernel=kernel,
        app_cmdline="/redis.conf",
        netbridge=True,
        ushell_devices=ushell_devices,
        initrd=initrd,
        ushelldir=ushelldir,
        symfile=symfile,
        rootfs_9p=PROJECT_ROOT / "apps/redis/fs0",
        fs1_9p=PROJECT_ROOT / "apps/redis/fs1",
    )


def uk_nginx(shell: str, bootfs: str, bpf: str = "", lto: bool = False) -> UkVmSpec:
    flake_name = f"uk-nginx-{shell}"
    if len(bpf): flake_name += f"-{bpf}"
    flake_name += f"-{bootfs}"
    if lto: flake_name += "-lto"
    build = uk_build(f".#{flake_name}")
    kernel = build / "nginx_kvm-x86_64"
    initrd = build / "fs0.cpio"
    ushelldir = build / "fs1"
    symfile = ushelldir / "symbol.txt"
    ushell_devices = shell != "noshell"
    return UkVmSpec(
        flake_name=flake_name,
        kernel=kernel,
        app_cmdline="-c /nginx/conf/nginx.conf",
        netbridge=True,
        ushell_devices=ushell_devices,
        initrd=initrd,
        ushelldir=ushelldir,
        symfile=symfile,
        rootfs_9p=PROJECT_ROOT / "apps/nginx/fs0",
        fs1_9p=PROJECT_ROOT / "apps/nginx/fs1",
    )


def uk_count(shell: str = "ushell", bpf: str = "", lto: bool = False) -> UkVmSpec:
    flake_name = f"uk-count-{shell}"
    if len(bpf): flake_name += f"-{bpf}"
    if lto: flake_name += "-lto"
    build = uk_build(f".#{flake_name}")
    kernel = build / "count_kvm-x86_64"
    initrd = build / "fs0.cpio"
    ushelldir = build / "fs0"
    symfile = ushelldir / "symbol.txt"
    ushell_devices = shell != "noshell"
    return UkVmSpec(
        flake_name=flake_name,
        kernel=kernel,
        app_cmdline="",
        netbridge=False,
        ushell_devices=ushell_devices,
        initrd=None,
        ushelldir=ushelldir,
        symfile=symfile,
        rootfs_9p=PROJECT_ROOT / "apps/count/fs0",
        fs1_9p=PROJECT_ROOT / "apps/count/fs0",
    )


import shutil
from tempfile import TemporaryDirectory


@contextmanager
def nixos_nginx() -> Iterator[NixosVmSpec]:
    with TemporaryDirectory() as tempdir_:
        tempdir = Path(tempdir_)
        build = uk_build(".#nginx-image")
        qcowRo = build / "nixos.qcow2"  # read only
        qcow = tempdir / "nixos.qcow2"
        shutil.copy(str(qcowRo), str(qcow))
        yield NixosVmSpec(
            qcow=qcow,
            netbridge=True,
            mnt_9p=PROJECT_ROOT
            / "apps/nginx/fs0",  # TODO do tmpdirs as with measure_apps.py run_nginx_native
        )


def writable_image(name: str) -> Iterator[Path]:
    image = nix_build(name)
    out = image[0]["outputs"]["out"]
    with NamedTemporaryFile() as n:
        with open(out, "rb") as f:
            shutil.copyfileobj(f, n)
        n.flush()
        yield Path(n.name)


@contextmanager
def busybox_image() -> Iterator[Path]:
    yield from writable_image(".#busybox-image")


@contextmanager
def alpine_sec_scanner_image() -> Iterator[Path]:
    yield from writable_image(".#alpine-sec-scanner-image")


@contextmanager
def passwd_image() -> Iterator[Path]:
    yield from writable_image(".#passwd-image")


NOTOS_IMAGE = ".#not-os-image"


def notos_image(nix: str = NOTOS_IMAGE) -> VmImage:
    data = nix_build(nix)
    with open(data[0]["outputs"]["out"]) as f:
        data = json.load(f)
        return VmImage(
            kernel=Path(data["kernel"]),
            kerneldir=Path(data["kerneldir"]),
            squashfs=Path(data["squashfs"]),
            initial_ramdisk=Path(data["initialRamdisk"]).joinpath("initrd"),
            kernel_params=data["kernelParams"],
        )


def notos_image_custom_kernel(nix: str = NOTOS_IMAGE) -> VmImage:
    """
    This is useful for debugging.
    Make sure to use the same kernel version in your kernel as used in notos
    """
    image = notos_image(nix)
    image.kerneldir = PROJECT_ROOT.joinpath("..", "linux")
    image.kernel = image.kerneldir.joinpath("arch", "x86", "boot")
    return image

def build_all():
    print("Building all nix (flake) packages in this repository")
    result = subprocess.run(
        ["nix", "flake", "show", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        check=True,
        cwd=PROJECT_ROOT,
    )
    outputs = json.loads(result.stdout)
    for package in tqdm(outputs['packages']['x86_64-linux']):
        print(f"\nBuilding {package}...")
        nix_build(f".#{package}")


if __name__ == "__main__":
    build_all()
