package com.aimong.backend.domain.chat.service;

import com.aimong.backend.domain.auth.entity.ChildProfile;
import com.aimong.backend.domain.auth.repository.ChildProfileRepository;
import com.aimong.backend.domain.auth.service.ChildActivityService;
import com.aimong.backend.domain.chat.dto.ChatResponse;
import com.aimong.backend.domain.chat.entity.ChatMessage;
import com.aimong.backend.domain.chat.entity.ChatSession;
import com.aimong.backend.domain.chat.entity.ChatUsage;
import com.aimong.backend.domain.chat.repository.ChatMessageRepository;
import com.aimong.backend.domain.chat.repository.ChatSessionRepository;
import com.aimong.backend.domain.chat.repository.ChatUsageRepository;
import com.aimong.backend.domain.pet.service.PetGrowthService;
import com.aimong.backend.domain.privacy.entity.PrivacyEvent;
import com.aimong.backend.domain.privacy.repository.PrivacyEventRepository;
import com.aimong.backend.domain.quest.service.AchievementService;
import com.aimong.backend.domain.quest.service.DailyQuestService;
import com.aimong.backend.domain.quest.service.WeeklyQuestService;
import com.aimong.backend.global.config.OpenAiProperties;
import com.aimong.backend.global.exception.AimongException;
import com.aimong.backend.global.exception.ErrorCode;
import com.aimong.backend.global.util.KstDateUtils;
import com.aimong.backend.infra.openai.OpenAiClient;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@RequiredArgsConstructor
public class ChatService {

    private static final int DAILY_LIMIT = 20;
    private static final int DAILY_IMAGE_LIMIT = 5;
    private static final int FIRST_CHAT_XP = 5;
    private static final int GPT_TIMEOUT_SECONDS = 15;
    private static final int IMAGE_TIMEOUT_SECONDS = 60;
    private static final Duration SESSION_TTL = Duration.ofHours(1);
    private static final String CHAT_MODEL = "gpt-5-mini";
    private static final String IMAGE_MODEL = "gpt-image-1-mini";
    private static final String IMAGE_SIZE = "1024x1024";
    private static final String IMAGE_QUALITY = "low";
    private static final String HINT_SUGGESTION = "스스로 생각해보는 건 어때요? 힌트만 받아보세요!";
    private static final List<String> HINT_TRIGGER_WORDS = List.of(
            "숙제", "해줘", "대신", "써줘",
            "homework", "help", "answer", "solve"
    );
    private static final String DEVELOPER_PROMPT = """
            너는 초등학생 전용 AI 학습 도우미야.
            욕설, 폭력, 성인 내용은 절대 포함하지 않는다.
            모든 답변은 초등학교 5학년 수준으로 쉽게 설명한다.
            숙제나 글쓰기를 대신 완성해 달라는 요청에는 정답 전체를 대신 작성하지 말고 방법과 힌트를 알려준다.
            답변은 3~5문장 이내로 한다.
            """;

    private final ChatUsageRepository chatUsageRepository;
    private final ChatSessionRepository chatSessionRepository;
    private final ChatMessageRepository chatMessageRepository;
    private final ChildProfileRepository childProfileRepository;
    private final ChildActivityService childActivityService;
    private final PrivacyMaskingService privacyMaskingService;
    private final ChatSafetyFilterService chatSafetyFilterService;
    private final PrivacyEventRepository privacyEventRepository;
    private final OpenAiClient openAiClient;
    private final OpenAiProperties openAiProperties;
    private final PetGrowthService petGrowthService;
    private final DailyQuestService dailyQuestService;
    private final WeeklyQuestService weeklyQuestService;
    private final AchievementService achievementService;
    private final TransactionTemplate transactionTemplate;
    @org.springframework.beans.factory.annotation.Qualifier(
            com.aimong.backend.global.config.OpenAiExecutorConfig.OPENAI_EXECUTOR)
    private final Executor openAiExecutor;

    public ChatResponse send(UUID childId, String message, boolean masked) {
        return send(childId, message, masked, null);
    }

    public ChatResponse send(UUID childId, String message, boolean masked, UUID sessionId) {
        return send(childId, message, masked, sessionId, false);
    }

