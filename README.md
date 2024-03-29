# Distributed Fault-Tolerant Hash Table (DFTHT)

Project realized under the direction of [**Joeri Hermans**](https://github.com/JoeriHermans) as part of the course *Large scale data systems* given by [**Gilles Louppe**](https://github.com/glouppe) to graduate computer science students at the [University of Liège](https://www.uliege.be/) during the academic year 2019-2020.

## Altered Chord

The developed framework is an *altered* version of [Chord](https://en.wikipedia.org/wiki/Chord_(peer-to-peer)). It has been implemented using [Flask](https://github.com/pallets/flask), [Requests](https://github.com/psf/requests) and a few other Python libraries.

```bash
pip install -r requirements.txt
```

### Boot

In order to initialize a node, one shall call the following command
```bash
python python/application.py -p $PORT -b $BOOT
```
where `$PORT` is the port of the new node and `$BOOT` the ip address of a node in a network. By default, the former is set to `5000` and the later to `127.0.0.1:5000`. If `127.0.0.1:$PORT == $BOOT`, the node starts a new network.

> A node isn't activated until it receives its first request.

To communicate with the network, one can use the [curl](https://curl.haxx.se/) library.

### Interface

Among others, the framework presents the `exists`, `get`, `put`, `remove`, `copy`, `list` and `shutdown` requests.

* `exists(path)` checks whether a value is stored at path `path` (`True` or `False`).
* `get(path)` returns the value stored, if any, at path `path`.
* `put(path, value)` stores the value `value` at path `path`, if unused.
* `remove(path)` removes the value stored, if any, at path `path`.
* `copy(src, dst)` copies the value stored, if any, at path `src` to path `dst`, if unused.
* `list()` lists all occupied paths in the system.
* `shudown()` shuts down a process. Could be used to simulate the crash of a process.

```bash
curl http://127.0.0.1:$PORT/exists/$PATH
curl http://127.0.0.1:$PORT/get/$PATH
curl http://127.0.0.1:$PORT/put/$PATH -X POST --data $VALUE --header 'Content-Type: application/json'
curl http://127.0.0.1:$PORT/remove/$PATH
curl http://127.0.0.1:$PORT/copy/$SRC/$DST
curl http://127.0.0.1:$PORT/list
curl http://127.0.0.1:$PORT/shutdown
```
> The argument `--header 'Content-Type: application/json'` is mandatory.

### Example

```bash
N=5

./bash/boot.sh $N
./bash/ping.sh $N

curl http://127.0.0.1:5000/put/1 -X POST --data 1 --header 'Content-Type: application/json' > log.txt
curl http://127.0.0.1:5001/put/2 -X POST --data 2 --header 'Content-Type: application/json' >> log.txt
curl http://127.0.0.1:5002/put/3 -X POST --data 3 --header 'Content-Type: application/json' >> log.txt

curl http://127.0.0.1:5003/exists/1 >> log.txt
curl http://127.0.0.1:5004/get/2 >> log.txt
curl http://127.0.0.1:5000/copy/3/4 >> log.txt

curl http://127.0.0.1:5001/remove/3 >> log.txt
curl http://127.0.0.1:5002/shutdown >> log.txt

curl http://127.0.0.1:5003/get/3 >> log.txt
curl http://127.0.0.1:5004/exists/4 >> log.txt

curl http://127.0.0.1:5000/list >> log.txt

./bash/shut.sh $N
```

```
Value successfully stored at path 1.
Value successfully stored at path 2.
Value successfully stored at path 3.
true
2
Value successfully stored at path 4.
Value successfully removed from path 3.
Server shutting down.
No value stored at path 3.
true
["1","2","4"]
```

## Concept

As the regular Chord protocol, this version organizes the participating nodes in an *orverlay network*, where each node (machine) is responsible for a set of keys defined as `m`-bit identifiers. The overlay network is arranged in an *identifier circle* ranging from `0` to `2^m - 1`. The position (or identifier) `n` of a node on this circle is chosen by *hashing* the node IP address.

The responsibility  of a key `k` belongs to a node if it is the first node whose identifier `n` follows or equals `k` in the identifier circle. If true, `n` is said to be the *successor node* of `k` : `n = successor(k)`. The concept of successor is used for nodes as well : the successor of a node (whose identifier is `n`) is `m` such that `m = successor(n + 1)`. In this case, `n` is referenced as the *predecessor* of `m`.

Because, each key is under the responsibility of a node, the core usage of the Chord protocol is to query a key `k` from a client (a node as well), i.e. to find `successor(k)`. If the client is not the said successor, it will pass the query to another node **it knows** (see below). This is called the *lookup* mechanism.

In the regular Chord protocol, each node keeps a *finger table* of up to `m` other (smartly selected) nodes which ensures *logarithmic* complexity for the lookup. However, this table has to be updated each time a node joins or leaves the network (or crashes) through a *stabilization* protocol running periodically in the background.

To avoid such processing waste, another mechanism has been implemented. Instead of a finger table, each node possesses an *internal representation* of the network, i.e. a table mapping node identifiers to IP addresses. This representation isn't necessarily correct nor complete.

Moreover, instead of returning `successor(k)`, the lookup function returns the *sequence* of nodes (their IP address) that were involved in the search and, thanks to its *recursive* implementation, the later can *improve* their representation of the network at the same time.

```python
def lookup(n, k):
    if n == successor(k):
        chain = []
    else:
        chain = lookup(next(n, k), k)
        improve(n, chain)

    return chain + [ip(n)]
```

The worst-case complexity of this procedure is `O(N)` where `N` is the number of nodes. But, assuming that the network isn't changing too quickly (several nodes joining between lookups), the average complexity will eventually be `O(1)`. It should be noted that no background process is required.

However, there is a tradeoff : the memory space needed to store the internal network representation is `O(N^2)` (`O(N)` for `N` nodes) instead of `O(N * log(N))` for the regular Chord protocol.

### Architecture

Each node is composed of two layers. The *external* layer ([`application.py`](python/application.py)) handles the incomming `HTTP` requests and transmit them to the *internal* layer ([`dht.py`](python/dftht/dht.py)) which acts as a storage unit for both the files and the network representation.

Internally, files are stored in hash tables (dictionaries) using *separate chaining* which means a file described by a pair `(path, value)` will be stored in a list accessible through the key `hash(path)` in a dictionary.

```python
def put(path, value):
    key = hash(path)

    if key in hash_table:
        hash_table[key].append((path, value))
    else:
        hash_table[key] = [(path, value)]
```

This technique prevents key collisions while guaranteeing an `O(1)` complexity for both search and addition of files (in the table, not the whole system).
> In fact, the complexity is proportional to the *load factor* of the hash table, which is assumed to be smaller than `1`.

### Fault-tolerance

The failure assumption is *crash-stop* : a faulty process stops to take steps and **never** recovers.

The system has been made resiliant to failures trough replication of files. When a file described by a pair `(path, value)` is inserted in the system, it actually is with several keys : `hash(path)`, `hash(hash(path))`, etc.

Therefore, if the node responsible of the key `hash(path)` crashes, the value is still accessible trough the nodes responsible of `hash(hash(path))`, `hash(hash(hash(path)))`, etc.

In the actual implementation, it has been chosen to replicate `3` times each file. The system is therefore resilitant to up to `2` faulty processes. However, because the hashing process is unpredictable, it is possible, yet very unlikely, that all copies of the file are under the responsibility of the same node.

### Requests implementation

* `exists`, `get`, `put` and `remove` execute a `lookup` for key `k`. If `successor(k)` 
    1. is `self`, transmit the request to the internal node. For `exist` or `get`, return the answer, for `put` and `remove`, update `k` to `hash(k)` and start again.
    2. hasn't crashed, transmit the request to it.
    3. has crashed, update `k` to `hash(k)` and start again.

* `list` contacts every nodes in the network through an iterative version of the *Depth-first search* algorithm. Each time a new node is reached, its content is retrieved.

    ```python
    def list():
        stack = Stack(self.network)
        visited = Set(self)
        content = List(self.content)

        while not empty(stack):
            node = stack.pop()

            if node in visited:
                continue

            visited.add(node)

            stack.push(node.network)
            content.extend(node.content)

        return content
    ```

## Performance assessment

The scripts [`eval.sh`](eval/eval.sh) and [`eval.py`](eval/eval.py) have been used to evaluate the complexity of the lookup mechanism and the memory space used by the internal network representations.

![lookup](eval/products/png/lookup.png)
> Average number of sub-requests per lookup with respect to the number of nodes in the network.

![memory](eval/products/png/memory.png)
> Average number of edges with respect to the number of nodes in the network.
