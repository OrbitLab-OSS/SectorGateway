#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal, NamedTuple


class SectorGatewayTool(ABC):
    """Abstract base class for sector gateway configuration tools."""

    def __init__(self, config: Path) -> None:
        """Initialize tool."""
        self.__ensure_root__()
        self.config = config

    @abstractmethod
    def set(self, args: argparse.Namespace) -> None:
        """Set the tool config."""

    @abstractmethod
    def get(self, args: argparse.Namespace) -> None:
        """Get the current tool config."""

    @abstractmethod
    def restart(self, args: argparse.Namespace) -> None:
        """Restart the current tool."""

    def __ensure_root__(self) -> None:
        """Ensure the script is running as root user."""
        if os.geteuid() != 0:
            self.__die__("This command must be run as root")

    def __pre_checks__(self) -> None:
        """Perform pre-flight checks to ensure config directory exists and config file is present."""
        self.config.parent.mkdir(parents=True, exist_ok=True)
        if not self.config.exists():
            self.__die__(f"{self.config} does not exist")

    def __die__(self, msg: str) -> None:
        """Print error message and exit with code 1."""
        print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    def __format_row__(self, col_widths: list[int], row: list[str]) -> str:
        """Format a table row with proper column alignment."""
        return "  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row))

    def __print_table__(self, headers: list[str], rows: list[list[str]]) -> None:
        """Print a formatted table with headers and rows."""
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))

        print(self.__format_row__(col_widths=col_widths, row=headers))
        print(self.__format_row__(col_widths=col_widths, row=["-" * w for w in col_widths]))
        for row in rows:
            print(self.__format_row__(col_widths=col_widths, row=row))

    def __run__(self, cmd: list[str]) -> None:
        """Run a subprocess command and handle errors."""
        try:
            subprocess.run(cmd, check=True)  # noqa: S603
        except subprocess.CalledProcessError:
            self.__die__(f"Command failed: {' '.join(cmd)}")


class FrrSetArgs(NamedTuple):
    """Arguments for FRR set operation."""

    sector_addresses: list[str]
    backplane_assigned_addr: str
    backplane_gw_ip: str


class FRR(SectorGatewayTool):
    """FRR configuration tool for managing Free Range Routing settings."""

    def set(self, args: FrrSetArgs) -> None:
        """Set FRR configuration with the provided arguments."""
        lines = [
            "frr defaults traditional",
            "log syslog warning",
            "ip forwarding",
            "!",
            "interface eth0",
            *[f" ip address {addr}" for addr in args.sector_addresses],
            " no shutdown",
            "!",
            "interface eth1",
            f" ip address {args.backplane_assigned_addr}",
            " no shutdown",
            "!",
            f"ip route 0.0.0.0/0 {args.backplane_gw_ip}",
            "!",
            "end",
            "",
        ]

        self.config.write_text("\n".join(lines))

        print(f"Wrote FRR configuration to {self.config}")

    def get(self, _: argparse.Namespace) -> None:
        """Get current FRR config."""
        self.__pre_checks__()

        sector_addresses = []
        backplane_addr = ""
        backplane_gateway = ""
        ip_type: Literal["sector", "backplane", ""] = ""

        for line in self.config.read_text().splitlines():
            config_line = line.strip()

            if config_line.startswith("interface"):
                ip_type = "sector" if "eth0" in config_line else "backplane"

            if config_line.startswith("ip address"):
                addr = config_line.split()[2]
                if ip_type == "sector":
                    sector_addresses.append(addr)
                else:
                    backplane_addr = addr
                    ip_type = ""
            elif config_line.startswith("ip route 0.0.0.0/0"):
                backplane_gateway = config_line.split()[-1]

        rows = [
            ["Sector Gateways", ", ".join(sector_addresses)],
            ["Backplane Address", backplane_addr],
            ["Backplane Gateway", backplane_gateway],
            ["Config Path", str(self.config)],
        ]

        self.__print_table__(["Field", "Value"], rows)

    def restart(self, _: argparse.Namespace) -> None:
        """Restart the FRR service using available service manager."""
        self.__pre_checks__()
        self.__run__(["systemctl", "restart", "frr"])
        print("FRR restarted successfully")


class NFTablesSetArgs(NamedTuple):
    """Arguments for NFTables set operation."""

    primary_sector_ip: str
    backplane_network: str