    public ChatResponse send(UUID childId, String message, boolean masked, UUID sessionId, boolean imageRequested) {
        childActivityService.touchLastActiveAt(childId);
        PrivacyMaskingService.MaskingResult maskingResult = privacyMaskingService.mask(message);
        ChatPreflight preflight = transactionTemplate.execute(status ->
                prepareChat(childId, sessionId, imageRequested));
        boolean hintTriggered = isHintTriggered(maskingResult.sanitizedMessage());
        ChatSafetyFilterService.FilterDecision safetyDecision = chatSafetyFilterService.evaluate(
                maskingResult.sanitizedMessage(),
                imageRequested
        );

        if (!safetyDecision.allowed()) {
            ChatCommit commit = transactionTemplate.execute(status -> commitChat(
                    childId,
                    maskingResult,
                    masked,
                    preflight.sessionId(),
                    safetyDecision.safeReply(),
                    false,
                    false
            ));
            return new ChatResponse(
                    safetyDecision.safeReply(),
                    commit.remainingCalls(),
                    null,
                    commit.sessionId(),
                    commit.sessionExpiresAt(),
                    null,
                    imageRequested ? commit.remainingImageCalls() : null
            );
        }

        ChatResponse.GeneratedImageResponse generatedImage = null;
        String safeReply;
        if (imageRequested) {
            generatedImage = requestGeneratedImage(maskingResult.sanitizedMessage());
            safeReply = "Image generated.";
        } else {
            String reply = requestGptReply(
                    maskingResult.sanitizedMessage(),
                    contextualPrompt(preflight.previousMessages(), maskingResult.sanitizedMessage())
            );
            safeReply = privacyMaskingService.mask(reply).sanitizedMessage();
        }

        ChatCommit commit = transactionTemplate.execute(status -> commitChat(
                childId,
                maskingResult,
                masked,
                preflight.sessionId(),
                safeReply,
                imageRequested,
                true
        ));

        return new ChatResponse(
                safeReply,
                commit.remainingCalls(),
                hintTriggered ? HINT_SUGGESTION : null,
                commit.sessionId(),
                commit.sessionExpiresAt(),
                generatedImage,
                imageRequested ? commit.remainingImageCalls() : null
        );
    }

    private ChatPreflight prepareChat(UUID childId, UUID sessionId, boolean imageRequested) {
        childProfileRepository.findByIdAndDeletedAtIsNull(childId)
                .orElseThrow(() -> new AimongException(ErrorCode.CHILD_NOT_FOUND));
        ChatUsage usage = chatUsageRepository.findByChildIdAndUsageDate(childId, KstDateUtils.today())
                .orElse(null);
        validateUsageLimit(usage, imageRequested);

        Instant now = Instant.now();
        UUID resolvedSessionId = resolveExistingSessionId(childId, sessionId, now);
        List<ConversationMessage> previousMessages = resolvedSessionId == null
                ? List.of()
                : recentMessages(resolvedSessionId);
        return new ChatPreflight(resolvedSessionId, previousMessages);
    }

