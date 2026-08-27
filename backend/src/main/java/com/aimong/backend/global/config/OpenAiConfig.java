package com.aimong.backend.global.config;

import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(OpenAiProperties.class)
public class OpenAiConfig {

    /**
     * The request factory is configured explicitly because {@code RestClient.builder()}
     * is the plain static factory and does not pick up Spring Boot's
     * {@code spring.http.client.*} defaults. Without these timeouts an upstream that
     * accepts the connection and never answers holds the calling thread for as long
     * as it keeps the socket open. Callers wrap the call in
     * {@code CompletableFuture.get(timeout)}, but that only abandons the waiter; it
     * does not cancel the task or close the socket, so the thread is never returned.
     */
    @Bean
    public RestClient openAiRestClient(OpenAiProperties properties) {
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory();
        requestFactory.setReadTimeout(properties.readTimeout());

        return RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    /** Upper bound on how long any single OpenAI call may hold a thread. */
    public static Duration defaultReadTimeout() {
        return Duration.ofSeconds(20);
    }
}