class NFTables(SectorGatewayTool):
    """NFTables configuration tool for managing firewall rules."""

    def set(self, args: NFTablesSetArgs) -> None:
        """Set NFTables configuration with the provided arguments."""
        lines = [
            "table ip nat {",
            "  chain prerouting {",
            "    type nat hook prerouting priority -100;",
            f'    iif "eth1" ip daddr {args.backplane_network} dnat to {args.primary_sector_ip}',
            f'    iif "eth0" ip daddr {args.backplane_network} drop',
            "  }",
            "",
            "  chain postrouting {",
            "    type nat hook postrouting priority 100;",
            '    oif "eth1" masquerade',
            "  }",
            "}",
            "",
        ]

        self.config.write_text("\n".join(lines))

        print(f"Wrote nftables configuration to {self.config}")

    def get(self, _: argparse.Namespace) -> None:
        """Get current NFTables config."""
        self.__pre_checks__()

        prerouting = ""
        postrouting = ""

        for line in self.config.read_text().splitlines():
            config_line = line.strip()
            if config_line.startswith("iif"):
                prerouting = config_line
            elif config_line.startswith("oif"):
                postrouting = config_line

        rows = [
            ["Prerouting Rule", prerouting],
            ["Postrouting Rule", postrouting],
            ["Config Path", str(self.config)],
        ]

        self.__print_table__(["Field", "Value"], rows)

    def restart(self, _: argparse.Namespace) -> None:
        """Restart the FRR service using available service manager."""
        self.__pre_checks__()
        self.__run__(["systemctl", "restart", "nftables"])
        print("nftables restarted successfully")


def main() -> None:
    """Main entry point for the sector gateway configuration tool."""
    frr_tool = FRR(config=Path("/etc/frr/frr.conf"))
    nftables_tool = NFTables(config=Path("/etc/nftables.conf"))

    parser = argparse.ArgumentParser(
        prog="sgwtool",
        description="Sector Gateway configuration tool for OrbitLab",
    )

    subparsers = parser.add_subparsers(dest="tool", required=True)

    frr = subparsers.add_parser("frr", help="Manage FRR configuration")
    frr_sub = frr.add_subparsers(dest="action", required=True)

    frr_set_p = frr_sub.add_parser("set", help="Write FRR configuration")
    frr_set_p.add_argument(
        "--sector-subnet-addr",
        dest="sector_addresses",
        action="append",
        help="Sector Subnet IPv4 Address with CIDR bit (X.X.X.X/Y). Can be used multiple times (one for each subnet).",
        required=True,
    )
    frr_set_p.add_argument(
        "--backplane-assigned-addr",
        help="Backplane IPv4 Address with CIDR bit assigned to the router (X.X.X.X/Y).",
        required=True,
    )
    frr_set_p.add_argument("--backplane-gw-ip", help="Backplane Gateway IPv4 Address (X.X.X.X).", required=True)
    frr_set_p.set_defaults(func=frr_tool.set)

    frr_get_p = frr_sub.add_parser("get", help="Show FRR configuration")
    frr_get_p.set_defaults(func=frr_tool.get)

    frr_restart_p = frr_sub.add_parser("restart", help="Restart FRR")
    frr_restart_p.set_defaults(func=frr_tool.restart)

    nft = subparsers.add_parser("nftables", help="Manage nftables configuration")
    nft_sub = nft.add_subparsers(dest="action", required=True)

    nft_set_p = nft_sub.add_parser("set", help="Write nftables configuration")
    nft_set_p.add_argument(
        "--primary-sector-ip",
        help=(
            "Primary Sector Gateway IPv4 Address (X.X.X.X). "
            "This is usually the X.X.X.1/Y address of the entire sector CIDR."
        ),
        required=True,
    )
    nft_set_p.add_argument("--backplane-network", help="Backplane network CIDR block (X.X.X.X/Y)", required=True)
    nft_set_p.set_defaults(func=nftables_tool.set)

    nft_get_p = nft_sub.add_parser("get", help="Show nftables configuration")
    nft_get_p.set_defaults(func=nftables_tool.get)

    nft_restart_p = nft_sub.add_parser("restart", help="Reload nftables rules")
    nft_restart_p.set_defaults(func=nftables_tool.restart)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
