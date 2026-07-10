# 0001 — 런타임 트레이스 오버레이

- **상태**: 🚧 진행 — Phase 1 ✅ (Spring), Phase 2 @Async 스티칭 ✅ / tx 타임라인 ⏸(jch 사인오프 대기), Phase 3 대기
- **로드맵**: v0.3 (기획안 §14 — "런타임 오버레이")
- **백로그**: ideas.md ⏱ 등급(런타임) 항목 전반의 기반. 트레이스 뷰는 §10에 UI 방향 확정됨.
- **브랜치**: `feat/runtime-trace-overlay`
- **담당**: kys(Spring) 선행 → 패리티 이슈 → jch(FastAPI) 미러

## 무엇 / 왜

실행 중인 앱에서 **실제 호출 트레이스를 수집해, 정적 그래프 위에 "실제로 탄 경로"를 덧칠한다.**
정적 스캐너가 그린 구조 그래프는 그대로 두고, 같은 `nodeId`를 참조하는 트레이스를 얹는다.

- **차별점**: Swagger(외부 계약)도 아니고 분산 트레이싱(운영 관측, 무거움)도 아닌, **"개발자가 코드 읽는 단계에서 보는 문서"에 실제 실행을 덧칠**한 것. 정적이 추정만 하던 걸(트랜잭션 propagation, 어느 분기를 타는지) 런타임이 **사후 검증**한다.
- **핵심 통찰**: 정적 그래프와 런타임 트레이스의 **괴리 자체가 정보다** (선언한 의도 ↔ 실제 실행).

## 스펙 영향

`Trace`/`Span` 레코드는 **이미 존재**한다 (`flowdoc-core`, schema `$defs/trace`). Phase 1은 스키마 무변경.

```
trace  = { traceId, sequenceTag, spans[] }
span   = { id, nodeId, parent, tEnter, tExit, thread }
```

Phase 2/3에서 아래가 필요해지면 **스키마 확장 = 공유 계약** → collaboration.md 따라 양측 합의 후 양쪽 동시 반영:
- 트랜잭션 생명주기: span에 `tx: { event: begin|commit|rollback, propagation }` 또는 별도 `txEvents[]`
- 가드 점유 구간: span에 `acquiredAt`/`releasedAt`
- 괴리 표시: 트레이스 소비 시 UI가 계산(스펙 무변경) 가능 — 우선 UI 계산으로.

## 아키텍처 + 기술 난제

신규 모듈 `flowdoc-runtime` (`flowdoc-scanner`와 형제, `flowdoc-core` 의존). starter가 트레이스를 서빙.

```
@Around AOP advice ─→ ThreadLocal span 스택 ─→ Trace 버퍼 ─→ /flowdoc/traces.json
TransactionSynchronization ─→ tx begin/commit/rollback 타임라인 (Phase 2)
```

**진짜 난제 (= 기술 깊이가 사는 곳):**

1. **nodeId 정합성 (핵심).** 정적 스캐너는 `FQN#method(SimpleType1,...)` 포맷 — `flowdoc-scanner`의 `Ids.of()`가 JavaParser 기준으로 제네릭/배열을 단순화해서 만든다(`List<Foo>[]` → `List[]`). 런타임은 **리플렉션으로 바이트 단위 동일 포맷을 재현**해야 트레이스가 트리에 붙는다. 이게 안 맞으면 오버레이 전체가 무용지물.
   - 엣지케이스: 제네릭 소거, varargs, synthetic bridge 메서드, 중첩/익명 클래스 이름.
   - 대응: `Ids.of()` 포맷 규칙을 런타임/정적이 공유할 수 있게 `flowdoc-core`로 끌어올리는 것도 검토(정적은 JavaParser 타입, 런타임은 reflection 타입 → 동일 정규화 함수에 통과).

2. **CGLIB 프록시 언래핑.** AOP join point의 클래스는 `OrderService$$EnhancerBySpringCGLIB$$...` 프록시다. `ClassUtils.getUserClass()` / `AopUtils.getTargetClass()`로 **유저 클래스를 복원**해야 정적 nodeId와 맞는다.

