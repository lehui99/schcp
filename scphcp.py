import json
import logging
try:
    from gevent import socket
    from gevent import Greenlet as Concurrent
except ImportError:
    import socket
    from threading import Thread as Concurrent
    print('Cannot find gevent, using threading')
import sys
import re

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

    def __init__(self, config, client):
        Pipe.__init__(self)
        self.config = config
        self.client = client

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

        def startPipe():
            if clientData != b'':
                self.parent.send(clientData)
            if parentData != b'':
                self.client.send(parentData)
            pipe = Pipe()
            pipe.setSockPair(client, parent)
            pipe.start()
            self.setSockPair(parent, client)
            self.pipeData()

        def sslHandshake(clientData, parentData):

            def pipeHello(paramList):
                sockIn, inData, sockOut = paramList
                missDataLen = 5 - len(inData)
                if missDataLen > 0:
                    inData += recvFully(sockIn, missDataLen)
                helloLen = ord(inData[3]) << 8 | ord(inData[4])
                missDataLen = 5 + helloLen - len(inData)
                if missDataLen > 0:
                    inData += recvFully(sockIn, missDataLen)
                packetLen = 5 + helloLen
                sockOut.send(inData[ : packetLen])
                return inData[packetLen : ]

            clientData = pipeHello(self.client, clientData, self.parent)
            parentData = pipeHello(self.parent, parentData, self,client)
            raise Exception('Not implemented yet')  #   TODO:
            return clientData, parentData

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
            if clientData[0] != '\x22':    #   Not SSL
                startPipe()
            clientData, parentData = sslHandshake(clientData, parentData)
            startPipe()
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
        while True:
            try:
                client, addr = server.accept()
                Tunnel(self.config, client).start()
            except Exception:
                logging.exception('Exception in Main.start:')

if __name__ == '__main__':
    Main(json.loads(open(sys.argv[1], 'r').read())).start()
