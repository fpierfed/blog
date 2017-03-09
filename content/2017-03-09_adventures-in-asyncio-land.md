Title: Adventures in Asyncio Land
Date: 2017-03-09
Tags: Python, Redis, asyncio, uvloop
Slug: adventures-in-asyncio-land
Category: Performance


## Case Study

I have been interested in distributed task queues and, more in general, in distributed producer/consumer architectures for a while. In this context I have been looking at [Redis](https://redis.io), an extremely popular in-memory data store, with great interest for a while. 

If you have played with [Celery](http://www.celeryproject.org) for instance, you might have used Redis as a broker and/or result backend. [Python RQ](http://python-rq.org), another distributed task queue project, relies exclusively on Redis to both store work requests as well as results.

In my curiosity, I wanted to look at Redis performance and suitability as a low-latency message broker. I will be using Redis 3.2.8 and Python 3.6 on MacOS Sierra (bare metal), Debian 8.2 (virtualised) and FreeBSD 11.0 (virtualised). 

As I will be using a wide range of CPUs, physical virtual machines, the point of this article is to look at relative performance gains/losses when accessing Redis in different ways.


## Code

The simplest "benchmark" I could think of is just setting and getting a key in a loop, within a pipeline (or not). One note about the test setup: by default Redis will periodically persist its database to disk. In order to remove one possible source of variability, persistence was completely disabled (i.e., by starting Redis as ```redis-server --save "" --appendonly no```).

Using the de-facto standard [Python Redis Client](https://github.com/andymccurdy/redis-py), one could simply write something along these lines:

    #!python3
    def test_sync(n, host, port):
        r = redis.StrictRedis(host, port, decode_responses=True)
        for i in range(n):
            key = f'test_sync:keys:{i}'
            value = f'{i}'
    
            r.set(key, value)
            fetched = r.get(key)
            assert value == fetched

The code should be self explanatory: we open a connection to a Redis server (listening on ```host:port```) and ask the connection object to take care of any decoding between bytes and strings for us (line 2).

Once that is done, we simply loop n-times (line 3) setting a key (line 7) and getting its value (line 8) immediately afterwards. We also want to be super sure that what we get out is what we put in and that is why we slap an ```assert``` on line 9. Keys (line 4) and values (line 5) are strings, which will be unique as long as we flush the DB in between runs (which is simple enough: ```redis-cli flushall```).

For this simple example, pipelining ```get``` and ```set``` operations would definitely help: the change is simple enough (lines 8-11):

    #!python3
    def test_sync_pipe(n, host, port):
        r = redis.StrictRedis(host, port, decode_responses=True)
        for i in range(n):
            key = f'test_sync_pipe:keys:{i}'
            value = f'{i}'
    
            pipe = r.pipeline()
            pipe.set(key, value)
            pipe.get(key)
            _, fetched = pipe.execute()
            assert value == fetched

How fast can these two functions run using a local Redis server? Out of five repetitions, the number of get+set operations per seconds are given in the following table:

Function Name        | Best      | Worst      | Stdev
-------------------- | --------- | ---------- | ------
test_sync            | 8655.07   | 8565.18    | 35.91
test_sync_pipe       | 9670.29   | 9171.65    | 217.31

Well, not bad at all: almost nine thousand get/set operations per second! Pipelining the get and set brings us to almost 10k operation/s (with a local Redis, it should be stressed).



## Code (asyncio)

How would asyncio fare with this type of code? Would it be faster? Slower? Since I have always wanted to play with asyncio, I thought of taking it for a spin and transforming the code above from synchronous to asynchronous.

The first attempt:

    #!python3
    import aioredis
    
    async def test_async(n, host, port, cid, loop):
        r = await aioredis.create_redis((host, port), loop=loop)
        for i in range(n):
            key = f'test_async:keys:{cid}:{i}'
            value = f'{i}'
    
            await r.set(key, value)
            fetched = await r.get(key)
            assert fetched.decode('utf-8') == value
        r.close()
        await r.wait_closed()

Tu run the function above, we need an event loop, of course:

    #!python3
    import asyncio
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_async(n, host, port, i, loop))

Results (again five repetitions):

Function Name        | Best      | Worst      | Stdev
-------------------- | --------- | ---------- | ------
test_async           | 5392.60   | 5352.36    | 14.73

The result is not (that) surprising: the asynchronous code is doing a lot more than is evident at first sight. It has to run an event loop, schedule coroutines, etc. However, exactly because it is doing all of that and because IO activities (just like connecting to a server and communicating with it) imply a lot of dead time, we should be able to break the number of get+set operations in chunks and schedule all those at the same time. The event loop would then run any coroutine that is ready to do some work any time another one is waiting for data. Let's try!

We need a helper function to do the splitting:

    #!python3
    def async_runner(n, host, port, nworkers=100):
        def closest_divistor(n, d):
            while n % d:
                d += 1
            return d
    
        nw = closest_divistor(n, nworkers)
        loop = asyncio.get_event_loop()
        
        tasks = [asyncio.ensure_future(
                    test_async(n // nw, host, port, i, loop))
                 for i in range(nw)]
        loop.run_until_complete(asyncio.wait(tasks))

Here we split the number ```n``` of operations to perform into ```nw``` chunks (line 12). We just want to make sure that ```nw``` is a divisor of ```n``` to avoid having to deal with reminders (see function on lines 3-6 and line 8).

In order to schedule many coroutines, one can use ```asyncio.ensure_future``` (line 11). We will then need to stick around until they are all done. This is accomplished on line 14 where we use ```asyncio.wait``` (rather than e.g., ```asyncio.gather```) since we do not need the return values of the scheduled coroutines.

It should also be clear now why the ```cid``` argument to ```test_async```: we use it to make sure that each coroutine creates a separate set of keys.

Interestingly, ```test_async``` remains unchanged. Neat, huh?

Speed results?

Function Name        | Best      | Worst      | Stdev
-------------------- | --------- | ---------- | ------
test_async (nw=100)  | 10770.29  | 10085.96   | 283.71

The choice of ```nw=1000``` was done by running the tests in a loop with changing values for the number of "worker" coroutines. One hundred seemed to give consistently better results.

Aside from this, nice to see our asyncio code being somewhat faster than the serial version!


## uvloop to the Rescue!

There is an exciting player in asyncio land: [uvloop](https://github.com/MagicStack/uvloop), which promises to be an _ultra fast implementation of asyncio event loop__. Let's see if that is true even for our simple test.

Code changes are minimal and restricted to our ```async_runner``` helper function:

    #!python3
    def async_runner_uvloop(n, host, port, nworkers=100):
        def closest_divistor(n, d):
            while n % d:
                d += 1
            return d
    
        nw = closest_divistor(n, nworkers)
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        loop = asyncio.get_event_loop()
        
        tasks = [asyncio.ensure_future(
                    test_async(n // nw, host, port, i, loop))
                 for i in range(nw)]
        loop.run_until_complete(asyncio.wait(tasks))

Indeed: just one extra statement: line 9 is where we install uvloop's event loop.

Performance numbers are pretty impressive:

Function Name               | Best      | Worst      | Stdev
--------------------------- | --------- | ---------- | ------
test_async (nw=100, uvloop) | 17853.57  | 16403.31   | 568.29

Almost twice as fast as our non-pipelined sequential code!


## Final Words

One interesting aspect of the asyncio-based code is that it does not use Redis pipelines to avoid the round-trip between a set and corresponding a get operation. The ```aioredis``` package does support pipelines and my tests with them did not produce any faster code. Quite the opposite, actually: the code run significantly slower. I guess the reason is that pipelining helps with a small number of coroutines since one is already spending as much time as possible in the server and there is not as much dead time to fill with other requests. A simple test:

    #!python3
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

Changing the value of ```nw``` from 1 to 200 shows performance increase with ```nw```, reach a maximum of just over 10k operation/s (with ```uvloop```!) at ```nw=100``` and then get progressively worse with increasing values of ```nw```.

All tests were run on my MacBook Pro with 16 GB of RAM, the stock SSD and Intel i7-4870HQ CPU @ 2.50GHz CPU. Running the same tests on a 2010 Mac Pro with 32 GB RAM (the slow kind at 1066 MHz) a slow-ish SSD and upgraded 2x 6-core Intel Xeon X5650  @ 2.67GHz produced results that were approximately 48-50% slower.

The same thing on a Debian 8.2 KVM virtual machine running on two physical cores of a Dell PowerEdge 730 with two nice 8-core Xeon E5-2620 v4 @ 2.10GHz showed results consistently above 10k operation/s for all tests. The fasts was again ```test_async  (nw=100, uvloop)``` at 18648 get+set/s. Which is probably just as fast as Redis would go (which is pretty darn fast!).

In the next instalment, we will look at performing these tests across the network!


## Resources

All code available in this [git repo](https://github.com/fpierfed/blog-code). The blog itself is available in this other [git repo](https://github.com/fpierfed/blog).