3. **자기호출(self-invocation) 비가시성.** Spring AOP는 프록시 경유 호출만 가로채므로 `this.foo()` 내부 호출은 트레이스에 안 잡힌다. 정적 그래프엔 있는데 런타임엔 없음 → **"정적엔 있으나 안 탐"으로 정직하게 표시**(숨기지 않음). 이게 위의 "괴리 = 정보".

4. **@Async 스레드 홉.** `traceId` + 부모 span을 executor 스레드 경계 너머로 전파해야 async 자식이 같은 트레이스에 붙는다. `TaskDecorator`로 ThreadLocal 컨텍스트를 복사.

5. **트랜잭션 생명주기 (Phase 2).** `TransactionSynchronizationManager.registerSynchronization`으로 begin/commit/rollback + **실제 propagation**을 포착 → 정적이 추정만 하던 걸 확정.

6. **오버헤드.** advice 경량화 + 바운드 링버퍼(최근 N개 트레이스만) + 샘플링 옵션. 런타임 부하가 운영에 새지 않게.

## 단계 분할

- **Phase 1 (MVP, 시연 가능) ✅ — Spring:**
  1. ✅ `flowdoc-runtime` 모듈 추가 (core + spring-aop + aspectjweaver). aspectjweaver를 `api`로 둬서 앱 클래스패스에 올라가면 Boot AOP가 켜짐.
  2. ✅ `RuntimeIds` — `Ids.of()`와 동일 포맷을 리플렉션으로 재현. 프록시 언래핑(`ClassUtils.getUserClass`), bridge/most-specific 해석, varargs(요소타입), 중첩클래스(`$`→`.`) 처리. `RuntimeIdsTest`로 포맷 고정.
  3. ✅ `FlowDocTraceAspect`(`@Around`, HIGHEST_PRECEDENCE) + `TraceRecorder`(ThreadLocal span 스택 + 바운드 링버퍼). 스테레오타입 빈만, 프레임워크/flowdoc 패키지는 제외.
  4. ✅ starter `FlowDocRuntimeAutoConfiguration` — 빈 등록 + `GET /flowdoc/traces.json` / `DELETE /flowdoc/traces`. 프로퍼티 `flowdoc.tracing`, `flowdoc.max-traces`.
  5. ✅ UI `index.html` 트레이스 뷰 — 사이드바 트레이스 목록, 선택 시 탄 노드 강조 + observed ms 배지, 안 탄 노드 흐리게, "구조만 보기"/"새로고침".
  6. ✅ coupon-rush E2E — GET `/remaining`·POST `/coupons` 요청이 정적 그래프와 **바이트 일치**하는 nodeId로 트레이스됨. self-invocation(`reserveStock`)은 의도대로 누락 = 괴리 가시화.

  > **검증된 한계(설계대로):** Spring AOP라 `this.foo()` self-invocation·Spring Data repository 프록시(인터페이스)는 트레이스에 안 잡힘.

- **Phase 1.5 (신뢰도) ✅ — UI:** 협업자 리뷰 피드백 반영.
  - **노드 3상태**: `관측됨`(진하게+ms) / `관측 밖`(repository·external·self-invocation → 점선+배지, 흐리지 않음) / `안 탐`(계측 가능하나 미실행만 흐리게). 기존엔 "안 탐"과 "관측 불가"를 같은 흐림으로 뭉개 신뢰가 깨졌음.
  - **트레이스 목록**: 트리거(`GET/POST 경로`) + 결과(OK / ⚠ 에러, 호버 시 예외 타입·메시지). 500과 200을 구분.
  - **오버레이 범례** 추가.
  - **스펙 변경**: `Trace.error`(optional) + 스키마 `trace.error` 추가 → **공유 계약** (collaboration.md). 런타임 전용·additive지만 jch 사인오프 필요(Python 런타임 생기면 동일 필드).
