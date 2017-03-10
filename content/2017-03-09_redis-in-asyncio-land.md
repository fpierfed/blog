Title: Redis in Asyncio Land
Date: 2017-03-09
Tags: Python, Redis, asyncio, uvloop
Slug: redis-in-asyncio-land
Category: Performance


## Case Study

I have been interested in distributed task queues and, more in general, in distributed producer/consumer architectures for a while. In this context I have been looking at [Redis](https://redis.io), an extremely popular in-memory data store, with great interest for a while. 

Redis is used in various Python projects. For instance, if you have played with [Celery](http://www.celeryproject.org) you might have used Redis as a broker and/or result backend. [Python RQ](http://python-rq.org), another distributed task queue project, relies exclusively on Redis to both store work requests as well as results.

out of curiosity, I wanted to look at Redis' performance and suitability as a low-latency message broker. In what follows, I will be using Redis 3.2.8 and Python 3.6 on MacOS Sierra (bare metal) and Debian 8.2 (virtualised). 

One note about my test setup: by default Redis will periodically persist its database to disk. In order to remove one possible source of variability, this persistence mechanism was completely disabled (i.e., by starting Redis as ```redis-server --save "" --appendonly no```).



## Code

The simplest "benchmark" I could think of is just setting and getting a key in a loop, with and without pipelines. Using the de-facto standard [Python Redis Client](https://github.com/andymccurdy/redis-py), one could simply write something along these lines:

```python3
import redis

def test_sync(n, host, port):
    r = redis.StrictRedis(host, port, 
                          decode_responses=True)
    for i in range(n):
        key = f'test_sync:keys:{i}'
        value = f'{i}'
    
        r.set(key, value)
        fetched = r.get(key)
        assert value == fetched
```

The code should be self explanatory: open a connection to a Redis server (listening on ```host:port```) and ask the connection object to take care of any decoding between bytes and strings transparently.

Once that is done, simply loop n-times setting a key and getting its value immediately afterwards. Make sure that the value fetched from Redis is the same as the one inserted (see the ```assert```. Keys and values are strings, which will be unique as long as I flush the DB in between runs (which is simple enough: ```# redis-cli flushall```).

For this simple example, pipelining ```get``` and ```set``` operations would definitely help and the change is simple enough:

```python3
import redis

def test_sync_pipe(n, host, port):
    r = redis.StrictRedis(host, port, 
                          decode_responses=True)
    for i in range(n):
        key = f'test_sync_pipe:keys:{i}'
        value = f'{i}'
    
        pipe = r.pipeline()
        pipe.set(key, value)
        pipe.get(key)
        _, fetched = pipe.execute()
        assert value == fetched
```

How fast can these two functions run (using a local Redis server)? Out of five repetitions, the number of set+get operations (i.e., a set followed by a get) per seconds are given in the following table:

Function Name         | Best      | Worst      | Stdev
--------------------- | --------- | ---------- | ------
test_sync             | 8655.07   | 8565.18    | 35.91
test_sync\_pipe       | 9670.29   | 9171.65    | 217.31

Not bad at all! Almost nine thousand set+get operations per second! Pipelining the set and get gives almost 10k operation/s (again, with a local Redis server!).



## Code (asyncio)

How would asyncio fare with this type of code? Would it be faster? Slower? Since I have always wanted to play with asyncio, I thought of taking it for a spin. My first attempt:

```python3
import aioredis
    
async def test_async(n, host, port, cid, loop):
    r = await aioredis.create_redis((host, port), 
                                    loop=loop)
    for i in range(n):
        key = f'test_async:keys:{cid}:{i}'
        value = f'{i}'
    
        await r.set(key, value)
        fetched = await r.get(key)
        assert fetched.decode('utf-8') == value
    r.close()
    await r.wait_closed()
```

The code above uses the asynchronous [aioredis](https://github.com/aio-libs/aioredis) package. To run the ```test_async``` function, we need an event loop, of course:

```python3
import asyncio
    
loop = asyncio.get_event_loop()
loop.run_until_complete(
    test_async(n, host, port, i, loop))
```

Results (again after five repetitions):

Function Name        | Best      | Worst      | Stdev
-------------------- | --------- | ---------- | ------
test_async           | 5392.60   | 5352.36    | 14.73

The result is not (that) surprising: the asynchronous code is doing a lot more than appears at first sight. It has to run an event loop, schedule coroutines, etc. However IO activities, like communicating with a server, imply a lot of dead time. For this reason, one should be able to break the number of set+get operations into chunks and schedule all those at the same time. The event loop would then run any coroutine that is ready to do some work whenever the another ones are waiting for data. Let's try!

I need a helper function to do the splitting:

```python3
import asyncio

def async_runner(n, host, port, 
                 nworkers=100):
    def closest_divistor(n, d):
        while n % d:
            d += 1
        return d
    
    nw = closest_divistor(n, nworkers)
    loop = asyncio.get_event_loop()
    
    tasks = [asyncio.ensure_future(
                test_async(n // nw, host, port, 
                           i, loop))
             for i in range(nw)]
    loop.run_until_complete(asyncio.wait(tasks))
```

Here I split the ```n``` set+get operations into ```nw``` chunks. I just want to make sure that ```nw``` is a divisor of ```n``` to avoid having to deal with reminders (see ```closest_divisor```).

In order to schedule coroutines, I use ```asyncio.ensure_future```. I then need to ensure that the code sticks around until all the coroutines are done. This is accomplished with ```asyncio.wait```.

It should be clear by now the reason for the  ```cid``` argument to ```test_async```: I use it to make sure that each coroutine creates a separate set of keys (again, I need to wipe the database clean before each run). Interestingly, ```test_async``` remains unchanged. Neat, huh?

Performance results from five repetitions:

Function Name        | Best      | Worst      | Stdev
-------------------- | --------- | ---------- | ------
test_async (nw=100)  | 10770.29  | 10085.96   | 283.71

The choice of ```nw=1000``` was done by running the tests code in a loop changing the number of "worker" coroutines. One hundred seemed to give consistently better results. Aside from this, nice to see the asyncio code being somewhat faster than the serial version!


## uvloop to the Rescue!

There is an exciting new player in asyncio land: [uvloop](https://github.com/MagicStack/uvloop), which promises to be an _ultra fast implementation of asyncio event loop_. Let's see if that is true even for our simple test.

Code changes are minimal (just one extra line) and restricted to our ```async_runner``` helper function:

```python3
import asyncio
import uvloop

def async_runner_uvloop(n, host, port, 
                        nworkers=100):
    def closest_divistor(n, d):
        while n % d:
            d += 1
        return d
    
    nw = closest_divistor(n, nworkers)
    asyncio.set_event_loop_policy(
        uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()
    
    tasks = [asyncio.ensure_future(
                test_async(n // nw, host, port, 
                           i, loop))
             for i in range(nw)]
    loop.run_until_complete(asyncio.wait(tasks))
```

Performance numbers are pretty impressive:

Function Name               | Best      | Worst      | Stdev
--------------------------- | --------- | ---------- | ------
test_async (nw=100, uvloop) | 17853.57  | 16403.31   | 568.29

Almost twice as fast as our non-pipelined sequential code!


## Final Words

One interesting aspect of the asyncio code is that it does not use Redis pipelines to avoid the round-trip between a set and the corresponding get operation. The ```aioredis``` package does support pipelines and my tests with them did not produce faster code. Quite the opposite, actually: the code run significantly slower. I guess the reason is that pipelining helps only when using a small number of coroutines as it reduces wait times. A simple test:

```python3
import aioredis

async def test_async_pipe(n, host, port, cid, loop):
    r = await aioredis.create_redis((host, port), loop=loop)
    for i in range(n):
        key = f'test_async:keys:{cid}:{i}'
        value = f'{i}'
    
        pipe = r.pipeline()
        pipe.set(key, value)
        pipe.get(key)
        _, fetched = await pipe.execute()
        assert fetched.decode('utf-8') == value
    r.close()
    await r.wait_closed()
```

Changing the value of ```nw``` from 1 to 200 shows performance increasing with ```nw```, reach a maximum at around ```nw=100``` and then falling.

Removing the asserts from all test functions improves performance by roughly two-percent.

All tests were run on my 15" MacBook Pro with 16 GB of RAM, the stock SSD and a 4-core Intel i7-4870HQ @ 2.50GHz. Running the same tests on a 2010 Mac Pro with 32 GB RAM (the slow kind at 1066 MHz), a slow-ish SSD and two 6-core Intel Xeons X5650 @ 2.67GHz produced results that were approximately 48-50% slower.

The same tests on a Debian 8.2 KVM virtual machine running on two physical cores of a Dell PowerEdge R730 with 128 GB of RAM and two 8-core Intel Xeons E5-2620 v4 @ 2.10GHz showed results consistently above 10k set+get operation/s for all tests. The fastest test was again ```test_async  (nw=100, uvloop)``` at 18648 set+get/s. Which maybe is just as fast as Redis would go (which is pretty darn fast!).

In the next instalment, we will look at performing these tests across the network!


## Resources

All code available in this [git repo](https://github.com/fpierfed/blog-code). The blog itself is available in this other [git repo](https://github.com/fpierfed/blog).

