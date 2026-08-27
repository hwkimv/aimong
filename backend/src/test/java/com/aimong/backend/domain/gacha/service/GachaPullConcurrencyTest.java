package com.aimong.backend.domain.gacha.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.aimong.backend.domain.gacha.entity.TicketType;
import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.FirebaseAuth;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * Concurrent gacha pulls against a real PostgreSQL.
 *
 * <p>A gacha pull is the flow where a duplicate reward would be most visible: it
 * spends a ticket, increments a per-child pull counter, and grants a pet or
 * fragments. The read-check-write shape — find an unused ticket, then mark it
 * used — is exactly what races.
 *
 * <p>{@code GachaPullService.pull} takes {@code PESSIMISTIC_WRITE} on the child
 * profile and again on the ticket. These tests do not assume that is enough;
 * they run real concurrent transactions and count what actually landed.
 *
 * <p>PostgreSQL is required. Row-level locking is the behaviour under test, so
 * an embedded database would not be evidence of anything.
 */
@SpringBootTest(properties = "spring.flyway.enabled=true")
@EnabledIfEnvironmentVariable(
        named = "TEST_DB_URL",
        matches = "jdbc:.+",
        disabledReason = "TEST_DB_URL is not set"
)
class GachaPullConcurrencyTest {

    @MockitoBean
    FirebaseApp firebaseApp;

    @MockitoBean
    FirebaseAuth firebaseAuth;

    @Autowired
    GachaPullService gachaPullService;

    @Autowired
    JdbcTemplate jdbc;

    private UUID childId;

    @BeforeEach
    void seed() {
        // equipped_pet_id references pets, so it has to be released before pets go.
        jdbc.execute("UPDATE public.child_profiles SET equipped_pet_id = NULL");
        jdbc.execute("DELETE FROM public.gacha_pulls");
        jdbc.execute("DELETE FROM public.tickets");
        jdbc.execute("DELETE FROM public.pets");
        jdbc.execute("DELETE FROM public.pet_fragments");
        jdbc.execute("DELETE FROM public.child_profiles");
        jdbc.execute("DELETE FROM public.parent_accounts");

        // No FCM token, so the level-up notification path stays out of the test.
        jdbc.update("INSERT INTO public.parent_accounts (parent_id, email, fcm_token) VALUES (?, ?, NULL)",
                "gacha-concurrency-parent", "parent@example.test");
        childId = UUID.randomUUID();
        jdbc.update("INSERT INTO public.child_profiles (child_id, parent_id, nickname) VALUES (?, ?, ?)",
                childId, "gacha-concurrency-parent", "동시성");
    }

    private void issueTickets(int count) {
        for (int i = 0; i < count; i++) {
            jdbc.update("INSERT INTO public.tickets (child_id, ticket_type, used_at) VALUES (?, ?::ticket_type_enum, NULL)",
                    childId, TicketType.NORMAL.name());
        }
    }

    private record Outcome(int succeeded, int failed) {
    }

    /** Fires {@code threads} pulls that start together, and counts how many won. */
    private Outcome pullConcurrently(int threads) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger succeeded = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();

        try {
            for (int i = 0; i < threads; i++) {
                pool.submit(() -> {
                    try {
                        start.await();
                        gachaPullService.pull(childId, TicketType.NORMAL);
                        succeeded.incrementAndGet();
                    } catch (Exception expected) {
                        failed.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                });
            }
            start.countDown();
            assertThat(done.await(60, TimeUnit.SECONDS))
                    .as("all pull attempts must finish; a hang would mean a deadlock")
                    .isTrue();
        } finally {
            pool.shutdownNow();
        }
        return new Outcome(succeeded.get(), failed.get());
    }

    private long count(String sql) {
        return jdbc.queryForObject(sql, Long.class);
    }

    private long usedTickets() {
        return count("SELECT count(*) FROM public.tickets WHERE used_at IS NOT NULL");
    }