    private ChatCommit commitChat(
            UUID childId,
            PrivacyMaskingService.MaskingResult maskingResult,
            boolean masked,
            UUID requestedSessionId,
            String safeReply,
            boolean imageRequested,
            boolean rewardEligible
    ) {
        ChildProfile childProfile = childProfileRepository.findWithLockById(childId)
                .filter(profile -> profile.getDeletedAt() == null)
                .orElseThrow(() -> new AimongException(ErrorCode.CHILD_NOT_FOUND));
        ChatUsage usage = chatUsageRepository.findWithLockByChildIdAndUsageDate(childId, KstDateUtils.today())
                .orElseGet(() -> chatUsageRepository.save(ChatUsage.create(childId, KstDateUtils.today())));
        validateUsageLimit(usage, imageRequested);
        savePrivacyEvents(childId, maskingResult, masked);

        Instant now = Instant.now();
        ChatSession chatSession = resolveWritableSession(childId, requestedSessionId, now);
        chatSession.refresh(now, SESSION_TTL);
        chatSessionRepository.save(chatSession);
        chatMessageRepository.save(ChatMessage.user(chatSession, maskingResult.sanitizedMessage(), now));
        chatMessageRepository.save(ChatMessage.assistant(chatSession, safeReply, Instant.now()));

        boolean firstSuccessToday = rewardEligible && usage.getCount() == 0;
        if (rewardEligible) {
            usage.increment();
            if (imageRequested) {
                usage.incrementImage();
            }
        }

        if (rewardEligible && firstSuccessToday) {
            childProfile.applyMissionXp(FIRST_CHAT_XP, KstDateUtils.today(), KstDateUtils.currentWeekStart());
            childProfile.refreshProfileImageType();
            petGrowthService.applyMissionReward(childId, FIRST_CHAT_XP);
        }

        if (rewardEligible) {
            dailyQuestService.updateForChatSuccess(childId);
            weeklyQuestService.updateForChatSuccess(childId);
            achievementService.unlockByTotalXp(childId, childProfile);
        }

        return new ChatCommit(
                chatSession.getId(),
                chatSession.getExpiresAt(),
                DAILY_LIMIT - usage.getCount(),
                DAILY_IMAGE_LIMIT - usage.getImageCount()
        );
    }

    private void validateUsageLimit(ChatUsage usage, boolean imageRequested) {
        if (usage == null) {
            return;
        }
        if (usage.getCount() >= DAILY_LIMIT) {
            throw new AimongException(ErrorCode.TOO_MANY_REQUESTS, "오늘은 충분히 이야기했어요! 내일 또 만나요");
        }
        if (imageRequested && usage.getImageCount() >= DAILY_IMAGE_LIMIT) {
            throw new AimongException(ErrorCode.TOO_MANY_REQUESTS, "Today's image generation limit has been reached.");
        }
    }

    private UUID resolveExistingSessionId(UUID childId, UUID sessionId, Instant now) {
        if (sessionId != null) {
            return chatSessionRepository.findByIdAndChildIdAndExpiresAtAfter(sessionId, childId, now)
                    .map(ChatSession::getId)
                    .orElse(null);
        }
        return chatSessionRepository.findFirstByChildIdAndExpiresAtAfterOrderByUpdatedAtDesc(childId, now)
                .map(ChatSession::getId)
                .orElse(null);
    }

    private ChatSession resolveWritableSession(UUID childId, UUID sessionId, Instant now) {
        if (sessionId != null) {
            return chatSessionRepository.findByIdAndChildIdAndExpiresAtAfter(sessionId, childId, now)
                    .orElseGet(() -> chatSessionRepository.save(ChatSession.create(childId, now, SESSION_TTL)));
        }
        return chatSessionRepository.findFirstByChildIdAndExpiresAtAfterOrderByUpdatedAtDesc(childId, now)
                .orElseGet(() -> chatSessionRepository.save(ChatSession.create(childId, now, SESSION_TTL)));
    }

    private List<ConversationMessage> recentMessages(UUID sessionId) {
        List<ChatMessage> messages = new ArrayList<>(
                chatMessageRepository.findTop10BySession_IdOrderByCreatedAtDesc(sessionId)
        );
        messages.sort(Comparator.comparing(ChatMessage::getCreatedAt));
        return messages.stream()
                .map(message -> new ConversationMessage(message.getRole(), message.getContentMasked()))
                .toList();
    }

    private String contextualPrompt(List<ConversationMessage> previousMessages, String currentMessage) {
        if (previousMessages.isEmpty()) {
            return currentMessage;
        }

        StringBuilder prompt = new StringBuilder();
        prompt.append("[같은 채팅 세션의 최근 대화입니다. 개인정보는 마스킹된 내용만 포함합니다.]\n");
        for (ConversationMessage message : previousMessages) {
            prompt.append(message.role()).append(": ").append(message.contentMasked()).append('\n');
        }
        prompt.append("\n[현재 사용자 메시지]\n");
        prompt.append(currentMessage);
        return prompt.toString();
    }

