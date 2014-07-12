import json
import logging
try:
    from gevent import socket
    from gevent import Greenlet as Concurrent
except ImportError:
    import socket
    from threading import Thread as Concurrent
    print('Cannot find gevent, using threading')
from threading import Lock
import sys
import re
import pickle
import os

class CertificationStore(object):

    def __init__(self, config):
        try:
            f = open(config['certFilename'], 'rb')
            self.certs = pickle.load(f)
            f.close()
        except IOError:
            self.certs = {}
        self.config = config
        self.lock = Lock()

    def getCert(self, hostname):
        return self.certs[hostname.lower()]

    def checkCert(self, hostname, cert):
        hostname = hostname.lower()
        self.lock.acquire()
        try:
            if hostname in self.certs:
                if self.certs[hostname] != cert:
                    errmsg = b'Certification changed for hostname ' + hostname
                    logging.warning(errmsg)
                    raise Exception(errmsg)
            else:
                self.certs[hostname] = cert
                try:
                    os.remove(self.config['certFilename'] + '.bak')
                except Exception:
                    pass
                try:
                    os.rename(self.config['certFilename'], self.config['certFilename'] + '.bak')
                except Exception:
                    pass
                f = open(self.config['certFilename'], 'wb')
                try:
                    pickle.dump(self.certs, f)
                    f.flush()
                finally:
                    f.close()
        finally:
            self.lock.release()

class ProxyType:
    NONE = 0
    SOCKS = 1
    CONNECT = 2

class Pipe(Concurrent):

    def __init__(self):
        Concurrent.__init__(self)

    def setSockPair(self, sockIn, sockOut):
        self.sockIn = sockIn
        self.sockOut = sockOut

    def pipeData(self):
        try:
            while True:
                data = self.sockIn.recv(65536)
                if data == b'' or data == '' or data == None:
                    break
                self.sockOut.send(data)
        except Exception:
            logging.info('Pipe end')
        finally:
            self.sockIn.close()
            self.sockOut.close()

    def run(self):
        self.pipeData()

    def _run(self):
        self.run()