    @Test
    @DisplayName("one ticket and eight concurrent pulls spend exactly one ticket")
    void oneTicketIsSpentOnce() throws InterruptedException {
        issueTickets(1);

        Outcome outcome = pullConcurrently(8);

        System.out.printf("[concurrency] 1 ticket, 8 threads -> %d succeeded, %d rejected%n",
                outcome.succeeded(), outcome.failed());

        assertThat(outcome.succeeded()).as("exactly one pull may win").isEqualTo(1);
        assertThat(outcome.failed()).isEqualTo(7);
        assertThat(usedTickets()).as("the ticket must be spent once").isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.gacha_pulls")).as("one reward granted").isEqualTo(1);
        assertThat(count("SELECT gacha_pull_count FROM public.child_profiles"))
                .as("the pull counter must move exactly once").isEqualTo(1);
        assertThat(count("SELECT count(*) FROM public.tickets WHERE used_at IS NULL")).isZero();
    }

    @ParameterizedTest(name = "{0} tickets, {1} concurrent pulls")
    @CsvSource({"1,4", "3,12", "5,20"})
    @DisplayName("no more pulls succeed than there are tickets")
    void successesNeverExceedTickets(int tickets, int threads) throws InterruptedException {
        issueTickets(tickets);

        Outcome outcome = pullConcurrently(threads);

        System.out.printf("[concurrency] %d tickets, %d threads -> %d succeeded, %d rejected, %d used%n",
                tickets, threads, outcome.succeeded(), outcome.failed(), usedTickets());

        assertThat(outcome.succeeded()).isEqualTo(tickets);
        assertThat(outcome.failed()).isEqualTo(threads - tickets);
        assertThat(usedTickets()).isEqualTo(tickets);
        assertThat(count("SELECT count(*) FROM public.gacha_pulls")).isEqualTo(tickets);
        assertThat(count("SELECT gacha_pull_count FROM public.child_profiles")).isEqualTo(tickets);
    }

    @Test
    @DisplayName("fragment totals stay consistent under concurrent pulls")
    void fragmentTotalsAreConsistent() throws InterruptedException {
        issueTickets(10);

        Outcome outcome = pullConcurrently(10);
        assertThat(outcome.succeeded()).isEqualTo(10);

        Long fragmentRows = count("SELECT count(*) FROM public.pet_fragments WHERE child_id = '" + childId + "'");
        Long duplicateGrants = count(
                "SELECT count(*) FROM public.gacha_pulls WHERE fragments_got > 0");
        Long fragmentTotal = jdbc.queryForObject(
                "SELECT COALESCE(sum(fragments_got), 0) FROM public.gacha_pulls", Long.class);
        Long storedFragments = jdbc.queryForObject(
                "SELECT COALESCE(count, 0) FROM public.pet_fragments WHERE child_id = ?", Long.class, childId);

        System.out.printf("[concurrency] 10 pulls -> %d fragment rows, %d duplicate grants, granted %d, stored %d%n",
                fragmentRows, duplicateGrants, fragmentTotal, storedFragments == null ? 0 : storedFragments);

        assertThat(fragmentRows).as("a child must never end up with two fragment rows").isLessThanOrEqualTo(1);
        assertThat(storedFragments == null ? 0L : storedFragments)
                .as("stored fragments must equal the sum of what was granted")
                .isEqualTo(fragmentTotal);
    }

    @Test
    @DisplayName("a pet is never granted twice for the same pet type")
    void petsAreNotDuplicated() throws InterruptedException {
        issueTickets(10);

        pullConcurrently(10);

        Long duplicatePetTypes = count("""
                SELECT count(*) FROM (
                    SELECT pet_type FROM public.pets GROUP BY child_id, pet_type HAVING count(*) > 1
                ) t
                """);
        System.out.printf("[concurrency] duplicate pet types after 10 pulls: %d%n", duplicatePetTypes);
        assertThat(duplicatePetTypes).isZero();
    }
}