- **Phase 2:** ([이슈 #9](https://github.com/yeseul-kim01/flowdoc/issues/9))
  - **@Async 스레드홉 전파 ✅ — Spring (스키마 무변경):** async 자식 span을 **호출자 트레이스에 스티칭**. 핵심 발견 — Spring `@Async` advice가 우리 aspect보다 **바깥(outer)**이라 aspect는 async 메서드를 **워커 스레드에서** 가로챈다. 그래서:
    1. `TraceRecorder`를 **Accumulator(트레이스 공유)** + **ThreadState(스레드별 스택)**로 재설계. Accumulator 단위로 락 → 호출자·워커 동시 접근 안전.
    2. `FlowDocTraceTaskDecorator`(`TaskDecorator`)가 제출 스레드에서 호출자 프레임을 스냅샷(`captureAsyncParent`) + 플러시 보류(`armAsync`), 워커에서 링크 설치(`beginAsyncScope`) → 워커의 첫 `enter`가 새 트레이스 대신 **호출자 트레이스를 이어감**.
    3. **참조카운트 deferred-flush**: 루트가 풀려도 미완 async가 있으면 플러시 보류, 마지막 async 종료 시 플러시(양 순서 안전). 계측 안 된 async는 `cancelAsync`로 arm 해제 → 트레이스 방치 방지.
    4. **배선 한 줄**: Spring Boot `TaskExecutionAutoConfiguration`이 단일 `TaskDecorator` 빈을 `applicationTaskExecutor`에 자동 적용 → 데코레이터 빈만 등록. (커스텀 executor 앱은 직접 세팅 — 정직한 한계로 문서화.)
    5. **스키마 무변경**: span의 기존 `parent`+`thread`만 씀 → `ui/` 무변경(공유 계약 안 건드림). coupon-rush E2E: POST 발급 성공 → `NotificationService#notifyIssued`가 **`task-1` 스레드로 같은 트레이스에 붙음**, 에러 경로/동시요청 회귀 없음, `$defs/trace` 통과.
  - **tx 타임라인 ⏸ — jch 사인오프 대기 (공유 계약):** `TransactionSynchronization` begin/commit/rollback + 실제 propagation. `span.tx[]`(또는 `trace.txEvents[]`) **스키마 확장 = 공유 계약** → 이슈 #9에 초안 올림, jch 합의 후 spec·ui 동시 반영.
- **Phase 3:** 가드 acquire/release 타이밍, 샘플링/버퍼 설정, **정적↔런타임 괴리 감지**(안 탄 분기 / 정적에 없는 호출).

## 패리티 (Spring ↔ FastAPI)

같은 `traces[]` 스펙을 양쪽이 산출해야 한다. kys(Spring) 선행 → **패리티 이슈** → jch(FastAPI) 미러.

| 개념 | Spring (kys) | FastAPI (jch) |
|---|---|---|
| 진입/스팬 enter·exit | AOP `@Around` (빈 메서드) | ASGI 미들웨어 + 함수 래핑/`sys.setprofile` 또는 명시 계측 |
| 트레이스 컨텍스트 | `ThreadLocal` span 스택 | `contextvars.ContextVar` (async-safe) |
| async 전파 | `TaskDecorator` | contextvars는 `await` 경계서 자동 전파 (BackgroundTasks는 별도) |
| nodeId | `FQN#method(simpleTypes)` 리플렉션 재현 | `module.Class.func` 등 **Python 정적 스캐너의 id와 동일 포맷** 재현 |
| tx 생명주기 | `TransactionSynchronization` | SQLAlchemy `session` 이벤트(`after_begin`/`after_commit`/`after_rollback`) |
| 서빙 | starter `/flowdoc/traces.json` | FastAPI 라우터 mount `/flowdoc/traces.json` |

> 메타 원칙 동일: 런타임도 **nodeId 정합성이 생명**. 양쪽 다 자기 정적 스캐너의 id 포맷을 런타임에서 그대로 재현해야 같은 UI에 트레이스가 붙는다. Python은 동적이라 프록시 문제는 없지만 함수 식별(데코레이터로 감싼 원함수 추적)이 대신 까다롭다.

## 완료 기준

- Phase 1: coupon-rush에 요청 → `/flowdoc`에서 **그 요청이 탄 경로가 기존 트리 위에 강조**되어 보임. `traces[]`가 schema 통과.
- 패리티: FastAPI 동등 데모에서 같은 요청 → **같은 `ui/index.html`에서 동일한 트레이스 오버레이**로 보이면 달성.
- 회귀: 양쪽 예제의 `flowdoc.json`(traces 포함)을 `spec/flowdoc-0.1.schema.json`으로 검증.
