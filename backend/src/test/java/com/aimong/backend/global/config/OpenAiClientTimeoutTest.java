package com.aimong.backend.global.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aimong.backend.infra.openai.OpenAiClient;
import com.aimong.backend.global.exception.AimongException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/**
 * The chat path wraps every OpenAI call in {@code CompletableFuture.get(timeout)},
 * which makes the call look bounded. It is not: {@code get} abandons the waiter
 * but never cancels the task, so without a read timeout on the HTTP client the
 * worker thread stays blocked on the socket for as long as the upstream holds
 * the connection open. Those workers come from the common ForkJoinPool, so
 * leaked calls accumulate against a pool the whole JVM shares.
 *
 * <p>These tests pin the client's own behaviour against a server that accepts
 * the connection and then never answers.
 */
class OpenAiClientTimeoutTest {

    private HttpServer server;
    private CountDownLatch release;
    private String baseUrl;

    @BeforeEach
    void startHangingServer() throws IOException {
        release = new CountDownLatch(1);
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/responses", exchange -> {
            try {
                // Accept the request, then hold the connection without replying.
                release.await(30, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            exchange.sendResponseHeaders(504, -1);
            exchange.close();
        });
        server.start();
        baseUrl = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
    }

    @AfterEach
    void stopServer() {
        release.countDown();
        server.stop(0);
    }

    private OpenAiClient clientUnderTest() {
        OpenAiProperties properties = new OpenAiProperties(
                "test-key", "test-key", "test-key", baseUrl, "/responses", false, Duration.ofSeconds(3)
        );
        RestClient restClient = new OpenAiConfig().openAiRestClient(properties);
        return new OpenAiClient(restClient, properties, new ObjectMapper());
    }

    @Test
    @DisplayName("an upstream that never responds fails the call instead of blocking the worker")
    void unresponsiveUpstreamFailsWithinReadTimeout() {
        OpenAiClient client = clientUnderTest();

        long startedAt = System.nanoTime();
        assertThatThrownBy(() -> client.createChatReply("gpt-test", "developer", "user"))
                .isInstanceOf(AimongException.class);
        Duration elapsed = Duration.ofNanos(System.nanoTime() - startedAt);

        // Without a read timeout this call returns only when the server gives up.
        assertThat(elapsed)
                .as("call must be bounded by the client's own read timeout")
                .isLessThan(Duration.ofSeconds(25));
    }

    @Test
    @DisplayName("the worker thread is released, not left blocked on the socket")
    void workerThreadIsReleasedAfterTimeout() throws Exception {
        OpenAiClient client = clientUnderTest();
        CountDownLatch finished = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                client.createChatReply("gpt-test", "developer", "user");
            } catch (RuntimeException expected) {
                // the client is expected to give up
            } finally {
                finished.countDown();
            }
        });
        worker.setDaemon(true);
        worker.start();

        assertThat(finished.await(25, TimeUnit.SECONDS))
                .as("a call whose caller already gave up must still release its thread")
                .isTrue();
    }
}