class Tunnel(Pipe):

    def __init__(self, config, client, certStore):
        Pipe.__init__(self)
        self.config = config
        self.client = client
        self.certStore = certStore

    def run(self):

        def recvFully(sock, byteslen):
            buf = b''
            while byteslen != 0:
                t = sock.recv(byteslen)
                if t == b'':
                    raise Exception('End connection in socksHandshake')
                buf += t
                byteslen -= len(t)
            return buf

        def tryOrd(b):
            try:
                return ord(b)
            except TypeError:
                return b

        def recvSocksAddr(sock):
            buf = sock.recv(1)  #   atyp
            if buf == b'\x01':
                hostname = recvFully(sock, 4)
                buf += hostname
                hostname = b'.'.join([str(tryOrd(b)).encode('iso-8859-1') for b in hostname])
            elif buf == b'\x03':
                hostnameLen = sock.recv(1)
                buf += hostnameLen
                hostname = recvFully(sock, ord(hostnameLen))
                buf += hostname
            elif buf == b'\x04':
                hostname = recvFully(sock, 16)
                buf += hostname
                hostname = b':'.join([str(tryOrd(b)).encode('iso-8859-1') for b in hostname])
            else:
                raise Exception('Unknown atyp')
            port = recvFully(sock, 2)
            buf += port
            port = tryOrd(port[0]) << 8 | tryOrd(port[1])
            return buf, (hostname, port)

        def localHandshake():
            self.client.recv(1) #   ver
            nmethods = self.client.recv(1)
            recvFully(self.client, ord(nmethods))
            self.client.send(b'\x05\x00')
            self.client.recv(1) #   ver
            cmd = self.client.recv(1)
            if cmd != b'\x01':
                raise Exception('Non connect cmd not implemented yet')
            self.client.recv(1) #   rsv
            buf, addr = recvSocksAddr(self.client)
            self.parent.connect(addr)
            self.hostname = addr[0]
            self.client.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')

        def socksHandshake():
            clientBuf = b''
            clientBuf += self.client.recv(1) #   ver
            nmethods = self.client.recv(1)
            clientBuf += nmethods
            clientBuf += recvFully(self.client, ord(nmethods))
            self.parent.send(clientBuf)
            parentBuf = b''
            parentBuf += self.parent.recv(1) #   ver
            method = self.parent.recv(1)
            if method != b'\x00':
                raise Exception('Non no-authentication socks protocol not implemented yet')
            parentBuf += method
            self.client.send(parentBuf)
            clientBuf = b''
            clientBuf += self.client.recv(1) #   ver
            cmd = self.client.recv(1)
            if cmd != b'\x01':
                raise Exception('Non connect cmd not implemented yet')
            clientBuf += cmd
            clientBuf += self.client.recv(1) #   rsv
            buf, addr = recvSocksAddr(self.client)
            self.hostname = addr[0]
            clientBuf += buf
            self.parent.send(clientBuf)
            parentBuf = b''
            parentBuf += self.parent.recv(1) #   ver
            rep = self.parent.recv(1)
            if rep != b'\x00':
                logging.info('socksHandshake connect failed')
            parentBuf += self.parent.recv(1) #   rsv
            buf, addr = recvSocksAddr(self.parent)
            parentBuf += buf
            self.client.send(parentBuf)

        def connectHandshake():

            def recvHeaderFully(sock):
                endBytes = b'\r\n\r\n'
                idx = 0
                buf = b''
                while True:
                    t = sock.recv(65536)
                    if t == b'':
                        raise Exception('End connection in connectHandshake')
                    buf += t
                    try:
                        idx = buf.index(endBytes, idx)
                        idx += len(endBytes)
                        return buf[ : idx], buf[idx : ]
                    except ValueError:
                        idx = len(buf) - len(endBytes) + 1

            request, clientData = recvHeaderFully(self.client)
            method, host, protocol = re.split(b'\\s+', request[ : request.index(b'\r\n')])    #   Although not meets RFC, it's no matter.  Because it's a local proxy.
            if method.upper() != b'CONNECT':
                raise Exception('Not a CONNECT(HTTPS) proxy.')
            self.hostname, port = host.split(b':')
            self.parent.send(request)
            response, parentData = recvHeaderFully(self.parent)
            self.client.send(response)
            return clientData, parentData

        def startClientParentPipe():
            if clientData != b'':
                self.parent.send(clientData)
            pipe = Pipe()
            pipe.setSockPair(self.client, self.parent)
            pipe.start()

        def startParentClientPipe():
            if parentData != b'':
                self.client.send(parentData)
            self.setSockPair(self.parent, self.client)
            self.pipeData()

        def startPipe():
            startClientParentPipe()
            startParentClientPipe()

        def sslCheckCertification(packet):
            if tryOrd(packet[5]) != 0x0b:
                return
            certChainLen = (tryOrd(packet[9]) << 16) | (tryOrd(packet[10]) << 8) | tryOrd(packet[11])
            certChain = packet[12 : 12 + certChainLen]
            self.certStore.checkCert(self.hostname, certChain)

        def sslGetPacket(sock, data):
            missDataLen = 5 - len(data)
            if missDataLen > 0:
                data += recvFully(sock, missDataLen)
            missDataLen = 5 + ((tryOrd(data[3]) << 8) | tryOrd(data[4])) - len(data)
            if missDataLen > 0:
                data += recvFully(sock, missDataLen)
            packetLen = 5 + ((tryOrd(data[3]) << 8) | tryOrd(data[4]))
            return data[ : packetLen], data[packetLen : ]

        self.parent = socket.socket()
        try:
            if self.config['parentProxyType'] != ProxyType.NONE:
                self.parent.connect((self.config['parentProxyHost'], self.config['parentProxyPort']))
            if self.config['parentProxyType'] == ProxyType.NONE:
                localHandshake()
                clientData = b''
                parentData = b''
            elif self.config['parentProxyType'] == ProxyType.SOCKS:
                socksHandshake()
                clientData = b''
                parentData = b''
            elif self.config['parentProxyType'] == ProxyType.CONNECT:
                clientData, parentData = connectHandshake()
            else:
                assert(False)
            if clientData == b'':
                clientData = self.client.recv(65536)
            if tryOrd(clientData[0]) != 0x16:    #   Not SSL Handshake
                startPipe()
                return
            startClientParentPipe()
            while True:
                packet, parentData = sslGetPacket(self.parent, parentData)
                if tryOrd(packet[0]) == 0x17:    #   Start SSL Application Data
                    self.client.send(packet)
                    break
                sslCheckCertification(packet)
                self.client.send(packet)
            startParentClientPipe()
        except Exception:
            logging.exception('Exception in Tunnel.run:')
        finally:
            self.client.close()
            self.parent.close()

class Main(object):

    def __init__(self, config):
        logging.basicConfig(filename = config['logFilename'], level = getattr(logging, config['logLevel']))
        config['parentProxyType'] = config['parentProxyType'].lower()
        proxyTypeMap = {
            'none' : ProxyType.NONE,
            'socks' : ProxyType.SOCKS,
            'connect' : ProxyType.CONNECT,
            }
        config['parentProxyType'] = proxyTypeMap[config['parentProxyType']]
        self.config = config

    def start(self):
        server = socket.socket()
        server.bind((self.config['proxyHost'], self.config['proxyPort']))
        server.listen(50)
        certStore = CertificationStore(self.config)
        while True:
            try:
                client, addr = server.accept()
                Tunnel(self.config, client, certStore).start()
            except Exception:
                logging.exception('Exception in Main.start:')

if __name__ == '__main__':
    Main(json.loads(open(sys.argv[1], 'r').read())).start()
