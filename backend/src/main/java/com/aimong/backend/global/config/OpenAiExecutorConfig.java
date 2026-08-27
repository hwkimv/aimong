package com.aimong.backend.global.config;

import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

/**
 * A dedicated pool for outbound OpenAI calls.
 *
 * <p>These calls were previously submitted through {@code CompletableFuture.supplyAsync}
 * without an executor, which runs them on the common ForkJoinPool. That pool is
 * sized to {@code availableProcessors - 1} and is shared with every parallel
 * stream in the JVM, so a slow upstream competed with unrelated work on a pool
 * that can be a single thread on a small container.
 *
 * <p>Keeping them here bounds the blast radius: a slow upstream saturates only
 * this pool, and a saturated pool rejects fast instead of queueing without limit.
 */
@Configuration
public class OpenAiExecutorConfig {

    public static final String OPENAI_EXECUTOR = "openAiExecutor";

    @Bean(name = OPENAI_EXECUTOR)
    public Executor openAiExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("openai-");
        // Surface saturation as a rejection the caller can turn into a 503,
        // rather than letting callers pile up behind an unbounded queue.
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.initialize();
        return executor;
    }

    /** Marker for the exception the abort policy raises, kept for readability at call sites. */
    public static boolean isSaturation(Throwable throwable) {
        return throwable instanceof RejectedExecutionException;
    }
}
