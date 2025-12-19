#!/bin/bash

set -eou pipefail

if [ "${CHROOT:-'unset'}" == "unset" ]; then
    echo "CHROOT was not provided."
    exit 1
fi
version="${VERSION:-dev}"

# Make sure it's installed
sudo apt install -y debootstrap

set -o xtrace

# Create root filesystem build directory
mkdir "$CHROOT/sgwfs"

# Install debian/trixie into build directory
sudo debootstrap --variant=minbase trixie "$CHROOT/sgwfs" http://deb.debian.org/debian

# Add current resolv.conf for network resolution
sudo cp /etc/resolv.conf "$CHROOT/sgwfs/etc/resolv.conf"

# Install the sgwtool
sudo install -Dm755 "$CHROOT/sgwtool/cli.py" "$CHROOT/sgwfs/usr/local/bin/sgwtool"

# Mount these for chroot
sudo mount --bind /proc "$CHROOT/sgwfs/proc"
sudo mount --bind /sys  "$CHROOT/sgwfs/sys"
sudo mount --bind /dev  "$CHROOT/sgwfs/dev"

# Run commands to configure the root filesystem
sudo chroot "$CHROOT/sgwfs" apt update -y
sudo chroot "$CHROOT/sgwfs" apt install -y systemd-sysv frr nftables iproute2 netbase procps curl ca-certificates iputils-ping
sudo chroot "$CHROOT/sgwfs" systemctl enable nftables
sudo chroot "$CHROOT/sgwfs" systemctl enable frr

# Unmount 
sudo umount "$CHROOT/sgwfs/proc"
sudo umount "$CHROOT/sgwfs/sys"
sudo umount "$CHROOT/sgwfs/dev"

# Remove resolv.conf from root filesystem
sudo rm -f "$CHROOT/sgwfs/etc/resolv.conf"

# Create tarball for usage as LXC appliance
sudo tar --numeric-owner -czf "sector-gateway-${version}.tar.gz" -C "$CHROOT/sgwfs" .
sha256sum sector-gateway-${version}.tar.gz > sector-gateway-${version}.tar.gz.sha256
