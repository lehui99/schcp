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
    SOCKS = 1
    CONNECT = 2

class Tunnel(Concurrent):

    def __init__(self, config, client):
        self.config = config
        self.client = client

    def socksHandshake(self):
        def recvFully(sock, byteslen):
            buf = b''
            while byteslen != 0:
                t += sock.recv(byteslen)
                if t == b'':
                    raise Exception('End connection in socksHandshake')
                buf += t
                byteslen -= len(t)
            return buf

    def connectHandshake(self):
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
        request, self.clientData = recvHeaderFully(self.client)
        method, host, protocol = re.split(b'\\s+', request[ : request.index(b'\r\n')])    #   Although not met RFC, it's no matter.  Because it's a local proxy.
        if method.upper() != b'CONNECT':
            raise Exception('Not a CONNECT(HTTPS) proxy.')
        self.hostname, self.port = host.split(b':')
        self.port = int(self.port)
        self.parent.send(request)
        response, self.parentData = recvHeaderFully(self.parent)
        self.client.send(response)

    def run(self):
        self.parent = socket.socket()
        try:
            self.parent.connect((self.config['parentProxyHost'], self.config['parentProxyPort']))
            if self.config['parentProxyType'] == ProxyType.SOCKS:
                self.socksHandshake()
            elif self.config['parentProxyType'] == ProxyType.CONNECT:
                self.connectHandshake()
            else:
                assert(False)
        except Exception:
            logging.exception('Exception in Tunnel.run:')
        finally:
            self.client.close()
            self.parent.close()

    def _run(self):
        self.run()

class Main(object):

    def __init__(self, config):
        logging.basicConfig(filename = config['logFilename'], level = getattr(logging, config['logLevel']))
        config['parentProxyType'] = config['parentProxyType'].lower()
        if config['parentProxyType'] == 'socks':
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
