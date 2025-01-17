#!/bin/bash
sudo qemu-system-x86_64 \
  -cpu host \
  -enable-kvm \
  -m 500M \
  -chardev socket,path=/tmp/port0,server=on,wait=off,id=char0 \
  -device virtio-serial \
  -device virtconsole,chardev=char0,id=ushell,nr=0 \
  -fsdev local,id=myid,path="$(pwd)/fs0",security_model=none \
  -device virtio-9p-pci,fsdev=myid,mount_tag=fs0,disable-modern=on,disable-legacy=off \
  -kernel build/ubpf_tracer_kvm-x86_64 \
  -nographic
