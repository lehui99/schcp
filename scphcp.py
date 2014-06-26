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

class PublicKeyStore(object):

    def __init__(self, config):
        try:
            f = open(config['pubKeysFilename'], 'r')
            self.keys = pickle.load(f)
            f.close()
        except IOError:
            self.keys = {}
        self.config = config
        self.lock = Lock()

    def getKey(self, hostname, port):
        return self.keys[hostname][port]

    def storeKey(self, hostname, port, key):
        self.keys[hostname][port] = key
        self.lock.acquire()
        try:
            os.remove(config['pubKeysFilename'] + '.bak')
        except Exception:
            pass
        try:
            os.rename(config['pubKeysFilename'], config['pubKeysFilename'] + '.bak')
        except Exception:
            pass
        f = open(config['pubKeysFilename'], 'w')
        pickle.dump(self.keys, f)
        f.close()
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

    def __init__(self, config, client, pubKeyStore):
        Pipe.__init__(self)
        self.config = config
        self.client = client
        self.pubKeyStore = pubKeyStore

    def run(self):

        def recvFully(sock, byteslen):
            buf = b''
            while byteslen != 0:
                t += sock.recv(byteslen)
                if t == b'':
                    raise Exception('End connection in socksHandshake')
                buf += t
                byteslen -= len(t)
            return buf

        def socksHandshake():
            raise Exception('Not implemented yet')  #   TODO:

        def connectHandshake():

            def recvHeaderFully(sock):
                endBytes = b'\r\n\r\n'
                idx = 0
                buf = b''
                while True:
                    t = self.client.recv(65536)
                    if t == b'':
                        raise Exception('End connection in connectHandshake')
                    try:
                        idx = buf.index(endBytes, idx)
                        idx += 4
                        return buf[ : idx], buf[idx : ]
                    except ValueError:
                        idx = len(buf) - len(endBytes) + 1

            request, clientData = recvHeaderFully(self.client)
            method, host, protocol = re.split(b'\\s+', request[ : request.index(b'\r\n')])    #   Although not meets RFC, it's no matter.  Because it's a local proxy.
            if method.upper() != b'CONNECT':
                raise Exception('Not a CONNECT(HTTPS) proxy.')
            self.hostname, self.port = host.split(b':')
            self.port = int(self.port)
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
            if packet[5] != b'\x0b':
                return
            certLen = (ord(packet[12]) << 16) | (ord(packet[13]) << 8) | ord(packet[14])
            cert = packet[15 : 15 + certLen]
            raise Exception('Not implemented yet')  #   TODO: verify certification

        def sslGetPacket(sock, data):
            missDataLen = 5 - len(data)
            if missDataLen > 0:
                data += recvFully(sock, missDataLen)
            missDataLen = 5 + ((ord(data[3]) << 8) | ord(data[4])) - len(data)
            if missDataLen > 0:
                data += recvFully(sock, missDataLen)
            packetLen = 5 + helloLen
            return data[ : packetLen], data[packetLen : ]

        self.parent = socket.socket()
        try:
            if self.config['parentProxyHost'] != None:
                self.parent.connect((self.config['parentProxyHost'], self.config['parentProxyPort']))
            if self.config['parentProxyType'] == ProxyType.NONE:
                raise Exception('Not implemented yet')  #   TODO: Implement as local socks5 proxy
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
            if clientData[0] != b'\x16':    #   Not SSL Handshake
                startPipe()
                return
            startClientParentPipe()
            while True:
                packet, parentData = sslGetPacket(self.parent, parentData)
                if parentData[0] == b'\x17':    #   Start SSL Application Data
                    self.client.send(packet)
                    break
                parentData = sslCheckCertification(packet)
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
        if config['parentProxyType'] == 'none':
            config['parentProxyType'] = ProxyType.NONE
        elif config['parentProxyType'] == 'socks':
            config['parentProxyType'] = ProxyType.SOCKS
        elif config['parentProxyType'] == 'socks':
            config['parentProxyType'] = ProxyType.CONNECT
        else:
            logging.error('Unknown parentProxyType %s', config['parentProxyType'])
            raise Exception('Unknown parentProxyType %s' % (config['parentProxyType'], ))
        self.config = config

    def start(self):
        server = socket.socket()
        server.bind((config['proxyHost'], config['proxyPort']))
        server.listen(50)
        pubKeyStore = PublicKeyStore(config)
        while True:
            try:
                client, addr = server.accept()
                Tunnel(self.config, client, pubKeyStore).start()
            except Exception:
                logging.exception('Exception in Main.start:')

if __name__ == '__main__':
    Main(json.loads(open(sys.argv[1], 'r').read())).start()
