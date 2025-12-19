# Sector Gateway LXC
The Sector Gateway is a lightweight LXC based on debian/trixie used by OrbitLab to provide the routing logic between a user's Sector and OrbitLab's Backplane. It does this by implementing `frr` and `nftables` to provide routing and NAT-ing, respectively. OrbitLab manages the configuration on the router via `pct exec` from Proxmox and the `sgwtool` built into the appliance.

> While it is possible to manage and reconfigure the sector gateway manually, the OrbitLab control plane can and will nuke any changes made outside of the control plane. This is mainly to provide a low-resistance interface between the control plane and the appliance without having to build and install a custom agent.

## Architecture

The Sector Gateway operates as a dual-homed router:
- **eth0**: Connects to Sector networks (VXLAN VNet)
- **eth1**: Connects to OrbitLab's Backplane (EVPN VNet)

Traffic flow:
1. Sector traffic routes through eth0 to the gateway
2. NAT translation occurs for backplane communication
3. Default route directs traffic via eth1 to backplane gateway
4. Return traffic is reverse-NAT'd back to sector networks

## `sgwtool` - Sector Gateway Configuration Tool

The `sgwtool` is a command-line utility for configuring and managing the Sector Gateway's routing and NAT functionality.

> NOTE: The `sgwtool` MUST be ran as ***root***.

### Usage

```bash
sgwtool <tool> <action> [options]
```

Where `<tool>` is either **frr** or **nftables** and `<action>` is **get**, **set**, or **restart**.

### FRR

#### Set

```bash
sgwtool frr set --sector-subnet-addr <CIDR> --backplane-assigned-addr <CIDR> --backplane-gw-ip <IP>
```

Options:
- `--sector-subnet-addr <CIDR>`: Sector Subnet IPv4 Address with CIDR notation (e.g., 10.1.1.0/24). Can be specified multiple times for multiple subnets. **Required**
- `--backplane-assigned-addr <CIDR>`: Backplane IPv4 Address with CIDR notation assigned to this router (e.g., 192.168.1.100/24). **Required**
- `--backplane-gw-ip <IP>`: Backplane Gateway IPv4 Address (e.g., 192.168.1.1). **Required**

#### Get

```bash
sgwtool frr get
```

#### Restart

```bash
sgwtool frr restart
```

### NFTables

#### Set

```bash
sgwtool nftables set --primary-sector-ip <IP> --backplane-network <CIDR>
```

Options:
- `--primary-sector-ip <IP>`: Primary Sector Gateway IPv4 Address (e.g., 10.1.1.1). This is typically the .1 address of the sector CIDR block. **Required**
- `--backplane-network <CIDR>`: Backplane network CIDR block (e.g., 192.168.1.0/24). **Required**

#### Get

```bash
sgwtool nftables get
```

#### Restart

```bash
sgwtool nftables restart
```

### Examples

**Complete Setup Example:**
```bash
# Configure FRR for a sector with two subnets
sudo sgwtool frr set \
  --sector-subnet-addr 10.1.1.1/24 \
  --sector-subnet-addr 10.1.2.1/24 \
  --backplane-assigned-addr 192.168.100.50/24 \
  --backplane-gw-ip 192.168.100.1

# Configure nftables for NAT
sudo sgwtool nftables set \
  --primary-sector-ip 10.1.1.1 \
  --backplane-network 192.168.100.0/24

# Restart both services
sudo sgwtool frr restart
sudo sgwtool nftables restart
```

**View Current Configuration:**
```bash
# View FRR configuration
sudo sgwtool frr get

# View nftables configuration
sudo sgwtool nftables get
```

## Troubleshooting

**Service Status:**
```bash
systemctl status frr
systemctl status nftables
```

**Routing Table:**
```bash
ip route show
```

**NAT Rule Verification:**
```bash
nft list table ip nat
```

**Interface Status:**
```bash
ip addr show eth0
ip addr show eth1
```
