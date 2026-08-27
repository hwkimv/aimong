package com.aimong.backend.domain.mission.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.aimong.backend.domain.mission.repository.MissionSetRepository;
import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.FirebaseAuth;
import jakarta.persistence.EntityManagerFactory;
import java.lang.reflect.Field;
import java.util.UUID;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * Counts the SQL statements behind the home screen's recommended-mission lookup.
 *
 * <p>The concern is a per-mission or per-set query hidden inside a stream. The
 * only way to settle that is to count statements against a real database with a
 * realistic number of sets, and then change the number of sets and see whether
 * the count moves.
 *
 * <p>Requires {@code TEST_DB_URL}; see {@code BackendApplicationTests}.
 */
@SpringBootTest(properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.properties.hibernate.generate_statistics=true"
})
@EnabledIfEnvironmentVariable(
        named = "TEST_DB_URL",
        matches = "jdbc:.+",
        disabledReason = "TEST_DB_URL is not set"
)
class MissionSetAvailabilityQueryCountTest {

    private static final int MISSIONS = 16;
    private static final int SETS_PER_MISSION = 6;

    @MockitoBean
    FirebaseApp firebaseApp;

    @MockitoBean
    FirebaseAuth firebaseAuth;

    @Autowired
    MissionService missionService;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    MissionSetRepository missionSetRepository;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    private UUID childId;

    @BeforeEach
    void seed() {
        jdbc.execute("DELETE FROM public.mission_set_progress");
        jdbc.execute("DELETE FROM public.question_bank");
        jdbc.execute("DELETE FROM public.mission_sets");
        jdbc.execute("DELETE FROM public.child_profiles");
        jdbc.execute("DELETE FROM public.missions");
        jdbc.execute("DELETE FROM public.parent_accounts");

        jdbc.update("INSERT INTO public.parent_accounts (parent_id, email) VALUES (?, ?)",
                "query-count-parent", "parent@example.test");
        childId = UUID.randomUUID();
        jdbc.update("INSERT INTO public.child_profiles (child_id, parent_id, nickname) VALUES (?, ?, ?)",
                childId, "query-count-parent", "쿼리수측정");

        seedMissionSets(MISSIONS);
    }

    /** Creates {@code missions} missions with six sets each, mirroring the real bank. */
    private void seedMissionSets(int missions) {
        for (int missionNo = 1; missionNo <= missions; missionNo++) {
            UUID missionId = UUID.randomUUID();
            short stage = (short) ((missionNo - 1) % 3 + 1);
            String code = String.format("S%02d%02d", stage, missionNo);
            jdbc.update(
                    "INSERT INTO public.missions (id, stage, title, mission_code, description) VALUES (?, ?, ?, ?, ?)",
                    missionId, stage, "mission " + code, code, "seeded for query counting"
            );
            for (int packNo = 1; packNo <= SETS_PER_MISSION; packNo++) {
                jdbc.update("""
                        INSERT INTO public.mission_sets
                            (set_id, mission_id, mission_code, star_level, variant_no, stage,
                             title, description, question_count, display_order, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 10, ?, TRUE)
                        """,
                        code + "-L" + packNo, missionId, code,
                        (packNo - 1) / 2 + 1, packNo % 2 == 1 ? 1 : 2, stage,
                        "set " + code + "-L" + packNo, "",
                        stage * 1000 + missionNo * 10 + packNo
                );
            }
        }
    }

    /**
     * The service caches active mission sets for 30 seconds. Clearing it between
     * scenarios makes each measurement start from the same cold state instead of
     * silently reusing the previous scenario's set list.
     */
    private void clearMissionSetCache() throws Exception {
        Field cacheField = MissionService.class.getDeclaredField("activeMissionSetCache");
        cacheField.setAccessible(true);
        Class<?> cacheType = Class.forName(
                "com.aimong.backend.domain.mission.service.MissionService$ActiveMissionSetCache");
        var constructor = cacheType.getDeclaredConstructors()[0];
        constructor.setAccessible(true);
        cacheField.set(missionService, constructor.newInstance(java.util.List.of(), java.time.Instant.EPOCH));
    }