    private String requestGptReply(String sanitizedMessage, String contextualPrompt) {
        if (openAiProperties.mockEnabled()) {
            return createMockReply(sanitizedMessage);
        }

        try {
            return CompletableFuture
                    .supplyAsync(() -> openAiClient.createChatReply(CHAT_MODEL, DEVELOPER_PROMPT, contextualPrompt), openAiExecutor)
                    .get(GPT_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (RejectedExecutionException exception) {
            throw new AimongException(ErrorCode.GATEWAY_TIMEOUT, "AI 친구가 지금 바빠요. 잠시 후 다시 시도해주세요");
        } catch (TimeoutException exception) {
            throw new AimongException(ErrorCode.GATEWAY_TIMEOUT, "AI 친구가 생각 중이에요. 다시 시도해볼까요?");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AimongException(ErrorCode.GATEWAY_TIMEOUT, "AI 친구가 생각 중이에요. 다시 시도해볼까요?");
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof AimongException aimongException) {
                throw aimongException;
            }
            throw new AimongException(ErrorCode.INTERNAL_SERVER_ERROR, "AI 친구가 지금 쉬고 있어요. 잠시 후 다시 시도해주세요");
        }
    }

    private String createMockReply(String sanitizedMessage) {
        if (isHintTriggered(sanitizedMessage)) {
            return "테스트 응답이에요. 대신 완성해주기보다는 먼저 네 생각을 한 문장으로 적고, 그다음 필요한 힌트를 물어보면 좋아요.";
        }
        return "테스트 응답이에요. 실제 OpenAI 호출 없이 챗봇 흐름, 사용량, 퀘스트 진행도만 확인하고 있어요.";
    }

    private ChatResponse.GeneratedImageResponse requestGeneratedImage(String sanitizedPrompt) {
        if (openAiProperties.mockEnabled()) {
            return new ChatResponse.GeneratedImageResponse(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
                    "image/png",
                    "png",
                    IMAGE_SIZE,
                    IMAGE_QUALITY
            );
        }

        try {
            OpenAiClient.GeneratedImage image = CompletableFuture
                    .supplyAsync(() -> openAiClient.createImage(IMAGE_MODEL, sanitizedPrompt, IMAGE_SIZE, IMAGE_QUALITY), openAiExecutor)
                    .get(IMAGE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            return new ChatResponse.GeneratedImageResponse(
                    image.b64Json(),
                    mimeType(image.outputFormat()),
                    image.outputFormat(),
                    image.size(),
                    image.quality()
            );
        } catch (TimeoutException exception) {
            throw new AimongException(ErrorCode.GATEWAY_TIMEOUT, "Image generation timed out. Please try again.");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AimongException(ErrorCode.GATEWAY_TIMEOUT, "Image generation timed out. Please try again.");
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof AimongException aimongException) {
                throw aimongException;
            }
            throw new AimongException(ErrorCode.INTERNAL_SERVER_ERROR, "Image generation failed. Please try again.");
        }
    }

    private String mimeType(String outputFormat) {
        return switch (outputFormat) {
            case "jpeg", "jpg" -> "image/jpeg";
            case "webp" -> "image/webp";
            default -> "image/png";
        };
    }

    private void savePrivacyEvents(UUID childId, PrivacyMaskingService.MaskingResult maskingResult, boolean requestMasked) {
        if (maskingResult.detectedTypes().isEmpty()) {
            return;
        }

        boolean masked = requestMasked || !maskingResult.sanitizedMessage().isBlank();
        privacyEventRepository.saveAll(maskingResult.detectedTypes().stream()
                .map(type -> PrivacyEvent.create(childId, type, masked))
                .toList());
    }

    private boolean isHintTriggered(String sanitizedMessage) {
        String lowerCaseMessage = sanitizedMessage.toLowerCase(Locale.ROOT);
        return HINT_TRIGGER_WORDS.stream().anyMatch(lowerCaseMessage::contains);
    }

    private record ChatPreflight(UUID sessionId, List<ConversationMessage> previousMessages) {
    }

    private record ChatCommit(UUID sessionId, Instant sessionExpiresAt, int remainingCalls, int remainingImageCalls) {
    }

    private record ConversationMessage(String role, String contentMasked) {
    }
}
