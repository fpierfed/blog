Title: Redis in Asyncio Land Part 2
Date: 2017-04-16
Tags: Python, Redis, asyncio, uvloop
Slug: redis-in-asyncio-land-part-2
Category: Performance


## Intro

In [part 1]({filename}2017-03-09_redis-in-asyncio-land.md) of this series, I have looked at a dead-simple "benchmark": set a key, get a key, twenty thousand times. I have used a local Redis server on a couple of systems, both on bare metal and on a virtual machine. Both synchronous and asynchronous frameworks/modules were used. The results were quite interesting: Python's asyncio with uvloop with one hundred coroutines was the fastest option by a good margin.

Repeating the same tests (for a description of the tests, their code and the test setup, please refer to [part 1]({filename}2017-03-09_redis-in-asyncio-land.md)) using a remote Redis server proved to be quite interesting. I am using a remote Redis in the local network: ping times are of the order of 0.2-0.3 ms. Here are the results

Test                | Client    | Server    | Worst     | Best      | Stdev
--------------------|-----------|-----------|-----------|-----------|-----------
test_sync           | Debian VM | Mac Pro   | 1173.38   | 1259.33   | 32.24 (3%)
test\_sync\_pipe    | Debian VM | Mac Pro   | 2129.48   | 2219.08   | 32.59 (2%)
async_runner        | Debian VM | Mac Pro   | 8228.97   | 12072.66  | 1634.06 (13%)
async\_runner\_uvloop | Debian VM | Mac Pro | 17467.09  | 18314.50  | 374.80 (2%)
test_sync           | Mac Pro   | Debian VM | 1565.76   | 1586.45   | 7.65 (<1%)
test\_sync\_pipe    | Mac Pro   | Debian VM | 2259.72   | 2416.88   | 66.23 (3%)
async_runner        | Mac Pro   | Debian VM | 5002.71   | 5080.10   | 31.20 (<1%)
async\_runner\_uvloop | Mac Pro   | Debian VM | 8223.74 | 8536.67   | 133.42 (2%)

The table above shows that, with the test code used, asyncio-based tests are significantly faster than the synchronous ones. The reason might be the greater role that latency plays in the communication with a remote server.

Interesting things to notice: all the test show some variability, as it should be expected. The observed variability (as measured by the stdev of the five repetitions) is of the order of a few percent. There are some outliers with a large variation in run times. As mentioned in [part 1]({filename}2017-03-09_redis-in-asyncio-land.md), we should not read too much in the standard deviation figures: lots of processes are normally active on a modern computer and they can all interfere with the tests, however.

In any case, it is interesting to see how one could easily reach one thousand set+get operations per second on a remote Redis without breaking much of a sweat. Using asyncio, even trivially, can make our code five to ten time faster! Not bad at all.