    private long countQueries(Runnable action) {
        Statistics statistics = entityManagerFactory.unwrap(SessionFactory.class).getStatistics();
        statistics.clear();
        action.run();
        return statistics.getPrepareStatementCount();
    }

    @Test
    @DisplayName("the recommended-mission lookup does not issue a query per set")
    void lookupIsNotPerSet() throws Exception {
        clearMissionSetCache();
        long cold = countQueries(() -> missionService.missionSetAvailability(childId));

        assertThat(jdbc.queryForObject("SELECT count(*) FROM public.mission_sets", Long.class))
                .isEqualTo((long) MISSIONS * SETS_PER_MISSION);

        // One query for the active sets, one for this child's progress.
        System.out.printf("[query-count] %d sets, cold lookup: %d statements%n",
                MISSIONS * SETS_PER_MISSION, cold);
        assertThat(cold)
                .as("96 sets must not produce a query per set")
                .isLessThanOrEqualTo(4);
    }

    @Test
    @DisplayName("the query count does not grow with the number of sets")
    void queryCountIsIndependentOfSetCount() throws Exception {
        clearMissionSetCache();
        long with96Sets = countQueries(() -> missionService.missionSetAvailability(childId));

        jdbc.execute("DELETE FROM public.mission_set_progress");
        jdbc.execute("DELETE FROM public.mission_sets");
        jdbc.execute("DELETE FROM public.missions");
        seedMissionSets(2);

        clearMissionSetCache();
        long with12Sets = countQueries(() -> missionService.missionSetAvailability(childId));

        System.out.printf("[query-count] 96 sets: %d statements, 12 sets: %d statements%n",
                with96Sets, with12Sets);
        assertThat(with96Sets)
                .as("query count must be the same for 96 sets and for 12")
                .isEqualTo(with12Sets);
    }

    @Test
    @DisplayName("progress rows do not add a query each")
    void progressRowsDoNotAddQueries() throws Exception {
        clearMissionSetCache();
        long withoutProgress = countQueries(() -> missionService.missionSetAvailability(childId));

        jdbc.query("SELECT set_id, mission_id, stage FROM public.mission_sets", rs -> {
            jdbc.update("""
                    INSERT INTO public.mission_set_progress
                        (child_id, set_id, mission_id, stage, total, star_level, variant_no, completed, completed_at)
                    VALUES (?, ?, ?, ?, 10, 1, 1, TRUE, NOW())
                    """,
                    childId, rs.getString("set_id"), UUID.fromString(rs.getString("mission_id")), rs.getShort("stage"));
        });

        clearMissionSetCache();
        long withProgress = countQueries(() -> missionService.missionSetAvailability(childId));

        System.out.printf("[query-count] 0 progress rows: %d statements, 96 progress rows: %d statements%n",
                withoutProgress, withProgress);
        assertThat(withProgress)
                .as("96 progress rows must not add 96 queries")
                .isEqualTo(withoutProgress);
    }

    /**
     * Control for the measurement itself.
     *
     * <p>A statement counter that cannot see an N+1 would make every other
     * assertion here meaningless. This deliberately issues one query per set and
     * asserts the counter rises accordingly, so a low count elsewhere is
     * evidence rather than an artefact of statement caching.
     */
    @Test
    @DisplayName("the statement counter detects a deliberate query-per-set loop")
    void counterDetectsPerSetQueries() {
        java.util.List<String> setIds = jdbc.queryForList(
                "SELECT set_id FROM public.mission_sets ORDER BY set_id", String.class);
        assertThat(setIds).hasSize(MISSIONS * SETS_PER_MISSION);

        long perSet = countQueries(() -> setIds.forEach(missionSetRepository::findBySetIdAndActiveTrue));

        System.out.printf("[query-count] control, one query per set over %d sets: %d statements%n",
                setIds.size(), perSet);
        assertThat(perSet)
                .as("the counter must scale with a real per-set loop")
                .isGreaterThanOrEqualTo(setIds.size());
    }
}
