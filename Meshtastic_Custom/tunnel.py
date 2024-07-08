"""Code for IP tunnel over a mesh"""

import logging
import platform
import threading

from pubsub import pub
from pytap2 import TapDevice

from meshtastic import portnums_pb2, mt_config
from meshtastic.util import ipstr, readnet_u16

def onTunnelReceive(packet, interface):
    """Callback for received tunneled messages from mesh."""
    logging.debug(f"in onTunnelReceive()")
    print("Packet received!")
    tunnelInstance = mt_config.tunnelInstance
    tunnelInstance.onReceive(packet)

class Tunnel:
    """A TUN based IP tunnel over meshtastic"""

    class TunnelError(Exception):
        """An exception class for general tunnel errors"""
        def __init__(self, message):
            self.message = message
            super().__init__(self.message)

    def __init__(self, iface, subnet="10.115", netmask="255.255.0.0"):
        """
        Constructor

        iface is the already open MeshInterface instance
        subnet is used to construct our network number (normally 10.115.x.x)
        """

        if not iface:
            raise Tunnel.TunnelError("Tunnel() must have a interface")

        if not subnet:
            raise Tunnel.TunnelError("Tunnel() must have a subnet")

        if not netmask:
            raise Tunnel.TunnelError("Tunnel() must have a netmask")

        self.iface = iface
        self.subnetPrefix = subnet
        self._closing = False  # Initialize the _closing attribute
        
        if platform.system() != "Linux":
            raise Tunnel.TunnelError("Tunnel() can only be run instantiated on a Linux system")

        mt_config.tunnelInstance = self

        """A list of chatty UDP services we should never accidentally
        forward to our slow network"""
        self.udpBlacklist = {
            1900,  # SSDP
            5353,  # multicast DNS
            9001,  # Yggdrasil multicast discovery
            64512, # cjdns beacon
        }

        """A list of TCP services to block"""
        self.tcpBlacklist = {
            5900,  # VNC (Note: Only adding for testing purposes.)
        }

        """A list of protocols we ignore"""
        self.protocolBlacklist = {
            0x02,  # IGMP
            0x80,  # Service-Specific Connection-Oriented Protocol in a Multilink and Connectionless Environment
        }

        # A new non standard log level that is lower level than DEBUG
        self.LOG_TRACE = 5

        # TODO: check if root?
        logging.info(
            "Starting IP to mesh tunnel (you must be root for this *pre-alpha* "
            "feature to work).  Mesh members:"
        )

        pub.subscribe(onTunnelReceive, "meshtastic.receive.data.IP_TUNNEL_APP")
        myAddr = self._nodeNumToIp(self.iface.myInfo.my_node_num)
        
        print(f"My IP is : {myAddr}")
        if self.iface.nodes:
            for node in self.iface.nodes.values():
                nodeId = node["user"]["id"]
                ip = self._nodeNumToIp(node["num"])
                logging.info(f"Node { nodeId } has IP address { ip }")
                print(f"Available IP's : {ip}")

        logging.debug("creating TUN device with MTU=200")
        self.tun = None
        if self.iface.noProto:
            logging.warning(
                f"Not creating a TapDevice() because it is disabled by noProto"
            )
        else:
            self.tun = TapDevice(name="mesh")
            self.tun.up()
            self.tun.ifconfig(address=myAddr, netmask=netmask, mtu=200)

        self._rxThread = None
        if self.iface.noProto:
            logging.warning(
                f"Not starting TUN reader because it is disabled by noProto"
            )
        else:
            logging.debug(f"starting TUN reader, our IP address is {myAddr}")
            self._rxThread = threading.Thread(
                target=self._tunReader, args=(), daemon=True
            )
            self._rxThread.start()
        
    def onReceive(self, packet):
        """onReceive"""
        if self._closing:
            return
        p = packet["decoded"]["payload"]
        if packet["from"] == self.iface.myInfo.my_node_num:
            print(f"Packet received from self : {p}")
            logging.debug("Ignoring message we sent")
        else:
            logging.debug(f"Received mesh tunnel message type={type(p)} len={len(p)}")
            if not self.iface.noProto:
                if not self._shouldFilterPacket(p):
                    self.tun.write(p)

    def _shouldFilterPacket(self, p):
        """Given a packet, decode it and return true if it should be ignored"""
        protocol = p[8 + 1]
        srcaddr = p[12:16]
        destAddr = p[16:20]
        subheader = 20
        ignore = False  # Assume we will be forwarding the packet
        if protocol in self.protocolBlacklist:
            ignore = True
            logging.log(
                self.LOG_TRACE, f"Ignoring blacklisted protocol 0x{protocol:02x}"
            )
        elif protocol == 0x01:  # ICMP
            icmpType = p[20]
            icmpCode = p[21]
            checksum = p[22:24]
            logging.debug(
                f"forwarding ICMP message src={ipstr(srcaddr)}, dest={ipstr(destAddr)}, type={icmpType}, code={icmpCode}, checksum={checksum}"
            )
        elif protocol == 0x11:  # UDP
            srcport = readnet_u16(p, subheader)
            destport = readnet_u16(p, subheader + 2)
            if destport in self.udpBlacklist:
                ignore = True
                logging.log(self.LOG_TRACE, f"ignoring blacklisted UDP port {destport}")
            else:
                logging.debug(f"forwarding udp srcport={srcport}, destport={destport}")
        elif protocol == 0x06:  # TCP
            srcport = readnet_u16(p, subheader)
            destport = readnet_u16(p, subheader + 2)
            if destport in self.tcpBlacklist:
                ignore = True
                logging.log(self.LOG_TRACE, f"ignoring blacklisted TCP port {destport}")
            else:
                logging.debug(f"forwarding tcp srcport={srcport}, destport={destport}")
        else:
            logging.warning(
                f"forwarding unexpected protocol 0x{protocol:02x}, "
                "src={ipstr(srcaddr)}, dest={ipstr(destAddr)}"
            )

        return ignore

    def _tunReader(self):
        tap = self.tun
        logging.debug("TUN reader running")
        print("TUN reader running")
        while not self._closing:
            try:
                p = tap.read()
                destAddr = p[16:20]
                if not self._shouldFilterPacket(p):
                    self.sendPacket(destAddr, p)
            except OSError as e:
                if e.errno == 9:  # Bad file descriptor
                    logging.debug("TUN device closed, exiting reader thread.")
                    break
                else:
                    raise

    def _ipToNodeId(self, ipAddr):
        ipBits = ipAddr.split('.')
        ipBits = int(ipBits[2]) * 256 + int(ipBits[3])

        if ipBits == 0xFFFF:
            return "^all"

        for node in self.iface.nodes.values():
            nodeNum = node["num"] & 0xFFFF
            if nodeNum == ipBits:
                return node["user"]["id"]
        return None

    def _nodeNumToIp(self, nodeNum):
        return f"{self.subnetPrefix}.{(nodeNum >> 8) & 0xff}.{nodeNum & 0xff}"

    def sendPacket(self, destAddr, p):
        """Forward the provided IP packet into the mesh"""
        nodeId = self._ipToNodeId(destAddr)
        if nodeId is not None:
            logging.debug(
                f"Forwarding packet bytelen={len(p)} dest={ipstr(destAddr)}, destNode={nodeId}"
            )
            self.iface.sendData(p, nodeId, portnums_pb2.IP_TUNNEL_APP, wantAck=False)
        else:
            logging.warning(
                f"Dropping packet because no node found for destIP={ipstr(destAddr)}"
            )

    def close(self):
        """Close"""
        print("TUN Closing")
        self._closing = True
        if self.tun:
            self.tun.close()
            print("TUN Closed Succesfully!")

    def start_client(self):
        """Start tunnel client"""
        logging.info("Starting tunnel client...")

    def start_gateway(self):
        """Start tunnel gateway"""
        logging.info("Starting tunnel gateway...")
