# External API timeouts

## Context

`ChatService` calls OpenAI for chat replies and image generation. Both calls are
on the request path: a child sends a message and waits for the response.

## Problem

Every call is wrapped in a bounded wait:

```java
return CompletableFuture
        .supplyAsync(() -> openAiClient.createChatReply(CHAT_MODEL, DEVELOPER_PROMPT, contextualPrompt))
        .get(GPT_TIMEOUT_SECONDS, TimeUnit.SECONDS);   // 15 seconds
```

This looks like a 15-second bound. It is not.

`Future.get(timeout)` gives up on *waiting*. It does not cancel the task, does
not interrupt the worker, and does not close the socket. The HTTP call continues
on its worker thread until the client's own timeout fires — and the client had
none.

`RestClient.builder()` is the plain static factory. It does not pick up Spring
Boot's auto-configured `spring.http.client.*` settings, so the request factory
was left at its defaults with no read timeout:

```java
return RestClient.builder()
        .baseUrl(properties.baseUrl())
        .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
        .build();
```

Compounding it, `supplyAsync` was called without an executor, so the work ran on
the **common ForkJoinPool** — sized `availableProcessors - 1` and shared with
every parallel stream in the JVM. On a small container that can be one thread.

## Reproduction

`OpenAiClientTimeoutTest` starts a local HTTP server that accepts the request
and then holds the connection without replying, and points the production
`OpenAiConfig` client at it.

Before the fix:

```
[29.056s] an upstream that never responds fails the call instead of blocking the worker: FAIL
    Expecting actual: 30.017613071S  to be less than: 25S
[24.434s] the worker thread is released, not left blocked on the socket: FAIL
    Expecting value to be true but was false
```

The call was bounded only by the test server letting go at 30 seconds. A real
upstream holding the socket open holds the thread for as long as it likes.

## Root cause

Three separate gaps stacked:

1. no read timeout on the OpenAI HTTP client;
2. `Future.get(timeout)` abandons the waiter without cancelling the work, so the
   caller's 15-second bound never reaches the socket;
3. the abandoned work occupies a thread on a pool shared by the whole JVM.

Individually each is survivable. Together they mean a hung upstream steadily
consumes a small shared pool with no upper bound on how long each leaked call
holds its thread.

## Alternatives considered

| Option | Assessment |
|---|---|
| Read timeout + dedicated bounded pool | Bounds both how long a call can hold a thread and which pool it can exhaust. **Chosen.** |
| Read timeout only | Fixes the unbounded hold, but slow calls still block the common pool and compete with unrelated work. |
| Cancel the future on timeout | `cancel(true)` does not close a socket blocked in a read; the interrupt is not observed. Does not solve it. |
| Circuit breaker (Resilience4j) | A new dependency and failure mode for one integration whose actual defect is a missing timeout. Not warranted at this size. |
| Retry with backoff | Would multiply load against an upstream that is already slow. Not added. |

## Decision

Set an explicit read timeout on the request factory, and move the calls to a
dedicated bounded executor.

The timeout is 20 seconds by default, above the caller's 15-second chat wait so
the caller's own timeout stays the normal path, and below anything that would
hold a thread meaningfully long. It is configurable through
`OPENAI_READ_TIMEOUT`.

Pool saturation raises `RejectedExecutionException` rather than queueing without
limit, and the chat path turns that into the same timeout-shaped response a slow
upstream produces — a busy signal rather than an internal error.

## Implementation

`global/config/OpenAiConfig.java`:

```java
JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory();
requestFactory.setReadTimeout(properties.readTimeout());
```

`global/config/OpenAiExecutorConfig.java`: core 4, max 16, queue 32,
`AbortPolicy`, thread prefix `openai-`.

`ChatService`: both `supplyAsync` calls now take `openAiExecutor`, and
`RejectedExecutionException` is handled alongside `TimeoutException`.

## Verification

Same test, after the fix:

```
[3.02s]  an upstream that never responds fails the call instead of blocking the worker: PASS
[2.491s] the worker thread is released, not left blocked on the socket: PASS
```

Full backend suite at the time of the fix: 151 tests, 0 failures. Currently
161 tests, 0 failures with a database.

## Results

| | Thread held by an unresponsive upstream | Pool affected |
|---|---|---|
| Before | 30.0s in the test; unbounded in principle | common ForkJoinPool, shared JVM-wide |
| After | 3.0s, bounded by the configured read timeout | dedicated `openai-` pool, max 16 |

The test's 3-second figure is the test's configured timeout, not the production
default. Production is bounded at 20 seconds.

## Trade-offs

- A legitimate OpenAI call slower than the read timeout now fails where it
  previously completed. The chat caller already gave up at 15 seconds, so no
  response that a user could have seen is lost.
- The pool sizes are chosen, not measured. There is no production load data in
  this repository to size them against, and they are deliberately generous
  relative to the container sizes this runs on.

## Limitations

- No connect timeout is set separately; `JdkClientHttpRequestFactory` applies its
  own default for connection establishment.
- Not measured under real concurrency. The claim verified here is that a single
  call is now bounded and releases its thread, not a throughput result.
- Image generation keeps a 60-second caller wait against a 20-second read
  timeout, so image calls now fail earlier than the caller's bound. That is the
  intended direction but was not separately exercised against a live upstream.
