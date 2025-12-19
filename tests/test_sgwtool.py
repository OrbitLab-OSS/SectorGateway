import argparse
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sgwtool.cli import (
    FRR,
    FrrSetArgs,
    NFTables,
    NFTablesSetArgs,
    main,
)

FRR_TEST_CONFIG = """frr defaults traditional
log syslog warning
ip forwarding
!
interface eth0
 ip address 10.1.1.1/24
 ip address 10.1.2.1/24
 no shutdown
!
interface eth1
 ip address 192.168.1.100/24
 no shutdown
!
ip route 0.0.0.0/0 192.168.1.1
!
hostname testhost
end
"""
NFTABLES_TEST_CONFIG = """table ip nat {
  chain prerouting {
    type nat hook prerouting priority -100;
    iif "eth1" ip daddr 192.168.1.0/24 dnat to 10.1.1.1
    iif "eth0" ip daddr 192.168.1.0/24 drop
  }

  chain postrouting {
    type nat hook postrouting priority 100;
    oif "eth1" masquerade
  }
}
"""

class TestSectorGatewayTool:

    @pytest.mark.parametrize(("uid", "is_root"), [(0, True), (1000, False)])
    def test_ensure_root_as_root(self, uid: int, is_root: bool):
        with patch("os.geteuid", return_value=uid), patch("sys.exit") as mock_exit:
            FRR(config=Path().cwd())
            if is_root:
                mock_exit.assert_not_called()
            else:
                mock_exit.assert_called_once_with(1)

    @pytest.mark.parametrize(("exists"), [False, True])
    def test_pre_checks(self, exists: bool):
        with (
            patch("os.geteuid", return_value=0),
            patch("sys.exit") as mock_exit,
            patch("pathlib.Path.exists", return_value=exists),
        ):
            FRR(config=Path().cwd()).__pre_checks__()
            if exists:
                mock_exit.assert_not_called()
            else:
                mock_exit.assert_called_once_with(1)

    @pytest.mark.parametrize(("exception"), [None, subprocess.CalledProcessError(1,"test")])
    @patch("subprocess.run")
    def test_run(self, mock_run: MagicMock, exception: None | subprocess.CalledProcessError):
        mock_run.side_effect = exception

        with patch("os.geteuid", return_value=0), patch("sys.exit") as mock_exit:
            frr = FRR(config=Path().cwd())
            frr.__run__(["echo", "test"])
            mock_run.assert_called_once_with(["echo", "test"], check=True)
            if exception:
                mock_exit.assert_called_once_with(1)
            else:
                mock_exit.assert_not_called()


class TestFRR:
    def setup_method(self):
        with tempfile.NamedTemporaryFile() as file, patch("os.geteuid", return_value=0):
            self.frr = FRR(config=Path(file.name))

    def test_set(self):
        args = FrrSetArgs(
            sector_addresses=["10.1.1.1/24", "10.1.2.1/24"],
            backplane_assigned_addr="192.168.1.100/24",
            backplane_gw_ip="192.168.1.1",
        )

        with patch("pathlib.Path.write_text") as mock_write:
            self.frr.set(args)

            mock_write.assert_called_once()
            written_content = mock_write.call_args[0][0]

            assert "frr defaults traditional" in written_content
            assert "interface eth0" in written_content
            assert " ip address 10.1.1.1/24" in written_content
            assert " ip address 10.1.2.1/24" in written_content
            assert "interface eth1" in written_content
            assert " ip address 192.168.1.100/24" in written_content
            assert "ip route 0.0.0.0/0 192.168.1.1" in written_content

    def test_get(self): 
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=FRR_TEST_CONFIG),
        ):
            self.frr.get(argparse.Namespace())

    @patch("subprocess.run")
    def test_restart(self, mock_run: MagicMock):
        with patch("pathlib.Path.exists", return_value=True):
            self.frr.restart(argparse.Namespace())
            mock_run.assert_called_once_with(["systemctl", "restart", "frr"], check=True)


class TestNFTables:
    def setup_method(self):
        with tempfile.NamedTemporaryFile() as file, patch("os.geteuid", return_value=0):
            self.nftables = NFTables(config=Path(file.name))

    def test_set(self):
        args = NFTablesSetArgs(
            primary_sector_ip="10.1.1.1",
            backplane_network="192.168.1.0/24",
        )

        with patch("pathlib.Path.write_text") as mock_write:
            self.nftables.set(args)

            mock_write.assert_called_once()
            written_content = mock_write.call_args[0][0]

            assert "table ip nat {" in written_content
            assert "chain prerouting {" in written_content
            assert "dnat to 10.1.1.1" in written_content
            assert "ip daddr 192.168.1.0/24" in written_content
            assert "chain postrouting {" in written_content
            assert "masquerade" in written_content

    def test_get(self): 
        with (
            patch("pathlib.Path.read_text", return_value=NFTABLES_TEST_CONFIG),
            patch("pathlib.Path.exists", return_value=True),
        ):
            self.nftables.get(argparse.Namespace())

    @patch("subprocess.run")
    def test_restart(self, mock_run: MagicMock):
        with patch("pathlib.Path.exists", return_value=True):
            self.nftables.restart(argparse.Namespace())
            mock_run.assert_called_once_with(["systemctl", "restart", "nftables"], check=True)


@pytest.mark.parametrize(("args"), [
    (
        "sgwtool frr set --sector-subnet-addr 10.1.1.1/24 --sector-subnet-addr 10.1.2.1/24 "
        "--backplane-assigned-addr 192.168.1.100/24 --backplane-gw-ip 192.168.1.1"
    ),
    (
        "sgwtool nftables set --primary-sector-ip 10.1.1.1 --backplane-network 192.168.1.0/24"
    ),
])
@patch(f"{main.__module__}.Path.exists")
@patch(f"{main.__module__}.Path.write_text")
def test_main(mock_write: MagicMock, mock_exists: MagicMock, args: str):
    mock_exists.return_value = True
    with patch("os.geteuid", return_value=0), patch("sys.argv", args.split(" ")):
        main()

    mock_write.assert_called_once()
