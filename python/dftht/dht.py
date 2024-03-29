# Imports
import json
import requests

from hashlib import sha1
from threading import Lock

# Parameters
m = 10
size = 2 ** m

# Methods
def address(host):
    '''Returns the address associated to a host.'''
    return 'http://{}/'.format(host)

def contact(url, msg='', timeout=0.1):
    '''Returns the response of a get request.'''
    try:
        resp = requests.get(url, timeout=timeout)

        if resp.status_code != 200:
            raise ConnectionError

        return resp.text
    except:
        raise ConnectionError(msg)

def hash(x, n=1):
    '''Hashes a string or integer.'''
    if n == 0:
        return x
    else:
        return int(int.from_bytes(sha1(str(hash(x, n - 1)).encode()).digest(), 'big') % size)

# Node class
class DHTNode(object):
    # Static methods
    @staticmethod
    def distance(a, b):
        '''Computes the clockwise distance between two keys.'''
        if a > b:
            return size - DHTNode.distance(b, a)
        return b - a

    @staticmethod
    def between(a, b, c):
        '''States whether \'b\' is within the interval \'[a, b]\'.'''
        return (a == c) or (b != a and DHTNode.distance(a, b) + DHTNode.distance(b, c) == DHTNode.distance(a, c))

    # Class methods
    def __init__(self, host):
        self.host = host
        self.id = hash(self.host)

        self.predecessor = (self.id, self.host)

        self.host_table = {}
        self.hash_table = {}

        self.lock = Lock()

    def join(self, boot):
        '''Joins a network through a bootstrap node.'''
        # Ping boot
        url = address(boot)
        contact(url)

        # Lookup successor
        url = address(boot) + 'lookup/{:d}'.format(self.id)
        chain = json.loads(contact(url))

        successor = chain[0]
        if hash(successor) == self.id:
            raise Exception

        self.improve(chain)

        # Get predecessor
        url = address(successor) + 'predecessor'
        predecessor = json.loads(contact(url))

        # Update predecessor
        self.update_predecessor(predecessor)

        # Inform successor
        url = address(successor) + 'update_predecessor/{}'.format(self.host)
        contact(url)

        # Take space domain responsibility
        url = address(successor) + 'content'
        content = json.loads(contact(url))

        for key, value in content.items():
            key = int(key)
            if DHTNode.between(self.predecessor[0], key, self.id):
                self.hash_table[key] = value

        try:
            url = address(successor) + 'delete/{:d}/{:d}'.format(self.predecessor[0], self.id)
            contact(url)
        except:
            pass

    def improve(self, chain):
        '''Improves internal representation of the network.'''
        for host in chain:
            if host is not None:
                self.host_table[hash(host)] = host

    def update_predecessor(self, host):
        '''Updates predecessor.'''
        self.predecessor = (hash(host), host)
        self.improve([host])

    def lookup(self, key):
        '''Looks up the successor of a given key.'''
        if DHTNode.between(self.predecessor[0], key, self.id):
            chain = []
        else:
            while True:
                id, host = min(
                    self.host_table.items(),
                    key=lambda x: DHTNode.distance(key, x[0])
                )

                try:
                    url = address(host) + 'lookup/{:d}'.format(key)
                    chain = json.loads(contact(url))
                except:
                    if host == self.predecessor[1]:
                        # self.predecessor has crashed
                        chain = [None]
                    else:
                        del self.host_table[id]
                        continue

                break

            self.improve(chain)

        return chain + [self.host]

    def exists(self, key, path):
        '''Checks whether a value is stored at a path.'''
        return self.get(key, path) is not None

    def get(self, key, path):
        '''Returns the value stored at a path.'''
        try:
            for i in self.hash_table[key]:
                if i[0] == path:
                    return i[1]
        except:
            pass

        return None

    def pop(self, key, path):
        '''Pops the value stored at a path.'''
        try:
            for i, j in enumerate(self.hash_table[key].copy()):
                if j[0] == path:
                    return self.hash_table[key].pop(i)
        except:
            pass

        return None

    def put(self, key, path, value):
        '''Stores a value at a path.'''
        if key in self.hash_table:
            if self.exists(key, path):
                raise KeyError('Value already stored at key {:d} and path {}.'.format(key, path))
            else:
                self.hash_table[key].append((path, value))
        else:
            self.hash_table[key] = [(path, value)]

    def delete(self, a, b):
        '''Deletes all values stored within a key interval.'''
        self.hash_table = dict(
            i for i in self.hash_table.items() if not DHTNode.between(a, i[0], b)
        )
