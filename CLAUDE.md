# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of **boot-time installer scripts and SD-card boot-partition config files** that turn a freshly flashed DietPi (or Raspberry Pi OS) image into a PiMox7 node — i.e. an unofficial Proxmox VE 7 install for ARM64 SBCs (Raspberry Pi 3B+/4B and Rock Pi 4A).

There is **no build system, no test suite, no linter, no package manifest**. The "artifacts" are the files themselves; the user copies them onto the FAT `/boot/` partition of a flashed SD card before first boot.

## Repo layout (one folder per target image)

- `dietpi/` — DietPi image for Raspberry Pi 4B (fully headless install). Contains `dietpi.txt`, `config.txt`, and `Automation_Custom_Script.sh`.
- `rockpi4a/` — DietPi image for Rock Pi 4A. Contains `dietpi.txt`, `armbianEnv.txt`, and `Automation_Custom_Script.sh`. Known limitations are documented in its `README.md` (apparmor service fails; LXC needs a per-CT `lxc.apparmor.profile: lxc-default-with-nesting` workaround; KVM does not work).
- `rpios/` — Raspberry Pi OS path. Currently just a pointer to the interactive installer hosted in `TuxfeatMac/pimox7`.
- `standalone/` — placeholder, empty.

Each subfolder's `README.md` is the authoritative install procedure for that target. When changing a folder, update its `README.md` to match.

## How a deployment actually runs

1. User flashes the upstream DietPi image, then drops this repo's files into the SD card's `/boot/` partition (replacing DietPi's defaults).
2. On first boot, DietPi reads `dietpi.txt` for network/locale/hostname/password and runs in headless mode (`AUTO_SETUP_AUTOMATED=1`).
3. After DietPi's own first-run finishes, it executes `/boot/Automation_Custom_Script.sh` (this is a DietPi convention, **not** something we wire up ourselves).
4. The custom script sources network values back out of `dietpi.txt` (greps `AUTO_SETUP_NET_*`), installs the PiMox7 apt repo + key, installs `proxmox-ve`, rewrites `/etc/network/interfaces` to use a `vmbr0` bridge, and reboots.

This means the script runs **once, as root, on the target device** — not on a developer workstation. Don't try to execute or "test" it locally.

## Conventions when editing the install scripts

- The two `Automation_Custom_Script.sh` files (dietpi/ and rockpi4a/) are near-duplicates that diverge in three places: kernel-headers package (`raspberrypi-kernel-headers` vs `linux-headers-current-rockchip64`), the RPi-only cgroup fix that edits `/boot/cmdline.txt`, and the duration string in the banner. **A change relevant to both targets must be applied to both files** — they are intentionally not factored into a shared script because each ships independently on its own SD card.
- The `# CONFIGURE-OPTIONS` block at the top (between the two ruler comments) is the only intended user-tunable surface. `# ! NO TOUCHI BELOW THIS LINE !` means edits below it change install behavior — make them deliberately.
- `dietpi.txt` and `config.txt` are upstream DietPi/RPi-firmware files with project-specific overrides. When DietPi releases a new template, prefer rebasing our changes onto the new upstream rather than diffing line-by-line.
- The PiMox7 apt source pinned in the scripts is the upstream `pimox/pimox7` dev repo; `rpios/README.md` notes that for the RPi OS path the user currently has to swap it for `TuxfeatMac/pimox7` because a PR is unmerged. Keep that note accurate.
- Banner replacement uses a `sed` against `/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js`. The `SEARCH` anchor (`return Ext.String.format('`) is fragile to upstream Proxmox UI changes — if it breaks, that's why.

## Known bugs to be aware of when reading the scripts

- Both scripts reference `$RPI_IP_ONLY` in the first `/etc/hosts` write, but only `$RPI_IP` is ever assigned. The variable is empty at that point. Don't "clean this up" without checking whether downstream behavior depends on the empty value (the second `/etc/hosts` write later in the script uses the correct `$RPI_IP`).
- `CONFIG_ZRAM`/`CONFIG_SWAP`/`GET_STD_CTS`/`GET_STD_ISO` default to the literal string `'yes/no'`, which is neither — the `if [ "$CONFIG_X" == "yes" ]` guards therefore fall through. This is intentional: the user picks one by editing the value before flashing.

## Git / branching

Active development branch for documentation work: `claude/add-claude-documentation-BJMyP`. Push to that branch; do not push to `main` without an explicit ask.
