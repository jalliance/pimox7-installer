# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of first-boot installer scripts and boot-partition config files that turn a freshly flashed DietPi image into a PiMox7 (unofficial Proxmox VE 7 for ARM64) node. There is no build system, test suite, or package — the "artifacts" are shell scripts and `/boot/` config files that are consumed by DietPi's automation on the target SBC.

## Repository layout

- `dietpi/` — Target: Raspberry Pi 3B+ / 4B using the DietPi Bullseye RPi image. Ships `dietpi.txt`, `config.txt`, and `Automation_Custom_Script.sh`.
- `rockpi4a/` — Target: Radxa ROCK Pi 4A using the DietPi Bullseye ROCKPi4 image. Ships `dietpi.txt`, `armbianEnv.txt`, and `Automation_Custom_Script.sh`. Note: VMs don't work here (`kvm_arm_vcpu_init failed`) and containers need an AppArmor workaround — see `rockpi4a/README.md`.
- `rpios/` — README-only pointer to an interactive installer hosted in the `TuxfeatMac/pimox7` fork. No scripts live here.
- `standalone/` — Placeholder, empty.

## How the install actually runs

There is no local dev loop. The end-to-end cycle is:

1. User flashes the vendor DietPi image to an SD card.
2. User copies the files from one of `dietpi/` or `rockpi4a/` into the card's `/boot/` FAT partition, overwriting the vendor `dietpi.txt` / `config.txt`.
3. User edits `dietpi.txt` to set `AUTO_SETUP_NET_HOSTNAME`, `AUTO_SETUP_NET_STATIC_IP`, `AUTO_SETUP_NET_STATIC_MASK`, `AUTO_SETUP_NET_STATIC_GATEWAY`, `AUTO_SETUP_NET_STATIC_DNS`, locale, timezone, and password. User optionally edits the `CONFIGURE-OPTIONS` block at the top of `Automation_Custom_Script.sh`.
4. DietPi boots, applies its own automation from `dietpi.txt`, and then invokes `/boot/Automation_Custom_Script.sh` as root.
5. The custom script reboots at the end; PiMox7 web UI lands on `https://<IP>:8006/`.

Because the script only runs on a real target device, changes cannot be validated in this repo — review by reading diffs and, where possible, shellcheck-ing the script. Treat a commit as the release.

## Conventions for editing `Automation_Custom_Script.sh`

Both variants (`dietpi/`, `rockpi4a/`) share the same shape — keep them aligned when changing one, unless the change is platform-specific.

- **Config block**: User-tunable flags live in a banner-fenced `CONFIGURE-OPTIONS` section at the top (`CONFIG_ZRAM`, `ZRAM`, `CONFIG_SWAP`, `SWAP`, `GET_STD_CTS`, `GET_STD_ISO`, `CONF_BANNER`). The defaults shown in the comment column are the intended out-of-box behavior; preserve that column alignment when adding flags.
- **Network inputs are scraped from `/boot/dietpi.txt`** (not passed in): `RPI_IP`, `NETMASK`, `GATEWAY`, `HOSTNAME` are read via `grep ... | cut -d '=' -f 2`. If you add a new input, follow the same pattern and namespace it under `AUTO_SETUP_NET_*` or a new `AUTO_SETUP_*` key in `dietpi.txt`.
- **Two-phase network rewrite**: the script first writes a plain static `eth0` config to `/etc/network/interfaces` so the PiMox7 `apt install` can succeed, then writes a bridged `vmbr0`-on-`eth0` config to `/etc/network/interfaces.new` which PVE promotes on reboot. Do not collapse these into one step.
- **Known latent bug**: `$RPI_IP_ONLY` is referenced in the first `/etc/hosts` write but is never assigned. It expands to empty, so the line becomes `\t<HOSTNAME>`. The second `/etc/hosts` write (further down) uses `$RPI_IP` correctly. Fix both sites if you touch this.
- **Non-interactive apt**: PVE and ZFS installs must stay `DEBIAN_FRONTEND=noninteractive apt install -y -o Dpkg::Options::="--force-confdef" ...` — they will hang on config prompts otherwise.
- **Pimox repo + key**: added via `/etc/apt/sources.list.d/pimox.list` and `apt-key add -` from `https://raw.githubusercontent.com/pimox/pimox7/master/`. `apt-key` is deprecated on newer Debian; if upgrading, migrate to `/etc/apt/keyrings/` + `signed-by=`.
- **Platform kernel headers differ**: `dietpi/` installs `raspberrypi-kernel-headers`, `rockpi4a/` installs `linux-headers-current-rockchip64`. ZFS-DKMS builds against whichever is present — don't cross-pollinate.
- **Banner patch**: `CONF_BANNER=yes` `sed`s the PVE no-subscription nag in `/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js`. The search string (`return Ext.String.format('`) is PVE-version-sensitive; if Pimox bumps the bundled widget toolkit, this regex may need updating.
- **Script ends with `reboot`**; anything added must come before `sleep 15 && reboot`.

## Platform-specific files

- `dietpi/config.txt` — Raspberry Pi firmware config. Notable choices: `arm_64bit=1`, WiFi+BT disabled via `dtoverlay`, `cgroup_enable=...` is *not* here — the script patches `/boot/cmdline.txt` at runtime to enable cpuset/memory cgroups so PVE container stats render.
- `rockpi4a/armbianEnv.txt` — U-Boot env for the RockPi. `fdtfile=rockchip/rk3399-rock-pi-4a.dtb` pins the 4A device tree specifically (not 4B); the directory name `rockpi4a` is meaningful.
- `dietpi/dietpi.txt` and `rockpi4a/dietpi.txt` — The first ~25 lines are a custom PVE-config header added by this repo; everything below is the upstream DietPi template. Preserve that split when syncing from upstream DietPi.
