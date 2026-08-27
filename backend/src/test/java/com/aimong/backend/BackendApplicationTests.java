package com.aimong.backend;

import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.FirebaseAuth;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * Boots the full application context.
 *
 * <p>This is the only test that needs a database. The schema uses PostgreSQL
 * enum types, JSONB columns and native queries that cast to those enums, so an
 * embedded H2 would not exercise the same behaviour and would report a pass the
 * real database would not give.
 *
 * <p>It runs whenever {@code TEST_DB_URL} points at a throwaway PostgreSQL, and
 * is skipped otherwise so that a fresh clone with no database still runs the
 * rest of the suite green. CI always supplies the variable, so this is never
 * silently skipped there.
 *
 * <pre>
 * TEST_DB_URL=jdbc:postgresql://localhost:5432/aimong_test \
 * TEST_DB_USERNAME=postgres TEST_DB_PASSWORD=postgres \
 * JWT_SECRET=local-test-secret ./gradlew test
 * </pre>
 */
@SpringBootTest(properties = "spring.flyway.enabled=false")
@EnabledIfEnvironmentVariable(
        named = "TEST_DB_URL",
        matches = "jdbc:.+",
        disabledReason = "TEST_DB_URL is not set; see the class javadoc for how to run this test"
)
class BackendApplicationTests {

	@MockitoBean
	FirebaseApp firebaseApp;

	@MockitoBean
	FirebaseAuth firebaseAuth;

	@Test
	void contextLoads() {
	}

}
